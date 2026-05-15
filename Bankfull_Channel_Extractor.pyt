# -*- coding: utf-8 -*-
"""ArcGIS Pro Python toolbox for bankfull channel extraction."""
from __future__ import annotations
import os, sys
TOOLBOX_DIR = os.path.dirname(__file__)
if TOOLBOX_DIR not in sys.path: sys.path.insert(0, TOOLBOX_DIR)
try:
    import arcpy  # type: ignore
except Exception:
    arcpy = None

from bankfull_core.candidate_detection import detect_bankfull_candidates
from bankfull_core.continuity_check import select_best_candidates
from bankfull_core.geometry_utils import generate_cross_sections, generate_station_points
from bankfull_core.hydraulic_metrics import detect_thalweg_and_hydraulic_metrics
from bankfull_core.io_utils import log_stage_parameters, output_path, prepare_inputs, read_run_param, run_output_name
from bankfull_core.polygon_creation import create_bankfull_polygon
from bankfull_core.profile_sampling import sample_dem_profiles
from bankfull_core.qa_report import generate_qa_report
from bankfull_core.smoothing import smooth_bank_lines

def _require_arcpy():
    if arcpy is None: raise RuntimeError("Run inside ArcGIS Pro.")
def _bool(p):
    v = p.value
    return str(v).lower() in {"true", "1", "yes"} if v is not None else False
def _txt(p):
    t = p.valueAsText
    return None if t in (None, "") else t
def _flt(p):
    t = _txt(p)
    return None if t is None else float(t)
def _p(name,label,dt,direction="Input",ptype="Required",default=None,help_text=None):
    x=arcpy.Parameter(name=name,displayName=label,datatype=dt,direction=direction,parameterType=ptype)
    if default is not None: x.value = default
    x.description = help_text or f"{label}. See docs/tool_help.md for details."
    return x
def _auto(gdb, run, suffix): return output_path(gdb, run_output_name(run, suffix))
def _get_dem(gdb, run):
    clipped = _auto(gdb, run, "dem_clip")
    if arcpy.Exists(clipped): return clipped
    dem = read_run_param(gdb, run, "dem_for_processing") or read_run_param(gdb, run, "dem_raster")
    if dem and arcpy.Exists(dem): return dem
    raise ValueError("No DEM found for this run. Run Setup Bankfull Project first.")

class Toolbox(object):
    def __init__(self):
        self.label="Bankfull Channel Extractor"; self.alias="bankfull_channel"
        self.tools=[SetupBankfullProject,CreateCrossSectionsAndDEMProfiles,CalculateHydraulicMetrics,DetectAndSelectBankfull,CreateBankfullOutputsAndQAReport,RunFullBankfullWorkflow]

class SetupBankfullProject(object):
    def __init__(self): self.label="01 Setup Bankfull Project"; self.description="Prepare project geodatabase and standard datasets for a run."
    def getParameterInfo(self):
        _require_arcpy(); p=[_p("stream","Input stream centreline","DEFeatureClass"),_p("dem","Input LiDAR DEM","DERasterDataset"),_p("folder","Project folder","DEFolder"),_p("gdb_name","Output geodatabase name","GPString",default="bankfull_outputs.gdb"),_p("run","Run name","GPString",default="bf01"),_p("reach_mode","Reach handling mode","GPString",default="Treat all input streams as one reach"),_p("reach_field","Reach ID field","Field",ptype="Optional"),_p("clip_buf","Optional DEM clip buffer","GPString",ptype="Optional"),_p("check_proj","Check projection","GPBoolean",default=True),_p("out_gdb","Project geodatabase","DEWorkspace","Output","Derived")]
        p[5].filter.type="ValueList"; p[5].filter.list=["Treat all input streams as one reach","Preserve input features as separate reaches","Use a selected reach ID field"]
        p[6].parameterDependencies=[p[0].name]
        return p
    def updateMessages(self, parameters):
        if parameters[5].valueAsText=="Use a selected reach ID field" and not parameters[6].valueAsText: parameters[6].setErrorMessage("Select a Reach ID field, or choose a different reach handling mode.")
        if parameters[4].valueAsText and len(parameters[4].valueAsText)>20: parameters[4].setWarningMessage("Short run names are recommended because they are used in output dataset names.")
    def execute(self, parameters, messages):
        out=prepare_inputs(parameters[0].valueAsText,parameters[1].valueAsText,parameters[2].valueAsText,parameters[3].valueAsText,_txt(parameters[7]),False,_bool(parameters[8]),run_name=parameters[4].valueAsText,reach_mode=parameters[5].valueAsText,reach_field=_txt(parameters[6]))
        parameters[9].value=out["output_gdb"]; log_stage_parameters(out["output_gdb"],parameters[4].valueAsText,self.label,{"stream":parameters[0].valueAsText,"dem":parameters[1].valueAsText},out)

