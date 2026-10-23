"""3D-scan inspection (separate capability, not part of root-cause analysis).

iPad LiDAR is about 1-1.5 cm RMSE, so cracks are looked for in the colour texture and
dents only against a reference scan, above a configurable noise threshold."""

SENSOR_NOTE = ("iPad LiDAR accuracy is about 1-1.5 cm. Small cracks and shallow dents are not "
               "detectable in depth; cracks are searched in the colour texture, dents only against a "
               "reference scan above the chosen threshold.")
