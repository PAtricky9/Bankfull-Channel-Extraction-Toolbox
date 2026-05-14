# Bankfull Channel Extractor

Bankfull Channel Extractor is an ArcGIS Pro Python toolbox for deriving bankfull channel candidates from a stream centreline and LiDAR DEM. It is designed for step by step processing, visual QA, and parameter testing rather than as a single black box model.

The first version is intended for Australian east coast river settings where high resolution LiDAR DEMs are available, including natural, urban modified, lowland alluvial, vegetated, intermittent, bridged, and culverted reaches. It will still need manual review in difficult reaches.

## Required Software

- ArcGIS Pro with ArcPy.
- Spatial Analyst is recommended for DEM sampling, slope creation, and DEM clipping.
- Python packages included with ArcGIS Pro. The core profile algorithms use ordinary Python data structures and can be extended to NumPy or Pandas where useful.

## Input Data

- Stream centreline polyline feature class.
- High resolution DEM raster in a projected coordinate system with metre units.
- Optional slope raster in degrees.
- A project folder for the output file geodatabase and QA report.

Recommended DEM resolution depends on channel scale. As a starting point, use the finest reliable LiDAR DEM available and set profile sample spacing at or finer than the DEM cell size.

## Workflow

Run the tools in order and inspect intermediate outputs before continuing.

1. **01 Prepare Inputs** creates the project geodatabase, prepared stream centreline, optional clipped DEM, processing boundary, and configuration table.
2. **02 Generate Station Points** creates evenly spaced points along each stream feature or dissolved reach.
3. **03 Generate Cross Sections** creates fast perpendicular cross sections using local stream tangent direction.
4. **04 Sample DEM Profiles** densifies cross sections and samples DEM elevation and optional slope.
5. **05 Detect Thalweg And Hydraulic Metrics** detects the thalweg near the centreline and calculates top width, cross-sectional flow area, and hydraulic depth over simulated water levels.
6. **06 Bankfull Candidate Detection** creates slope-threshold, hydraulic-breakpoint, and agreement candidates.
7. **07 Select Best Candidate And Continuity Check** selects one result per cross section and flags abrupt width or level changes.
8. **08 Create Bankfull Polygon** builds raw left and right bank lines and a raw bankfull polygon.
9. **09 Smooth Bank Lines** optionally applies transparent rolling median smoothing and records changes.
10. **10 Generate QA Report** writes CSV and Markdown summaries for review.

## Parameter Guide

- **Station interval** controls along-stream spacing between cross sections. Smaller intervals improve detail but increase processing time.
- **Cross-section half width** should be wide enough to reach the floodplain on both sides, but not so wide that adjacent channels or drains dominate the profile.
- **Tangent distance** controls how local stream direction is estimated. Increase it for noisy centrelines; decrease it in tight bends.
- **Sample spacing** controls profile density. Use a value close to DEM cell size.
- **Centre search distance** constrains thalweg detection near the centreline so side depressions are less likely to be selected.
- **Maximum water level above thalweg** limits hydraulic curve simulation and candidate search height.
- **Slope threshold** is evidence for bank edges, not the only decision rule.
- **Hydraulic breakpoint sensitivity** controls how strong a top-width or hydraulic-depth curve break must be to be treated as strong evidence.
- **Width jump and elevation jump thresholds** flag cross sections that are discontinuous relative to neighbours.

## Outputs

Important fields use compact geodatabase-safe names:

- `xsec_id`: cross-section identifier.
- `chain_m`: chainage along stream.
- `elev_m`: DEM elevation.
- `slope_deg`: slope in degrees.
- `thalweg_z`: thalweg elevation.
- `wl_z`: simulated water level.
- `top_w_m`: connected top width around the thalweg.
- `flow_area`: cross-sectional flow area below water level and above terrain.
- `hyd_depth`: hydraulic depth, calculated as `flow_area / top_w_m`.
- `bf_level`: candidate or selected bankfull level.
- `bf_width`: bankfull width.
- `conf` or `confidence`: confidence score or class.
- `qa_flag`, `qa_reason`, `review_req`: QA outputs for manual checking.

## QA Checklist

- Confirm station points cover the intended stream reach.
- Confirm cross sections are approximately perpendicular and do not cross too much in tight meanders.
- Inspect sampled profile points for DEM NoData and obvious bridges, roads, culverts, levees, vegetation artefacts, or adjacent drains.
- Check thalweg points on representative cross sections.
- Compare slope-threshold and hydraulic-breakpoint candidates.
- Review all Low confidence and manual review cross sections before polygon generation.
- Inspect raw bank lines and polygon before using them in analysis.
- Treat smoothing as optional and review the correction log.

## Known Limitations

- Version 1 uses a fast perpendicular cross-section method. A warped method can be added later.
- Hydraulic breakpoint detection is intentionally simple and explainable.
- Low gradient or shallow channels may not show a clear curve break.
- Bridges, culverts, roads, levees, vegetation, DEM voids, and adjacent drains can create false candidates.
- Cross-sectional flow area is a two-dimensional profile metric, not a planimetric inundation area.
- The tool has not been independently validated and should be calibrated with local field or expert knowledge.

## Licence And Attribution

This implementation is a new modular toolbox inspired by the Cross Sections and Dimensions Tool:

- Repository: <https://github.com/jkunapo/Cross-Sections-Dimensions-Tool>
- DOI: <https://doi.org/10.5281/zenodo.18950771>
- Licence noted for the reference project: MIT License

This project does not imply endorsement by the original authors or the University of Melbourne. If code from the reference project is copied or adapted in the future, preserve the original copyright and MIT licence notice.

No source code from the reference repository is included in this initial implementation. See `THIRD_PARTY_NOTICES.md` for the attribution note.
