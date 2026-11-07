"""Numerically stable reporting statistics shared by the inversion engines.

This module holds reporting-level numerics only: the inversion solvers keep
their own mathematics. The single shared quantity is the percentage RMS

    ``100 * sqrt(mean(((predicted / observed) - 1) ** 2))``

which both the 2D ERT engine and the VES engine report next to the log10 RMS.

Why it is not evaluated directly: the conventional expression squares each
relative residual, so a *representable* percentage is reported as ``inf`` (with
``RuntimeWarning: overflow encountered in square``) as soon as one relative
residual exceeds ``sqrt(float_max) ~ 1.3e154``. Resistance and apparent
resistivity inputs are validated only as finite and positive, and an initial
model may legitimately be extreme, so that range is reachable through the
public APIs (for example ``invert_ert(..., 1e300)`` or a sounding whose
apparent resistivities are ~1e-190).

The evaluation therefore switches to a scaled sum-of-squares form whenever the
direct expression cannot be guaranteed to be overflow-free. The two forms are
mathematically identical; the direct one is kept for the ordinary range so
that historical, representable results stay bit-identical.

The mixed-magnitude case needs care: when one relative residual is enormous and
another is minute, the scale must be the largest *residual magnitude* and not,
as an earlier revision did, the largest ``log10`` ratio. Scaling by the extreme
ratio exponent drove every contribution to underflow and rejected a finite,
representable result. The scaled branch now selects the largest residual
magnitude as the scale and accumulates the ``(residual / scale) ** 2``
contributions, so a minute residual contributes its true (necessarily tiny)
share instead of erasing the dominant ones. Residual magnitudes and the scale
are formed directly in double precision whenever the division does not
overflow; only when a ratio overflows is a log10 form used.
"""

from __future__ import annotations

import math
import sys
from typing import Sequence

_FLOAT_MAX = sys.float_info.max
_FLOAT_MAX_LOG10 = math.log10(_FLOAT_MAX)
"""``308.2547...``: the largest power of ten a double can represent."""

_LN10 = math.log(10.0)

__all__ = ["percent_rms"]


def percent_rms(predicted: Sequence[float], observed: Sequence[float]) -> float:
    """Return ``100 * sqrt(mean(((predicted / observed) - 1) ** 2))`` safely.

    ``predicted`` and ``observed`` must be equally sized, non-empty sequences of
    finite, strictly positive values; anything else raises :class:`ValueError`
    (both engines validate their inputs before calling this, so the check is a
    defensive boundary rather than a user-facing path).

    Representability semantics, all of which are honest IEEE-754 outcomes:

    * **representable** — the exact value is returned (to double precision);
    * **mathematically finite but not representable** — the exact value exceeds
      ``float_max``, so ``inf`` is returned. This is not an error and no finite
      substitute is invented: the log10 residual remains finite and is the
      quantity to report in that regime;
    * **invalid input** — non-finite or non-positive values raise
      :class:`ValueError` instead of silently producing ``nan``.
    """
    predicted_values = [float(value) for value in predicted]
    observed_values = [float(value) for value in observed]
    count = len(predicted_values)
    if count == 0 or count != len(observed_values):
        raise ValueError("percent_rms requires non-empty equally sized sequences")
    if not all(
        math.isfinite(value) for value in (*predicted_values, *observed_values)
    ):
        raise ValueError("percent_rms requires finite predicted and observed values")
    if any(value <= 0.0 for value in (*predicted_values, *observed_values)):
        raise ValueError("percent_rms requires strictly positive values")

    relative = [
        predicted_value / observed_value - 1.0
        for predicted_value, observed_value in zip(predicted_values, observed_values)
    ]
    # Squaring is the only operation that can overflow here (division overflows
    # to inf, which is caught by the bound check below). The factor of two is
    # headroom for rounding, so a direct result can never come from an
    # intermediate overflow.
    direct_bound = math.sqrt(_FLOAT_MAX / count) / 2.0
    if all(abs(value) <= direct_bound for value in relative):
        return math.sqrt(sum(value * value for value in relative) / count) * 100.0
    return _scaled_percent_rms(predicted_values, observed_values)