class CreateCrossSectionsAndDEMProfiles(object):
    def __init__(self): self.label="02 Create Cross Sections And DEM Profiles"; self.description="Generate station points, cross sections, and sampled profiles."
    def getParameterInfo(self): _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("station_interval_m","Station interval","GPDouble",default=10.0),_p("cross_section_half_width_m","Cross section half width","GPDouble",default=50.0),_p("tangent_distance_m","Tangent calculation distance","GPDouble",default=20.0),_p("dem_sample_spacing_m","DEM sample spacing","GPDouble",default=1.0),_p("slope_raster","Optional slope raster","DERasterDataset",ptype="Optional"),_p("create_slope_raster","Create slope raster if missing","GPBoolean",default=True)]
    def updateMessages(self, p):
        if p[2].value is not None and float(p[2].value)<=0: p[2].setErrorMessage("Station interval must be greater than zero.")
        if p[3].value is not None and float(p[3].value)<=0: p[3].setErrorMessage("Cross section half width must be greater than zero.")
        if p[5].value is not None and float(p[5].value)<=0: p[5].setErrorMessage("DEM sample spacing must be greater than zero.")
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText; stream=_auto(gdb,run,"stream"); dem=_get_dem(gdb,run)
        stations,xsecs=_auto(gdb,run,"stations"),_auto(gdb,run,"xsecs")
        generate_station_points(stream,float(p[2].value),"reach_id",stations); generate_cross_sections(stations,stream,float(p[3].value),"fast_perpendicular",float(p[4].value),xsecs)
        out=sample_dem_profiles(xsecs,dem,float(p[5].value),_txt(p[6]),_bool(p[7]),_auto(gdb,run,"profile_pts"),_auto(gdb,run,"profile_tbl"))
        log_stage_parameters(gdb,run,self.label,{"station_interval_m":p[2].value,"dem_for_processing":dem},{"stations":stations,"xsecs":xsecs,**out})

class CalculateHydraulicMetrics(object):
    def __init__(self): self.label="03 Calculate Hydraulic Metrics"; self.description="Detect thalweg and compute hydraulic curves."
    def getParameterInfo(self): _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("thalweg_search_distance_m","Thalweg search distance","GPDouble",default=10.0),_p("max_water_height_m","Maximum water level above thalweg","GPDouble",default=5.0),_p("water_level_step_m","Water level step","GPDouble",default=0.1),_p("min_top_width_m","Minimum valid top width","GPDouble",default=0.5)]
    def updateMessages(self,p):
        if p[4].value is not None and float(p[4].value)<=0: p[4].setErrorMessage("Water level step must be greater than zero.")
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        out=detect_thalweg_and_hydraulic_metrics(_auto(gdb,run,"profile_tbl"),float(p[2].value),float(p[3].value),float(p[4].value),float(p[5].value),_auto(gdb,run,"thalweg"),_auto(gdb,run,"hyd_curve"),_auto(gdb,run,"profile_metrics"),spatial_ref_source=_auto(gdb,run,"xsecs"))
        log_stage_parameters(gdb,run,self.label,{"water_level_step_m":p[4].value},out)

