"""Candidate selection and reach continuity checks."""
from __future__ import annotations
import os
from collections import defaultdict
from statistics import median
from .candidate_detection import CANDIDATE_FIELDS
from .io_utils import add_field, add_message, add_text_field, delete_if_allowed

def _arcpy():
    import arcpy  # type: ignore
    return arcpy

SELECTED_FIELDS=["xsec_id","reach_id","chain_m","sel_method","bf_level","bf_width","confidence","review_req","qa_flag","qa_reason","local_med","width_dev","level_jump","left_x","left_y","left_z","right_x","right_y","right_z"]

def _read_candidates(candidate_table:str)->list[dict]:
    arcpy=_arcpy(); rows=[]
    with arcpy.da.SearchCursor(candidate_table,CANDIDATE_FIELDS) as c:
        for v in c: rows.append(dict(zip(CANDIDATE_FIELDS,v)))
    return rows

def _base_score(candidate:dict)->float:
    score=float(candidate.get("conf_raw") or 0.0)
    if candidate.get("method")=="agreement": score+=0.12
    if candidate.get("cand_flag") not in (None,"","ok"): score-=0.12
    if int(candidate.get("water_reaches_profile_edge") or 0)==1: score-=0.25
    if candidate.get("left_x") is None or candidate.get("right_x") is None: score-=0.3
    return max(0.0,min(1.0,score))

def _confidence_label(score:float)->str:
    return "High" if score>=0.75 else ("Medium" if score>=0.5 else "Low")

def _build_local_references(candidates:list[dict]):
    by_xsec=defaultdict(list)
    for c in candidates: by_xsec[int(c["xsec_id"])].append(c)
    refs=[]
    for xsec_id,rows in by_xsec.items():
        widths=[float(r["bf_width"]) for r in rows if r.get("bf_width") is not None]
        levels=[float(r["bf_level"]) for r in rows if r.get("bf_level") is not None]
        first=rows[0]
        refs.append({"xsec_id":xsec_id,"reach_id":str(first.get("reach_id")),"chain_m":float(first.get("chain_m") or 0.0),"median_width":median(widths) if widths else None,"median_level":median(levels) if levels else None})
    refs_by_reach=defaultdict(list)
    for r in refs: refs_by_reach[r["reach_id"]].append(r)
    for lst in refs_by_reach.values(): lst.sort(key=lambda r:r["chain_m"])
    return refs_by_reach

def _create_selected_table(path,overwrite):
    arcpy=_arcpy();w,n=os.path.split(path);delete_if_allowed(path,overwrite=overwrite);arcpy.management.CreateTable(w,n)
    for n,t in [("xsec_id","LONG"),("chain_m","DOUBLE"),("bf_level","DOUBLE"),("bf_width","DOUBLE"),("local_med","DOUBLE"),("width_dev","DOUBLE"),("level_jump","DOUBLE"),("left_x","DOUBLE"),("left_y","DOUBLE"),("left_z","DOUBLE"),("right_x","DOUBLE"),("right_y","DOUBLE"),("right_z","DOUBLE")]: add_field(path,n,t)
    for n,l in [("reach_id",128),("sel_method",64),("confidence",16),("review_req",8),("qa_flag",128),("qa_reason",512)]: add_text_field(path,n,l)

def _create_selected_points(path,sr,overwrite):
    arcpy=_arcpy();w,n=os.path.split(path);delete_if_allowed(path,overwrite=overwrite);arcpy.management.CreateFeatureclass(w,n,"POINT",spatial_reference=sr)
    for n,t in [("xsec_id","LONG"),("chain_m","DOUBLE"),("bf_level","DOUBLE"),("bank_z","DOUBLE"),("bf_width","DOUBLE")]: add_field(path,n,t)
    for n,l in [("reach_id",128),("side",16),("sel_method",64),("confidence",16),("review_req",8)]: add_text_field(path,n,l)

def _create_selected_lines(path,sr,overwrite):
    arcpy=_arcpy();w,n=os.path.split(path);delete_if_allowed(path,overwrite=overwrite);arcpy.management.CreateFeatureclass(w,n,"POLYLINE",spatial_reference=sr)
    for n,t in [("xsec_id","LONG"),("chain_m","DOUBLE"),("bf_level","DOUBLE"),("bf_width","DOUBLE")]: add_field(path,n,t)
    for n,l in [("reach_id",128),("sel_method",64),("confidence",16),("review_req",8)]: add_text_field(path,n,l)

def _create_qa_table(path,overwrite):
    arcpy=_arcpy();w,n=os.path.split(path);delete_if_allowed(path,overwrite=overwrite);arcpy.management.CreateTable(w,n)
    for n,t in [("xsec_id","LONG"),("chain_m","DOUBLE")]: add_field(path,n,t)
    for n,l in [("reach_id",128),("qa_flag",128),("qa_reason",512),("review_req",8)]: add_text_field(path,n,l)

