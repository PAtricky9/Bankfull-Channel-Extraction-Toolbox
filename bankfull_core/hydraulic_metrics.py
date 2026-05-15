"""Thalweg detection and cross-sectional hydraulic metrics."""

from __future__ import annotations

import math
import os
from collections import defaultdict
from typing import Iterable

from .io_utils import add_field, add_message, add_text_field, delete_if_allowed


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


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


def clean_profile_rows(rows: Iterable[dict]) -> list[dict]:
    """Return profile rows sorted by distance, excluding missing elevations."""
    clean = []
    for row in rows:
        elev = _to_float(row.get("elev_m"))
        dist = _to_float(row.get("dist_left"))
        if elev is None or dist is None:
            continue
        new_row = dict(row)
        new_row["elev_m"] = elev
        new_row["dist_left"] = dist
        clean.append(new_row)
    clean.sort(key=lambda item: item["dist_left"])
    return clean


def detect_thalweg(profile_rows: list[dict], centre_search_m: float) -> dict | None:
    """Find the lowest valid profile point close to the centreline."""
    clean = clean_profile_rows(profile_rows)
    if not clean:
        return None
    candidates = [
        (idx, row)
        for idx, row in enumerate(clean)
        if abs(float(row.get("dist_ctr") or 0.0)) <= centre_search_m
    ]
    if not candidates:
        candidates = list(enumerate(clean))
        flag = "outside_search_window"
        confidence = 0.35
    else:
        flag = "ok"
        confidence = 0.8
    idx, row = min(candidates, key=lambda item: item[1]["elev_m"])
    result = dict(row)
    result["profile_index"] = idx
    result["thalweg_z"] = row["elev_m"]
    result["thalweg_flag"] = flag
    result["thalweg_conf"] = confidence
    return result


def _interpolate_at_level(left: dict, right: dict, water_level: float) -> dict:
    z1 = float(left["elev_m"])
    z2 = float(right["elev_m"])
    if z1 == z2:
        t = 0.0
    else:
        t = (water_level - z1) / (z2 - z1)
    t = min(1.0, max(0.0, t))
    out = {}
    for key in ("dist_left", "dist_ctr", "x", "y"):
        a = _to_float(left.get(key))
        b = _to_float(right.get(key))
        out[key] = None if a is None or b is None else a + (b - a) * t
    out["elev_m"] = water_level
    return out


def connected_wetted_region(
    profile_rows: list[dict],
    thalweg_index: int,
    water_level: float,
) -> dict | None:
    """Return the wetted region connected to the thalweg for one water level."""
    profile = clean_profile_rows(profile_rows)
    if not profile or thalweg_index < 0 or thalweg_index >= len(profile):
        return None
    if profile[thalweg_index]["elev_m"] > water_level:
        return None

    left_idx = thalweg_index
    while left_idx > 0 and profile[left_idx - 1]["elev_m"] <= water_level:
        left_idx -= 1
    right_idx = thalweg_index
    while right_idx < len(profile) - 1 and profile[right_idx + 1]["elev_m"] <= water_level:
        right_idx += 1

    left_edge_wet = left_idx == 0
    right_edge_wet = right_idx == len(profile) - 1

    if left_idx > 0:
        left_boundary = _interpolate_at_level(
            profile[left_idx - 1], profile[left_idx], water_level
        )
    else:
        left_boundary = dict(profile[left_idx])
        left_boundary["elev_m"] = min(left_boundary["elev_m"], water_level)

    if right_idx < len(profile) - 1:
        right_boundary = _interpolate_at_level(
            profile[right_idx], profile[right_idx + 1], water_level
        )
    else:
        right_boundary = dict(profile[right_idx])
        right_boundary["elev_m"] = min(right_boundary["elev_m"], water_level)

    wet_points = [left_boundary]
    wet_points.extend(profile[left_idx : right_idx + 1])
    wet_points.append(right_boundary)

    deduped = []
    last_dist = None
    for point in wet_points:
        dist = _to_float(point.get("dist_left"))
        if dist is None:
            continue
        if last_dist is not None and abs(dist - last_dist) < 1e-9:
            deduped[-1] = point
        else:
            deduped.append(point)
            last_dist = dist

    if len(deduped) < 2:
        return None

    left_dist = float(deduped[0]["dist_left"])
    right_dist = float(deduped[-1]["dist_left"])
    top_width = right_dist - left_dist
    if top_width <= 0:
        return None

    area = 0.0
    for a, b in zip(deduped[:-1], deduped[1:]):
        da = max(0.0, water_level - float(a["elev_m"]))
        db = max(0.0, water_level - float(b["elev_m"]))
        width = float(b["dist_left"]) - float(a["dist_left"])
        area += (da + db) * 0.5 * width

    return {
        "left": deduped[0],
        "right": deduped[-1],
        "points": deduped,
        "top_width_m": top_width,
        "flow_area_m2": area,
        "hydraulic_depth_m": area / top_width if top_width > 0 else None,
        "left_edge_wet": int(left_edge_wet),
        "right_edge_wet": int(right_edge_wet),
        "section_too_short": 1 if left_edge_wet or right_edge_wet else 0,
        "water_reaches_profile_edge": 1 if left_edge_wet or right_edge_wet else 0,
    }


