"""VES geometry, layered-earth forward modeling, and bounded 1D inversion.

The forward model uses the resistivity-transform recursion for horizontal layers
and evaluates the surface potential with a numerically integrated zero-order
Hankel transform. The homogeneous half-space contribution is integrated
analytically; only the exponentially decaying layered correction is integrated
numerically. This keeps the calculation finite and makes the half-space limit
an exact regression test.

The correction integral is evaluated with a deterministic composite 8-point
Gauss-Legendre rule on panels half an oscillation period wide, over the range
``[0, lambda_cut]`` where ``lambda_cut`` is determined from the numerically
detected exponential decay of ``T(lambda) - rho_1``. The node count is bounded by
``VES_QUADRATURE_NODE_BUDGET``; a model whose response cannot be certified inside
that budget raises :class:`VESNumericalError` instead of returning an unreliable
value. See :func:`certified_thickness_lower_bound` for the documented domain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import least_squares
from scipy.special import j0

from nix_ert.core.numerics import percent_rms


class VESError(ValueError):
    """Raised for invalid VES geometry, models, or measurements."""


class VESNumericalError(VESError):
    """Raised when a response cannot be certified at the documented accuracy.

    This is a *numerical* failure of the forward model (the quadrature budget is
    insufficient for the requested model/geometry), not invalid input. Callers
    must not reclassify it as ``INVALID_INPUT``.
    """


VES_QUADRATURE_NODE_BUDGET = 200_000
"""Maximum Gauss-Legendre nodes per correction integral evaluation.

The budget bounds the runtime of a single forward response and defines the
certified model domain: models whose transform decay needs more nodes are
rejected with :class:`VESNumericalError` rather than integrated unreliably.
"""

_VES_DECAY_RELATIVE_TOLERANCE = 1e-13
"""Relative tolerance used to locate the exponential decay of T(lambda)-rho_1."""

_VES_MIN_QUADRATURE_PANELS = 800
"""Minimum panels spanning the correction range, independent of the sampling.

