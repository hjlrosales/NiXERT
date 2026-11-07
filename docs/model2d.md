# 2D model visualization notes

`ResistivitySection` represents a validated rectangular cell model with explicit x/depth edges. It rejects non-finite or non-positive cells and mismatched shapes. Display controls support logarithmic or linear normalization, user-editable positive color limits, electrode markers, topography overlays, and contour-level metadata.

Cell inspection returns column/layer, cell-center coordinates, and resistivity. CSV export emits every cell in stable row order. Matplotlib rendering is optional and produces a publication/report-oriented section image with an appropriate scale and inverted depth axis.

The section is a visualization of a model produced elsewhere; display limits and clipping do not alter model values. The M7 baseline’s flat rectangular mesh and finite-domain assumptions still apply.
