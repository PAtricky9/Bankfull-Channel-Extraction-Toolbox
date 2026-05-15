"""Input preparation and ArcPy utility helpers."""

from __future__ import annotations

import datetime as _dt
import os


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


def add_message(message: str) -> None:
    """Send a message to ArcGIS when available, otherwise print it."""
    try:
        _arcpy().AddMessage(message)
    except Exception:
        print(message)


def add_warning(message: str) -> None:
    """Send a warning to ArcGIS when available, otherwise print it."""
    try:
        _arcpy().AddWarning(message)
    except Exception:
        print(f"WARNING: {message}")


def add_error(message: str) -> None:
    """Send an error to ArcGIS when available, otherwise print it."""
    try:
        _arcpy().AddError(message)
    except Exception:
        print(f"ERROR: {message}")


def output_path(workspace: str, name: str) -> str:
    return os.path.join(workspace, name)


def clean_name(name: str | None) -> str:
    """Return a short ArcGIS-friendly lowercase token for run-based outputs."""
    cleaned = "".join(
        ch.lower() if ch.isalnum() else "_" for ch in str(name or "")
    )
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "bf01"


def run_output_name(run_name: str | None, suffix: str) -> str:
    """Create a standard run-scoped dataset name such as bf01_xsecs."""
    clean_suffix = clean_name(suffix)
    return f"{clean_name(run_name)}_{clean_suffix}"


def resolve_run_output_path(workspace: str, run_name: str | None, suffix: str) -> str:
    """Resolve a standard run-scoped dataset path inside a workspace."""
    return output_path(workspace, run_output_name(run_name, suffix))


RUN_PARAMETER_FIELDS = [
    "tool_name",
    "run_name",
    "param_name",
    "param_value",
    "input_path",
    "output_path",
    "recorded_utc",
    "toolbox_version",
]


def _ensure_run_parameter_table(workspace: str, run_name: str | None) -> str:
    """Create the run parameter table if needed and ensure expected fields exist."""
    arcpy = _arcpy()
    table_name = run_output_name(run_name, "run_params")
    table = output_path(workspace, table_name)
    if not arcpy.Exists(table):
        arcpy.management.CreateTable(workspace, table_name)

    add_text_field(table, "tool_name", 128)
    add_text_field(table, "run_name", 128)
    add_text_field(table, "param_name", 128)
    add_text_field(table, "param_value", 2048)
    add_text_field(table, "input_path", 1024)
    add_text_field(table, "output_path", 1024)
    add_text_field(table, "recorded_utc", 64)
    add_text_field(table, "toolbox_version", 64)
    return table


def _iter_parameter_items(parameters) -> list[tuple[str, object]]:
    if parameters is None:
        return []
    if hasattr(parameters, "items"):
        return list(parameters.items())
    return list(parameters)


def read_run_param(
    workspace: str,
    run_name: str | None,
    param_name: str,
) -> str | None:
    """Read the most recent value for a run parameter, if the table exists."""
    arcpy = _arcpy()
    table = resolve_run_output_path(workspace, run_name, "run_params")
    if not arcpy.Exists(table):
        return None

    fields = [field.name for field in arcpy.ListFields(table)]
    if "param_name" not in fields or "param_value" not in fields:
        return None

    value = None
    with arcpy.da.SearchCursor(table, ["param_name", "param_value"]) as cursor:
        for key, param_value in cursor:
            if key == param_name:
                value = param_value
    return value


def append_run_parameters(
    workspace: str,
    run_name: str | None,
    tool_name: str,
    parameters,
    input_paths: dict[str, str] | None = None,
    output_paths: dict[str, str] | None = None,
    toolbox_version: str = "0.1.0",
) -> str:
    """Append parameter records to the run-scoped parameter table.

    This helper is intentionally additive and is not wired into the current
    toolbox workflow yet.
    """
    arcpy = _arcpy()
    table = _ensure_run_parameter_table(workspace, run_name)
    recorded_utc = _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    input_paths = input_paths or {}
    output_paths = output_paths or {}

    with arcpy.da.InsertCursor(table, RUN_PARAMETER_FIELDS) as cursor:
        for key, value in _iter_parameter_items(parameters):
            name = str(key)
            cursor.insertRow(
                (
                    tool_name,
                    clean_name(run_name),
                    name,
                    "" if value is None else str(value),
                    input_paths.get(name, ""),
                    output_paths.get(name, ""),
                    recorded_utc,
                    toolbox_version,
                )
            )
    return table


