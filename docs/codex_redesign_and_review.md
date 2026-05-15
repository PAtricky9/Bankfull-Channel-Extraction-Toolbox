# Bankfull Channel Extraction Toolbox Redesign And Code Review Prompt

## 1. Purpose Of This Prompt

This prompt replaces the previous review prompt.

The current toolbox has two types of issues:

1. Algorithm and reliability issues.
2. ArcGIS Pro toolbox user experience issues.

The user experience issues are now the highest priority. The toolbox currently feels like a collection of internal developer functions exposed directly to the user. A user must already understand the internal workflow before they can run the toolbox. This is not acceptable for a practical ArcGIS Pro Python Toolbox.

Before adding more algorithm features, redesign the toolbox interface, parameter names, output naming system, tool help, and workflow chaining.

## 2. Current Overall Assessment

The repository is a promising version 0.1 prototype.

The internal code direction is mostly correct:

1. It uses a modular code structure.
2. It creates intermediate outputs for QA.
3. It uses cross section profile analysis.
4. It includes thalweg detection.
5. It calculates top width, cross sectional flow area and hydraulic depth.
6. It uses slope evidence and hydraulic breakpoint evidence.
7. It produces candidate results, selected results, confidence classes and QA flags.
8. The documentation correctly says cross sectional flow area is not map inundation area.

However, the toolbox is not yet usable enough as an ArcGIS Pro tool.

The current main problem is that the user interface exposes too many low level processing steps and too many intermediate products as required inputs. A user who does not already understand the internal workflow will be confused.

## 3. Main User Experience Problems Observed During Testing

### 3.1 Too many user visible tools

The toolbox currently exposes many separate tools. The original intention was modular internal code and QA friendly outputs, not necessarily a separate user facing tool for every internal function.

The current design makes the user manually run many tools in a strict sequence.

This creates problems:

1. The workflow feels mechanical and fragile.
2. The user must remember which output from the previous tool goes into the next tool.
3. The user has to browse through many intermediate datasets.
4. The toolbox feels like a developer demo rather than a practical GIS tool.
5. It is hard for new users to understand the full workflow.

Required redesign:

Keep the internal Python modules, but reduce the number of main user visible tools.

Recommended main tools:

1. `01 Setup Bankfull Project`
2. `02 Create Cross Sections And DEM Profiles`
3. `03 Calculate Hydraulic Metrics`
4. `04 Detect And Select Bankfull`
5. `05 Create Bankfull Outputs And QA Report`
6. `Run Full Bankfull Workflow`

The detailed internal functions can still exist in the codebase. They do not all need to be exposed as separate tools in the main toolbox.

### 3.2 Inputs are named from a programmer perspective

Many current input names are technically correct but not clear to a GIS user.

Examples of confusing input names:

```text
prepared_stream
profile_table
hydraulic_curve
candidate_table
candidate_points
candidate_lines
selected_table
selected_lines
qa_flags
```

These names make sense only if the user already knows the internal workflow.

Required redesign:

Use user facing display names that explain what the input actually is.

Examples:

```text
Input stream centreline
Input LiDAR DEM
Project geodatabase
Run name
Cross section lines from this project
DEM profile table from this project
Hydraulic curve table from this project
Bankfull candidate table from this project
Selected bankfull result table from this project
```

Even better, avoid asking the user to manually select most intermediate inputs. Use the project geodatabase and run name to find them automatically.

### 3.3 Users are forced to manually chain previous outputs into the next tool

The current workflow often works like this:

1. Tool A creates an output.
2. Tool B requires that output as input.
3. The user must find the output dataset manually.
4. The output name is long or unclear.
5. The user is not sure whether they selected the correct dataset.

This is a poor user experience.

Required redesign:

The main workflow should use:

```text
Project folder
Project geodatabase
Run name
```

Each tool should automatically find required previous outputs using standard names.

For example:

```text
bf01_stream
bf01_stations
bf01_xsecs
bf01_profile_pts
bf01_profile_tbl
bf01_thalweg
bf01_hyd_curve
bf01_candidates
bf01_selected
bf01_polygon_raw
bf01_qa_flags
```

