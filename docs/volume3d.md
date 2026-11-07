# 3D visualization notes

`ResistivityVolume` is a validated, explicit cell volume with x/y/depth edges. It supports horizontal and vertical slice copies, threshold masks, coordinate/value inspection, stable CSV export, and an optional matplotlib point-cloud rendering. Thresholds and opacity are view controls and never mutate resistivity values.

This milestone is visualization only. It does not interpolate sparse 2D lines into a volume, perform 3D inversion, or claim that a displayed volume is a uniquely resolved geological model. A future volume-construction workflow must define interpolation and uncertainty before it can be scientifically relied upon.
