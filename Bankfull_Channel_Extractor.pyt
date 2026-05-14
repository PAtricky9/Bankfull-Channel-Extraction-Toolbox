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
from bankfull_core.io_utils import prepare_inputs
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


class PrepareInputs(object):
    def __init__(self):
        self.label = "01 Prepare Inputs"
        self.description = "Prepare stream centreline, DEM, boundary and configuration table."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("stream_centerline", "Stream centreline", "DEFeatureClass"),
            _parameter("dem_raster", "DEM raster", "DERasterDataset"),
            _parameter("project_folder", "Project folder", "DEFolder"),
            _parameter("output_gdb_name", "Output geodatabase name", "GPString", default="bankfull_outputs.gdb"),
            _parameter("dem_clip_buffer", "Optional DEM clip buffer distance", "GPString", parameter_type="Optional"),
            _parameter("dissolve_stream", "Dissolve stream centreline", "GPBoolean", default=True),
            _parameter("check_projection", "Check projection compatibility", "GPBoolean", default=True),
            _parameter("prepared_stream", "Prepared stream centreline", "DEFeatureClass", "Output", "Derived"),
            _parameter("clipped_dem", "Clipped DEM", "DERasterDataset", "Output", "Derived"),
            _parameter("processing_boundary", "Processing boundary", "DEFeatureClass", "Output", "Derived"),
            _parameter("project_config", "Project configuration table", "DETable", "Output", "Derived"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        outputs = prepare_inputs(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            _text_or_none(parameters[4]),
            _bool(parameters[5]),
            _bool(parameters[6]),
        )
        parameters[7].value = outputs["prepared_stream"]
        parameters[8].value = outputs["clipped_dem"]
        parameters[9].value = outputs["processing_boundary"]
        parameters[10].value = outputs["project_config"]


class GenerateStationPoints(object):
    def __init__(self):
        self.label = "02 Generate Station Points"
        self.description = "Create evenly spaced station points along the prepared stream centreline."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("prepared_stream", "Prepared stream centreline", "DEFeatureClass"),
            _parameter("station_interval_m", "Station interval in metres", "GPDouble", default=10.0),
            _parameter("reach_id_field", "Optional reach ID field", "Field", parameter_type="Optional"),
            _parameter("output_station_points", "Output station points", "DEFeatureClass", "Output"),
        ]
        params[2].parameterDependencies = [params[0].name]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        output_fc = _resolve_output(parameters[3].valueAsText, _workspace_of(parameters[0].valueAsText))
        generate_station_points(
            parameters[0].valueAsText,
            float(parameters[1].value),
            _text_or_none(parameters[2]),
            output_fc,
        )
        parameters[3].value = output_fc


class GenerateCrossSections(object):
    def __init__(self):
        self.label = "03 Generate Cross Sections"
        self.description = "Generate fast perpendicular cross-section lines from station points."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("station_points", "Station points", "DEFeatureClass"),
            _parameter("prepared_stream", "Prepared stream centreline", "DEFeatureClass"),
            _parameter("half_width_m", "Cross-section half width in metres", "GPDouble", default=50.0),
            _parameter("method", "Cross-section method", "GPString", default="fast_perpendicular"),
            _parameter("tangent_distance_m", "Tangent calculation distance in metres", "GPDouble", default=20.0),
            _parameter("output_cross_sections", "Output cross sections", "DEFeatureClass", "Output"),
        ]
        params[3].filter.type = "ValueList"
        params[3].filter.list = ["fast_perpendicular"]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        output_fc = _resolve_output(parameters[5].valueAsText, _workspace_of(parameters[0].valueAsText))
        generate_cross_sections(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            float(parameters[2].value),
            parameters[3].valueAsText,
            float(parameters[4].value),
            output_fc,
        )
        parameters[5].value = output_fc


