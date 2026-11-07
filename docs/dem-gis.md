# GIS and DEM notes

The dependency-light GIS core supports complete rectangular DEM grids in CSV form, bilinear elevation sampling, transferring DEM elevations to local electrode coordinates, GeoJSON LineString export, and WGS84 geographic coordinates to UTM zone/easting/northing conversion using the standard ellipsoidal Transverse Mercator series.

DEM coordinates must be monotonic and the CSV must contain every point in the rectangular grid. Samples outside the grid are rejected instead of extrapolated. GeoJSON coordinates are emitted in the line's current coordinate reference metadata; no automatic reprojection is performed. GeoTIFF, GeoJSON import, shapefile support, datum transformations, and map tiles remain future extensions requiring dedicated format validation.
