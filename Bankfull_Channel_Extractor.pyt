# -*- coding: utf-8 -*-
"""ArcGIS Pro Python toolbox for bankfull channel extraction."""
from __future__ import annotations
import os, sys
TOOLBOX_DIR=os.path.dirname(__file__)
if TOOLBOX_DIR not in sys.path: sys.path.insert(0, TOOLBOX_DIR)
try:
    import arcpy  # type: ignore
except Exception:
    arcpy=None
from bankfull_core.candidate_detection import detect_bankfull_candidates
from bankfull_core.continuity_check import select_best_candidates
from bankfull_core.geometry_utils import generate_cross_sections, generate_station_points
from bankfull_core.hydraulic_metrics import detect_thalweg_and_hydraulic_metrics
from bankfull_core.io_utils import output_path, prepare_inputs, run_output_name
from bankfull_core.polygon_creation import create_bankfull_polygon
from bankfull_core.profile_sampling import sample_dem_profiles
from bankfull_core.qa_report import generate_qa_report
from bankfull_core.smoothing import smooth_bank_lines

def _require_arcpy():
    if arcpy is None: raise RuntimeError("Run inside ArcGIS Pro.")
def _bool(p):
    v=p.value
    return str(v).lower() in {"true","1","yes"} if v is not None else False
def _txt(p):
    t=p.valueAsText
    return None if t in (None,"") else t
def _flt(p):
    t=_txt(p)
    return None if t is None else float(t)
def _p(name,label,dt,direction="Input",ptype="Required",default=None):
    x=arcpy.Parameter(name=name,displayName=label,datatype=dt,direction=direction,parameterType=ptype)
    if default is not None: x.value=default
    return x

def _auto(gdb,run,suffix): return output_path(gdb, run_output_name(run,suffix))

def _get_dem(gdb, run):
    for s in ["dem_clip","dem_raster"]:
        p=_auto(gdb,run,s)
        if arcpy.Exists(p): return p
    raise ValueError("No DEM found in project for run.")

class Toolbox(object):
    def __init__(self):
        self.label="Bankfull Channel Extractor"
        self.alias="bankfull_channel"
        self.tools=[RunFullBankfullWorkflow, SetupBankfullProject, CreateCrossSectionsAndDEMProfiles, CalculateHydraulicMetrics, DetectAndSelectBankfull, CreateBankfullOutputsAndQAReport]

class SetupBankfullProject(object):
    def __init__(self):
        self.label="01 Setup Bankfull Project"; self.description="Prepare project geodatabase and standard datasets for a run."
    def getParameterInfo(self):
        _require_arcpy(); p=[
            _p("stream","Input stream centreline","DEFeatureClass"),_p("dem","Input LiDAR DEM","DERasterDataset"),
            _p("folder","Project folder","DEFolder"),_p("gdb_name","Output geodatabase name","GPString",default="bankfull_outputs.gdb"),
            _p("run","Run name","GPString",default="bf01"),_p("reach_mode","Reach handling mode","GPString",default="Treat all input streams as one reach"),
            _p("reach_field","Reach ID field","Field",ptype="Optional"),_p("clip_buf","Optional DEM clip buffer","GPString",ptype="Optional"),
            _p("check_proj","Check projection","GPBoolean",default=True),
            _p("out_gdb","Project geodatabase","DEWorkspace","Output","Derived")]
        p[5].filter.type="ValueList"; p[5].filter.list=["Treat all input streams as one reach","Preserve input features as separate reaches","Use a selected reach ID field"]
        p[6].parameterDependencies=[p[0].name]
        return p
    def execute(self, parameters, messages):
        _require_arcpy()
        out=prepare_inputs(parameters[0].valueAsText,parameters[1].valueAsText,parameters[2].valueAsText,parameters[3].valueAsText,_txt(parameters[7]),False,_bool(parameters[8]),run_name=parameters[4].valueAsText,reach_mode=parameters[5].valueAsText,reach_field=_txt(parameters[6]))
        parameters[9].value=out["output_gdb"]

class CreateCrossSectionsAndDEMProfiles(object):
    def __init__(self): self.label="02 Create Cross Sections And DEM Profiles"; self.description="Create station points, cross sections, and sampled DEM profiles from project inputs."
    def getParameterInfo(self):
        _require_arcpy(); return [
            _p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("station","Station interval","GPDouble",default=10.0),
            _p("half","Cross section half width","GPDouble",default=50.0),_p("tangent","Tangent calculation distance","GPDouble",default=20.0),
            _p("spacing","DEM sample spacing","GPDouble",default=1.0),_p("slope","Optional slope raster","DERasterDataset",ptype="Optional"),
            _p("create_slope","Create slope raster if missing","GPBoolean",default=True)]
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        stream=_auto(gdb,run,"stream"); dem=_get_dem(gdb,run)
        stations=_auto(gdb,run,"stations"); xsecs=_auto(gdb,run,"xsecs")
        generate_station_points(stream,float(p[2].value),"reach_id",stations)
        generate_cross_sections(stations,stream,float(p[3].value),"fast_perpendicular",float(p[4].value),xsecs)
        sample_dem_profiles(xsecs,dem,float(p[5].value),_txt(p[6]),_bool(p[7]),_auto(gdb,run,"profile_pts"),_auto(gdb,run,"profile_tbl"))

class CalculateHydraulicMetrics(object):
    def __init__(self): self.label="03 Calculate Hydraulic Metrics"; self.description="Detect thalweg and compute hydraulic metrics from sampled profile table."
    def getParameterInfo(self):
        _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("search","Thalweg search distance","GPDouble",default=10.0),_p("max_h","Maximum bankfull search height","GPDouble",default=5.0),_p("step","Water level step","GPDouble",default=0.1),_p("min_w","Minimum valid top width","GPDouble",default=0.5)]
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        detect_thalweg_and_hydraulic_metrics(_auto(gdb,run,"profile_tbl"),float(p[2].value),float(p[3].value),float(p[4].value),float(p[5].value),_auto(gdb,run,"thalweg"),_auto(gdb,run,"hyd_curve"),_auto(gdb,run,"profile_metrics"))

