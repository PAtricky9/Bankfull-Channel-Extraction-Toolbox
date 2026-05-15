"""QA report generation for bankfull extraction outputs."""

from __future__ import annotations

import csv
import os
from collections import Counter

from .candidate_detection import CANDIDATE_FIELDS
from .continuity_check import SELECTED_FIELDS
from .io_utils import add_message


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


def _read_rows(table: str, fields: list[str]) -> list[dict]:
    arcpy = _arcpy()
    rows = []
    with arcpy.da.SearchCursor(table, fields) as cursor:
        for values in cursor:
            rows.append(dict(zip(fields, values)))
    return rows


def _read_config(config_table: str) -> list[tuple[str, str]]:
    arcpy = _arcpy()
    fields = [field.name for field in arcpy.ListFields(config_table)]
    if "param_name" not in fields or "param_value" not in fields:
        return []
    rows = []
    with arcpy.da.SearchCursor(config_table, ["param_name", "param_value"]) as cursor:
        for key, value in cursor:
            rows.append((key, value))
    return rows


def _write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def generate_qa_report(
    selected_bankfull_table: str,
    qa_flags_table: str,
    candidate_table: str,
    project_config_table: str,
    output_report_folder: str,
) -> dict[str, str]:
    """Create CSV and Markdown QA summaries."""
    os.makedirs(output_report_folder, exist_ok=True)
    selected = _read_rows(selected_bankfull_table, SELECTED_FIELDS)
    candidates = _read_rows(candidate_table, CANDIDATE_FIELDS)
    qa_rows = _read_rows(
        qa_flags_table,
        ["xsec_id", "reach_id", "chain_m", "qa_flag", "qa_reason", "review_req"],
    )
    config = _read_config(project_config_table)

    confidence_counts = Counter(row.get("confidence") for row in selected)
    review_count = sum(1 for row in selected if row.get("review_req") == "Yes")
    widths = [float(row["bf_width"]) for row in selected if row.get("bf_width") is not None]
    width_stats = {
        "average_bankfull_width_m": sum(widths) / len(widths) if widths else None,
        "minimum_bankfull_width_m": min(widths) if widths else None,
        "maximum_bankfull_width_m": max(widths) if widths else None,
    }

    summary_rows = [
        {"metric": "total_cross_sections", "value": len(selected)},
        {"metric": "successful_selected_results", "value": len(widths)},
        {"metric": "high_confidence", "value": confidence_counts.get("High", 0)},
        {"metric": "medium_confidence", "value": confidence_counts.get("Medium", 0)},
        {"metric": "low_confidence", "value": confidence_counts.get("Low", 0)},
        {"metric": "manual_review_required", "value": review_count},
        {"metric": "candidate_count", "value": len(candidates)},
    ]
    summary_rows.extend(
        {"metric": key, "value": value} for key, value in width_stats.items()
    )

    qa_summary_csv = os.path.join(output_report_folder, "qa_summary.csv")
    low_confidence_csv = os.path.join(output_report_folder, "low_confidence_cross_sections.csv")
    parameter_summary_md = os.path.join(output_report_folder, "parameter_summary.md")
    qa_flags_csv = os.path.join(output_report_folder, "qa_flags.csv")

    _write_csv(qa_summary_csv, summary_rows, ["metric", "value"])
    low_rows = [
        row
        for row in selected
        if row.get("confidence") == "Low" or row.get("review_req") == "Yes"
    ]
    _write_csv(low_confidence_csv, low_rows, SELECTED_FIELDS)
    _write_csv(qa_flags_csv, qa_rows, ["xsec_id", "reach_id", "chain_m", "qa_flag", "qa_reason", "review_req"])

    largest_width_jumps = sorted(
        selected,
        key=lambda row: float(row.get("width_dev") or 0.0),
        reverse=True,
    )[:10]
    largest_level_jumps = sorted(
        selected,
        key=lambda row: float(row.get("level_jump") or 0.0),
        reverse=True,
    )[:10]

    with open(parameter_summary_md, "w", encoding="utf-8") as handle:
        handle.write("# Bankfull Channel Extractor QA Report\n\n")
        handle.write("## Summary\n\n")
        for row in summary_rows:
            handle.write(f"- {row['metric']}: {row['value']}\n")
        handle.write("\n## Largest Width Deviations\n\n")
        for row in largest_width_jumps:
            handle.write(
                f"- xsec_id {row.get('xsec_id')}: width {row.get('bf_width')} m, "
                f"deviation ratio {row.get('width_dev')}\n"
            )
        handle.write("\n## Largest Bankfull Level Jumps\n\n")
        for row in largest_level_jumps:
            handle.write(
                f"- xsec_id {row.get('xsec_id')}: level {row.get('bf_level')} m, "
                f"jump {row.get('level_jump')} m\n"
            )
        handle.write("\n## Parameters And Inputs\n\n")
        for key, value in config:
            handle.write(f"- {key}: {value}\n")
        handle.write("\n## Known Limitations\n\n")
        handle.write(
            "- Candidate detection is a transparent first version and requires manual QA.\n"
            "- Cross-sectional flow area is a two-dimensional profile metric, not a mapped inundation area.\n"
            "- Bridges, culverts, vegetation, DEM voids and adjacent drains can affect results.\n"
        )

    add_message(f"QA report written to {output_report_folder}.")
    return {
        "qa_summary_csv": qa_summary_csv,
        "low_confidence_csv": low_confidence_csv,
        "qa_flags_csv": qa_flags_csv,
        "parameter_summary_md": parameter_summary_md,
    }