The user should not need to manually select every previous output unless they choose an advanced rerun mode.

### 3.4 Output names are too long and hard to understand

Long output names are difficult to browse in ArcGIS Pro, especially inside a geodatabase.

Required output naming rules:

1. Use short names.
2. Use stable names.
3. Use a short run prefix.
4. Use consistent suffixes.
5. Avoid encoding long parameter values in output names.
6. Avoid overly descriptive names in feature class names.
7. Use aliases and metadata for human readable descriptions instead of very long feature class names.

Recommended naming pattern:

```text
<run_id>_stream
<run_id>_boundary
<run_id>_stations
<run_id>_xsecs
<run_id>_profile_pts
<run_id>_profile_tbl
<run_id>_thalweg
<run_id>_hyd_curve
<run_id>_profile_metrics
<run_id>_cand_pts
<run_id>_cand_lines
<run_id>_cand_tbl
<run_id>_selected_pts
<run_id>_selected_lines
<run_id>_selected_tbl
<run_id>_qa_flags
<run_id>_left_bank
<run_id>_right_bank
<run_id>_polygon_raw
<run_id>_polygon_smooth
<run_id>_run_params
<run_id>_correction_log
```

Example run IDs:

```text
bf01
bf02
test01
reach01
```

The default run ID should be short, for example `bf01`.

### 3.5 Tool help and parameter descriptions are missing or insufficient

When the user clicks a parameter in the ArcGIS Pro tool interface, they should understand what to provide. Currently the tools do not provide enough detailed help.

Required fix:

Add clear descriptions for every tool and every parameter.

Each parameter should explain:

1. What the input is.
2. Which previous tool creates it, if it is an intermediate dataset.
3. Whether the user normally needs to select it manually.
4. Expected geometry or data type.
5. Important assumptions.
6. Recommended default value.
7. Common mistakes.

For example:

Parameter:

```text
DEM profile table
```

Description:

```text
Table containing sampled elevation values along each cross section. This is normally created automatically by Tool 02. Only choose this manually if you are rerunning the hydraulic metrics step from an existing project.
```

Parameter:

```text
Hydraulic breakpoint sensitivity
```

Description:

```text
Controls how strong the hydraulic curve break must be before the tool treats it as a reliable bankfull candidate. Higher values are more conservative. Start with 1.0 and adjust after reviewing candidate lines and QA flags.
```

### 3.6 Too many outputs are exposed as normal required outputs

Some outputs should be standard automatic outputs, not something the user must name every time.

Required redesign:

Main tools should ask for:

```text
Project folder
Output geodatabase name
Run name
```

Then outputs should be generated automatically.

Advanced mode can allow custom output names, but default mode should not require this.

### 3.7 There is no clear basic mode versus advanced mode

New users need a simple mode.

Expert users may still want to rerun one step with custom inputs.

Required redesign:

Add two usage levels:

1. Basic mode.
2. Advanced or debug mode.

Basic mode:

1. Minimal required inputs.
2. Automatic output names.
3. Standard workflow.
4. Clear defaults.

Advanced mode:

1. Allows rerunning individual stages.
2. Allows manual input of intermediate tables.
3. Allows writing full debug outputs.
4. Allows parameter tuning.

### 3.8 Reach ID handling is confusing

The current workflow has optional reach ID input, but the first tool can dissolve the stream. If streams are dissolved, the reach ID field may disappear or become meaningless.

Required redesign:

Add clear reach handling choices:

```text
Reach handling mode:
1. Treat all input streams as one reach.
2. Preserve input features as separate reaches.
3. Use a selected reach ID field.
```

If the user chooses one reach, create `reach_id = 1`.

If the user chooses preserve features, create a stable reach ID from source feature IDs.

If the user chooses a reach field, copy that field into the prepared stream and all later outputs.

Do not ask for reach ID again in later tools.

## 4. Required New Toolbox Design

### 4.1 Main tool: Run Full Bankfull Workflow

This should be the main tool most users run first.

Inputs:

