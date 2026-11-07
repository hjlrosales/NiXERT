# Pseudosection notes

The pseudosection builder creates display points from imported apparent resistivity and electrode x coordinates. Point x is the mean of the four electrode positions. Display depth is a documented pseudo-depth proxy based on the median current/potential separation; it is **not** an inversion depth, geological interface, or substitute for a mesh model.

Excluded measurements are hidden by default but can be included for audit views. Non-positive/non-finite values are never plotted. CSV exports include row identity, geometry, apparent resistivity, log10 display value, status, and electrode tuple so an exported view remains traceable to its source measurement.