def hydraulic_curve_for_profile(
    profile_rows: list[dict],
    thalweg_index: int,
    thalweg_z: float,
    max_height_m: float,
    level_step_m: float,
    min_top_width_m: float,
) -> list[dict]:
    """Calculate hydraulic curve rows for one cross section."""
    if level_step_m <= 0:
        raise ValueError("Water level step must be greater than zero.")
    if max_height_m <= 0:
        raise ValueError("Maximum water level above thalweg must be greater than zero.")

    levels = []
    height = 0.0
    while height <= max_height_m + (level_step_m * 0.001):
        levels.append(height)
        height += level_step_m

    curve = []
    for height in levels:
        wl_z = thalweg_z + height
        region = connected_wetted_region(profile_rows, thalweg_index, wl_z)
        valid = region is not None and region["top_width_m"] >= min_top_width_m
        curve.append(
            {
                "wl_z": wl_z,
                "wl_above": height,
                "top_w_m": region["top_width_m"] if region else None,
                "flow_area": region["flow_area_m2"] if region else None,
                "hyd_depth": region["hydraulic_depth_m"] if region else None,
                "width_rate": None,
                "area_rate": None,
                "hyd_depth_rate": None,
                "left_edge_wet": region["left_edge_wet"] if region else 0,
                "right_edge_wet": region["right_edge_wet"] if region else 0,
                "section_too_short": region["section_too_short"] if region else 0,
                "water_reaches_profile_edge": region["water_reaches_profile_edge"] if region else 0,
                "valid": 1 if valid else 0,
            }
        )

    previous = None
    for row in curve:
        if previous and row["valid"] and previous["valid"]:
            delta_h = row["wl_above"] - previous["wl_above"]
            if delta_h > 0:
                row["width_rate"] = (row["top_w_m"] - previous["top_w_m"]) / delta_h
                row["area_rate"] = (row["flow_area"] - previous["flow_area"]) / delta_h
                row["hyd_depth_rate"] = (
                    row["hyd_depth"] - previous["hyd_depth"]
                ) / delta_h
        if row["valid"]:
            previous = row
    return curve


