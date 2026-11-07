# Multi-line coordinate notes

`SurveyLine` stores local electrode coordinates and applies an explicit azimuth, origin translation, and optional direction reversal. `aggregate_lines` returns transformed 3D coordinates for later visualization. Direction reversal changes display/order only; electrode identifiers are preserved.

GPS references use WGS84 geodetic-to-ECEF conversion and local ENU deltas, avoiding a degree-to-metre approximation. UTM references validate and preserve zone and hemisphere metadata; full UTM projection and datum transformations are intentionally deferred to the GIS/DEM milestone.

Coordinates and transforms are validated for finite values, unique positive electrode numbers, valid GPS ranges, and valid UTM zones. No automatic line alignment or inferred coordinate system is performed.