class SampleDEMProfiles(object):
    def __init__(self):
        self.label = "04 Sample DEM Profiles"
        self.description = "Densify cross sections and sample DEM elevation and slope."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("cross_sections", "Cross-section lines", "DEFeatureClass"),
            _parameter("dem_raster", "DEM raster", "DERasterDataset"),
            _parameter("sample_spacing_m", "Sample spacing in metres", "GPDouble", default=1.0),
            _parameter("slope_raster", "Optional slope raster", "DERasterDataset", parameter_type="Optional"),
            _parameter("create_slope", "Create slope raster if missing", "GPBoolean", default=True),
            _parameter("output_profile_points", "Output profile points", "DEFeatureClass", "Output"),
            _parameter("output_profile_table", "Output profile table", "DETable", "Output"),
            _parameter("created_slope_raster", "Created or supplied slope raster", "DERasterDataset", "Output", "Derived"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = _workspace_of(parameters[0].valueAsText)
        output_points = _resolve_output(parameters[5].valueAsText, workspace)
        output_table = _resolve_output(parameters[6].valueAsText, workspace)
        outputs = sample_dem_profiles(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
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
        self.description = "Detect thalweg points and compute hydraulic curves."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("profile_table", "Profile table", "DETable"),
            _parameter("centre_search_m", "Centre search distance in metres", "GPDouble", default=10.0),
            _parameter("max_water_height_m", "Maximum water level above thalweg in metres", "GPDouble", default=5.0),
            _parameter("water_level_step_m", "Water level step in metres", "GPDouble", default=0.1),
            _parameter("min_top_width_m", "Minimum valid top width in metres", "GPDouble", default=0.5),
            _parameter("output_thalweg_points", "Output thalweg points", "DEFeatureClass", "Output"),
            _parameter("output_hydraulic_curve", "Output hydraulic curve table", "DETable", "Output"),
            _parameter("output_profile_metrics", "Output profile metrics table", "DETable", "Output"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = _workspace_of(parameters[0].valueAsText)
        thalweg_points = _resolve_output(parameters[5].valueAsText, workspace)
        curve_table = _resolve_output(parameters[6].valueAsText, workspace)
        metrics_table = _resolve_output(parameters[7].valueAsText, workspace)
        outputs = detect_thalweg_and_hydraulic_metrics(
            parameters[0].valueAsText,
            float(parameters[1].value),
            float(parameters[2].value),
            float(parameters[3].value),
            float(parameters[4].value),
            thalweg_points,
            curve_table,
            metrics_table,
        )
        parameters[5].value = outputs["thalweg_points"]
        parameters[6].value = outputs["hydraulic_curve_table"]
        parameters[7].value = outputs["profile_metrics_table"]


class BankfullCandidateDetection(object):
    def __init__(self):
        self.label = "06 Bankfull Candidate Detection"
        self.description = "Generate slope, hydraulic and agreement bankfull candidates."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("profile_table", "Profile table", "DETable"),
            _parameter("hydraulic_curve", "Hydraulic curve table", "DETable"),
            _parameter("thalweg_points", "Thalweg points", "DEFeatureClass"),
            _parameter("slope_threshold_deg", "Slope threshold in degrees", "GPDouble", default=15.0),
            _parameter("hydraulic_sensitivity", "Hydraulic breakpoint sensitivity", "GPDouble", default=1.0),
            _parameter("max_bankfull_height_m", "Optional maximum bankfull height above thalweg", "GPDouble", parameter_type="Optional"),
            _parameter("output_candidate_points", "Output candidate points", "DEFeatureClass", "Output"),
            _parameter("output_candidate_lines", "Output candidate width lines", "DEFeatureClass", "Output"),
            _parameter("output_candidate_table", "Output candidate table", "DETable", "Output"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = _workspace_of(parameters[0].valueAsText)
        candidate_points = _resolve_output(parameters[6].valueAsText, workspace)
        candidate_lines = _resolve_output(parameters[7].valueAsText, workspace)
        candidate_table = _resolve_output(parameters[8].valueAsText, workspace)
        outputs = detect_bankfull_candidates(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            float(parameters[3].value),
            float(parameters[4].value),
            _float_or_none(parameters[5]),
            candidate_points,
            candidate_lines,
            candidate_table,
        )
        parameters[6].value = outputs["candidate_points"]
        parameters[7].value = outputs["candidate_width_lines"]
        parameters[8].value = outputs["candidate_table"]


class SelectBestCandidateAndContinuityCheck(object):
    def __init__(self):
        self.label = "07 Select Best Candidate And Continuity Check"
        self.description = "Select the best bankfull candidate per cross section and flag continuity issues."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("candidate_table", "Bankfull candidate table", "DETable"),
            _parameter("candidate_points", "Candidate points", "DEFeatureClass"),
            _parameter("candidate_lines", "Candidate width lines", "DEFeatureClass"),
            _parameter("width_jump_threshold", "Width jump threshold ratio", "GPDouble", default=0.75),
            _parameter("elevation_jump_threshold_m", "Elevation jump threshold in metres", "GPDouble", default=1.0),
            _parameter("moving_window_size", "Moving window size", "GPLong", default=5),
            _parameter("output_selected_points", "Output selected bankfull points", "DEFeatureClass", "Output"),
            _parameter("output_selected_lines", "Output selected bankfull width lines", "DEFeatureClass", "Output"),
            _parameter("output_selected_table", "Output selected bankfull table", "DETable", "Output"),
            _parameter("output_qa_flags", "Output QA flags table", "DETable", "Output"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = _workspace_of(parameters[0].valueAsText)
        selected_points = _resolve_output(parameters[6].valueAsText, workspace)
        selected_lines = _resolve_output(parameters[7].valueAsText, workspace)
        selected_table = _resolve_output(parameters[8].valueAsText, workspace)
        qa_flags = _resolve_output(parameters[9].valueAsText, workspace)
        outputs = select_best_candidates(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            float(parameters[3].value),
            float(parameters[4].value),
            int(parameters[5].value),
            selected_points,
            selected_lines,
            selected_table,
            qa_flags,
        )
        parameters[6].value = outputs["selected_points"]
        parameters[7].value = outputs["selected_width_lines"]
        parameters[8].value = outputs["selected_table"]
        parameters[9].value = outputs["qa_flags"]


class CreateBankfullPolygon(object):
    def __init__(self):
        self.label = "08 Create Bankfull Polygon"
        self.description = "Create raw left/right bank lines and bankfull polygon."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("selected_points", "Selected bankfull points", "DEFeatureClass"),
            _parameter("selected_lines", "Selected bankfull width lines", "DEFeatureClass"),
            _parameter("prepared_stream", "Prepared stream centreline", "DEFeatureClass"),
            _parameter("selected_table", "Selected bankfull table", "DETable"),
            _parameter("output_polygon", "Output raw bankfull polygon", "DEFeatureClass", "Output"),
            _parameter("output_left_bank", "Output left bank line", "DEFeatureClass", "Output"),
            _parameter("output_right_bank", "Output right bank line", "DEFeatureClass", "Output"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = _workspace_of(parameters[1].valueAsText)
        polygon = _resolve_output(parameters[4].valueAsText, workspace)
        left_bank = _resolve_output(parameters[5].valueAsText, workspace)
        right_bank = _resolve_output(parameters[6].valueAsText, workspace)
        outputs = create_bankfull_polygon(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            polygon,
            left_bank,
            right_bank,
        )
        parameters[4].value = outputs["bankfull_polygon_raw"]
        parameters[5].value = outputs["left_bank_line"]
        parameters[6].value = outputs["right_bank_line"]


class SmoothBankLines(object):
    def __init__(self):
        self.label = "09 Smooth Bank Lines"
        self.description = "Optionally smooth selected bank points and create a smoothed polygon."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("selected_points", "Selected bankfull points", "DEFeatureClass"),
            _parameter("selected_table", "Selected bankfull table", "DETable"),
            _parameter("smoothing_method", "Smoothing method", "GPString", default="none"),
            _parameter("smoothing_window_size", "Smoothing window size", "GPLong", default=5),
            _parameter("preserve_low_confidence", "Preserve low confidence points", "GPBoolean", default=True),
            _parameter("output_smoothed_points", "Output smoothed bankfull points", "DEFeatureClass", "Output"),
            _parameter("output_smoothed_polygon", "Output smoothed bankfull polygon", "DEFeatureClass", "Output"),
            _parameter("output_correction_log", "Output correction log", "DETable", "Output"),
        ]
        params[2].filter.type = "ValueList"
        params[2].filter.list = ["none", "rolling_median"]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        workspace = _workspace_of(parameters[0].valueAsText)
        smoothed_points = _resolve_output(parameters[5].valueAsText, workspace)
        smoothed_polygon = _resolve_output(parameters[6].valueAsText, workspace)
        correction_log = _resolve_output(parameters[7].valueAsText, workspace)
        outputs = smooth_bank_lines(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
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
        self.description = "Generate CSV and Markdown QA report outputs."
        self.canRunInBackground = False

    def getParameterInfo(self):
        _require_arcpy()
        params = [
            _parameter("selected_table", "Selected bankfull table", "DETable"),
            _parameter("qa_flags", "QA flags table", "DETable"),
            _parameter("candidate_table", "Candidate table", "DETable"),
            _parameter("project_config", "Project configuration table", "DETable"),
            _parameter("output_report_folder", "Output report folder", "DEFolder"),
        ]
        return params

    def execute(self, parameters, messages):
        _require_arcpy()
        generate_qa_report(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
        )