def log_stage_parameters(
    workspace: str,
    run_name: str | None,
    tool_name: str,
    parameters,
    input_paths: dict[str, str] | None = None,
    output_paths: dict[str, str] | None = None,
    toolbox_version: str = "0.1.0",
) -> str:
    """Alias for append_run_parameters with stage-oriented naming."""
    return append_run_parameters(
        workspace,
        run_name,
        tool_name,
        parameters,
        input_paths=input_paths,
        output_paths=output_paths,
        toolbox_version=toolbox_version,
    )


def ensure_file_geodatabase(project_folder: str, gdb_name: str) -> str:
    """Create the project folder and geodatabase if needed."""
    arcpy = _arcpy()
    os.makedirs(project_folder, exist_ok=True)
    if not gdb_name.lower().endswith(".gdb"):
        gdb_name = f"{gdb_name}.gdb"
    gdb_path = os.path.join(project_folder, gdb_name)
    if not arcpy.Exists(gdb_path):
        add_message(f"Creating output geodatabase: {gdb_path}")
        arcpy.management.CreateFileGDB(project_folder, gdb_name)
    return gdb_path


def require_exists(path: str, label: str) -> None:
    arcpy = _arcpy()
    if not arcpy.Exists(path):
        raise ValueError(f"{label} does not exist: {path}")


def delete_if_allowed(path: str, overwrite: bool = True) -> None:
    arcpy = _arcpy()
    if arcpy.Exists(path):
        if not overwrite:
            raise ValueError(f"Output already exists: {path}")
        add_warning(f"Overwriting existing output: {path}")
        arcpy.management.Delete(path)


def get_spatial_reference_name(dataset: str) -> str:
    arcpy = _arcpy()
    sr = arcpy.Describe(dataset).spatialReference
    if sr is None:
        return "Unknown"
    return sr.name or "Unknown"


def assert_polyline(feature_class: str) -> None:
    arcpy = _arcpy()
    shape_type = arcpy.Describe(feature_class).shapeType
    if str(shape_type).lower() != "polyline":
        raise ValueError(
            f"Stream centreline must be a polyline feature class, got {shape_type}."
        )


def add_text_field(table: str, name: str, length: int = 255) -> None:
    arcpy = _arcpy()
    if name not in [field.name for field in arcpy.ListFields(table)]:
        arcpy.management.AddField(table, name, "TEXT", field_length=length)


def add_field(table: str, name: str, field_type: str, **kwargs) -> None:
    arcpy = _arcpy()
    if name not in [field.name for field in arcpy.ListFields(table)]:
        arcpy.management.AddField(table, name, field_type, **kwargs)


def create_config_table(
    workspace: str,
    table_name: str,
    rows: list[tuple[str, str]],
    overwrite: bool = True,
) -> str:
    """Write a simple key-value project configuration table."""
    arcpy = _arcpy()
    table = output_path(workspace, table_name)
    delete_if_allowed(table, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, table_name)
    add_text_field(table, "param_name", 128)
    add_text_field(table, "param_value", 1024)
    add_text_field(table, "recorded_utc", 64)
    recorded_utc = _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    with arcpy.da.InsertCursor(
        table, ["param_name", "param_value", "recorded_utc"]
    ) as cursor:
        for key, value in rows:
            cursor.insertRow((key, str(value), recorded_utc))
    return table


