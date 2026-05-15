"""Bankfull candidate detection from profile and hydraulic evidence."""

from __future__ import annotations

import math
import os
from collections import defaultdict
from statistics import mean, pstdev

from .hydraulic_metrics import (
    clean_profile_rows,
    connected_wetted_region,
    detect_thalweg,
)
from .io_utils import add_field, add_message, add_text_field, delete_if_allowed


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


PROFILE_FIELDS = [
    "xsec_id",
    "station_id",
    "reach_id",
    "chain_m",
    "pt_order",
    "dist_left",
    "dist_ctr",
    "x",
    "y",
    "elev_m",
    "slope_deg",
    "dem_nodata",
]

CURVE_FIELDS = [
    "xsec_id",
    "wl_z",
    "wl_above",
    "top_w_m",
    "flow_area",
    "hyd_depth",
    "width_rate",
    "area_rate",
    "hyd_rate",
    "left_edge_wet",
    "right_edge_wet",
    "section_too_short",
    "water_reaches_profile_edge",
    "valid",
]

CANDIDATE_FIELDS = [
    "xsec_id",
    "reach_id",
    "chain_m",
    "method",
    "bf_level",
    "left_x",
    "left_y",
    "left_z",
    "right_x",
    "right_y",
    "right_z",
    "bf_width",
    "conf_raw",
    "reason",
    "cand_flag",
    "left_edge_wet",
    "right_edge_wet",
    "water_reaches_profile_edge",
    "width_reason",
    "height_above_thalweg",
]


