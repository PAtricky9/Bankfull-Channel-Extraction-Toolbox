# -*- coding: utf-8 -*-
"""ArcGIS Pro Python toolbox for bankfull channel extraction."""

from __future__ import annotations

import os
import sys

TOOLBOX_DIR = os.path.dirname(__file__)
if TOOLBOX_DIR not in sys.path:
    sys.path.insert(0, TOOLBOX_DIR)

try:
    import arcpy  # type: ignore
except Exception:  # pragma: no cover - ArcPy is available inside ArcGIS Pro.
    arcpy = None

from bankfull_core.candidate_detection import detect_bankfull_candidates
from bankfull_core.continuity_check import select_best_candidates
from bankfull_core.geometry_utils import generate_cross_sections, generate_station_points
from bankfull_core.hydraulic_metrics import detect_thalweg_and_hydraulic_metrics
from bankfull_core.io_utils import prepare_inputs, read_run_param, resolve_run_output_path
from bankfull_core.polygon_creation import create_bankfull_polygon
from bankfull_core.profile_sampling import sample_dem_profiles
from bankfull_core.qa_report import generate_qa_report
from bankfull_core.smoothing import smooth_bank_lines


def _require_arcpy():
    if arcpy is None:
        raise RuntimeError("This toolbox must be run inside ArcGIS Pro with ArcPy.")


def _bool(parameter) -> bool:
    value = parameter.value
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def _float_or_none(parameter):
    text = parameter.valueAsText
    if text in (None, ""):
        return None
    return float(text)


def _text_or_none(parameter):
    text = parameter.valueAsText
    return None if text in (None, "") else text


def _resolve_output(path: str, fallback_workspace: str | None = None) -> str:
    if os.path.dirname(path):
        return path
    workspace = fallback_workspace or arcpy.env.workspace
    if not workspace:
        raise ValueError(f"Output {path} needs a workspace path.")
    return os.path.join(workspace, path)


def _workspace_of(dataset: str) -> str:
    desc = arcpy.Describe(dataset)
    return desc.path


def _run_output(workspace: str, run_name: str, suffix: str) -> str:
    return resolve_run_output_path(workspace, run_name, suffix)


def _require_run_output(workspace: str, run_name: str, suffix: str, label: str, previous_tool: str) -> str:
    path = _run_output(workspace, run_name, suffix)
    if not arcpy.Exists(path):
        raise ValueError(f"{label} was not found: {path}. Run {previous_tool} first.")
    return path


def _resolve_dem_for_run(workspace: str, run_name: str) -> str:
    clipped_dem = _run_output(workspace, run_name, "dem_clip")
    if arcpy.Exists(clipped_dem):
        return clipped_dem

    dem = read_run_param(workspace, run_name, "dem_for_processing")
    if dem and arcpy.Exists(dem):
        return dem

    dem = read_run_param(workspace, run_name, "dem_raster")
    if dem and arcpy.Exists(dem):
        return dem

    raise ValueError(
        "No DEM was found for this run. Run 01 Prepare Inputs first."
    )


def _validate_run_name(parameter) -> None:
    text = parameter.valueAsText
    if text in (None, ""):
        parameter.setErrorMessage("Run name is required.")
    elif len(text) > 20:
        parameter.setWarningMessage(
            "Short run names are recommended because they are used in output names."
        )


def _validate_positive_number(parameter, label: str) -> None:
    text = parameter.valueAsText
    if text in (None, ""):
        return
    try:
        value = float(text)
    except (TypeError, ValueError):
        parameter.setErrorMessage(f"{label} must be a number greater than zero.")
        return
    if value <= 0:
        parameter.setErrorMessage(f"{label} must be greater than zero.")


def _validate_project_gdb(parameter) -> bool:
    text = parameter.valueAsText
    if text in (None, ""):
        parameter.setErrorMessage("Project geodatabase is required.")
        return False
    if not arcpy.Exists(text):
        parameter.setErrorMessage(f"Project geodatabase does not exist: {text}")
        return False
    return True


def _validate_standard_output(parameters, workspace_index: int, run_index: int, suffix: str, label: str, previous_tool: str) -> None:
    workspace = parameters[workspace_index].valueAsText
    run_name = parameters[run_index].valueAsText
    if workspace in (None, "") or run_name in (None, "") or not arcpy.Exists(workspace):
        return
    path = _run_output(workspace, run_name, suffix)
    if not arcpy.Exists(path):
        parameters[workspace_index].setErrorMessage(
            f"{label} was not found: {path}. Run {previous_tool} first."
        )


