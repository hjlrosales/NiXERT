# 2D ERT inversion notes

The current M7 engine is a deliberately bounded baseline. It uses a cell-centred rectangular finite-volume discretization of the 2D conductivity equation, zero-flux outer boundaries, top-cell electrode sources/sinks, numerical central-difference sensitivities, and damped Gauss–Newton updates in log10 resistivity.

Apparent resistivity is normalized against the same mesh and quadrupole with a homogeneous unit-resistivity model. This is a useful internal synthetic convention, not a half-space analytic correction and not RES2DINV equivalence.

Validation covers mesh construction, homogeneous normalization, finite Jacobians, synthetic residual reduction, excluded observations, and invalid inputs. The finite domain, 2D approximation, electrode discretization, boundary conditions, and absence of topography are known limitations. Benchmark comparison against trusted software and real/reference datasets is still required before this engine can be called production-ready.
