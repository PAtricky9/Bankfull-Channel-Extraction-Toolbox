from __future__ import annotations

from pathlib import Path

from bankfull_core.candidate_detection import (
    hydraulic_breakpoint_candidate,
    slope_threshold_candidate,
)


def _profile_rows() -> list[dict]:
    return [
        {
            "xsec_id": 1,
            "reach_id": "1",
            "chain_m": 0,
            "dist_left": 0,
            "dist_ctr": -5,
            "elev_m": 12,
            "slope_deg": 20,
            "x": 0,
            "y": 0,
        },
        {
            "xsec_id": 1,
            "reach_id": "1",
            "chain_m": 0,
            "dist_left": 5,
            "dist_ctr": 0,
            "elev_m": 10,
            "slope_deg": 2,
            "x": 5,
            "y": 0,
        },
        {
            "xsec_id": 1,
            "reach_id": "1",
            "chain_m": 0,
            "dist_left": 10,
            "dist_ctr": 5,
            "elev_m": 12,
            "slope_deg": 20,
            "x": 10,
            "y": 0,
        },
    ]


def test_slope_threshold_candidate() -> None:
    rows = _profile_rows()
    thalweg = {"dist_ctr": 0, "thalweg_z": 10}
    cand = slope_threshold_candidate(rows, thalweg, 15, None)
    assert cand is not None
    assert cand["method"] == "slope_threshold"
    assert abs(cand["bf_width"] - 10) < 1e-6
    assert cand["height_above_thalweg"] == 2


def test_hydraulic_breakpoint_candidate() -> None:
    rows = _profile_rows()
    thalweg = {"dist_ctr": 0, "thalweg_z": 10}
    curve = [
        {
            "xsec_id": 1,
            "wl_z": 11.0,
            "wl_above": 1.0,
            "top_w_m": 8.0,
            "flow_area": 5.0,
            "hyd_depth": 0.6,
            "width_rate": 2.0,
            "area_rate": 1.0,
            "hyd_rate": 0.2,
            "left_edge_wet": 1,
            "right_edge_wet": 0,
            "section_too_short": 1,
            "water_reaches_profile_edge": 1,
            "valid": 1,
        }
    ]
    cand = hydraulic_breakpoint_candidate(rows, curve, thalweg, 0.0, None)
    assert cand is not None
    assert cand["method"] == "hydraulic_breakpoint"
    assert cand["left_edge_wet"] == 1
    assert cand["right_edge_wet"] == 0
    assert cand["water_reaches_profile_edge"] == 1
    assert cand["width_reason"] == "water_reaches_profile_edge"
    assert cand["height_above_thalweg"] == 1
    assert cand["conf_raw"] <= 0.35


def test_no_known_bad_f_string_pattern() -> None:
    source = Path("bankfull_core/candidate_detection.py").read_text(encoding="utf-8")
    assert 'f"width_rate={float(best.get("' not in source
    assert "width_rate = float(best.get(" in source


def run() -> None:
    test_slope_threshold_candidate()
    test_hydraulic_breakpoint_candidate()
    test_no_known_bad_f_string_pattern()


if __name__ == "__main__":
    run()
    print("basic tests passed")
