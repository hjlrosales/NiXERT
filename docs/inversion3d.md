# 3D inversion notes

The M14 baseline uses a rectangular cell-centred finite-volume discretization of the 3D conductivity equation with zero-flux outer boundaries, top-layer electrode cells, a zero-mean potential gauge, homogeneous numerical normalization, central-difference log-space sensitivities, and damped Gauss–Newton updates.

Validation covers homogeneous response normalization, reciprocal source/sink behavior, finite Jacobians, synthetic anomaly residual reduction, invalid quadrupoles, and rejection of electrodes outside the mesh. The implementation is not a RES2DINV equivalent, is not yet benchmarked against trusted 3D software, and does not support topography, adaptive meshes, uncertainty/resolution analysis, or production-scale acceleration. It must not be treated as a validated geological inversion solely because it fits synthetic data.
