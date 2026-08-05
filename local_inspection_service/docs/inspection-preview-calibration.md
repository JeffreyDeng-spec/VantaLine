# Inspection preview scale provenance

The cleanup branch preserves the scale already running in the sampled production source: a 1280-pixel preview width maps to a nominal 600 mm field width (`1280 / 600 = 2.1333 px/mm`). The focused pipeline regression therefore expects the production footprints `[85, 213]` for the watch fixture and `[96, 96]` for the 45 mm cap fixture.

This is a production-baseline compatibility assertion, not a new claim that the physical camera has been metrologically calibrated. The source comment models a camera mounted at approximately 700 mm with an approximately 600 mm field of view. Before measurements from real images are used as certified physical dimensions, operators must capture a calibration target in the installed camera/lens/height configuration, record the measured field width and distortion, and explicitly approve any change to `INSPECTION_CAMERA_FRAME_WIDTH_MM` together with updated independent golden fixtures.
