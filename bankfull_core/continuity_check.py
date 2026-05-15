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


SELECTED_FIELDS = [
    "xsec_id",
    "reach_id",
    "chain_m",
    "sel_method",
    "bf_level",
    "bf_width",
    "confidence",
    "review_req",
    "qa_flag",
    "qa_reason",
    "local_med",
    "width_dev",
    "level_jump",
    "left_x",
    "left_y",
    "left_z",
    "right_x",
    "right_y",
    "right_z",
]


def _read_candidates(candidate_table: str) -> list[dict]:
    arcpy = _arcpy()
    rows = []
    with arcpy.da.SearchCursor(candidate_table, CANDIDATE_FIELDS) as cursor:
        for values in cursor:
            row = dict(zip(CANDIDATE_FIELDS, values))
            rows.append(row)
    return rows


def _base_score(candidate: dict) -> float:
    score = float(candidate.get("conf_raw") or 0.0)
    if candidate.get("method") == "agreement":
        score += 0.12
    if candidate.get("cand_flag") not in (None, "", "ok"):
        score -= 0.12
    if int(candidate.get("water_reaches_profile_edge") or 0) == 1:
        score -= 0.2
    if candidate.get("left_x") is None or candidate.get("right_x") is None:
        score -= 0.3
    return max(0.0, min(1.0, score))


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def _create_selected_table(path: str, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "sel_method", 64)
    add_field(path, "bf_level", "DOUBLE")
    add_field(path, "bf_width", "DOUBLE")
    add_text_field(path, "confidence", 16)
    add_text_field(path, "review_req", 8)
    add_text_field(path, "qa_flag", 128)
    add_text_field(path, "qa_reason", 512)
    add_field(path, "local_med", "DOUBLE")
    add_field(path, "width_dev", "DOUBLE")
    add_field(path, "level_jump", "DOUBLE")
    add_field(path, "left_x", "DOUBLE")
    add_field(path, "left_y", "DOUBLE")
    add_field(path, "left_z", "DOUBLE")
    add_field(path, "right_x", "DOUBLE")
    add_field(path, "right_y", "DOUBLE")
    add_field(path, "right_z", "DOUBLE")