def _validate_dem_for_run(parameters, workspace_index: int, run_index: int) -> None:
    workspace = parameters[workspace_index].valueAsText
    run_name = parameters[run_index].valueAsText
    if workspace in (None, "") or run_name in (None, "") or not arcpy.Exists(workspace):
        return
    clipped_dem = _run_output(workspace, run_name, "dem_clip")
    if arcpy.Exists(clipped_dem):
        return
    for key in ("dem_for_processing", "dem_raster"):
        dem = read_run_param(workspace, run_name, key)
        if dem and arcpy.Exists(dem):
            return
    parameters[workspace_index].setErrorMessage(
        "No DEM was found for this run. Run 01 Prepare Inputs first."
    )


def _validate_required_text(parameter, label: str) -> None:
    if parameter.valueAsText in (None, ""):
        parameter.setErrorMessage(f"{label} is required.")


def _parameter(
    name,
    display_name,
    datatype,
    direction="Input",
    parameter_type="Required",
    default=None,
):
    param = arcpy.Parameter(
        name=name,
        displayName=display_name,
        datatype=datatype,
        direction=direction,
        parameterType=parameter_type,
    )
    if default is not None:
        param.value = default
    return param


class Toolbox(object):
    def __init__(self):
        self.label = "Bankfull Channel Extractor"
        self.alias = "bankfull_channel"
        self.tools = [
            RunFullBankfullWorkflow,
            PrepareInputs,
            GenerateStationPoints,
            GenerateCrossSections,
            SampleDEMProfiles,
            DetectThalwegAndHydraulicMetrics,
            BankfullCandidateDetection,
            SelectBestCandidateAndContinuityCheck,
            CreateBankfullPolygon,
            SmoothBankLines,
            GenerateQAReport,
        ]


