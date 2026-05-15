# Method Notes

## Original Slope Threshold Concept

The reference workflow identifies likely bank edges from high slope values along DEM-sampled cross sections. The assumption is that channel banks often appear as slope breaks in a cross-section profile.

This is a useful baseline, but it can fail where banks are subtle, modified, noisy, vegetated, or interrupted by roads, bridges, culverts, levees, drains, and DEM artefacts.

## Multi Evidence Method

This toolbox treats slope threshold evidence as one part of a larger cross-section profile assessment. Version 1 combines:

- Slope threshold or local slope peak evidence.
- Hydraulic curve breakpoint evidence.
- Relative elevation above the thalweg.
- Left/right bank completeness.
- Candidate agreement between methods.
- Width and bankfull level continuity along the reach.
- DEM NoData and geometry QA flags.

The intent is not to claim a perfect automated answer. The intent is to produce transparent candidates, reasons, and confidence values that support efficient manual QA.

## Thalweg Detection

The thalweg is detected as the lowest valid DEM profile point within a user controlled centre search distance. This prevents floodplain drains or side depressions far from the stream centreline from being selected as the main channel low point.

If no valid point exists in the search window, the tool falls back to the lowest point in the profile and flags reduced confidence.

## Hydraulic Depth

For each simulated water level:

```text
hydraulic_depth = cross_sectional_flow_area / top_width
```

Top width is the horizontal width along the cross section where the connected wetted part of the terrain profile lies below the simulated water level.

Cross-sectional flow area is the two-dimensional area between the water level line and the terrain profile. It is calculated with trapezoidal integration.

## Connected Wetted Region

Only the wetted profile region connected to the thalweg is included. Disconnected side depressions outside the main channel are ignored for hydraulic metrics.

This is important because a low floodplain drain can otherwise inflate top width and flow area before the simulated water level has actually connected to the main channel.

## Cross-Sectional Flow Area Is Not Map Inundation Area

Cross-sectional flow area is not a mapped flood extent, inundation area, or planimetric polygon area. It is a two-dimensional profile metric used to understand how channel shape changes as water level rises.

## Hydraulic Breakpoint Candidate

The first version uses a simple, explainable breakpoint method:

- Calculate top width, cross-sectional flow area, and hydraulic depth over water levels above the thalweg.
- Calculate first-difference rates for width, area, and hydraulic depth.
- Identify the strongest plausible top-width expansion point below the maximum allowed bankfull height.
- Intersect that water level with the connected profile region around the thalweg.
- Output the candidate bank points, level, width, score, reason, and QA flag.

The breakpoint is a candidate, not a final truth.

## Candidate Scoring

Candidate confidence is based on:

- Whether left and right banks are both found.
- Whether slope and hydraulic evidence agree.
- Whether a hydraulic breakpoint is strong enough for the selected sensitivity.
- Whether the selected width is close to the local moving median.
- Whether bankfull level changes smoothly relative to neighbouring cross sections.
- Whether QA flags indicate missing geometry, weak evidence, or divergent methods.

Final confidence classes are High, Medium, and Low. Low confidence and flagged cross sections should be manually reviewed.

## Manual QA Guidance

Review outputs in this order:

1. Station points and cross-section geometry.
2. DEM profile points and NoData flags.
3. Thalweg points.
4. Hydraulic curve table for representative cross sections.
5. Candidate points and width lines by method.
6. Selected bankfull points, width lines, and QA flags.
7. Raw bankfull polygon.
8. Smoothed polygon and correction log, if smoothing is used.

Prioritise review near bridges, culverts, roads, levees, confluences, tight meanders, low-gradient reaches, vegetation artefacts, and cross sections with large width or level jumps.

## Validation Status

This toolbox has not yet been validated against surveyed bankfull indicators or field verified channel boundaries. Outputs should be treated as candidate bankfull extents until reviewed by a geomorphologist or experienced hydraulic or GIS analyst.

The current method notes describe the intended calculation logic and QA workflow. They do not replace ArcGIS Pro runtime testing, field validation, or independent geomorphic review.
