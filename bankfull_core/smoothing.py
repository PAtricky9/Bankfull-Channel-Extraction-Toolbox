"""Optional transparent smoothing for selected bank points."""

from __future__ import annotations

import os
from collections import defaultdict
from statistics import median

from .continuity_check import SELECTED_FIELDS
from .io_utils import add_field, add_message, add_text_field, delete_if_allowed


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


def _read_rows(selected_table: str) -> dict[str, list[dict]]:
    arcpy = _arcpy()
    grouped: dict[str, list[dict]] = defaultdict(list)
    with arcpy.da.SearchCursor(selected_table, SELECTED_FIELDS) as cursor:
        for values in cursor:
            row = dict(zip(SELECTED_FIELDS, values))
            grouped[str(row["reach_id"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda item: float(item.get("chain_m") or 0.0))
    return grouped


def _create_points(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POINT", spatial_reference=spatial_ref)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "side", 16)
    add_text_field(path, "method", 64)
    add_field(path, "orig_x", "DOUBLE")
    add_field(path, "orig_y", "DOUBLE")
    add_field(path, "smooth_x", "DOUBLE")
    add_field(path, "smooth_y", "DOUBLE")
    add_text_field(path, "changed", 8)


def _create_polygon(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POLYGON", spatial_reference=spatial_ref)
    add_text_field(path, "reach_id", 128)
    add_field(path, "xsec_count", "LONG")
    add_text_field(path, "smooth_mth", 64)


def _create_log(path: str, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "side", 16)
    add_field(path, "delta_x", "DOUBLE")
    add_field(path, "delta_y", "DOUBLE")
    add_text_field(path, "reason", 512)


def _rolling_median(values: list[float], idx: int, half_window: int) -> float:
    lo = max(0, idx - half_window)
    hi = min(len(values), idx + half_window + 1)
    return median(values[lo:hi])


def smooth_bank_lines(
    selected_bankfull_points: str,
    selected_bankfull_table: str,
    smoothing_method: str,
    smoothing_window_size: int,
    preserve_low_confidence_points: bool,
    output_smoothed_points: str,
    output_smoothed_polygon: str,
    output_correction_log: str,
    overwrite: bool = True,
) -> dict[str, str]:
    """Smooth bank points with an optional rolling median."""
    arcpy = _arcpy()
    spatial_ref = arcpy.Describe(selected_bankfull_points).spatialReference
    grouped = _read_rows(selected_bankfull_table)

    method = (smoothing_method or "none").lower().replace(" ", "_")
    half_window = max(1, int(smoothing_window_size) // 2)
    smoothed_rows = []
    for reach_id, rows in grouped.items():
        left_x = [float(row["left_x"]) for row in rows]
        left_y = [float(row["left_y"]) for row in rows]
        right_x = [float(row["right_x"]) for row in rows]
        right_y = [float(row["right_y"]) for row in rows]
        for idx, row in enumerate(rows):
            out = dict(row)
            out["orig_left_x"] = row["left_x"]
            out["orig_left_y"] = row["left_y"]
            out["orig_right_x"] = row["right_x"]
            out["orig_right_y"] = row["right_y"]
            if method in {"rolling_median", "median"}:
                low_conf = row.get("confidence") == "Low"
                if preserve_low_confidence_points and low_conf:
                    reason = "preserved low confidence point"
                else:
                    out["left_x"] = _rolling_median(left_x, idx, half_window)
                    out["left_y"] = _rolling_median(left_y, idx, half_window)
                    out["right_x"] = _rolling_median(right_x, idx, half_window)
                    out["right_y"] = _rolling_median(right_y, idx, half_window)
                    reason = "rolling median smoothing"
            else:
                reason = "no smoothing"
            out["smooth_reason"] = reason
            smoothed_rows.append(out)

    _create_points(output_smoothed_points, spatial_ref, overwrite)
    _create_polygon(output_smoothed_polygon, spatial_ref, overwrite)
    _create_log(output_correction_log, overwrite)

    with arcpy.da.InsertCursor(
        output_smoothed_points,
        [
            "SHAPE@",
            "xsec_id",
            "reach_id",
            "chain_m",
            "side",
            "method",
            "orig_x",
            "orig_y",
            "smooth_x",
            "smooth_y",
            "changed",
        ],
    ) as point_cursor:
        with arcpy.da.InsertCursor(
            output_correction_log,
            ["xsec_id", "reach_id", "chain_m", "side", "delta_x", "delta_y", "reason"],
        ) as log_cursor:
            for row in smoothed_rows:
                for side in ("left", "right"):
                    orig_x = row[f"orig_{side}_x"]
                    orig_y = row[f"orig_{side}_y"]
                    smooth_x = row[f"{side}_x"]
                    smooth_y = row[f"{side}_y"]
                    delta_x = float(smooth_x) - float(orig_x)
                    delta_y = float(smooth_y) - float(orig_y)
                    changed = "Yes" if abs(delta_x) > 1e-9 or abs(delta_y) > 1e-9 else "No"
                    point = arcpy.Point(smooth_x, smooth_y)
                    point_cursor.insertRow(
                        (
                            arcpy.PointGeometry(point, spatial_ref),
                            row["xsec_id"],
                            row["reach_id"],
                            row["chain_m"],
                            side,
                            method,
                            orig_x,
                            orig_y,
                            smooth_x,
                            smooth_y,
                            changed,
                        )
                    )
                    log_cursor.insertRow(
                        (
                            row["xsec_id"],
                            row["reach_id"],
                            row["chain_m"],
                            side,
                            delta_x,
                            delta_y,
                            row["smooth_reason"],
                        )
                    )

    with arcpy.da.InsertCursor(
        output_smoothed_polygon, ["SHAPE@", "reach_id", "xsec_count", "smooth_mth"]
    ) as polygon_cursor:
        by_reach: dict[str, list[dict]] = defaultdict(list)
        for row in smoothed_rows:
            by_reach[str(row["reach_id"])].append(row)
        for reach_id, rows in by_reach.items():
            rows.sort(key=lambda item: float(item.get("chain_m") or 0.0))
            if len(rows) < 2:
                continue
            left_points = [arcpy.Point(row["left_x"], row["left_y"]) for row in rows]
            right_points = [arcpy.Point(row["right_x"], row["right_y"]) for row in rows]
            ring = left_points + list(reversed(right_points)) + [left_points[0]]
            polygon_cursor.insertRow(
                (arcpy.Polygon(arcpy.Array(ring), spatial_ref), reach_id, len(rows), method)
            )

    add_message(f"Created smoothed bankfull outputs for {len(grouped)} reaches.")
    return {
        "bankfull_points_smoothed": output_smoothed_points,
        "bankfull_polygon_smoothed": output_smoothed_polygon,
        "correction_log": output_correction_log,
    }