class DetectAndSelectBankfull(object):
    def __init__(self): self.label="04 Detect And Select Bankfull"; self.description="Generate and select bankfull candidates."
    def getParameterInfo(self): _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("slope_threshold_deg","Slope threshold","GPDouble",default=15.0),_p("hydraulic_breakpoint_sensitivity","Hydraulic breakpoint sensitivity","GPDouble",default=1.0),_p("max_bankfull_height_m","Maximum bankfull height above thalweg","GPDouble",ptype="Optional"),_p("width_jump_threshold","Width jump threshold","GPDouble",default=0.75),_p("bankfull_level_jump_threshold_m","Bankfull level jump threshold","GPDouble",default=1.0),_p("moving_window_size","Moving window size","GPLong",default=5)]
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        out1=detect_bankfull_candidates(_auto(gdb,run,"profile_tbl"),_auto(gdb,run,"hyd_curve"),_auto(gdb,run,"thalweg"),float(p[2].value),float(p[3].value),_flt(p[4]),_auto(gdb,run,"cand_pts"),_auto(gdb,run,"cand_lines"),_auto(gdb,run,"cand_tbl"))
        out2=select_best_candidates(_auto(gdb,run,"cand_tbl"),_auto(gdb,run,"cand_pts"),_auto(gdb,run,"cand_lines"),float(p[5].value),float(p[6].value),int(p[7].value),_auto(gdb,run,"selected_pts"),_auto(gdb,run,"selected_lines"),_auto(gdb,run,"selected_tbl"),_auto(gdb,run,"qa_flags"))
        log_stage_parameters(gdb,run,self.label,{"slope_threshold_deg":p[2].value},{**out1,**out2})

class CreateBankfullOutputsAndQAReport(object):
    def __init__(self): self.label="05 Create Bankfull Outputs And QA Report"; self.description="Create polygon outputs and optional report."
    def getParameterInfo(self): _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("smoothing_method","Smoothing method","GPString",default="none"),_p("smoothing_window_size","Smoothing window","GPLong",default=5),_p("preserve_low_confidence_points","Preserve low confidence points","GPBoolean",default=True),_p("create_qa_report","Create QA report","GPBoolean",default=True),_p("output_report_folder","Output report folder","DEFolder",ptype="Optional")]
    def updateMessages(self,p):
        if _bool(p[5]) and not _txt(p[6]): p[6].setErrorMessage("Output report folder is required when Create QA report is enabled.")
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        out1=create_bankfull_polygon(_auto(gdb,run,"selected_pts"),_auto(gdb,run,"selected_lines"),_auto(gdb,run,"stream"),_auto(gdb,run,"selected_tbl"),_auto(gdb,run,"polygon_raw"),_auto(gdb,run,"left_bank"),_auto(gdb,run,"right_bank"))
        out2=smooth_bank_lines(_auto(gdb,run,"selected_pts"),_auto(gdb,run,"selected_tbl"),p[2].valueAsText,int(p[3].value),_bool(p[4]),_auto(gdb,run,"selected_pts")+"_sm",_auto(gdb,run,"polygon_smooth"),_auto(gdb,run,"correction_log"))
        if _bool(p[5]) and _txt(p[6]): generate_qa_report(_auto(gdb,run,"selected_tbl"),_auto(gdb,run,"qa_flags"),_auto(gdb,run,"cand_tbl"),_auto(gdb,run,"run_params"),p[6].valueAsText)
        log_stage_parameters(gdb,run,self.label,{"create_qa_report":_bool(p[5])},{**out1,**out2})