class RunFullBankfullWorkflow(object):
    def __init__(self):
        self.label = "Run Full Bankfull Workflow"
        self.description = (
            "Run the full bankfull extraction workflow from stream centreline "
            "and DEM using standard run-based output names. This is the main "
            "entry point for basic users. Outputs are candidate bankfull "
            "extents and require QA review."
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("input_stream", "Input stream centreline", "DEFeatureClass"),
            _parameter("input_dem", "Input LiDAR DEM", "DERasterDataset"),
            _parameter("project_folder", "Project folder", "DEFolder"),
            _parameter("output_gdb_name", "Output geodatabase name", "GPString", default="bankfull_outputs.gdb"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("reach_mode", "Reach handling mode", "GPString", default="Treat all input streams as one reach"),
            _parameter("reach_id_field", "Reach ID field", "Field", parameter_type="Optional"),
            _parameter("dem_clip_buffer", "Optional DEM clip buffer", "GPString", parameter_type="Optional"),
            _parameter("check_projection", "Check projection compatibility", "GPBoolean", default=True),
            _parameter("station_interval_m", "Station interval", "GPDouble", default=10.0),
            _parameter("cross_section_half_width_m", "Cross section half width", "GPDouble", default=50.0),
            _parameter("tangent_distance_m", "Tangent calculation distance", "GPDouble", default=20.0),
            _parameter("dem_sample_spacing_m", "DEM sample spacing", "GPDouble", default=1.0),
            _parameter("slope_raster", "Optional slope raster", "DERasterDataset", parameter_type="Optional"),
            _parameter("create_slope_raster", "Create slope raster if missing", "GPBoolean", default=True),
            _parameter("thalweg_search_distance_m", "Thalweg search distance", "GPDouble", default=10.0),
            _parameter("max_water_height_m", "Maximum water level above thalweg", "GPDouble", default=5.0),
            _parameter("water_level_step_m", "Water level step", "GPDouble", default=0.1),
            _parameter("min_top_width_m", "Minimum valid top width", "GPDouble", default=0.5),
            _parameter("slope_threshold_deg", "Slope threshold", "GPDouble", default=15.0),
            _parameter("hydraulic_breakpoint_sensitivity", "Hydraulic breakpoint sensitivity", "GPDouble", default=1.0),
            _parameter("max_bankfull_height_m", "Optional maximum bankfull height above thalweg", "GPDouble", parameter_type="Optional"),
            _parameter("width_jump_threshold", "Width jump threshold ratio", "GPDouble", default=0.75),
            _parameter("bankfull_level_jump_threshold_m", "Bankfull level jump threshold", "GPDouble", default=1.0),
            _parameter("moving_window_size", "Moving window size", "GPLong", default=5),
            _parameter("smoothing_method", "Smoothing method", "GPString", default="none"),
            _parameter("smoothing_window_size", "Smoothing window", "GPLong", default=5),
            _parameter("preserve_low_confidence_points", "Preserve low confidence points", "GPBoolean", default=True),
            _parameter("create_qa_report", "Create QA report", "GPBoolean", default=True),
            _parameter("output_report_folder", "Output report folder", "DEFolder", parameter_type="Optional"),
        ]
        params[5].filter.type = "ValueList"
        params[5].filter.list = [
            "Treat all input streams as one reach",
            "Preserve input features as separate reaches",
            "Use a selected reach ID field",
        ]
        params[6].parameterDependencies = [params[0].name]
        params[25].filter.type = "ValueList"
        params[25].filter.list = ["none", "rolling_median"]
        return params

    def updateMessages(self, parameters):
        reach_mode = parameters[5].valueAsText
        if reach_mode == "Use a selected reach ID field" and not parameters[6].valueAsText:
            parameters[6].setErrorMessage(
                "Select a Reach ID field, or choose a different reach handling mode."
            )
        _validate_run_name(parameters[4])
        _validate_positive_number(parameters[9], "Station interval")
        _validate_positive_number(parameters[10], "Cross section half width")
        _validate_positive_number(parameters[11], "Tangent calculation distance")
        _validate_positive_number(parameters[12], "DEM sample spacing")
        _validate_positive_number(parameters[15], "Thalweg search distance")
        _validate_positive_number(parameters[16], "Maximum water level above thalweg")
        _validate_positive_number(parameters[17], "Water level step")
        _validate_positive_number(parameters[18], "Minimum valid top width")
        _validate_positive_number(parameters[19], "Slope threshold")
        _validate_positive_number(parameters[20], "Hydraulic breakpoint sensitivity")
        _validate_positive_number(parameters[21], "Maximum bankfull height above thalweg")
        _validate_positive_number(parameters[22], "Width jump threshold")
        _validate_positive_number(parameters[23], "Bankfull level jump threshold")
        _validate_positive_number(parameters[24], "Moving window size")
        _validate_positive_number(parameters[26], "Smoothing window")
        if _bool(parameters[28]) and not parameters[29].valueAsText:
            parameters[29].setErrorMessage(
                "Output report folder is required when Create QA report is enabled."
            )

    def execute(self, parameters, messages):
        _require_arcpy()
        input_stream = parameters[0].valueAsText
        input_dem = parameters[1].valueAsText
        project_folder = parameters[2].valueAsText
        output_gdb_name = parameters[3].valueAsText
        run_name = parameters[4].valueAsText
        reach_mode = parameters[5].valueAsText
        reach_id_field = parameters[6].valueAsText
        dem_clip_buffer = _text_or_none(parameters[7])
        check_projection = _bool(parameters[8])
        station_interval_m = float(parameters[9].value)
        cross_section_half_width_m = float(parameters[10].value)
        tangent_distance_m = float(parameters[11].value)
        dem_sample_spacing_m = float(parameters[12].value)
        slope_raster = _text_or_none(parameters[13])
        create_slope_raster = _bool(parameters[14])
        thalweg_search_distance_m = float(parameters[15].value)
        max_water_height_m = float(parameters[16].value)
        water_level_step_m = float(parameters[17].value)
        min_top_width_m = float(parameters[18].value)
        slope_threshold_deg = float(parameters[19].value)
        hydraulic_breakpoint_sensitivity = float(parameters[20].value)
        max_bankfull_height_m = _float_or_none(parameters[21])
        width_jump_threshold = float(parameters[22].value)
        bankfull_level_jump_threshold_m = float(parameters[23].value)
        moving_window_size = int(parameters[24].value)
        smoothing_method = parameters[25].valueAsText or "none"
        smoothing_window_size = int(parameters[26].value)
        preserve_low_confidence_points = _bool(parameters[27])
        create_qa_report = _bool(parameters[28])
        output_report_folder = parameters[29].valueAsText

        if reach_mode == "Treat all input streams as one reach":
            dissolve_stream = True
            station_reach_id_field = None
        elif reach_mode == "Use a selected reach ID field":
            dissolve_stream = False
            station_reach_id_field = reach_id_field
        else:
            dissolve_stream = False
            station_reach_id_field = None

        setup_outputs = prepare_inputs(
            input_stream,
            input_dem,
            project_folder,
            output_gdb_name,
            run_name,
            dem_clip_buffer,
            dissolve_stream,
            check_projection,
        )
        output_gdb = setup_outputs["output_gdb"]
        prepared_stream = setup_outputs["prepared_stream"]
        dem_for_processing = _resolve_dem_for_run(output_gdb, run_name)
        run_params = setup_outputs["project_config"]

        station_points = _run_output(output_gdb, run_name, "stations")
        cross_sections = _run_output(output_gdb, run_name, "xsecs")
        profile_points = _run_output(output_gdb, run_name, "profile_pts")
        profile_table = _run_output(output_gdb, run_name, "profile_tbl")
        thalweg_points = _run_output(output_gdb, run_name, "thalweg")
        hydraulic_curve_table = _run_output(output_gdb, run_name, "hyd_curve")
        profile_metrics_table = _run_output(output_gdb, run_name, "profile_metrics")
        candidate_points = _run_output(output_gdb, run_name, "cand_pts")
        candidate_lines = _run_output(output_gdb, run_name, "cand_lines")
        candidate_table = _run_output(output_gdb, run_name, "cand_tbl")
        selected_points = _run_output(output_gdb, run_name, "selected_pts")
        selected_lines = _run_output(output_gdb, run_name, "selected_lines")
        selected_table = _run_output(output_gdb, run_name, "selected_tbl")
        qa_flags = _run_output(output_gdb, run_name, "qa_flags")
        left_bank = _run_output(output_gdb, run_name, "left_bank")
        right_bank = _run_output(output_gdb, run_name, "right_bank")
        polygon_raw = _run_output(output_gdb, run_name, "polygon_raw")
        smoothed_points = _run_output(output_gdb, run_name, "smoothed_pts")
        polygon_smooth = _run_output(output_gdb, run_name, "polygon_smooth")
        correction_log = _run_output(output_gdb, run_name, "correction_log")

        generate_station_points(
            prepared_stream,
            station_interval_m,
            station_reach_id_field,
            station_points,
        )
        generate_cross_sections(
            station_points,
            prepared_stream,
            cross_section_half_width_m,
            "fast_perpendicular",
            tangent_distance_m,
            cross_sections,
        )
        sample_dem_profiles(
            cross_sections,
            dem_for_processing,
            dem_sample_spacing_m,
            slope_raster,
            create_slope_raster,
            profile_points,
            profile_table,
        )
        detect_thalweg_and_hydraulic_metrics(
            profile_table,
            thalweg_search_distance_m,
            max_water_height_m,
            water_level_step_m,
            min_top_width_m,
            thalweg_points,
            hydraulic_curve_table,
            profile_metrics_table,
            spatial_ref_source=cross_sections,
        )
        detect_bankfull_candidates(
            profile_table,
            hydraulic_curve_table,
            thalweg_points,
            slope_threshold_deg,
            hydraulic_breakpoint_sensitivity,
            max_bankfull_height_m,
            candidate_points,
            candidate_lines,
            candidate_table,
        )
        select_best_candidates(
            candidate_table,
            candidate_points,
            candidate_lines,
            width_jump_threshold,
            bankfull_level_jump_threshold_m,
            moving_window_size,
            selected_points,
            selected_lines,
            selected_table,
            qa_flags,
        )
        create_bankfull_polygon(
            selected_points,
            selected_lines,
            prepared_stream,
            selected_table,
            polygon_raw,
            left_bank,
            right_bank,
        )
        if smoothing_method.lower() not in {"", "none"}:
            smooth_bank_lines(
                selected_points,
                selected_table,
                smoothing_method,
                smoothing_window_size,
                preserve_low_confidence_points,
                smoothed_points,
                polygon_smooth,
                correction_log,
            )
        if create_qa_report:
            if not output_report_folder:
                raise ValueError(
                    "Output report folder is required when Create QA report is enabled."
                )
            generate_qa_report(
                selected_table,
                qa_flags,
                candidate_table,
                run_params,
                output_report_folder,
            )


class PrepareInputs(object):
    def __init__(self):
        self.label = "01 Prepare Inputs"
        self.description = "Prepare the input stream centreline, LiDAR DEM, processing boundary, and project configuration table."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("stream_centerline", "Input stream centreline", "DEFeatureClass"),
            _parameter("dem_raster", "Input LiDAR DEM", "DERasterDataset"),
            _parameter("project_folder", "Project folder", "DEFolder"),
            _parameter("output_gdb_name", "Output geodatabase name", "GPString", default="bankfull_outputs.gdb"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("dem_clip_buffer", "Optional DEM clip buffer distance", "GPString", parameter_type="Optional"),
            _parameter("dissolve_stream", "Dissolve stream centreline into one reach", "GPBoolean", default=True),
            _parameter("check_projection", "Check projection compatibility", "GPBoolean", default=True),
            _parameter("prepared_stream", "Output prepared stream centreline", "DEFeatureClass", "Output", "Derived"),
            _parameter("clipped_dem", "Clipped DEM", "DERasterDataset", "Output", "Derived"),
            _parameter("processing_boundary", "Processing boundary", "DEFeatureClass", "Output", "Derived"),
            _parameter("project_config", "Run parameter table", "DETable", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        _validate_run_name(parameters[4])

    def execute(self, parameters, messages):
        _require_arcpy()
        outputs = prepare_inputs(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            _text_or_none(parameters[5]),
            _bool(parameters[6]),
            _bool(parameters[7]),
        )
        parameters[8].value = outputs["prepared_stream"]
        parameters[9].value = outputs["clipped_dem"]
        parameters[10].value = outputs["processing_boundary"]
        parameters[11].value = outputs["project_config"]


class GenerateStationPoints(object):
    def __init__(self):
        self.label = "02 Generate Station Points"
        self.description = "Create evenly spaced cross-section station points along the prepared stream centreline."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("station_interval_m", "Station interval", "GPDouble", default=10.0),
            _parameter("output_station_points", "Output station points", "DEFeatureClass", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "stream", "Prepared stream centreline", "01 Prepare Inputs")
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[2], "Station interval")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        prepared_stream = _require_run_output(
            workspace, run_name, "stream", "Prepared stream centreline", "01 Prepare Inputs"
        )
        output_fc = _run_output(workspace, run_name, "stations")
        generate_station_points(
            prepared_stream,
            float(parameters[2].value),
            None,
            output_fc,
        )
        parameters[3].value = output_fc


class GenerateCrossSections(object):
    def __init__(self):
        self.label = "03 Generate Cross Sections"
        self.description = "Create perpendicular cross-section lines from station points and local stream direction."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("half_width_m", "Cross-section half width", "GPDouble", default=50.0),
            _parameter("tangent_distance_m", "Tangent calculation distance", "GPDouble", default=20.0),
            _parameter("output_cross_sections", "Output cross sections", "DEFeatureClass", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "stream", "Prepared stream centreline", "01 Prepare Inputs")
            _validate_standard_output(parameters, 0, 1, "stations", "Station points", "02 Generate Station Points")
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[2], "Cross-section half width")
        _validate_positive_number(parameters[3], "Tangent calculation distance")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        prepared_stream = _require_run_output(
            workspace, run_name, "stream", "Prepared stream centreline", "01 Prepare Inputs"
        )
        station_points = _require_run_output(
            workspace, run_name, "stations", "Station points", "02 Generate Station Points"
        )
        output_fc = _run_output(workspace, run_name, "xsecs")
        generate_cross_sections(
            station_points,
            prepared_stream,
            float(parameters[2].value),
            "fast_perpendicular",
            float(parameters[3].value),
            output_fc,
        )
        parameters[4].value = output_fc


class SampleDEMProfiles(object):
    def __init__(self):
        self.label = "04 Sample DEM Profiles"
        self.description = "Densify each cross section and sample LiDAR DEM elevation and optional slope."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("sample_spacing_m", "DEM sample spacing", "GPDouble", default=1.0),
            _parameter("slope_raster", "Optional slope raster", "DERasterDataset", parameter_type="Optional"),
            _parameter("create_slope", "Create slope raster if missing", "GPBoolean", default=True),
            _parameter("output_profile_points", "Output profile points", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_profile_table", "Output profile table", "DETable", "Output", "Derived"),
            _parameter("created_slope_raster", "Created or supplied slope raster", "DERasterDataset", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "xsecs", "Cross-section lines", "03 Generate Cross Sections")
            _validate_dem_for_run(parameters, 0, 1)
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[2], "DEM sample spacing")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        cross_sections = _require_run_output(
            workspace, run_name, "xsecs", "Cross-section lines", "03 Generate Cross Sections"
        )
        dem_raster = _resolve_dem_for_run(workspace, run_name)
        output_points = _run_output(workspace, run_name, "profile_pts")
        output_table = _run_output(workspace, run_name, "profile_tbl")
        outputs = sample_dem_profiles(
            cross_sections,
            dem_raster,
            float(parameters[2].value),
            _text_or_none(parameters[3]),
            _bool(parameters[4]),
            output_points,
            output_table,
        )
        parameters[5].value = outputs["profile_points"]
        parameters[6].value = outputs["profile_table"]
        parameters[7].value = outputs["slope_raster"]


class DetectThalwegAndHydraulicMetrics(object):
    def __init__(self):
        self.label = "05 Detect Thalweg And Hydraulic Metrics"
        self.description = "Detect thalweg points and compute cross-section hydraulic curve metrics."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("centre_search_m", "Thalweg search distance", "GPDouble", default=10.0),
            _parameter("max_water_height_m", "Maximum water level above thalweg", "GPDouble", default=5.0),
            _parameter("water_level_step_m", "Water level step", "GPDouble", default=0.1),
            _parameter("min_top_width_m", "Minimum valid top width", "GPDouble", default=0.5),
            _parameter("output_thalweg_points", "Output thalweg points", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_hydraulic_curve", "Output hydraulic curve table", "DETable", "Output", "Derived"),
            _parameter("output_profile_metrics", "Output profile metrics table", "DETable", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "profile_tbl", "Profile table", "04 Sample DEM Profiles")
            _validate_standard_output(parameters, 0, 1, "xsecs", "Cross-section lines", "03 Generate Cross Sections")
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[2], "Thalweg search distance")
        _validate_positive_number(parameters[3], "Maximum water level above thalweg")
        _validate_positive_number(parameters[4], "Water level step")
        _validate_positive_number(parameters[5], "Minimum valid top width")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        profile_table = _require_run_output(
            workspace, run_name, "profile_tbl", "Profile table", "04 Sample DEM Profiles"
        )
        cross_sections = _require_run_output(
            workspace, run_name, "xsecs", "Cross-section lines", "03 Generate Cross Sections"
        )
        thalweg_points = _run_output(workspace, run_name, "thalweg")
        curve_table = _run_output(workspace, run_name, "hyd_curve")
        metrics_table = _run_output(workspace, run_name, "profile_metrics")
        outputs = detect_thalweg_and_hydraulic_metrics(
            profile_table,
            float(parameters[2].value),
            float(parameters[3].value),
            float(parameters[4].value),
            float(parameters[5].value),
            thalweg_points,
            curve_table,
            metrics_table,
            spatial_ref_source=cross_sections,
        )
        parameters[6].value = outputs["thalweg_points"]
        parameters[7].value = outputs["hydraulic_curve_table"]
        parameters[8].value = outputs["profile_metrics_table"]


class BankfullCandidateDetection(object):
    def __init__(self):
        self.label = "06 Bankfull Candidate Detection"
        self.description = "Generate candidate bankfull points and width lines from slope, hydraulic, and agreement evidence."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("slope_threshold_deg", "Slope threshold", "GPDouble", default=15.0),
            _parameter("hydraulic_sensitivity", "Hydraulic breakpoint sensitivity", "GPDouble", default=1.0),
            _parameter("max_bankfull_height_m", "Optional maximum bankfull height above thalweg", "GPDouble", parameter_type="Optional"),
            _parameter("output_candidate_points", "Output candidate points", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_candidate_lines", "Output candidate width lines", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_candidate_table", "Output candidate table", "DETable", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "profile_tbl", "Profile table", "04 Sample DEM Profiles")
            _validate_standard_output(parameters, 0, 1, "hyd_curve", "Hydraulic curve table", "05 Detect Thalweg And Hydraulic Metrics")
            _validate_standard_output(parameters, 0, 1, "thalweg", "Thalweg points", "05 Detect Thalweg And Hydraulic Metrics")
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[2], "Slope threshold")
        _validate_positive_number(parameters[3], "Hydraulic breakpoint sensitivity")
        _validate_positive_number(parameters[4], "Maximum bankfull height above thalweg")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        profile_table = _require_run_output(
            workspace, run_name, "profile_tbl", "Profile table", "04 Sample DEM Profiles"
        )
        hydraulic_curve = _require_run_output(
            workspace, run_name, "hyd_curve", "Hydraulic curve table", "05 Detect Thalweg And Hydraulic Metrics"
        )
        thalweg_points = _require_run_output(
            workspace, run_name, "thalweg", "Thalweg points", "05 Detect Thalweg And Hydraulic Metrics"
        )
        candidate_points = _run_output(workspace, run_name, "cand_pts")
        candidate_lines = _run_output(workspace, run_name, "cand_lines")
        candidate_table = _run_output(workspace, run_name, "cand_tbl")
        outputs = detect_bankfull_candidates(
            profile_table,
            hydraulic_curve,
            thalweg_points,
            float(parameters[2].value),
            float(parameters[3].value),
            _float_or_none(parameters[4]),
            candidate_points,
            candidate_lines,
            candidate_table,
        )
        parameters[5].value = outputs["candidate_points"]
        parameters[6].value = outputs["candidate_width_lines"]
        parameters[7].value = outputs["candidate_table"]