1. Input stream centreline.
2. Input LiDAR DEM.
3. Project folder.
4. Output geodatabase name.
5. Run name.
6. Reach handling mode.
7. Optional reach ID field.
8. Station interval.
9. Cross section half width.
10. DEM sample spacing.
11. Thalweg search distance.
12. Maximum bankfull search height above thalweg.
13. Water level step.
14. Slope threshold.
15. Hydraulic breakpoint sensitivity.
16. Output detail level.
17. Create QA report.
18. Optional DEM clip buffer.

Outputs should be automatically named.

Output detail level should include:

```text
Summary outputs only
QA outputs
Full debug outputs
```

Summary outputs only:

1. Selected bankfull width lines.
2. Bankfull polygon.
3. QA flags.
4. QA summary report.
5. Run parameters.

QA outputs:

1. Everything in summary outputs.
2. Station points.
3. Cross sections.
4. Thalweg points.
5. Candidate points and lines.

Full debug outputs:

1. Everything in QA outputs.
2. Full profile points.
3. Full profile table.
4. Full hydraulic curve table.
5. Full candidate table.
6. Correction logs.

### 4.2 Stage tool: Setup Bankfull Project

Purpose:

Prepare the project geodatabase and standard naming structure.

Inputs:

1. Input stream centreline.
2. Input LiDAR DEM.
3. Project folder.
4. Output geodatabase name.
5. Run name.
6. Reach handling mode.
7. Optional reach ID field.
8. Optional DEM clip buffer.
9. Check projection.

Outputs:

Automatically named prepared stream, boundary, optional clipped DEM and run parameter table.

### 4.3 Stage tool: Create Cross Sections And DEM Profiles

Purpose:

Generate station points, cross section lines and DEM sampled profile data.

Inputs:

1. Project geodatabase.
2. Run name.
3. Station interval.
4. Cross section half width.
5. Tangent calculation distance.
6. DEM sample spacing.
7. Optional slope raster.
8. Create slope raster if missing.
9. Output detail level.

Outputs:

Automatically named station points, cross sections, profile points and profile table.

### 4.4 Stage tool: Calculate Hydraulic Metrics

Purpose:

Detect thalweg and calculate top width, cross sectional flow area and hydraulic depth.

Inputs:

1. Project geodatabase.
2. Run name.
3. Thalweg search distance.
4. Maximum water level above thalweg.
5. Water level step.
6. Minimum valid top width.
7. Output detail level.

Outputs:

Automatically named thalweg points, hydraulic curve table and profile metrics table.

### 4.5 Stage tool: Detect And Select Bankfull

Purpose:

Generate slope and hydraulic candidates, compare them, apply continuity checks and select one result per cross section.

Inputs:

1. Project geodatabase.
2. Run name.
3. Slope threshold.
4. Hydraulic breakpoint sensitivity.
5. Maximum bankfull height above thalweg.
6. Minimum bank distance from thalweg.
7. Maximum bank distance from thalweg.
8. Minimum bank height above thalweg.
9. Width jump threshold.
10. Elevation jump threshold.
11. Moving window size.

Outputs:

Automatically named candidate outputs, selected outputs and QA flags.

### 4.6 Stage tool: Create Bankfull Outputs And QA Report

Purpose:

Create final bank lines, polygon, optional smoothing and report.

Inputs:

1. Project geodatabase.
2. Run name.
3. Create raw polygon.
4. Smoothing method.
5. Smoothing window.
6. Preserve low confidence points.
7. Output report folder.

Outputs:

Automatically named left bank line, right bank line, raw polygon, optional smoothed polygon, QA report files.

## 5. Parameter Naming Standard

Use display names that are clear to a GIS user.

Avoid internal variable names in the visible UI.

Recommended visible names:

```text
Input stream centreline
Input LiDAR DEM
Project folder
Output geodatabase name
Run name
Reach handling mode
Reach ID field
Station interval
Cross section half width
Tangent calculation distance
DEM sample spacing
Optional slope raster
Create slope raster if missing
Thalweg search distance
Maximum bankfull search height
Water level step
Minimum valid top width
Slope threshold
Hydraulic breakpoint sensitivity
Maximum bankfull height above thalweg
Minimum bank distance from thalweg
Maximum bank distance from thalweg
Minimum bank height above thalweg
Width jump threshold
Bankfull level jump threshold
Moving window size
Output detail level
Create QA report
Output report folder
```