def prepare_inputs(
    stream_centerline: str,
    dem_raster: str,
    project_folder: str,
    output_gdb_name: str,
    run_name: str | None = None,
    dem_clip_buffer: str | float | None = None,
    dissolve_stream: bool = True,
    check_projection: bool = True,
    overwrite: bool = True,
) -> dict[str, str | None]:
    """Prepare the stream, optional DEM clip, boundary, and config table."""
    arcpy = _arcpy()
    require_exists(stream_centerline, "Stream centreline")
    require_exists(dem_raster, "DEM raster")
    assert_polyline(stream_centerline)

    gdb = ensure_file_geodatabase(project_folder, output_gdb_name)
    arcpy.env.workspace = gdb

    stream_sr = get_spatial_reference_name(stream_centerline)
    dem_sr = get_spatial_reference_name(dem_raster)
    if check_projection and stream_sr != dem_sr:
        add_warning(
            "Stream centreline and DEM coordinate systems differ: "
            f"stream={stream_sr}, dem={dem_sr}. Project inputs before relying on "
            "distance-based parameters."
        )

    prepared_stream_name = (
        run_output_name(run_name, "stream") if run_name else "prepared_stream_centerline"
    )
    boundary_name = (
        run_output_name(run_name, "boundary") if run_name else "processing_boundary"
    )
    dem_clip_name = run_output_name(run_name, "dem_clip") if run_name else "dem_clipped"

    prepared_stream = output_path(gdb, prepared_stream_name)
    delete_if_allowed(prepared_stream, overwrite=overwrite)
    if dissolve_stream:
        add_message("Dissolving stream centreline.")
        arcpy.management.Dissolve(stream_centerline, prepared_stream)
    else:
        add_message("Copying stream centreline.")
        arcpy.management.CopyFeatures(stream_centerline, prepared_stream)

    processing_boundary = output_path(gdb, boundary_name)
    clipped_dem = None
    if dem_clip_buffer not in (None, "", 0, "0"):
        delete_if_allowed(processing_boundary, overwrite=overwrite)
        add_message("Creating processing boundary from stream buffer.")
        arcpy.analysis.Buffer(
            prepared_stream,
            processing_boundary,
            dem_clip_buffer,
            dissolve_option="ALL",
        )
        clipped_dem = output_path(gdb, dem_clip_name)
        delete_if_allowed(clipped_dem, overwrite=overwrite)
        add_message("Clipping DEM to processing boundary.")
        try:
            from arcpy.sa import ExtractByMask  # type: ignore

            arcpy.CheckOutExtension("Spatial")
            ExtractByMask(dem_raster, processing_boundary).save(clipped_dem)
        except Exception as exc:
            add_warning(
                "DEM clipping through Spatial Analyst failed. The original DEM "
                f"will be used by later tools. Details: {exc}"
            )
            clipped_dem = None
    else:
        delete_if_allowed(processing_boundary, overwrite=overwrite)
        add_message("Creating processing boundary from stream extent.")
        arcpy.management.MinimumBoundingGeometry(
            prepared_stream,
            processing_boundary,
            "ENVELOPE",
            "ALL",
        )

    dem_for_processing = clipped_dem or dem_raster
    config_rows = [
        ("run_name", clean_name(run_name) if run_name else ""),
        ("stream_centerline", stream_centerline),
        ("dem_raster", dem_raster),
        ("dem_for_processing", dem_for_processing),
        ("project_folder", project_folder),
        ("output_gdb", gdb),
        ("dem_clip_buffer", dem_clip_buffer or ""),
        ("dissolve_stream", dissolve_stream),
        ("check_projection", check_projection),
        ("stream_spatial_reference", stream_sr),
        ("dem_spatial_reference", dem_sr),
        ("toolbox_version", "0.1.0"),
    ]
    if run_name:
        output_rows = [
            ("prepared_stream", prepared_stream),
            ("processing_boundary", processing_boundary),
            ("clipped_dem", clipped_dem or ""),
        ]
        config_table = append_run_parameters(
            gdb,
            run_name,
            "01 Prepare Inputs",
            config_rows + output_rows,
            input_paths={
                "stream_centerline": stream_centerline,
                "dem_raster": dem_raster,
            },
            output_paths={
                "output_gdb": gdb,
                "prepared_stream": prepared_stream,
                "processing_boundary": processing_boundary,
                "clipped_dem": clipped_dem or "",
            },
        )
    else:
        config_table = create_config_table(gdb, "project_config", config_rows, overwrite)

    return {
        "output_gdb": gdb,
        "prepared_stream": prepared_stream,
        "clipped_dem": clipped_dem,
        "processing_boundary": processing_boundary,
        "project_config": config_table,
    }