Together with the half-period panel limit this fixes the certified accuracy of
:func:`layered_apparent_resistivity`. The M23 reference tests measure typical
relative errors of ``1e-13`` and a worst case of ``2.1e-10`` against independent
two-layer image solutions over a 525-case two-layer sweep of resistivity
contrasts (0.01x - 100x), layer thicknesses (0.5 - 500 m) and Schlumberger
geometries (AB/2 10 - 500 m); see ``docs/m23_forward_physics_correction.md``.
"""

_VES_DOMAIN_SAFETY_FACTOR = 4.0
"""Safety factor applied when converting the node budget into a domain bound."""

_GL_NODES, _GL_WEIGHTS = np.polynomial.legendre.leggauss(8)
"""Fixed 8-point Gauss-Legendre rule used on every quadrature panel."""


@dataclass(frozen=True)
class VESPoint:
    ab2: float
    mn2: float
    apparent_resistivity: float | None = None
    resistance: float | None = None
    excluded: bool = False


@dataclass(frozen=True)
class LayeredEarthModel:
    resistivities: tuple[float, ...]
    thicknesses: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.resistivities) == 0:
            raise VESError("model must contain at least one layer")
        if len(self.thicknesses) != len(self.resistivities) - 1:
            raise VESError("there must be one thickness between each pair of layers")
        if any(not math.isfinite(value) or value <= 0 for value in self.resistivities):
            raise VESError("layer resistivities must be finite and positive")
        if any(not math.isfinite(value) or value <= 0 for value in self.thicknesses):
            raise VESError("layer thicknesses must be finite and positive")


@dataclass(frozen=True)
class VESInversionResult:
    """Layered-earth inversion output for a bounded least-squares fit.

    Semantics that callers must not over-read:

    * ``iterations`` is the optimizer's **function-evaluation count**
      (``scipy.optimize.least_squares`` ``nfev``), not an iteration count. The
      field name is retained for persisted-version compatibility.
    * ``converged`` is true only when the optimizer reported that one of its
      configured termination criteria (``xtol``/``ftol``/``gtol`` = 1e-8) was
      satisfied. A run that stops at ``max_nfev`` is not convergence.
    * ``rms_log10`` and ``residuals_log10`` describe the returned model.
    * No per-evaluation objective history is exposed by the scipy optimizer, so
      none is fabricated here. Qualification layers must record
      ``HISTORY_UNAVAILABLE`` instead.
    """

    model: LayeredEarthModel
    predicted: tuple[float, ...]
    residuals_log10: tuple[float, ...]
    rms_log10: float
    rms_percent: float
    converged: bool
    iterations: int
    message: str


def _positive(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise VESError(f"{label} must be finite and positive")
    return value


def schlumberger_geometric_factor(ab2: float, mn2: float) -> float:
    """Return K for Schlumberger half-spacings AB/2 and MN/2."""
    current_half = _positive(ab2, "AB/2")
    potential_half = _positive(mn2, "MN/2")
    if current_half <= potential_half:
        raise VESError("Schlumberger AB/2 must be greater than MN/2")
    return math.pi * (current_half**2 - potential_half**2) / (2 * potential_half)


def ves_apparent_resistivity(point: VESPoint) -> float:
    """Calculate rho_a from a Schlumberger resistance, or validate existing rho_a."""
    factor = schlumberger_geometric_factor(point.ab2, point.mn2)
    if point.apparent_resistivity is not None:
        value = _positive(point.apparent_resistivity, "apparent resistivity")
        return value
    if point.resistance is None:
        raise VESError("VES point has neither apparent resistivity nor resistance")
    resistance = _positive(point.resistance, "resistance")
    return resistance * factor


def _transform_array(wavenumbers: np.ndarray, model: LayeredEarthModel) -> np.ndarray:
    """Vectorized resistivity transform T(lambda) used by the quadrature.

    Implements exactly the same recursion as :func:`resistivity_transform`.
    """
    values = np.asarray(wavenumbers, dtype=float)
    equivalent = np.full(values.shape, model.resistivities[-1], dtype=float)
    for index in range(len(model.resistivities) - 2, -1, -1):
        rho = model.resistivities[index]
        tanh_term = np.tanh(values * model.thicknesses[index])
        denominator = rho + equivalent * tanh_term
        if np.any(denominator == 0):
            raise VESError("layer transform became singular")
        equivalent = rho * (equivalent + rho * tanh_term) / denominator
    return equivalent


def resistivity_transform(wavenumber: float, model: LayeredEarthModel) -> float:
    """Return the surface resistivity transform T(lambda) for a layered model."""
    wavenumber = float(wavenumber)
    if not math.isfinite(wavenumber) or wavenumber < 0:
        raise VESError("wavenumber must be finite and non-negative")
    return float(_transform_array(np.asarray([wavenumber]), model)[0])


def _transform_decay_cutoff(model: LayeredEarthModel) -> float:
    """Return ``lambda_cut`` where ``T(lambda) - rho_1`` has effectively decayed.

    ``T(lambda) -> rho_1`` as ``lambda -> infinity`` with an exponential rate set
    by the shallowest interface depth, so the tail beyond the first ``lambda``
    where the transform deviation falls below
    ``_VES_DECAY_RELATIVE_TOLERANCE * max(resistivity)`` contributes far less
    than the requested correction tolerance. The cutoff is detected numerically
    from the actual transform rather than assumed from the layer structure.
    """
    rho_surface = model.resistivities[0]
    scale = max(*model.resistivities, rho_surface)
    threshold = _VES_DECAY_RELATIVE_TOLERANCE * scale
    # The decay length is at most comparable to the top layer thickness, so a
    # geometric scan from 1/lambda_scale finds the cutoff deterministically.
    wavenumber = 1.0 / max(model.thicknesses)
    while wavenumber < 1e9:
        if abs(float(_transform_array(np.asarray([wavenumber]), model)[0]) - rho_surface) <= threshold:
            return wavenumber
        wavenumber *= 1.05
    raise VESNumericalError("layered-earth transform did not reach its asymptotic value")


def _quadrature_panel_width(max_distance: float, cutoff: float) -> float:
    """Return the panel width used for the correction integral.

    Each panel must be narrower than half a Bessel oscillation period
    (``pi / max_distance``) and the whole range must be covered by at least
    :data:`_VES_MIN_QUADRATURE_PANELS` panels so that the transform's own
    variation is resolved as well.
    """
    return min(math.pi / max_distance, cutoff / _VES_MIN_QUADRATURE_PANELS)


def _quadrature_node_count(max_distance: float, cutoff: float) -> int:
    """Return the nodes needed for the correction integral at this geometry."""
    panels = max(1, int(math.ceil(cutoff / _quadrature_panel_width(max_distance, cutoff))))
    return panels * int(_GL_NODES.size)


def certified_thickness_lower_bound(max_distance: float) -> float:
    """Return the thinnest top layer this engine can certify for a geometry.

    The correction integral of a model whose shallowest interface is at depth
    ``h`` decays like ``exp(-2*h*lambda)``, so resolving it to the documented
    relative tolerance needs ``lambda_cut ~ ln(1/eps)/(2*h)`` and about
    ``2 * max_distance * lambda_cut / pi`` quadrature nodes. Inverting the
    :data:`VES_QUADRATURE_NODE_BUDGET` bound gives the shallowest interface depth
    whose response the engine certifies; the documented safety factor covers
    models whose decay is slower than the two-layer leading term. Thinner top
    layers are outside the documented domain: they are physically unresolvable
    at such spacings and their Hankel integrand cannot be integrated reliably, so
    the engine reports :class:`VESNumericalError` instead of an uncertified
    value.
    """
    distance = _positive(max_distance, "maximum electrode distance")
    nodes_per_unit_wavenumber = 2.0 * distance * _GL_NODES.size / math.pi
    allowed_cutoff = VES_QUADRATURE_NODE_BUDGET / nodes_per_unit_wavenumber
    bound = math.log(1.0 / _VES_DECAY_RELATIVE_TOLERANCE) / (2.0 * allowed_cutoff)
    return bound * _VES_DOMAIN_SAFETY_FACTOR


def _correction_integral(
    model: LayeredEarthModel, rho_surface: float, distances: Sequence[float],
) -> float:
    """Integrate ``(T(lambda) - rho_1) * kernel(lambda)`` on ``[0, lambda_cut]``.

    A single adaptive call over a wide, rapidly oscillating range is not
    certifiable: the classic symptom is a silently wrong result together with a
    scipy ``IntegrationWarning``. The range is therefore cut where the transform
    has decayed, covered by panels half an oscillation period wide, and each
    panel integrated with the fixed 8-point Gauss-Legendre rule. The node count
    is checked against :data:`VES_QUADRATURE_NODE_BUDGET` *before* integrating.
    """
    cutoff = _transform_decay_cutoff(model)
    max_distance = max(distances)
    nodes_needed = _quadrature_node_count(max_distance, cutoff)
    if nodes_needed > VES_QUADRATURE_NODE_BUDGET:
        raise VESNumericalError(
            "layered-earth forward response cannot be certified at the documented quadrature "
            f"budget: {nodes_needed} nodes required, {VES_QUADRATURE_NODE_BUDGET} available "
            f"(shallowest layer {min(model.thicknesses):g} m at a maximum electrode distance of "
            f"{max_distance:g} m)"
        )
    panel_width = _quadrature_panel_width(max_distance, cutoff)
    panels = max(1, int(math.ceil(cutoff / panel_width)))
    edges = np.linspace(0.0, cutoff, panels + 1)
    half = np.diff(edges) / 2.0
    nodes = (edges[:-1, None] + (np.asarray(_GL_NODES) + 1.0) * half[:, None]).reshape(-1)
    weights = (half[:, None] * np.asarray(_GL_WEIGHTS)).reshape(-1)
    transform_delta = _transform_array(nodes, model) - rho_surface
    kernel = sum(
        sign * j0(nodes * distance)
        for sign, distance in zip((1, -1, -1, 1), distances)
    )
    return float(np.dot(weights, transform_delta * kernel))


def _electrode_reciprocal_sum(ab2: float, mn2: float) -> tuple[float, tuple[float, ...]]:
    # A=-AB/2, B=+AB/2, M=-MN/2, N=+MN/2.
    L = _positive(ab2, "AB/2")
    l = _positive(mn2, "MN/2")
    if L <= l:
        raise VESError("Schlumberger AB/2 must be greater than MN/2")
    distances = (L - l, L + l, L + l, L - l)
    reciprocal = 1 / distances[0] - 1 / distances[1] - 1 / distances[2] + 1 / distances[3]
    return reciprocal, distances


def layered_apparent_resistivity(model: LayeredEarthModel, ab2: float, mn2: float) -> float:
    """Evaluate Schlumberger apparent resistivity for a horizontal layered earth.

    Formulation and units
    ---------------------
    For a point current source ``I`` on the surface of a layered earth with
    surface resistivity ``rho_1`` and resistivity transform ``T(lambda)``, the
    surface potential at radial distance ``r`` is

        V(r) = (I / (2*pi)) * integral_0^inf T(lambda) * J0(lambda*r) dlambda.

    With A at ``-AB/2``, B at ``+AB/2``, M at ``-MN/2`` and N at ``+MN/2``, the
    four-electrode response is

        dV / I = (1/(2*pi)) * integral_0^inf T(lambda) *
                 (J0(lambda*AM) - J0(lambda*AN) - J0(lambda*BM) + J0(lambda*BN)) dlambda

    and the Schlumberger apparent resistivity is ``rho_app = K * dV / I`` with
    ``K = pi*(AB/2**2 - MN/2**2) / (2*MN/2)``.

    ``T`` tends to ``rho_1`` as ``lambda -> inf``, so the integral is not
    absolutely convergent. It is therefore evaluated as an exact homogeneous
    term plus a decaying correction:

        dV / I = (1/(2*pi)) * [ rho_1 * (1/AM - 1/AN - 1/BM + 1/BN)
                               + integral_0^inf (T(lambda) - rho_1) *
                                 (J0(lambda*AM) - J0(lambda*AN) - J0(lambda*BM) + J0(lambda*BN)) dlambda ]

    The homogeneous term uses the exact identity
    ``integral_0^inf J0(lambda*r) dlambda = 1/r``: the ``1/r`` factor belongs to
    that identity, **not** to the integrand. The correction integrand must
    therefore contain ``J0(lambda*d)`` without any ``1/d`` factor; the correction
    decays exponentially because ``T(lambda) - rho_1 -> 0`` as ``lambda -> inf``.

    Distances are in metres, resistivities in ohm-metres, and the returned value
    is in ohm-metres.
    """
    reciprocal, distances = _electrode_reciprocal_sum(ab2, mn2)
    rho_surface = model.resistivities[0]
    if all(rho == rho_surface for rho in model.resistivities):
        return rho_surface

    correction_integral = _correction_integral(model, rho_surface, distances)
    resistance = (rho_surface * reciprocal + correction_integral) / (2 * math.pi)
    value = schlumberger_geometric_factor(ab2, mn2) * resistance
    if not math.isfinite(value) or value <= 0:
        # A non-finite or non-positive response from an accepted model is a
        # numerical failure of the forward model, never invalid input.
        raise VESNumericalError("layered-earth forward model produced an invalid apparent resistivity")
    return value


def invert_ves(
    points: Sequence[VESPoint], initial_model: LayeredEarthModel,
    *, max_nfev: int = 200,
) -> VESInversionResult:
    """Fit a layered model by bounded least squares in log10 apparent resistivity.

    The search domain is the domain whose forward response the engine can
    *certify* at :data:`VES_QUADRATURE_NODE_BUDGET`. Layer thicknesses are
    bounded below by :func:`certified_thickness_lower_bound` for the widest
    electrode spacing in the sounding, replacing the previous arbitrary 1e-4 m
    floor. Thinner top layers are numerically unresolvable at those spacings;
    restricting the search domain keeps the inversion from silently relying on an
    uncertified (and previously sometimes non-physical) response. The optimizer,
    the objective, and the convergence criteria are unchanged.
    """
    usable = [point for point in points if not point.excluded]
    observed = np.asarray([ves_apparent_resistivity(point) for point in usable], dtype=float)
    if len(usable) < len(initial_model.resistivities) * 2 - 1:
        raise VESError("too few active VES points for the requested model complexity")
    if not np.all(np.isfinite(observed) & (observed > 0)):
        raise VESError("observed VES values must be finite and positive")
    if not isinstance(max_nfev, int) or max_nfev < 1:
        raise VESError("max_nfev must be a positive integer")

    count = len(initial_model.resistivities)
    initial = np.log10(np.asarray((*initial_model.resistivities, *initial_model.thicknesses)))
    lower = np.full(count + count - 1, -6.0)
    upper = np.full(count + count - 1, 12.0)
    thickness_floor = certified_thickness_lower_bound(max(point.ab2 + point.mn2 for point in usable))
    lower[count:] = math.log10(thickness_floor)
    upper[count:] = 6.0
    if np.any(initial < lower) or np.any(initial > upper):
        raise VESError(
            "initial model is outside the certified inversion domain "
            f"(thicknesses must be at least {thickness_floor:g} m for this sounding)"
        )

    def unpack(parameters: np.ndarray) -> LayeredEarthModel:
        values = 10.0 ** parameters
        return LayeredEarthModel(tuple(values[:count]), tuple(values[count:]))

    def residual(parameters: np.ndarray) -> np.ndarray:
        model = unpack(parameters)
        predicted = np.asarray([layered_apparent_resistivity(model, point.ab2, point.mn2) for point in usable])
        return np.log10(predicted) - np.log10(observed)

    result = least_squares(residual, initial, bounds=(lower, upper), max_nfev=max_nfev, xtol=1e-8, ftol=1e-8, gtol=1e-8)
    fitted = unpack(result.x)
    predicted = tuple(layered_apparent_resistivity(fitted, point.ab2, point.mn2) for point in usable)
    residuals = tuple(float(math.log10(predicted_value / observed_value)) for predicted_value, observed_value in zip(predicted, observed))
    rms_log10 = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    rms_percent = percent_rms(predicted, observed)
    return VESInversionResult(
        model=fitted, predicted=predicted, residuals_log10=residuals,
        rms_log10=rms_log10, rms_percent=rms_percent,
        converged=bool(result.success), iterations=int(result.nfev), message=str(result.message),
    )