class SelectBestCandidateAndContinuityCheck(object):
    def __init__(self):
        self.label = "07 Select Best Candidate And Continuity Check"
        self.description = "Select one bankfull candidate per cross section and flag width or level continuity issues."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("width_jump_threshold", "Width jump threshold ratio", "GPDouble", default=0.75),
            _parameter("elevation_jump_threshold_m", "Bankfull level jump threshold", "GPDouble", default=1.0),
            _parameter("moving_window_size", "Moving window size", "GPLong", default=5),
            _parameter("output_selected_points", "Output selected bankfull points", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_selected_lines", "Output selected bankfull width lines", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_selected_table", "Output selected bankfull table", "DETable", "Output", "Derived"),
            _parameter("output_qa_flags", "Output QA flags table", "DETable", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "cand_tbl", "Candidate table", "06 Bankfull Candidate Detection")
            _validate_standard_output(parameters, 0, 1, "cand_pts", "Candidate points", "06 Bankfull Candidate Detection")
            _validate_standard_output(parameters, 0, 1, "cand_lines", "Candidate width lines", "06 Bankfull Candidate Detection")
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[2], "Width jump threshold")
        _validate_positive_number(parameters[3], "Bankfull level jump threshold")
        _validate_positive_number(parameters[4], "Moving window size")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        candidate_table = _require_run_output(
            workspace, run_name, "cand_tbl", "Candidate table", "06 Bankfull Candidate Detection"
        )
        candidate_points = _require_run_output(
            workspace, run_name, "cand_pts", "Candidate points", "06 Bankfull Candidate Detection"
        )
        candidate_lines = _require_run_output(
            workspace, run_name, "cand_lines", "Candidate width lines", "06 Bankfull Candidate Detection"
        )
        selected_points = _run_output(workspace, run_name, "selected_pts")
        selected_lines = _run_output(workspace, run_name, "selected_lines")
        selected_table = _run_output(workspace, run_name, "selected_tbl")
        qa_flags = _run_output(workspace, run_name, "qa_flags")
        outputs = select_best_candidates(
            candidate_table,
            candidate_points,
            candidate_lines,
            float(parameters[2].value),
            float(parameters[3].value),
            int(parameters[4].value),
            selected_points,
            selected_lines,
            selected_table,
            qa_flags,
        )
        parameters[5].value = outputs["selected_points"]
        parameters[6].value = outputs["selected_width_lines"]
        parameters[7].value = outputs["selected_table"]
        parameters[8].value = outputs["qa_flags"]


