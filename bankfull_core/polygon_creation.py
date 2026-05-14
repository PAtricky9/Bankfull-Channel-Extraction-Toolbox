"""Create bank lines and raw bankfull polygons from selected candidates."""

from __future__ import annotations

import os
from collections import defaultdict

from .continuity_check import SELECTED_FIELDS
from .io_utils import add_field, add_message, add_text_field, delete_if_allowed


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


def _read_selected(selected_table: str) -> dict[str, list[dict]]:
    arcpy = _arcpy()
    grouped: dict[str, list[dict]] = defaultdict(list)
    with arcpy.da.SearchCursor(selected_table, SELECTED_FIELDS) as cursor:
        for values in cursor:
            row = dict(zip(SELECTED_FIELDS, values))
            grouped[str(row["reach_id"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda item: float(item.get("chain_m") or 0.0))
    return grouped


def _create_line_fc(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POLYLINE", spatial_reference=spatial_ref)
    add_text_field(path, "reach_id", 128)
    add_text_field(path, "side", 16)
    add_field(path, "pt_count", "LONG")
    add_text_field(path, "qa_flag", 128)


def _create_polygon_fc(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POLYGON", spatial_reference=spatial_ref)
    add_text_field(path, "reach_id", 128)
    add_field(path, "xsec_count", "LONG")
    add_text_field(path, "qa_flag", 128)
    add_text_field(path, "qa_reason", 512)


def create_bankfull_polygon(
    selected_bankfull_points: str,
    selected_bankfull_width_lines: str,
    prepared_stream_centerline: str,
    selected_bankfull_table: str,
    output_polygon: str,
    output_left_bank_line: str,
    output_right_bank_line: str,
    overwrite: bool = True,
) -> dict[str, str]:
    """Create raw bank lines and bankfull polygons from selected bank points."""
    del selected_bankfull_points, prepared_stream_centerline
    arcpy = _arcpy()
    spatial_ref = arcpy.Describe(selected_bankfull_width_lines).spatialReference
    selected = _read_selected(selected_bankfull_table)

    _create_line_fc(output_left_bank_line, spatial_ref, overwrite)
    _create_line_fc(output_right_bank_line, spatial_ref, overwrite)
    _create_polygon_fc(output_polygon, spatial_ref, overwrite)

    with arcpy.da.InsertCursor(
        output_left_bank_line, ["SHAPE@", "reach_id", "side", "pt_count", "qa_flag"]
    ) as left_cursor:
        with arcpy.da.InsertCursor(
            output_right_bank_line, ["SHAPE@", "reach_id", "side", "pt_count", "qa_flag"]
        ) as right_cursor:
            with arcpy.da.InsertCursor(
                output_polygon, ["SHAPE@", "reach_id", "xsec_count", "qa_flag", "qa_reason"]
            ) as polygon_cursor:
                for reach_id, rows in selected.items():
                    valid_rows = [
                        row
                        for row in rows
                        if row.get("left_x") is not None
                        and row.get("left_y") is not None
                        and row.get("right_x") is not None
                        and row.get("right_y") is not None
                    ]
                    if len(valid_rows) < 2:
                        continue
                    left_points = [
                        arcpy.Point(row["left_x"], row["left_y"]) for row in valid_rows
                    ]
                    right_points = [
                        arcpy.Point(row["right_x"], row["right_y"]) for row in valid_rows
                    ]
                    left_line = arcpy.Polyline(arcpy.Array(left_points), spatial_ref)
                    right_line = arcpy.Polyline(arcpy.Array(right_points), spatial_ref)
                    left_cursor.insertRow((left_line, reach_id, "left", len(left_points), "ok"))
                    right_cursor.insertRow((right_line, reach_id, "right", len(right_points), "ok"))

                    ring_points = left_points + list(reversed(right_points)) + [left_points[0]]
                    polygon = arcpy.Polygon(arcpy.Array(ring_points), spatial_ref)
                    qa_flag = "ok"
                    qa_reason = "raw polygon created"
                    if polygon.isMultipart:
                        qa_flag = "multipart"
                        qa_reason = "polygon is multipart after construction; inspect geometry"
                    if polygon.area <= 0:
                        qa_flag = "zero_area"
                        qa_reason = "polygon has zero or negative area; inspect bank ordering"
                    polygon_cursor.insertRow(
                        (polygon, reach_id, len(valid_rows), qa_flag, qa_reason)
                    )

    add_message(f"Created raw bankfull polygons for {len(selected)} reaches.")
    return {
        "left_bank_line": output_left_bank_line,
        "right_bank_line": output_right_bank_line,
        "bankfull_polygon_raw": output_polygon,
    }