def _create_selected_points(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POINT", spatial_reference=spatial_ref)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "side", 16)
    add_text_field(path, "sel_method", 64)
    add_field(path, "bf_level", "DOUBLE")
    add_field(path, "bank_z", "DOUBLE")
    add_field(path, "bf_width", "DOUBLE")
    add_text_field(path, "confidence", 16)
    add_text_field(path, "review_req", 8)


def _create_selected_lines(path: str, spatial_ref, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POLYLINE", spatial_reference=spatial_ref)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "sel_method", 64)
    add_field(path, "bf_level", "DOUBLE")
    add_field(path, "bf_width", "DOUBLE")
    add_text_field(path, "confidence", 16)
    add_text_field(path, "review_req", 8)


def _create_qa_table(path: str, overwrite: bool) -> None:
    arcpy = _arcpy()
    workspace, name = os.path.split(path)
    delete_if_allowed(path, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    add_field(path, "xsec_id", "LONG")
    add_text_field(path, "reach_id", 128)
    add_field(path, "chain_m", "DOUBLE")
    add_text_field(path, "qa_flag", 128)
    add_text_field(path, "qa_reason", 512)
    add_text_field(path, "review_req", 8)


def select_best_candidates(
    candidate_table: str,
    candidate_points: str,
    candidate_width_lines: str,
    width_jump_threshold: float,
    elevation_jump_threshold_m: float,
    moving_window_size: int,
    output_selected_points: str,
    output_selected_width_lines: str,
    output_selected_table: str,
    output_qa_flags: str,
    overwrite: bool = True,
) -> dict[str, str]:
    """Select one bankfull candidate per cross section and flag discontinuities."""
    arcpy = _arcpy()
    spatial_ref = arcpy.Describe(candidate_width_lines).spatialReference
    candidates = _read_candidates(candidate_table)
    by_xsec: dict[int, list[dict]] = defaultdict(list)
    for candidate in candidates:
        by_xsec[int(candidate["xsec_id"])].append(candidate)

    selected = []
    for xsec_id, rows in by_xsec.items():
        for r in rows: r["score"] = _base_score(r)
        selected.extend(rows)

    by_reach: dict[str, list[dict]] = defaultdict(list)
    for row in selected:
        by_reach[str(row.get("reach_id"))].append(row)

    final_rows = []
    window = max(1, int(moving_window_size))
    half_window = max(1, window // 2)
    for reach_id, rows in by_reach.items():
        rows.sort(key=lambda item: float(item.get("chain_m") or 0.0))
        for idx, row in enumerate(rows):
            lo = max(0, idx - half_window)
            hi = min(len(rows), idx + half_window + 1)
            widths = [
                float(item["bf_width"])
                for item in rows[lo:hi]
                if item.get("bf_width") is not None
            ]
            local_med = median(widths) if widths else None
            width_dev = None
            if local_med and local_med > 0 and row.get("bf_width") is not None:
                width_dev = abs(float(row["bf_width"]) - local_med) / local_med

            level_jumps = []
            if idx > 0 and row.get("bf_level") is not None and rows[idx - 1].get("bf_level") is not None:
                level_jumps.append(abs(float(row["bf_level"]) - float(rows[idx - 1]["bf_level"])))
            if idx < len(rows) - 1 and row.get("bf_level") is not None and rows[idx + 1].get("bf_level") is not None:
                level_jumps.append(abs(float(row["bf_level"]) - float(rows[idx + 1]["bf_level"])))
            level_jump = max(level_jumps) if level_jumps else 0.0

            score = float(row["score"])
            reasons = []
            flags = []
            if width_dev is not None and width_dev > width_jump_threshold:
                score -= 0.2
                flags.append("width_jump")
                reasons.append(f"width deviation {width_dev:.2f} exceeds threshold {width_jump_threshold:g}")
            if level_jump > elevation_jump_threshold_m:
                score -= 0.2
                flags.append("level_jump")
                reasons.append(f"level jump {level_jump:.2f} m exceeds threshold {elevation_jump_threshold_m:g} m")
            if row.get("cand_flag") not in (None, "", "ok"):
                flags.append(str(row.get("cand_flag")))
            if int(row.get("water_reaches_profile_edge") or 0) == 1:
                flags.append("water_reaches_profile_edge")
                reasons.append("water level reached profile edge")
                reasons.append(str(row.get("reason") or row.get("cand_flag")))
            if row.get("left_x") is None or row.get("right_x") is None:
                score -= 0.3
                flags.append("missing_bank")
                reasons.append("missing left or right bank point")

            score = max(0.0, min(1.0, score))
            confidence = _confidence_label(score)
            review_req = "Yes" if confidence == "Low" or flags else "No"
            final = {
                "_score": score,
                "xsec_id": row["xsec_id"],
                "reach_id": reach_id,
                "chain_m": row["chain_m"],
                "sel_method": row["method"],
                "bf_level": row["bf_level"],
                "bf_width": row["bf_width"],
                "confidence": confidence,
                "review_req": review_req,
                "qa_flag": ";".join(flags) if flags else "ok",
                "qa_reason": "; ".join(reasons) if reasons else "selected candidate passed continuity checks",
                "local_med": local_med,
                "width_dev": width_dev,
                "level_jump": level_jump,
                "left_x": row["left_x"],
                "left_y": row["left_y"],
                "left_z": row["left_z"],
                "right_x": row["right_x"],
                "right_y": row["right_y"],
                "right_z": row["right_z"],
            }
            final_rows.append(final)


    # choose best per cross section only after continuity/QA penalties
    best_by_xsec = {}
    for row in final_rows:
        xid = int(row["xsec_id"])
        if xid not in best_by_xsec or row.get("_score",0) > best_by_xsec[xid].get("_score",0):
            best_by_xsec[xid] = row
    final_rows = list(best_by_xsec.values())

    _create_selected_table(output_selected_table, overwrite)
    _create_selected_points(output_selected_points, spatial_ref, overwrite)
    _create_selected_lines(output_selected_width_lines, spatial_ref, overwrite)
    _create_qa_table(output_qa_flags, overwrite)

    with arcpy.da.InsertCursor(output_selected_table, SELECTED_FIELDS) as table_cursor:
        with arcpy.da.InsertCursor(
            output_selected_points,
            [
                "SHAPE@",
                "xsec_id",
                "reach_id",
                "chain_m",
                "side",
                "sel_method",
                "bf_level",
                "bank_z",
                "bf_width",
                "confidence",
                "review_req",
            ],
        ) as point_cursor:
            with arcpy.da.InsertCursor(
                output_selected_width_lines,
                [
                    "SHAPE@",
                    "xsec_id",
                    "reach_id",
                    "chain_m",
                    "sel_method",
                    "bf_level",
                    "bf_width",
                    "confidence",
                    "review_req",
                ],
            ) as line_cursor:
                with arcpy.da.InsertCursor(
                    output_qa_flags,
                    ["xsec_id", "reach_id", "chain_m", "qa_flag", "qa_reason", "review_req"],
                ) as qa_cursor:
                    for row in sorted(final_rows, key=lambda item: (item["reach_id"], item["chain_m"] or 0)):
                        table_cursor.insertRow(tuple(row[field] for field in SELECTED_FIELDS))
                        left_point = arcpy.Point(row["left_x"], row["left_y"])
                        right_point = arcpy.Point(row["right_x"], row["right_y"])
                        for side, point, bank_z in (
                            ("left", left_point, row["left_z"]),
                            ("right", right_point, row["right_z"]),
                        ):
                            point_cursor.insertRow(
                                (
                                    arcpy.PointGeometry(point, spatial_ref),
                                    row["xsec_id"],
                                    row["reach_id"],
                                    row["chain_m"],
                                    side,
                                    row["sel_method"],
                                    row["bf_level"],
                                    bank_z,
                                    row["bf_width"],
                                    row["confidence"],
                                    row["review_req"],
                                )
                            )
                        line_cursor.insertRow(
                            (
                                arcpy.Polyline(arcpy.Array([left_point, right_point]), spatial_ref),
                                row["xsec_id"],
                                row["reach_id"],
                                row["chain_m"],
                                row["sel_method"],
                                row["bf_level"],
                                row["bf_width"],
                                row["confidence"],
                                row["review_req"],
                            )
                        )
                        qa_cursor.insertRow(
                            (
                                row["xsec_id"],
                                row["reach_id"],
                                row["chain_m"],
                                row["qa_flag"],
                                row["qa_reason"],
                                row["review_req"],
                            )
                        )

    add_message(f"Selected final bankfull candidates for {len(final_rows)} cross sections.")
    return {
        "selected_points": output_selected_points,
        "selected_width_lines": output_selected_width_lines,
        "selected_table": output_selected_table,
        "qa_flags": output_qa_flags,
    }