def _materialise(log10_value: float) -> float:
    """Return ``10 ** log10_value``, or ``inf`` where the double range ends."""
    if log10_value >= _FLOAT_MAX_LOG10:
        return math.inf
    try:
        return 10.0 ** log10_value
    except OverflowError:  # pragma: no cover - rounding at the very boundary
        return math.inf


def _log10_ratio(predicted_value: float, observed_value: float) -> float:
    """Return ``log10(predicted / observed)`` without over- or underflowing."""
    ratio = predicted_value / observed_value
    if math.isfinite(ratio) and ratio > 0.0:
        return math.log10(ratio)
    # The ratio itself overflowed to inf or underflowed to zero; the difference
    # of the (individually finite) log10 magnitudes is bounded by +-~631.
    return math.log10(predicted_value) - math.log10(observed_value)


def _log10_residual_magnitude(log10_ratio: float) -> float:
    """Return ``log10|10 ** log10_ratio - 1|`` without over- or underflow.

    ``log10_ratio`` is finite. For a non-negative exponent the residual is
    ``10 ** d * (1 - 10 ** -d)``, whose correction factor is evaluated with
    ``log1p`` so that ``exp`` never has to represent the (possibly far
    out-of-range) ``10 ** d``. For a negative exponent the residual is
    ``-expm1(d * ln10)``, which lies in ``(0, 1]`` and cannot underflow to zero.
    """
    if log10_ratio >= 0.0:
        return log10_ratio + math.log1p(-10.0 ** (-log10_ratio)) / _LN10
    return math.log10(-math.expm1(log10_ratio * _LN10))


def _scaled_percent_rms(
    predicted: Sequence[float], observed: Sequence[float],
) -> float:
    """Evaluate the percentage RMS from scaled residual magnitudes.

    With ``r_i = |predicted_i / observed_i - 1|`` and ``s = max_i r_i``,

        ``100 * sqrt(mean(r_i ** 2))``
            ``= 100 * s * sqrt(mean((r_i / s) ** 2))``

    and every ``r_i / s`` lies in ``[0, 1]``, so its square cannot overflow.
    Each residual keeps its own magnitude: a minute residual contributes its
    true ``(r_i / s) ** 2`` share, which is the mathematically correct amount,
    instead of being annihilated by another residual's scale.

    ``|ratio - 1|`` is formed directly: a division that underflows to zero
    yields exactly the correct residual ``1``, and one that overflows to ``inf``
    marks a magnitude beyond double precision. Only in that overflow case is the
    log10 form used, since the scale itself is then unrepresentable.
    """
    magnitudes = [
        abs(predicted_value / observed_value - 1.0)
        for predicted_value, observed_value in zip(predicted, observed)
    ]
    scale = max(magnitudes)
    if scale == 0.0:
        # Every prediction matches its observation exactly.
        return 0.0
    if not math.isfinite(scale):
        return _log10_percent_rms(predicted, observed)
    total = sum((magnitude / scale) ** 2 for magnitude in magnitudes)
    # No log10 round trip is used here: the assembled value is exact to double
    # rounding. If it exceeds the double range the product is honestly ``inf``,
    # which is then the correct representability outcome rather than an error.
    return scale * math.sqrt(total / len(magnitudes)) * 100.0


def _log10_percent_rms(
    predicted: Sequence[float], observed: Sequence[float],
) -> float:
    """Scaled percentage RMS when the largest residual magnitude overflows.

    The scale is then taken in log10 space: with ``m_i = log10 r_i`` and
    ``m = max_i m_i`` every ``r_i / 10 ** m = 10 ** (m_i - m)`` is at most one,
    so the same sum of squares is formed without any intermediate overflowing.
    """
    log10_magnitudes = [
        _log10_residual_magnitude(_log10_ratio(predicted_value, observed_value))
        for predicted_value, observed_value in zip(predicted, observed)
    ]
    scale = max(log10_magnitudes)
    if scale == -math.inf:
        return 0.0
    total = sum(10.0 ** (2.0 * (magnitude - scale)) for magnitude in log10_magnitudes)
    log10_result = scale + math.log10(total / len(log10_magnitudes)) / 2.0 + 2.0
    return _materialise(log10_result)
