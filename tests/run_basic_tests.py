from bankfull_core.candidate_detection import slope_threshold_candidate, hydraulic_breakpoint_candidate

def run():
    rows=[
        {"xsec_id":1,"reach_id":"1","chain_m":0,"dist_left":0,"dist_ctr":-5,"elev_m":12,"slope_deg":20,"x":0,"y":0},
        {"xsec_id":1,"reach_id":"1","chain_m":0,"dist_left":5,"dist_ctr":0,"elev_m":10,"slope_deg":2,"x":5,"y":0},
        {"xsec_id":1,"reach_id":"1","chain_m":0,"dist_left":10,"dist_ctr":5,"elev_m":12,"slope_deg":20,"x":10,"y":0},
    ]
    thalweg={"dist_ctr":0,"thalweg_z":10}
    cand=slope_threshold_candidate(rows,thalweg,15,None)
    assert cand is not None and cand["method"]=="slope_threshold" and abs(cand["bf_width"]-10)<1e-6

    curve=[{"xsec_id":1,"wl_z":11.0,"wl_above":1.0,"top_w_m":8.0,"flow_area":5.0,"hyd_depth":0.6,"width_rate":2.0,"area_rate":1.0,"hyd_rate":0.2,"left_edge_wet":1,"right_edge_wet":0,"section_too_short":1,"water_reaches_profile_edge":1,"valid":1}]
    cand2=hydraulic_breakpoint_candidate(rows,curve,thalweg,0.0,None)
    assert cand2 is not None and cand2["method"]=="hydraulic_breakpoint"
    assert cand2["left_edge_wet"]==1 and cand2["water_reaches_profile_edge"]==1

if __name__=='__main__':
    run()
    print('basic tests passed')