class CreateBankfullPolygon(object):
    def __init__(self):
        self.label = "08 Create Bankfull Polygon"
        self.description = "Create raw left and right bank lines and a raw bankfull polygon from selected points."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("output_polygon", "Output raw bankfull polygon", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_left_bank", "Output left bank line", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_right_bank", "Output right bank line", "DEFeatureClass", "Output", "Derived"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "selected_pts", "Selected bankfull points", "07 Select Best Candidate And Continuity Check")
            _validate_standard_output(parameters, 0, 1, "selected_lines", "Selected bankfull width lines", "07 Select Best Candidate And Continuity Check")
            _validate_standard_output(parameters, 0, 1, "selected_tbl", "Selected bankfull table", "07 Select Best Candidate And Continuity Check")
            _validate_standard_output(parameters, 0, 1, "stream", "Prepared stream centreline", "01 Prepare Inputs")
        _validate_run_name(parameters[1])

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        selected_points = _require_run_output(
            workspace, run_name, "selected_pts", "Selected bankfull points", "07 Select Best Candidate And Continuity Check"
        )
        selected_lines = _require_run_output(
            workspace, run_name, "selected_lines", "Selected bankfull width lines", "07 Select Best Candidate And Continuity Check"
        )
        selected_table = _require_run_output(
            workspace, run_name, "selected_tbl", "Selected bankfull table", "07 Select Best Candidate And Continuity Check"
        )
        prepared_stream = _require_run_output(
            workspace, run_name, "stream", "Prepared stream centreline", "01 Prepare Inputs"
        )
        polygon = _run_output(workspace, run_name, "polygon_raw")
        left_bank = _run_output(workspace, run_name, "left_bank")
        right_bank = _run_output(workspace, run_name, "right_bank")
        outputs = create_bankfull_polygon(
            selected_points,
            selected_lines,
            prepared_stream,
            selected_table,
            polygon,
            left_bank,
            right_bank,
        )
        parameters[2].value = outputs["bankfull_polygon_raw"]
        parameters[3].value = outputs["left_bank_line"]
        parameters[4].value = outputs["right_bank_line"]