def _read_profile_table(profile_table: str) -> dict[int, list[dict]]:
    arcpy = _arcpy()
    grouped: dict[int, list[dict]] = defaultdict(list)
    fields = [
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
    with arcpy.da.SearchCursor(profile_table, fields) as cursor:
        for values in cursor:
            row = dict(zip(fields, values))
            grouped[int(row["xsec_id"])].append(row)
    return grouped


def _create_thalweg_points(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POINT", spatial_reference=spatial_ref)
    add_field(path, "xsec_id", "LONG")
    add_field(path, "thalweg_x", "DOUBLE")
    add_field(path, "thalweg_y", "DOUBLE")
    add_field(path, "thalweg_z", "DOUBLE")
    add_field(path, "dist_ctr", "DOUBLE")
    add_field(path, "thal_conf", "DOUBLE")
    add_text_field(path, "thal_flag", 128)


def _create_hydraulic_table(path: str, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    add_field(path, "xsec_id", "LONG")
    add_field(path, "wl_z", "DOUBLE")
    add_field(path, "wl_above", "DOUBLE")
    add_field(path, "top_w_m", "DOUBLE")
    add_field(path, "flow_area", "DOUBLE")
    add_field(path, "hyd_depth", "DOUBLE")
    add_field(path, "width_rate", "DOUBLE")
    add_field(path, "area_rate", "DOUBLE")
    add_field(path, "hyd_rate", "DOUBLE")
    add_field(path, "left_edge_wet", "SHORT")
    add_field(path, "right_edge_wet", "SHORT")
    add_field(path, "section_too_short", "SHORT")
    add_field(path, "water_reaches_profile_edge", "SHORT")
    add_field(path, "valid", "SHORT")


def _create_profile_metrics_table(path: str, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    add_field(path, "xsec_id", "LONG")
    add_field(path, "valid_pts", "LONG")
    add_field(path, "nodata_pts", "LONG")
    add_field(path, "min_elev", "DOUBLE")
    add_field(path, "max_elev", "DOUBLE")
    add_field(path, "thalweg_z", "DOUBLE")
    add_text_field(path, "qa_flag", 128)


def detect_thalweg_and_hydraulic_metrics(
    profile_table: str,
    centre_search_m: float,
    max_water_height_m: float,
    water_level_step_m: float,
    min_top_width_m: float,
    output_thalweg_points: str,
    output_hydraulic_curve_table: str,
    output_profile_metrics_table: str,
    spatial_ref_source: str | None = None,
    overwrite: bool = True,
) -> dict[str, str]:
    """ArcPy wrapper for thalweg and hydraulic metrics."""
    arcpy = _arcpy()
    sr_source = spatial_ref_source or profile_table
    spatial_ref = arcpy.Describe(sr_source).spatialReference
    _create_thalweg_points(output_thalweg_points, spatial_ref, overwrite)
    _create_hydraulic_table(output_hydraulic_curve_table, overwrite)
    _create_profile_metrics_table(output_profile_metrics_table, overwrite)

    grouped = _read_profile_table(profile_table)
    thalweg_fields = [
        "SHAPE@",
        "xsec_id",
        "thalweg_x",
        "thalweg_y",
        "thalweg_z",
        "dist_ctr",
        "thal_conf",
        "thal_flag",
    ]
    curve_fields = [
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
    metrics_fields = [
        "xsec_id",
        "valid_pts",
        "nodata_pts",
        "min_elev",
        "max_elev",
        "thalweg_z",
        "qa_flag",
    ]

    thalweg_insert_rows = []
    curve_insert_rows = []
    metric_insert_rows = []

    for xsec_id, rows in sorted(grouped.items()):
        clean = clean_profile_rows(rows)
        nodata_count = len(rows) - len(clean)
        if len(clean) < 3:
            metric_insert_rows.append(
                (xsec_id, len(clean), nodata_count, None, None, None, "too_few_points")
            )
            continue
        thalweg = detect_thalweg(clean, centre_search_m)
        if not thalweg:
            metric_insert_rows.append(
                (xsec_id, len(clean), nodata_count, None, None, None, "no_thalweg")
            )
            continue

        point = arcpy.PointGeometry(
            arcpy.Point(thalweg.get("x"), thalweg.get("y")), spatial_ref
        )
        thalweg_insert_rows.append(
            (
                point,
                xsec_id,
                thalweg.get("x"),
                thalweg.get("y"),
                thalweg.get("thalweg_z"),
                thalweg.get("dist_ctr"),
                thalweg.get("thalweg_conf"),
                thalweg.get("thalweg_flag"),
            )
        )

        curve = hydraulic_curve_for_profile(
            clean,
            int(thalweg["profile_index"]),
            float(thalweg["thalweg_z"]),
            max_water_height_m,
            water_level_step_m,
            min_top_width_m,
        )
        for curve_row in curve:
            curve_insert_rows.append(
                (
                    xsec_id,
                    curve_row["wl_z"],
                    curve_row["wl_above"],
                    curve_row["top_w_m"],
                    curve_row["flow_area"],
                    curve_row["hyd_depth"],
                    curve_row["width_rate"],
                    curve_row["area_rate"],
                    curve_row["hyd_depth_rate"],
                    curve_row["left_edge_wet"],
                    curve_row["right_edge_wet"],
                    curve_row["section_too_short"],
                    curve_row["water_reaches_profile_edge"],
                    curve_row["valid"],
                )
            )

        elevations = [row["elev_m"] for row in clean]
        metric_insert_rows.append(
            (
                xsec_id,
                len(clean),
                nodata_count,
                min(elevations),
                max(elevations),
                thalweg.get("thalweg_z"),
                thalweg.get("thalweg_flag"),
            )
        )

    with arcpy.da.InsertCursor(output_thalweg_points, thalweg_fields) as cursor:
        for row in thalweg_insert_rows:
            cursor.insertRow(row)

    with arcpy.da.InsertCursor(output_hydraulic_curve_table, curve_fields) as cursor:
        for row in curve_insert_rows:
            cursor.insertRow(row)

    with arcpy.da.InsertCursor(output_profile_metrics_table, metrics_fields) as cursor:
        for row in metric_insert_rows:
            cursor.insertRow(row)

    add_message(f"Processed hydraulic metrics for {len(grouped)} cross sections.")
    return {
        "thalweg_points": output_thalweg_points,
        "hydraulic_curve_table": output_hydraulic_curve_table,
        "profile_metrics_table": output_profile_metrics_table,
    }
