# Bankfull Channel Extractor

Bankfull Channel Extractor is an ArcGIS Pro Python toolbox for estimating bankfull channel extent and bankfull width from a stream centreline and a LiDAR DEM.

The toolbox is designed as a step by step QA workflow. It creates intermediate station points, cross sections, DEM profile samples, thalweg points, hydraulic curve tables, bankfull candidates, selected bankfull width lines, bank lines, polygons, and QA reports so the user can inspect and tune parameters before accepting final outputs.

## What This Tool Does

Given:

- A stream centreline polyline.
- A high resolution LiDAR DEM.
- User parameters such as station spacing, cross-section width, DEM sample spacing, slope threshold, and hydraulic breakpoint sensitivity.

It produces:

- Station points along the stream.
- Cross-section lines.
- DEM sampled profile points and profile tables.
- Thalweg points.
- Hydraulic curve metrics including top width, cross-sectional flow area, and hydraulic depth.
- Bankfull candidate points and width lines from slope and hydraulic methods.
- A selected best bankfull result per cross section.
- Raw and optional smoothed bankfull polygons.
- QA flags, confidence classes, and report files.

## Important Status Note

This is an initial implementation. It is intended for testing on short reaches first, not immediate production use over large river networks. You should manually inspect intermediate outputs, especially near bridges, culverts, levees, vegetation artefacts, adjacent drains, confluences, and tight bends.

## Installation In ArcGIS Pro

1. Download or clone this repository.
2. Keep this folder structure together:

```text
Bankfull_Channel_Extractor.pyt
bankfull_core/
docs/
examples/
```

3. Open ArcGIS Pro.
4. In the Catalog pane, browse to the repository folder.
5. Right-click `Bankfull_Channel_Extractor.pyt` and choose **Add To Project**.
6. Expand the toolbox. You should see tools numbered 01 to 10.

If ArcGIS Pro cannot load the toolbox, check that `bankfull_core/` is in the same folder as `Bankfull_Channel_Extractor.pyt`.

## Recommended First Test

Start with a short stream reach, for example 500 m to 2 km, before running a long river system.

Recommended starting parameters:

- Station interval: `10 m`
- Cross-section half width: `50 m`
- Tangent calculation distance: `20 m`
- DEM sample spacing: approximately the DEM cell size
- Centre search distance for thalweg: `10 m`
- Maximum water level above thalweg: `5 m`
- Water level step: `0.1 m`
- Slope threshold: `15 degrees`
- Hydraulic breakpoint sensitivity: `1.0`
- Width jump threshold ratio: `0.75`
- Elevation jump threshold: `1.0 m`
- Moving window size: `5`

These values are only a starting point. Adjust them after visually inspecting station points, cross sections, profile samples, thalweg points, candidates, and QA flags.

## Workflow

Run the tools in order.

### 01 Prepare Inputs

Checks the stream centreline and DEM, creates an output geodatabase, optionally dissolves the stream, optionally clips the DEM, creates a processing boundary, and writes a project configuration table.

Use this first so later tools write derived outputs without modifying original data.

### 02 Generate Station Points

Creates evenly spaced points along the prepared stream centreline.

Inspect the output before continuing. Confirm that station points cover the intended reach and are spaced appropriately.

### 03 Generate Cross Sections

Creates fast perpendicular cross sections from station points using local stream direction.

Inspect for:

- Cross sections approximately perpendicular to flow.
- Cross sections not crossing too much in meanders.
- Cross sections long enough to reach both banks.
- Cross sections not extending into unrelated drains or adjacent channels.

### 04 Sample DEM Profiles

Densifies each cross section and samples DEM elevation and optional slope.

Inspect profile points for DEM coverage, NoData areas, bridges, road embankments, culverts, vegetation artefacts, and other features that can confuse bank detection.

### 05 Detect Thalweg And Hydraulic Metrics

Finds the thalweg near the centreline and simulates water levels above it. For each water level it calculates:

