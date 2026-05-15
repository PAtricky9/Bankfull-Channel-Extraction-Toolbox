# Example Parameter Set

This is a starting point for testing a short reach. Adjust values after inspecting intermediate outputs.

## Prepare Inputs

- Output geodatabase name: `bankfull_outputs.gdb`
- DEM clip buffer distance: `150 Meters`
- Dissolve stream centreline: `True`
- Check projection compatibility: `True`

## Station Points

- Station interval: `10`
- Reach ID field: leave blank for a dissolved single reach, or choose an existing reach field.

## Cross Sections

- Cross-section half width: `50`
- Method: `fast_perpendicular`
- Tangent calculation distance: `20`

## DEM Profiles

- Sample spacing: `1`
- Optional slope raster: leave blank if the tool should create one.
- Create slope raster if missing: `True`

## Thalweg And Hydraulic Metrics

- Centre search distance: `10`
- Maximum water level above thalweg: `5`
- Water level step: `0.1`
- Minimum valid top width: `0.5`

## Candidate Detection

- Slope threshold: `15`
- Hydraulic breakpoint sensitivity: `1.0`
- Maximum bankfull height above thalweg: `4`

## Continuity Check

- Width jump threshold ratio: `0.75`
- Elevation jump threshold: `1.0`
- Moving window size: `5`

## Smoothing

- Smoothing method: `none` for first QA pass.
- Smoothing window size: `5`
- Preserve low confidence points: `True`

