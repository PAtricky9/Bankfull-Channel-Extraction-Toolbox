# Tool Help

This page describes the current user-facing tools in `Bankfull_Channel_Extractor.pyt`. The toolbox is a prototype and has not yet been validated against surveyed bankfull indicators or field verified channel boundaries. Treat outputs as candidate bankfull extents until they have been reviewed by a geomorphologist or experienced hydraulic or GIS analyst.

ArcGIS Pro runtime testing is still required. Syntax checks outside ArcGIS Pro do not prove that the `.pyt` can be opened or run successfully in ArcGIS Pro.

## Inputs

- Input stream centreline: a polyline feature class representing the stream or channel centreline to process.
- Input LiDAR DEM: a raster elevation model in a projected coordinate system with metre units.
- Output workspace or project geodatabase: the location where derived outputs are written.
- Run name: a short name such as `bf01` that prefixes standard outputs in the project geodatabase.
- Optional slope raster: a slope raster in degrees. If omitted, tools that need slope may create or sample one depending on tool parameters.

Use a short reach first. A 100 to 300 metre smoke test is recommended before running longer reaches.

## Current Tool Sequence

### Run Full Bankfull Workflow

Runs the full workflow from stream centreline and DEM using the standard Project geodatabase plus Run name model. This is the main entry point for basic users.

The tool writes short run-based output names such as `<run>_stream`, `<run>_stations`, `<run>_xsecs`, `<run>_profile_tbl`, `<run>_cand_tbl`, `<run>_selected_tbl`, and `<run>_polygon_raw`. Outputs are candidate bankfull extents and still require manual QA.

Smoothing is optional. The default smoothing method is `none`, so smoothed outputs are skipped unless the user selects a smoothing method.

QA report creation is optional. If Create QA report is enabled, an output report folder is required. If Create QA report is disabled, the report folder is not required.

### 01 Prepare Inputs

Checks the stream centreline and DEM, creates the output geodatabase, optionally clips the DEM, and prepares copied processing inputs. Outputs are setup layers and tables used by later tools.

For run `bf01`, expected setup outputs are `bf01_stream`, `bf01_boundary`, optional `bf01_dem_clip`, and `bf01_run_params`.

### 02 Generate Station Points

Creates regularly spaced station points along the prepared stream centreline. Inspect spacing and coverage before creating cross sections.

### 03 Generate Cross Sections

Creates cross-section lines at station points using local stream direction. Inspect cross-section orientation, length, and crossings before sampling the DEM.

### 04 Sample DEM Profiles

Samples DEM elevation and optional slope along each cross section. Outputs include profile points and a profile table. Inspect NoData flags, bridges, roads, culverts, vegetation artefacts, and adjacent drains.

The tool uses `<run>_dem_clip` when it exists. If no DEM clip was created, it reads `dem_for_processing` from `<run>_run_params`, then falls back to the original `dem_raster` recorded in that table.

### 05 Detect Thalweg And Hydraulic Metrics

Finds the thalweg near the centreline and calculates hydraulic curve metrics for simulated water levels above the thalweg. Outputs include thalweg points, a hydraulic curve table, and profile metrics.

### 06 Bankfull Candidate Detection

Creates candidate bankfull points and width lines using slope threshold evidence, hydraulic breakpoint evidence, and agreement between methods. These are candidate results, not final surveyed bankfull boundaries.

### 07 Select Best Candidate And Continuity Check

Selects one candidate per cross section and flags width jumps, bankfull level jumps, missing bank points, weak evidence, and method disagreement. Review all low confidence or flagged sections.

### 08 Create Bankfull Polygon

Creates raw left and right bank lines and a raw bankfull polygon from selected bankfull points. Inspect raw polygons carefully, especially in bends, confluences, braided reaches, and urban modified channels.

### 09 Smooth Bank Lines

Optionally smooths selected bank points and creates a correction log. Smoothing should remain optional and should not replace manual QA.

If smoothing is enabled, standard outputs are `<run>_smoothed_pts`, `<run>_polygon_smooth`, and `<run>_correction_log`.

### 10 Generate QA Report

Writes QA summaries to CSV and Markdown. The report helps identify confidence counts, manual review sections, width statistics, level jumps, and known limitations.

The tool requires an output report folder and reads `<run>_selected_tbl`, `<run>_qa_flags`, `<run>_cand_tbl`, and `<run>_run_params` from the selected project geodatabase.

## Expected Outputs

Important output types include:

- Standard run setup outputs: stream, boundary, optional DEM clip, and run parameter table.
- Station points and cross-section lines.
- DEM profile points and profile tables.
- Thalweg points.
- Hydraulic curve tables.
- Candidate bankfull points and width lines.
- Selected bankfull points and width lines.
- Raw and optional smoothed bankfull polygons.
- QA flags and QA report files.

## Final Versus QA Outputs

The most useful review outputs are selected bankfull points, selected bankfull width lines, raw bankfull polygon, QA flags, and QA reports.

Intermediate profile, hydraulic, and candidate outputs should be kept during testing because they explain why each result was selected.

## Recommended First Test Workflow

1. Use a short stream reach and a small DEM area.
2. For a simple smoke test, run `Run Full Bankfull Workflow`.
3. For detailed QA, run `01 Prepare Inputs`.
4. Run `02 Generate Station Points` and inspect spacing.
5. Run `03 Generate Cross Sections` and inspect geometry.
6. Run `04 Sample DEM Profiles` and inspect DEM samples.
7. Run `05 Detect Thalweg And Hydraulic Metrics`.
8. Run `06 Bankfull Candidate Detection`.
9. Run `07 Select Best Candidate And Continuity Check`.
10. Run `08 Create Bankfull Polygon`.
11. Run `10 Generate QA Report`.

Use `09 Smooth Bank Lines` only after reviewing raw outputs.

## Known Limitations

- The toolbox has not yet been runtime tested in ArcGIS Pro in this branch.
- Outputs have not yet been validated against surveyed bankfull indicators.
- Long reaches may be slow because processing cost grows with cross sections, profile samples, and simulated water levels.
- Bridges, culverts, levees, road embankments, confluences, vegetation artefacts, braided channels, and adjacent drains can produce misleading candidates.
- Manual QA is required before using outputs for analysis or reporting.