- Top width.
- Cross-sectional flow area.
- Hydraulic depth.
- First-difference rates for curve interpretation.

Only the wetted profile region connected to the thalweg is used, so disconnected side depressions are not counted as part of the main channel.

### 06 Bankfull Candidate Detection

Creates candidate bankfull results from:

- Slope threshold evidence.
- Hydraulic curve breakpoint evidence.
- Agreement between slope and hydraulic candidates.

Each candidate includes a method, bankfull level, bank points, bankfull width, confidence score, reason, and QA flag.

### 07 Select Best Candidate And Continuity Check

Selects one candidate per cross section and checks local continuity.

It penalises:

- Very large width jumps.
- Abrupt bankfull level jumps.
- Missing left or right bank points.
- Divergence between methods.
- Weak candidate evidence.

Review all Low confidence and manual review outputs before polygon generation.

### 08 Create Bankfull Polygon

Creates raw left and right bank lines and a raw bankfull polygon from selected bankfull points.

Inspect the polygon carefully before using it. Raw polygons can be invalid in complex bends, braided reaches, confluences, or places where selected candidates are wrong.

### 09 Smooth Bank Lines

Optionally smooths selected bank points with a transparent rolling median method and writes a correction log.

Use smoothing cautiously. Do not over-smooth real river bends.

### 10 Generate QA Report

Creates CSV and Markdown summaries including:

- Number of cross sections.
- Confidence counts.
- Manual review count.
- Width statistics.
- Largest width deviations.
- Largest bankfull level jumps.
- Parameters and input paths.
- Known limitations.

## Key Concepts

### Bankfull

Bankfull means the condition where flow fills the main channel up to the bank level before spreading substantially across the floodplain.

### Hydraulic Depth

Hydraulic depth is:

```text
hydraulic_depth = cross_sectional_flow_area / top_width
```

### Cross-Sectional Flow Area

Cross-sectional flow area is a two-dimensional profile metric. It is the area below a simulated water level and above the terrain profile along one cross section.

It is not a mapped inundation area or flood extent polygon.

## Output Guide

Common fields include:

- `xsec_id`: cross-section identifier.
- `chain_m`: distance along the stream.
- `elev_m`: sampled DEM elevation.
- `slope_deg`: sampled or derived slope in degrees.
- `thalweg_z`: thalweg elevation.
- `wl_z`: simulated water level elevation.
- `top_w_m`: top width at a simulated water level.
- `flow_area`: cross-sectional flow area.
- `hyd_depth`: hydraulic depth.
- `bf_level`: bankfull level.
- `bf_width`: bankfull width.
- `confidence`: High, Medium, or Low.
- `qa_flag`: compact QA flag.
- `qa_reason`: human-readable QA explanation.
- `review_req`: whether manual review is required.

## QA Checklist

Before accepting outputs:

- Confirm the stream centreline and DEM use appropriate projected coordinate systems.
- Inspect station points.
- Inspect cross-section geometry.
- Inspect DEM profile points and NoData flags.
- Check thalweg points on representative sections.
- Compare slope and hydraulic candidates.
- Review all Low confidence results.
- Review all cross sections with large width or level jumps.
- Inspect raw bank lines and polygon.
- Check the smoothing correction log if smoothing is used.

## Documentation

- Full user guide: `docs/README.md`
- Method notes: `docs/method_notes.md`
- Example parameters: `examples/example_config.md`
- Third party notice: `THIRD_PARTY_NOTICES.md`

## Attribution

This implementation was inspired by the Cross-Sections and Dimensions Tool by Joshphar Kunapo and Kathryn Russell:

- https://github.com/jkunapo/Cross-Sections-Dimensions-Tool
- https://doi.org/10.5281/zenodo.18950771

The reference project is MIT licensed. No source code from that repository is included in this initial implementation. The current toolbox was written independently from the project specification, using the reference tool as methodological inspiration only.