def select_best_candidates(candidate_table,candidate_points,candidate_width_lines,width_jump_threshold,elevation_jump_threshold_m,moving_window_size,output_selected_points,output_selected_width_lines,output_selected_table,output_qa_flags,overwrite=True):
    arcpy=_arcpy(); del candidate_points
    sr=arcpy.Describe(candidate_width_lines).spatialReference
    candidates=_read_candidates(candidate_table)
    refs_by_reach=_build_local_references(candidates)
    cand_by_xsec=defaultdict(list)
    for c in candidates:
        c["score"]=_base_score(c)
        cand_by_xsec[int(c["xsec_id"])].append(c)

    ref_lookup={r["xsec_id"]:r for lst in refs_by_reach.values() for r in lst}
    window=max(1,int(moving_window_size)); half=max(1,window//2)
    final_rows=[]
    for xsec_id,rows in cand_by_xsec.items():
        row0=rows[0]; reach_id=str(row0.get("reach_id")); chain_m=float(row0.get("chain_m") or 0.0)
        reach_refs=refs_by_reach.get(reach_id,[])
        idx=next((i for i,r in enumerate(reach_refs) if r["xsec_id"]==xsec_id),None)
        if idx is None: continue
        lo=max(0,idx-half); hi=min(len(reach_refs),idx+half+1)
        local_widths=[r["median_width"] for r in reach_refs[lo:hi] if r.get("median_width") is not None]
        local_levels=[r["median_level"] for r in reach_refs[lo:hi] if r.get("median_level") is not None]
        local_med=median(local_widths) if local_widths else None
        nbr_levels=[r for j,r in enumerate(reach_refs) if j in {idx-1,idx+1}]
        for row in rows:
            score=float(row["score"]); flags=[]; reasons=[]
            width_dev=None
            if local_med and local_med>0 and row.get("bf_width") is not None:
                width_dev=abs(float(row["bf_width"])-local_med)/local_med
                if width_dev>width_jump_threshold: score-=0.2; flags.append("width_jump"); reasons.append(f"width deviation {width_dev:.2f} exceeds threshold {width_jump_threshold:g}")
            level_jump=0.0
            if row.get("bf_level") is not None:
                jumps=[abs(float(row["bf_level"])-float(n["median_level"])) for n in nbr_levels if n.get("median_level") is not None]
                if jumps: level_jump=max(jumps)
            if level_jump>elevation_jump_threshold_m: score-=0.2; flags.append("level_jump"); reasons.append(f"level jump {level_jump:.2f} m exceeds threshold {elevation_jump_threshold_m:g} m")
            if row.get("cand_flag") not in (None,"","ok"): flags.append(str(row.get("cand_flag"))); reasons.append(str(row.get("reason") or row.get("cand_flag")))
            if int(row.get("water_reaches_profile_edge") or 0)==1: flags.append("water_reaches_profile_edge"); reasons.append("candidate water level reaches cross-section edge; cross section may be too short")
            if row.get("left_x") is None or row.get("right_x") is None: score-=0.3; flags.append("missing_bank")
            score=max(0.0,min(1.0,score)); conf=_confidence_label(score); review="Yes" if conf=="Low" or flags else "No"
            final_rows.append({"_score":score,"xsec_id":xsec_id,"reach_id":reach_id,"chain_m":chain_m,"sel_method":row["method"],"bf_level":row.get("bf_level"),"bf_width":row.get("bf_width"),"confidence":conf,"review_req":review,"qa_flag":";".join(flags) if flags else "ok","qa_reason":"; ".join(reasons) if reasons else "selected candidate passed continuity checks","local_med":local_med,"width_dev":width_dev,"level_jump":level_jump,"left_x":row.get("left_x"),"left_y":row.get("left_y"),"left_z":row.get("left_z"),"right_x":row.get("right_x"),"right_y":row.get("right_y"),"right_z":row.get("right_z")})

    best_by_xsec={}
    for row in final_rows:
        xid=int(row["xsec_id"])
        if xid not in best_by_xsec or row["_score"]>best_by_xsec[xid]["_score"]: best_by_xsec[xid]=row
    final_rows=list(best_by_xsec.values())

    _create_selected_table(output_selected_table,overwrite); _create_selected_points(output_selected_points,sr,overwrite); _create_selected_lines(output_selected_width_lines,sr,overwrite); _create_qa_table(output_qa_flags,overwrite)
    with arcpy.da.InsertCursor(output_selected_table,SELECTED_FIELDS) as tc, arcpy.da.InsertCursor(output_selected_points,["SHAPE@","xsec_id","reach_id","chain_m","side","sel_method","bf_level","bank_z","bf_width","confidence","review_req"]) as pc, arcpy.da.InsertCursor(output_selected_width_lines,["SHAPE@","xsec_id","reach_id","chain_m","sel_method","bf_level","bf_width","confidence","review_req"]) as lc, arcpy.da.InsertCursor(output_qa_flags,["xsec_id","reach_id","chain_m","qa_flag","qa_reason","review_req"]) as qc:
        for row in sorted(final_rows,key=lambda r:(r["reach_id"],r["chain_m"])):
            tc.insertRow(tuple(row[f] for f in SELECTED_FIELDS))
            lp,rp=_arcpy().Point(row["left_x"],row["left_y"]),_arcpy().Point(row["right_x"],row["right_y"])
            for side,pt,bz in (("left",lp,row["left_z"]),("right",rp,row["right_z"])):
                pc.insertRow((_arcpy().PointGeometry(pt,sr),row["xsec_id"],row["reach_id"],row["chain_m"],side,row["sel_method"],row["bf_level"],bz,row["bf_width"],row["confidence"],row["review_req"]))
            lc.insertRow((_arcpy().Polyline(_arcpy().Array([lp,rp]),sr),row["xsec_id"],row["reach_id"],row["chain_m"],row["sel_method"],row["bf_level"],row["bf_width"],row["confidence"],row["review_req"]))
            qc.insertRow((row["xsec_id"],row["reach_id"],row["chain_m"],row["qa_flag"],row["qa_reason"],row["review_req"]))
    add_message(f"Selected final bankfull candidates for {len(final_rows)} cross sections.")
    return {"selected_points":output_selected_points,"selected_width_lines":output_selected_width_lines,"selected_table":output_selected_table,"qa_flags":output_qa_flags}