class SmoothBankLines(object):
    def __init__(self):
        self.label = "09 Smooth Bank Lines"
        self.description = "Optionally smooth selected bankfull points and create a smoothed polygon with a correction log."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("smoothing_method", "Smoothing method", "GPString", default="none"),
            _parameter("smoothing_window_size", "Smoothing window", "GPLong", default=5),
            _parameter("preserve_low_confidence", "Preserve low confidence points", "GPBoolean", default=True),
            _parameter("output_smoothed_points", "Output smoothed bankfull points", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_smoothed_polygon", "Output smoothed bankfull polygon", "DEFeatureClass", "Output", "Derived"),
            _parameter("output_correction_log", "Output correction log", "DETable", "Output", "Derived"),
        ]
        params[2].filter.type = "ValueList"
        params[2].filter.list = ["none", "rolling_median"]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "selected_pts", "Selected bankfull points", "07 Select Best Candidate And Continuity Check")
            _validate_standard_output(parameters, 0, 1, "selected_tbl", "Selected bankfull table", "07 Select Best Candidate And Continuity Check")
        _validate_run_name(parameters[1])
        _validate_positive_number(parameters[3], "Smoothing window")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        selected_points = _require_run_output(
            workspace, run_name, "selected_pts", "Selected bankfull points", "07 Select Best Candidate And Continuity Check"
        )
        selected_table = _require_run_output(
            workspace, run_name, "selected_tbl", "Selected bankfull table", "07 Select Best Candidate And Continuity Check"
        )
        smoothed_points = _run_output(workspace, run_name, "smoothed_pts")
        smoothed_polygon = _run_output(workspace, run_name, "polygon_smooth")
        correction_log = _run_output(workspace, run_name, "correction_log")
        outputs = smooth_bank_lines(
            selected_points,
            selected_table,
            parameters[2].valueAsText,
            int(parameters[3].value),
            _bool(parameters[4]),
            smoothed_points,
            smoothed_polygon,
            correction_log,
        )
        parameters[5].value = outputs["bankfull_points_smoothed"]
        parameters[6].value = outputs["bankfull_polygon_smoothed"]
        parameters[7].value = outputs["correction_log"]