class DetectAndSelectBankfull(object):
    def __init__(self): self.label="04 Detect And Select Bankfull"; self.description="Detect candidate bankfull lines and select final outputs with continuity QA."
    def getParameterInfo(self):
        _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("slope","Slope threshold","GPDouble",default=15.0),_p("sens","Hydraulic breakpoint sensitivity","GPDouble",default=1.0),_p("max_h","Maximum bankfull height above thalweg","GPDouble",ptype="Optional"),_p("wjump","Width jump threshold","GPDouble",default=0.75),_p("ejump","Bankfull level jump threshold","GPDouble",default=1.0),_p("window","Moving window size","GPLong",default=5)]
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        detect_bankfull_candidates(_auto(gdb,run,"profile_tbl"),_auto(gdb,run,"hyd_curve"),_auto(gdb,run,"thalweg"),float(p[2].value),float(p[3].value),_flt(p[4]),_auto(gdb,run,"cand_pts"),_auto(gdb,run,"cand_lines"),_auto(gdb,run,"cand_tbl"))
        select_best_candidates(_auto(gdb,run,"cand_tbl"),_auto(gdb,run,"cand_pts"),_auto(gdb,run,"cand_lines"),float(p[5].value),float(p[6].value),int(p[7].value),_auto(gdb,run,"selected_pts"),_auto(gdb,run,"selected_lines"),_auto(gdb,run,"selected_tbl"),_auto(gdb,run,"qa_flags"))

class CreateBankfullOutputsAndQAReport(object):
    def __init__(self): self.label="05 Create Bankfull Outputs And QA Report"; self.description="Create bankfull polygon outputs and optional QA report."
    def getParameterInfo(self):
        _require_arcpy(); return [_p("gdb","Project geodatabase","DEWorkspace"),_p("run","Run name","GPString",default="bf01"),_p("smooth","Smoothing method","GPString",default="none"),_p("smooth_win","Smoothing window","GPLong",default=5),_p("preserve","Preserve low confidence points","GPBoolean",default=True),_p("qa","Create QA report","GPBoolean",default=True),_p("report","Output report folder","DEFolder",ptype="Optional")]
    def execute(self,p,m):
        gdb,run=p[0].valueAsText,p[1].valueAsText
        create_bankfull_polygon(_auto(gdb,run,"selected_pts"),_auto(gdb,run,"selected_lines"),_auto(gdb,run,"stream"),_auto(gdb,run,"selected_tbl"),_auto(gdb,run,"polygon_raw"),_auto(gdb,run,"left_bank"),_auto(gdb,run,"right_bank"))
        smooth_bank_lines(_auto(gdb,run,"selected_pts"),_auto(gdb,run,"selected_tbl"),p[2].valueAsText,int(p[3].value),_bool(p[4]),_auto(gdb,run,"selected_pts")+"_sm",_auto(gdb,run,"polygon_smooth"),_auto(gdb,run,"correction_log"))
        if _bool(p[5]) and _txt(p[6]): generate_qa_report(_auto(gdb,run,"selected_tbl"),_auto(gdb,run,"qa_flags"),_auto(gdb,run,"cand_tbl"),_auto(gdb,run,"run_params"),p[6].valueAsText)

class RunFullBankfullWorkflow(object):
    def __init__(self): self.label="Run Full Bankfull Workflow"; self.description="Run setup, cross sections, hydraulics, candidate selection, and final outputs in one tool."
    def getParameterInfo(self):
        _require_arcpy(); return SetupBankfullProject().getParameterInfo()[:-1]+CreateCrossSectionsAndDEMProfiles().getParameterInfo()[2:]+CalculateHydraulicMetrics().getParameterInfo()[2:]+DetectAndSelectBankfull().getParameterInfo()[2:]+CreateBankfullOutputsAndQAReport().getParameterInfo()[2:]
    def execute(self, parameters, messages):
        s=SetupBankfullProject(); s.execute(parameters[:9]+[arcpy.Parameter()],messages)
        gdb=output_path(parameters[2].valueAsText,parameters[3].valueAsText if parameters[3].valueAsText.endswith('.gdb') else parameters[3].valueAsText+'.gdb')
        run=parameters[4].valueAsText
        # map downstream segments by known positions
        vals=parameters
        c=[arcpy.Parameter() for _ in range(8)]
        c[0].value,c[1].value=gdb,run
        for i,j in enumerate(range(9,15),start=2): c[i].value=vals[j].value
        c[6].value=vals[15].value; c[7].value=vals[16].value
        CreateCrossSectionsAndDEMProfiles().execute(c,messages)
        h=[arcpy.Parameter() for _ in range(6)]; h[0].value,h[1].value=gdb,run
        for i,j in enumerate(range(17,21),start=2): h[i].value=vals[j].value
        h[5].value=vals[21].value; CalculateHydraulicMetrics().execute(h,messages)

        d=[arcpy.Parameter() for _ in range(8)]; d[0].value,d[1].value=gdb,run
        for i,j in enumerate(range(22,28),start=2): d[i].value=vals[j].value
        DetectAndSelectBankfull().execute(d,messages)
        o=[arcpy.Parameter() for _ in range(7)]; o[0].value,o[1].value=gdb,run
        for i,j in enumerate(range(28,33),start=2): o[i].value=vals[j].value
        o[6].value=vals[33].value
        CreateBankfullOutputsAndQAReport().execute(o,messages)