def _to_float(value):
    if value in (None, "", "NoData"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _read_grouped(table: str, fields: list[str]) -> dict[int, list[dict]]:
    arcpy = _arcpy()
    grouped: dict[int, list[dict]] = defaultdict(list)
    with arcpy.da.SearchCursor(table, fields) as cursor:
        for values in cursor:
            row = dict(zip(fields, values))
            grouped[int(row["xsec_id"])].append(row)
    return grouped


def _find_thalweg_index(profile: list[dict], thalweg: dict | None) -> int | None:
    if not profile:
        return None
    if thalweg and thalweg.get("dist_ctr") is not None:
        target = float(thalweg["dist_ctr"])
        return min(
            range(len(profile)),
            key=lambda idx: abs(float(profile[idx].get("dist_ctr") or 0.0) - target),
        )
    detected = detect_thalweg(profile, 999999.0)
    return int(detected["profile_index"]) if detected else None


def _point_from_row(row: dict) -> dict:
    return {
        "x": _to_float(row.get("x")),
        "y": _to_float(row.get("y")),
        "z": _to_float(row.get("elev_m")),
        "dist_left": _to_float(row.get("dist_left")),
        "dist_ctr": _to_float(row.get("dist_ctr")),
    }


def _candidate_from_bank_points(
    xsec_id: int,
    reach_id,
    chain_m,
    method: str,
    left: dict,
    right: dict,
    confidence: float,
    reason: str,
    flag: str,
    level: float | None = None,
) -> dict | None:
    if not left or not right:
        return None
    left_dist = _to_float(left.get("dist_left"))
    right_dist = _to_float(right.get("dist_left"))
    if left_dist is None or right_dist is None or right_dist <= left_dist:
        return None
    left_z = _to_float(left.get("z", left.get("elev_m")))
    right_z = _to_float(right.get("z", right.get("elev_m")))
    if level is None:
        if left_z is None or right_z is None:
            return None
        level = min(left_z, right_z)
    return {
        "xsec_id": xsec_id,
        "reach_id": str(reach_id),
        "chain_m": chain_m,
        "method": method,
        "bf_level": level,
        "left_x": left.get("x"),
        "left_y": left.get("y"),
        "left_z": left_z if left_z is not None else level,
        "right_x": right.get("x"),
        "right_y": right.get("y"),
        "right_z": right_z if right_z is not None else level,
        "bf_width": right_dist - left_dist,
        "conf_raw": max(0.0, min(1.0, confidence)),
        "reason": reason,
        "cand_flag": flag,
        "left_edge_wet": 0,
        "right_edge_wet": 0,
        "water_reaches_profile_edge": 0,
        "width_reason": "ok",
        "height_above_thalweg": None,
    }


def slope_threshold_candidate(
    profile_rows: list[dict],
    thalweg: dict | None,
    slope_threshold_deg: float,
    max_bankfull_height_m: float | None,
) -> dict | None:
    profile = clean_profile_rows(profile_rows)
    thal_idx = _find_thalweg_index(profile, thalweg)
    if thal_idx is None:
        return None
    thal_z = float(profile[thal_idx]["elev_m"])

    def plausible(row: dict) -> bool:
        elev = _to_float(row.get("elev_m"))
        slope = _to_float(row.get("slope_deg"))
        if elev is None or slope is None:
            return False
        if max_bankfull_height_m is not None and elev - thal_z > max_bankfull_height_m:
            return False
        return slope >= slope_threshold_deg

    left_matches = [row for row in reversed(profile[:thal_idx]) if plausible(row)]
    right_matches = [row for row in profile[thal_idx + 1 :] if plausible(row)]
    flag = "ok"
    confidence = 0.68
    reason = f"slope >= {slope_threshold_deg:g} degrees on both banks"

    if left_matches and right_matches:
        left_row = left_matches[0]
        right_row = right_matches[0]
    else:
        left_side = [row for row in profile[:thal_idx] if _to_float(row.get("slope_deg")) is not None]
        right_side = [row for row in profile[thal_idx + 1 :] if _to_float(row.get("slope_deg")) is not None]
        if not left_side or not right_side:
            return None
        left_row = max(left_side, key=lambda row: float(row.get("slope_deg") or 0.0))
        right_row = max(right_side, key=lambda row: float(row.get("slope_deg") or 0.0))
        flag = "threshold_not_met"
        confidence = 0.35
        reason = "used strongest slope peaks because threshold was not met on both banks"

    xsec_id = int(profile[0]["xsec_id"])
    cand = _candidate_from_bank_points(
        xsec_id,
        profile[0].get("reach_id"),
        profile[0].get("chain_m"),
        "slope_threshold",
        _point_from_row(left_row),
        _point_from_row(right_row),
        confidence,
        reason,
        flag,
    )
    if cand is not None:
        cand["height_above_thalweg"] = (
            float(cand["bf_level"]) - thal_z
            if cand.get("bf_level") is not None
            else None
        )
    return cand


def hydraulic_breakpoint_candidate(
    profile_rows: list[dict],
    curve_rows: list[dict],
    thalweg: dict | None,
    sensitivity: float,
    max_bankfull_height_m: float | None,
) -> dict | None:
    profile = clean_profile_rows(profile_rows)
    thal_idx = _find_thalweg_index(profile, thalweg)
    if thal_idx is None:
        return None

    valid = []
    for row in curve_rows:
        if int(row.get("valid") or 0) != 1:
            continue
        wl_above = _to_float(row.get("wl_above"))
        width_rate = _to_float(row.get("width_rate"))
        if wl_above is None or width_rate is None or wl_above <= 0:
            continue
        if max_bankfull_height_m is not None and wl_above > max_bankfull_height_m:
            continue
        valid.append(row)
    if not valid:
        return None

    rates = [max(0.0, float(row.get("width_rate") or 0.0)) for row in valid]
    rate_mean = mean(rates)
    rate_std = pstdev(rates) if len(rates) > 1 else 0.0
    scored = []
    for row, rate in zip(valid, rates):
        z_score = (rate - rate_mean) / rate_std if rate_std > 0 else rate
        hyd_rate = abs(float(row.get("hyd_rate") or 0.0))
        score = z_score + min(hyd_rate, 5.0) * 0.05
        scored.append((score, row))
    score, best = max(scored, key=lambda item: item[0])
    water_level = float(best["wl_z"])
    region = connected_wetted_region(profile, thal_idx, water_level)
    if not region:
        return None

    left_edge_wet = int(best.get("left_edge_wet") or region.get("left_edge_wet") or 0)
    right_edge_wet = int(best.get("right_edge_wet") or region.get("right_edge_wet") or 0)
    water_edge = int(
        best.get("water_reaches_profile_edge")
        or region.get("water_reaches_profile_edge")
        or 0
    )
    width_rate = float(best.get("width_rate") or 0.0)
    area_rate = float(best.get("area_rate") or 0.0)
    hyd_rate = float(best.get("hyd_rate") or 0.0)

    flag = "ok" if score >= sensitivity else "weak_breakpoint"
    if water_edge and flag == "ok":
        flag = "water_reaches_profile_edge"
    elif water_edge:
        flag = f"{flag};water_reaches_profile_edge"
    confidence = 0.72 if score >= sensitivity else 0.42
    reason = (
        f"largest hydraulic width-rate breakpoint, score={score:.2f}, "
        f"sensitivity={sensitivity:g}, width_rate={width_rate:.3f}, "
        f"area_rate={area_rate:.3f}, hyd_rate={hyd_rate:.3f}"
    )
    xsec_id = int(profile[0]["xsec_id"])
    left = dict(region["left"])
    left["z"] = water_level
    right = dict(region["right"])
    right["z"] = water_level
    cand = _candidate_from_bank_points(
        xsec_id,
        profile[0].get("reach_id"),
        profile[0].get("chain_m"),
        "hydraulic_breakpoint",
        left,
        right,
        confidence,
        reason,
        flag,
        level=water_level,
    )
    if cand is not None:
        height_above = water_level - float(profile[thal_idx]["elev_m"])
        cand["left_edge_wet"] = left_edge_wet
        cand["right_edge_wet"] = right_edge_wet
        cand["water_reaches_profile_edge"] = water_edge
        cand["width_reason"] = "water_reaches_profile_edge" if water_edge else "ok"
        cand["height_above_thalweg"] = height_above
        if water_edge:
            cand["conf_raw"] = min(float(cand["conf_raw"] or 0.0), 0.35)
    return cand


def agreement_candidate(slope_candidate: dict | None, hydraulic_candidate: dict | None) -> dict | None:
    if not slope_candidate or not hydraulic_candidate:
        return None
    width_a = slope_candidate.get("bf_width")
    width_b = hydraulic_candidate.get("bf_width")
    level_a = slope_candidate.get("bf_level")
    level_b = hydraulic_candidate.get("bf_level")
    if not all(value is not None for value in (width_a, width_b, level_a, level_b)):
        return None

    width_ref = max(float(width_a), float(width_b), 0.001)
    width_ratio = abs(float(width_a) - float(width_b)) / width_ref
    level_delta = abs(float(level_a) - float(level_b))
    agrees = width_ratio <= 0.25 and level_delta <= 0.5
    base = hydraulic_candidate if hydraulic_candidate["conf_raw"] >= slope_candidate["conf_raw"] else slope_candidate
    candidate = dict(base)
    candidate["method"] = "agreement"
    if agrees:
        candidate["conf_raw"] = min(1.0, max(base["conf_raw"], 0.82))
        candidate["reason"] = (
            "slope and hydraulic candidates agree "
            f"(width difference {width_ratio:.2f}, level difference {level_delta:.2f} m)"
        )
        candidate["cand_flag"] = "ok"
    else:
        candidate["conf_raw"] = min(base["conf_raw"], 0.45)
        candidate["reason"] = (
            "slope and hydraulic candidates diverge "
            f"(width difference {width_ratio:.2f}, level difference {level_delta:.2f} m)"
        )
        candidate["cand_flag"] = "methods_diverge"
    return candidate


def _create_candidate_table(path: str, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "method", 64)
    add_field(path, "bf_level", "DOUBLE")
    add_field(path, "left_x", "DOUBLE")
    add_field(path, "left_y", "DOUBLE")
    add_field(path, "left_z", "DOUBLE")
    add_field(path, "right_x", "DOUBLE")
    add_field(path, "right_y", "DOUBLE")
    add_field(path, "right_z", "DOUBLE")
    add_field(path, "bf_width", "DOUBLE")
    add_field(path, "conf_raw", "DOUBLE")
    add_text_field(path, "reason", 512)
    add_text_field(path, "cand_flag", 128)
    add_field(path, "left_edge_wet", "SHORT")
    add_field(path, "right_edge_wet", "SHORT")
    add_field(path, "water_reaches_profile_edge", "SHORT")
    add_text_field(path, "width_reason", 128)
    add_field(path, "height_above_thalweg", "DOUBLE")


def _create_candidate_points(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POINT", spatial_reference=spatial_ref)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "method", 64)
    add_text_field(path, "side", 16)
    add_field(path, "bf_level", "DOUBLE")
    add_field(path, "bank_z", "DOUBLE")
    add_field(path, "bf_width", "DOUBLE")
    add_field(path, "conf_raw", "DOUBLE")
    add_text_field(path, "cand_flag", 128)
    add_field(path, "left_edge_wet", "SHORT")
    add_field(path, "right_edge_wet", "SHORT")
    add_field(path, "water_reaches_profile_edge", "SHORT")
    add_text_field(path, "width_reason", 128)
    add_field(path, "height_above_thalweg", "DOUBLE")


def _create_candidate_lines(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POLYLINE", spatial_reference=spatial_ref)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "method", 64)
    add_field(path, "bf_level", "DOUBLE")
    add_field(path, "bf_width", "DOUBLE")
    add_field(path, "conf_raw", "DOUBLE")
    add_text_field(path, "cand_flag", 128)
    add_field(path, "left_edge_wet", "SHORT")
    add_field(path, "right_edge_wet", "SHORT")
    add_field(path, "water_reaches_profile_edge", "SHORT")
    add_text_field(path, "width_reason", 128)
    add_field(path, "height_above_thalweg", "DOUBLE")


def detect_bankfull_candidates(
    profile_table: str,
    hydraulic_curve_table: str,
    thalweg_points: str,
    slope_threshold_deg: float,
    hydraulic_sensitivity: float,
    max_bankfull_height_m: float | None,
    output_candidate_points: str,
    output_candidate_width_lines: str,
    output_candidate_table: str,
    overwrite: bool = True,
) -> dict[str, str]:
    """Generate slope, hydraulic, and agreement bankfull candidates."""
    arcpy = _arcpy()
    spatial_ref = arcpy.Describe(thalweg_points).spatialReference
    profiles = _read_grouped(profile_table, PROFILE_FIELDS)
    curves = _read_grouped(hydraulic_curve_table, CURVE_FIELDS)
    thalwegs = {}
    with arcpy.da.SearchCursor(
        thalweg_points, ["xsec_id", "thalweg_z", "dist_ctr", "thal_conf", "thal_flag"]
    ) as cursor:
        for xsec_id, thalweg_z, dist_ctr, thal_conf, thal_flag in cursor:
            thalwegs[int(xsec_id)] = {
                "thalweg_z": thalweg_z,
                "dist_ctr": dist_ctr,
                "thal_conf": thal_conf,
                "thal_flag": thal_flag,
            }

    _create_candidate_table(output_candidate_table, overwrite)
    _create_candidate_points(output_candidate_points, spatial_ref, overwrite)
    _create_candidate_lines(output_candidate_width_lines, spatial_ref, overwrite)

    table_insert_fields = CANDIDATE_FIELDS
    point_fields = [
        "SHAPE@",
        "xsec_id",
        "reach_id",
        "chain_m",
        "method",
        "side",
        "bf_level",
        "bank_z",
        "bf_width",
        "conf_raw",
        "cand_flag",
        "left_edge_wet",
        "right_edge_wet",
        "water_reaches_profile_edge",
        "width_reason",
        "height_above_thalweg",
    ]
    line_fields = [
        "SHAPE@",
        "xsec_id",
        "reach_id",
        "chain_m",
        "method",
        "bf_level",
        "bf_width",
        "conf_raw",
        "cand_flag",
        "left_edge_wet",
        "right_edge_wet",
        "water_reaches_profile_edge",
        "width_reason",
        "height_above_thalweg",
    ]

    total = 0
    with arcpy.da.InsertCursor(output_candidate_table, table_insert_fields) as table_cursor:
        with arcpy.da.InsertCursor(output_candidate_points, point_fields) as point_cursor:
            with arcpy.da.InsertCursor(output_candidate_width_lines, line_fields) as line_cursor:
                for xsec_id, profile_rows in sorted(profiles.items()):
                    thalweg = thalwegs.get(xsec_id)
                    slope = slope_threshold_candidate(
                        profile_rows,
                        thalweg,
                        slope_threshold_deg,
                        max_bankfull_height_m,
                    )
                    hydraulic = hydraulic_breakpoint_candidate(
                        profile_rows,
                        curves.get(xsec_id, []),
                        thalweg,
                        hydraulic_sensitivity,
                        max_bankfull_height_m,
                    )
                    candidates = [
                        cand
                        for cand in (slope, hydraulic, agreement_candidate(slope, hydraulic))
                        if cand is not None
                    ]
                    for candidate in candidates:
                        table_cursor.insertRow(tuple(candidate[field] for field in table_insert_fields))
                        left_pt = arcpy.Point(candidate["left_x"], candidate["left_y"])
                        right_pt = arcpy.Point(candidate["right_x"], candidate["right_y"])
                        for side, pt, bank_z in (
                            ("left", left_pt, candidate["left_z"]),
                            ("right", right_pt, candidate["right_z"]),
                        ):
                            point_cursor.insertRow(
                                (
                                    arcpy.PointGeometry(pt, spatial_ref),
                                    candidate["xsec_id"],
                                    candidate["reach_id"],
                                    candidate["chain_m"],
                                    candidate["method"],
                                    side,
                                    candidate["bf_level"],
                                    bank_z,
                                    candidate["bf_width"],
                                    candidate["conf_raw"],
                                    candidate["cand_flag"],
                                    candidate["left_edge_wet"],
                                    candidate["right_edge_wet"],
                                    candidate["water_reaches_profile_edge"],
                                    candidate["width_reason"],
                                    candidate["height_above_thalweg"],
                                )
                            )
                        line_cursor.insertRow(
                            (
                                arcpy.Polyline(arcpy.Array([left_pt, right_pt]), spatial_ref),
                                candidate["xsec_id"],
                                candidate["reach_id"],
                                candidate["chain_m"],
                                candidate["method"],
                                candidate["bf_level"],
                                candidate["bf_width"],
                                candidate["conf_raw"],
                                candidate["cand_flag"],
                                candidate["left_edge_wet"],
                                candidate["right_edge_wet"],
                                candidate["water_reaches_profile_edge"],
                                candidate["width_reason"],
                                candidate["height_above_thalweg"],
                            )
                        )
                        total += 1

    add_message(f"Generated {total} bankfull candidates.")
    return {
        "candidate_points": output_candidate_points,
        "candidate_width_lines": output_candidate_width_lines,
        "candidate_table": output_candidate_table,
    }
