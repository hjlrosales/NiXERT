# Apparent resistivity validation

The engine is based on the surface point-electrode homogeneous half-space equation. The reciprocal-distance sum produces the geometric factor `K`, and apparent resistivity is `rho_a = K * (V/I)`.

Validation currently includes:

- collinear Wenner geometry: `K = 2*pi*a`;
- collinear dipole-dipole geometry: `K = pi*a*n*(n+1)*(n+2)`;
- agreement between general coordinate geometry and named-array shortcuts;
- finite-input, coincident-electrode, zero-sensitivity, and missing-factor rejection.

Signed factors preserve electrode polarity. Absolute factors are available when the source data convention stores resistance as a magnitude. This milestone does not infer array geometry from arbitrary measurement rows, nor does it claim equivalence to RES2DINV. Pole and gradient arrays require survey-specific electrode conventions; unsupported parameterizations are rejected rather than approximated.