class GenerateQAReport(object):
    def __init__(self):
        self.label = "10 Generate QA Report"
        self.description = "Generate CSV and Markdown QA summaries for selected candidates, flags, and parameters."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("project_gdb", "Project geodatabase", "DEWorkspace"),
            _parameter("run_name", "Run name", "GPString", default="bf01"),
            _parameter("output_report_folder", "Output report folder", "DEFolder"),
        ]
        return params

    def updateMessages(self, parameters):
        if _validate_project_gdb(parameters[0]):
            _validate_standard_output(parameters, 0, 1, "selected_tbl", "Selected bankfull table", "07 Select Best Candidate And Continuity Check")
            _validate_standard_output(parameters, 0, 1, "qa_flags", "QA flags table", "07 Select Best Candidate And Continuity Check")
            _validate_standard_output(parameters, 0, 1, "cand_tbl", "Candidate table", "06 Bankfull Candidate Detection")
            _validate_standard_output(parameters, 0, 1, "run_params", "Run parameter table", "01 Prepare Inputs")
        _validate_run_name(parameters[1])
        _validate_required_text(parameters[2], "Output report folder")

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = parameters[0].valueAsText
        run_name = parameters[1].valueAsText
        selected_table = _require_run_output(
            workspace, run_name, "selected_tbl", "Selected bankfull table", "07 Select Best Candidate And Continuity Check"
        )
        qa_flags = _require_run_output(
            workspace, run_name, "qa_flags", "QA flags table", "07 Select Best Candidate And Continuity Check"
        )
        candidate_table = _require_run_output(
            workspace, run_name, "cand_tbl", "Candidate table", "06 Bankfull Candidate Detection"
        )
        run_params = _require_run_output(
            workspace, run_name, "run_params", "Run parameter table", "01 Prepare Inputs"
        )
        generate_qa_report(
            selected_table,
            qa_flags,
            candidate_table,
            run_params,
            parameters[2].valueAsText,
        )