Avoid visible names like:

```text
prepared_stream
profile_table
hydraulic_curve
candidate_table
selected_table
output_candidate_lines
output_profile_metrics
```

These can remain internal variable names, but not user facing display names.

## 6. Output Dataset Naming Standard

Implement a central naming function.

Example:

```python
def make_output_name(run_id, suffix):
    safe_run_id = clean_name(run_id)
    return f"{safe_run_id}_{suffix}"
```

Use this central list of suffixes:

```text
stream
boundary
dem_clip
stations
xsecs
profile_pts
profile_tbl
thalweg
hyd_curve
profile_metrics
cand_pts
cand_lines
cand_tbl
selected_pts
selected_lines
selected_tbl
qa_flags
left_bank
right_bank
polygon_raw
polygon_smooth
run_params
correction_log
```

The tool should create these names automatically in the project geodatabase.

## 7. Tool Help Requirements

Every tool must include a clear description.

Every parameter must include a clear user facing explanation.

For ArcGIS Python Toolbox implementation, use available parameter properties and tool documentation patterns. If ArcGIS Pro does not display long help directly from `.pyt`, include a generated help Markdown file and short parameter descriptions in the toolbox.

Minimum help text for each parameter should answer:

1. What is this input?
2. Where does it come from?
3. What format is expected?
4. What is the recommended value?
5. What happens if I leave it blank?
6. What common mistake should I avoid?

Add a `docs/tool_help.md` file with a complete explanation of all tools and parameters.

## 8. Algorithm And Reliability Fixes

After the toolbox interface is redesigned, fix these algorithm issues.

### 8.1 Spatial reference handling

Do not use `arcpy.env.outputCoordinateSystem` as the only source of spatial reference for generated feature classes.

Use spatial reference from a real input feature class, usually prepared stream, cross sections or profile points.

Tool 05 must not create thalweg points with unknown coordinate system.

### 8.2 Profile sampling point count

Use `math.ceil`, not `round`, when calculating how many profile sample points are required.

Recommended code:

```python
import math
steps = max(1, int(math.ceil(geom.length / sample_spacing_m)))
```

### 8.3 Edge wetting flags

Add hydraulic flags when the wetted region touches either end of the cross section.

Required flags:

```text
left_edge_wet
right_edge_wet
section_too_short
water_reaches_profile_edge
```

If a candidate is created from a water level that touches the profile edge, lower confidence and require manual review.

### 8.4 Candidate selection after continuity scoring

Do not select the best candidate first and only then apply continuity penalties.

Correct logic:

1. Score every candidate.
2. Apply continuity penalties to every candidate.
3. Apply QA penalties to every candidate.
4. Select the candidate with the best final score.

### 8.5 Slope candidate plausibility constraints

Add parameters:

```text
min_bank_distance_from_thalweg_m
max_bank_distance_from_thalweg_m
min_bank_height_above_thalweg_m
profile_slope_window_m
```

Slope peaks should not be accepted as bank candidates if they are too close to the thalweg, too far from the thalweg, too low above the thalweg, or likely caused by local noise.

### 8.6 Hydraulic breakpoint scoring

Improve scoring so it uses:

1. Top width rate.
2. Cross sectional flow area rate.
3. Hydraulic depth rate change.
4. Candidate height above thalweg.
5. Candidate width reasonableness.
6. Edge wetting status.
7. Agreement with slope evidence.

Write these metrics into the candidate table so the user can understand why a candidate was selected.

### 8.7 Polygon geometry QA

Add geometry QA for:

1. Self intersections.
2. Multipart polygons.
3. Zero area polygons.
4. Left and right bank crossing.
5. Width line crossing.
6. Side flips.
7. Spikes.
8. Polygon far away from stream centreline.

Use ArcPy geometry checks where practical.

### 8.8 Parameter logging

Record parameters from every stage, not only Tool 01.

Create or update a `run_params` table.

Record:

1. Tool name.
2. Run name.
3. Parameter name.
4. Parameter value.
5. Input path.
6. Output path.
7. Date and time.
8. Toolbox version.