class RunFullBankfullWorkflow(object):
    def __init__(self): self.label="Run Full Bankfull Workflow"; self.description="Run the full bankfull workflow in one tool."
    def getParameterInfo(self):
        _require_arcpy()
        return [
            _p("input_stream","Input stream centreline","DEFeatureClass"),_p("input_dem","Input LiDAR DEM","DERasterDataset"),_p("project_folder","Project folder","DEFolder"),_p("output_gdb_name","Output geodatabase name","GPString",default="bankfull_outputs.gdb"),_p("run_name","Run name","GPString",default="bf01"),_p("reach_mode","Reach handling mode","GPString",default="Treat all input streams as one reach"),_p("reach_id_field","Reach ID field","Field",ptype="Optional"),_p("dem_clip_buffer","Optional DEM clip buffer","GPString",ptype="Optional"),_p("check_projection","Check projection","GPBoolean",default=True),
            _p("station_interval_m","Station interval","GPDouble",default=10.0),_p("cross_section_half_width_m","Cross section half width","GPDouble",default=50.0),_p("tangent_distance_m","Tangent calculation distance","GPDouble",default=20.0),_p("dem_sample_spacing_m","DEM sample spacing","GPDouble",default=1.0),_p("slope_raster","Optional slope raster","DERasterDataset",ptype="Optional"),_p("create_slope_raster","Create slope raster if missing","GPBoolean",default=True),
            _p("thalweg_search_distance_m","Thalweg search distance","GPDouble",default=10.0),_p("max_water_height_m","Maximum water level above thalweg","GPDouble",default=5.0),_p("water_level_step_m","Water level step","GPDouble",default=0.1),_p("min_top_width_m","Minimum valid top width","GPDouble",default=0.5),
            _p("slope_threshold_deg","Slope threshold","GPDouble",default=15.0),_p("hydraulic_breakpoint_sensitivity","Hydraulic breakpoint sensitivity","GPDouble",default=1.0),_p("max_bankfull_height_m","Maximum bankfull height above thalweg","GPDouble",ptype="Optional"),_p("width_jump_threshold","Width jump threshold","GPDouble",default=0.75),_p("bankfull_level_jump_threshold_m","Bankfull level jump threshold","GPDouble",default=1.0),_p("moving_window_size","Moving window size","GPLong",default=5),
            _p("smoothing_method","Smoothing method","GPString",default="none"),_p("smoothing_window_size","Smoothing window","GPLong",default=5),_p("preserve_low_confidence_points","Preserve low confidence points","GPBoolean",default=True),_p("create_qa_report","Create QA report","GPBoolean",default=True),_p("output_report_folder","Output report folder","DEFolder",ptype="Optional")
        ]
    def updateMessages(self,p):
        if p[5].valueAsText=="Use a selected reach ID field" and not p[6].valueAsText: p[6].setErrorMessage("Select Reach ID field.")
        if p[9].value is not None and float(p[9].value)<=0: p[9].setErrorMessage("Station interval must be > 0")
        if p[10].value is not None and float(p[10].value)<=0: p[10].setErrorMessage("Cross section half width must be > 0")
        if p[12].value is not None and float(p[12].value)<=0: p[12].setErrorMessage("DEM sample spacing must be > 0")
        if p[17].value is not None and float(p[17].value)<=0: p[17].setErrorMessage("Water level step must be > 0")
        if _bool(p[28]) and not _txt(p[29]): p[29].setErrorMessage("Output report folder required when QA report enabled.")
    def execute(self, parameters, messages):
        input_stream=parameters[0].valueAsText; input_dem=parameters[1].valueAsText; project_folder=parameters[2].valueAsText; output_gdb_name=parameters[3].valueAsText
        run_name=parameters[4].valueAsText; reach_mode=parameters[5].valueAsText; reach_id_field=_txt(parameters[6]); dem_clip_buffer=_txt(parameters[7]); check_projection=_bool(parameters[8])
        station_interval_m=float(parameters[9].value); cross_section_half_width_m=float(parameters[10].value); tangent_distance_m=float(parameters[11].value); dem_sample_spacing_m=float(parameters[12].value); slope_raster=_txt(parameters[13]); create_slope_raster=_bool(parameters[14])
        thalweg_search_distance_m=float(parameters[15].value); max_water_height_m=float(parameters[16].value); water_level_step_m=float(parameters[17].value); min_top_width_m=float(parameters[18].value)
        slope_threshold_deg=float(parameters[19].value); hydraulic_breakpoint_sensitivity=float(parameters[20].value); max_bankfull_height_m=_flt(parameters[21]); width_jump_threshold=float(parameters[22].value); bankfull_level_jump_threshold_m=float(parameters[23].value); moving_window_size=int(parameters[24].value)
        smoothing_method=parameters[25].valueAsText; smoothing_window_size=int(parameters[26].value); preserve_low_confidence_points=_bool(parameters[27]); create_qa_report=_bool(parameters[28]); output_report_folder=_txt(parameters[29])

        setup=prepare_inputs(input_stream,input_dem,project_folder,output_gdb_name,dem_clip_buffer,False,check_projection,run_name=run_name,reach_mode=reach_mode,reach_field=reach_id_field)
        gdb=setup["output_gdb"]; dem_for_processing=_get_dem(gdb,run_name)
        stations=_auto(gdb,run_name,"stations"); xsecs=_auto(gdb,run_name,"xsecs")
        generate_station_points(_auto(gdb,run_name,"stream"),station_interval_m,"reach_id",stations)
        generate_cross_sections(stations,_auto(gdb,run_name,"stream"),cross_section_half_width_m,"fast_perpendicular",tangent_distance_m,xsecs)
        sample_dem_profiles(xsecs,dem_for_processing,dem_sample_spacing_m,slope_raster,create_slope_raster,_auto(gdb,run_name,"profile_pts"),_auto(gdb,run_name,"profile_tbl"))
        detect_thalweg_and_hydraulic_metrics(_auto(gdb,run_name,"profile_tbl"),thalweg_search_distance_m,max_water_height_m,water_level_step_m,min_top_width_m,_auto(gdb,run_name,"thalweg"),_auto(gdb,run_name,"hyd_curve"),_auto(gdb,run_name,"profile_metrics"),spatial_ref_source=xsecs)
        detect_bankfull_candidates(_auto(gdb,run_name,"profile_tbl"),_auto(gdb,run_name,"hyd_curve"),_auto(gdb,run_name,"thalweg"),slope_threshold_deg,hydraulic_breakpoint_sensitivity,max_bankfull_height_m,_auto(gdb,run_name,"cand_pts"),_auto(gdb,run_name,"cand_lines"),_auto(gdb,run_name,"cand_tbl"))
        select_best_candidates(_auto(gdb,run_name,"cand_tbl"),_auto(gdb,run_name,"cand_pts"),_auto(gdb,run_name,"cand_lines"),width_jump_threshold,bankfull_level_jump_threshold_m,moving_window_size,_auto(gdb,run_name,"selected_pts"),_auto(gdb,run_name,"selected_lines"),_auto(gdb,run_name,"selected_tbl"),_auto(gdb,run_name,"qa_flags"))
        create_bankfull_polygon(_auto(gdb,run_name,"selected_pts"),_auto(gdb,run_name,"selected_lines"),_auto(gdb,run_name,"stream"),_auto(gdb,run_name,"selected_tbl"),_auto(gdb,run_name,"polygon_raw"),_auto(gdb,run_name,"left_bank"),_auto(gdb,run_name,"right_bank"))
        smooth_bank_lines(_auto(gdb,run_name,"selected_pts"),_auto(gdb,run_name,"selected_tbl"),smoothing_method,smoothing_window_size,preserve_low_confidence_points,_auto(gdb,run_name,"selected_pts")+"_sm",_auto(gdb,run_name,"polygon_smooth"),_auto(gdb,run_name,"correction_log"))
        if create_qa_report and output_report_folder: generate_qa_report(_auto(gdb,run_name,"selected_tbl"),_auto(gdb,run_name,"qa_flags"),_auto(gdb,run_name,"cand_tbl"),_auto(gdb,run_name,"run_params"),output_report_folder)
