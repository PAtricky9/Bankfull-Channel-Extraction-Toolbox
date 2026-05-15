# Bankfull Channel Extractor Tool Help

## Run Full Bankfull Workflow
Runs Setup, Cross Sections/Profile Sampling, Hydraulic Metrics, Candidate Detection/Selection, and final output generation in one click.

### Core inputs
- **Input stream centreline**: Polyline stream centreline for the study reach.
- **Input LiDAR DEM**: Elevation raster used for profile sampling.
- **Project folder**: Folder where the project geodatabase is created.
- **Output geodatabase name**: Name of the file geodatabase; defaults to `bankfull_outputs.gdb`.
- **Run name**: Short run ID used to auto-name outputs (example `bf01`).
- **Reach handling mode**: Choose single reach, preserve features, or use selected reach field.
- **Reach ID field**: Optional source field when using reach field mode.

### Workflow parameters
- **Station interval**: Distance between cross sections.
- **Cross section half width**: Half width for generated cross sections.
- **DEM sample spacing**: Profile point spacing along each cross section.
- **Thalweg search distance**: Centerline search window for thalweg.
- **Maximum bankfull search height**: Hydraulic simulation cap above thalweg.
- **Water level step**: Increment for hydraulic simulation.
- **Slope threshold**: Candidate slope peak threshold.
- **Hydraulic breakpoint sensitivity**: Controls hydraulic breakpoint conservatism.
- **Output detail level / QA report options**: Use report output to include CSV/Markdown QA outputs.

## Stage tools
- **01 Setup Bankfull Project**: Creates run-scoped stream/boundary/DEM clip + run parameter table.
- **02 Create Cross Sections And DEM Profiles**: Auto-loads run inputs and creates stations/xsecs/profile outputs.
- **03 Calculate Hydraulic Metrics**: Creates thalweg, hydraulic curve, and profile metrics outputs.
- **04 Detect And Select Bankfull**: Creates candidate outputs and selected outputs with continuity QA.
- **05 Create Bankfull Outputs And QA Report**: Builds banks/polygons and optional report outputs.