### 8.9 Repository licence

Add a `LICENSE` file, or clearly state that the repository is not yet licensed for reuse.

Keep the third party notice for the Cross Sections and Dimensions Tool.

### 8.10 README validation note

Add this wording:

```text
This toolbox has not yet been validated against surveyed bankfull indicators or field verified channel boundaries. Outputs should be treated as candidate bankfull extents until reviewed by a geomorphologist or experienced hydraulic or GIS analyst.
```

## 9. Performance And Long Reach Readiness

The current tool is likely acceptable for short reaches but not yet suitable for long reaches.

The main cost is:

```text
number of cross sections × number of profile points per cross section × number of simulated water levels
```

Example:

```text
20 km reach
10 m station interval
about 2000 cross sections
about 101 profile points per cross section
about 51 water levels
about 10,302,000 profile hydraulic checks
```

This does not include raster sampling, geodatabase writing, feature class creation, polygon construction or QA checks.

Why long reaches are difficult:

1. Intermediate outputs become very large.
2. DEM and slope sampling becomes expensive.
3. One parameter set may not suit the whole reach.
4. Long meandering reaches are more likely to create polygon geometry problems.
5. Manual QA becomes difficult when thousands of cross sections are created.

Long reach improvements:

1. Process by reach or tile.
2. Add batch processing mode.
3. Allow different parameters by reach.
4. Add output detail levels.
5. Write only summary outputs unless full debug mode is selected.
6. Use NumPy based raster sampling where practical.
7. Stop hydraulic simulation when water reaches profile edges.
8. Use adaptive water level steps.
9. Add progress and timing logs.
10. Create and validate polygons by reach segment before merging.

## 10. Required Acceptance Criteria For The Next Version

The next version should satisfy these criteria before further algorithm expansion.

### 10.1 Basic usability

A new user should be able to run the full workflow using one main tool with only essential inputs.

Essential inputs:

1. Stream centreline.
2. LiDAR DEM.
3. Project folder.
4. Output geodatabase name.
5. Run name.
6. Main parameters.

The user should not need to manually select every intermediate output.

### 10.2 Clear input descriptions

Every visible input must have a clear display name and description.

The user should understand what to input without reading the source code.

### 10.3 Short automatic output names

All default outputs must use short, consistent names based on run ID.

### 10.4 Repeatable workflow

The tool must record parameters and output paths in a run parameter table.

### 10.5 QA friendly outputs

The user should still be able to inspect:

1. Cross sections.
2. Profile points, if QA or debug mode is enabled.
3. Thalweg points.
4. Candidate bank points.
5. Selected bankfull lines.
6. QA flags.
7. Final polygon.

### 10.6 Advanced rerun support

Advanced users should be able to rerun individual stages, but this should not make the basic workflow confusing.

### 10.7 Algorithm safety

Fix spatial reference handling, edge wetting flags, candidate scoring order and polygon QA before calling the tool production ready.

## 11. Development Priority

### Priority 1

Redesign the ArcGIS Pro toolbox user interface.

1. Add `Run Full Bankfull Workflow`.
2. Reduce main visible tools.
3. Add project geodatabase plus run name based workflow.
4. Add automatic output naming.
5. Add clear input descriptions.
6. Add basic mode and advanced mode.
7. Add complete tool help.

### Priority 2

Fix correctness issues.

1. Spatial reference handling.
2. Sampling point count.
3. Edge wetting flags.
4. Candidate selection scoring order.
5. Slope candidate constraints.
6. Polygon geometry QA.
7. Parameter logging.
8. Licence and validation notes.

### Priority 3

Improve performance and long reach readiness.

1. Reach segmentation.
2. Batch processing.
3. Output detail levels.
4. Runtime logging.
5. NumPy sampling and vectorised calculations.
6. Adaptive water level simulation.

## 12. Important Design Principle

Do not expose internal implementation complexity to the user unless they explicitly choose advanced mode.

The toolbox should feel like a practical ArcGIS Pro hydrology and geomorphology tool.

The user should not need to understand every intermediate table before they can run the workflow.

Intermediate outputs are important for QA, but they should be automatically created, clearly named and clearly documented.
