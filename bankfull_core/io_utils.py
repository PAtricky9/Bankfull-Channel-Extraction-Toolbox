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


def clean_name(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(name)).strip("_") or "bf01"

def run_output_name(run_name: str, suffix: str) -> str:
    return f"{clean_name(run_name)}_{suffix}"

def prepare_inputs(
    stream_centerline: str,
    dem_raster: str,
    project_folder: str,
    output_gdb_name: str,
    dem_clip_buffer: str | float | None = None,
    dissolve_stream: bool = True,
    check_projection: bool = True,
    overwrite: bool = True,
    run_name: str = "bf01",
    reach_mode: str = "Treat all input streams as one reach",
    reach_field: str | None = None,
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

    run_id = clean_name(run_name)
    prepared_stream = output_path(gdb, run_output_name(run_id, "stream"))
    delete_if_allowed(prepared_stream, overwrite=overwrite)
    if dissolve_stream:
        add_message("Dissolving stream centreline.")
        arcpy.management.Dissolve(stream_centerline, prepared_stream)
    else:
        add_message("Copying stream centreline.")
        arcpy.management.CopyFeatures(stream_centerline, prepared_stream)

    add_field(prepared_stream, "reach_id", "LONG")
    source_oid = arcpy.Describe(prepared_stream).OIDFieldName
    with arcpy.da.UpdateCursor(prepared_stream, [source_oid, "reach_id", reach_field] if reach_field else [source_oid, "reach_id"]) as cursor:
        for row in cursor:
            if reach_mode == "Treat all input streams as one reach":
                row[1] = 1
            elif reach_mode == "Use a selected reach ID field" and reach_field:
                row[1] = int(row[2]) if row[2] not in (None, "") else int(row[0])
            else:
                row[1] = int(row[0])
            cursor.updateRow(row)

    processing_boundary = output_path(gdb, run_output_name(run_id, "boundary"))
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
        clipped_dem = output_path(gdb, run_output_name(run_id, "dem_clip"))
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

    config_rows = [
        ("stream_centerline", stream_centerline),
        ("dem_raster", dem_raster),
        ("project_folder", project_folder),
        ("output_gdb", gdb),
        ("dem_clip_buffer", dem_clip_buffer or ""),
        ("dissolve_stream", dissolve_stream),
        ("check_projection", check_projection),
        ("stream_spatial_reference", stream_sr),
        ("dem_spatial_reference", dem_sr),
        ("toolbox_version", "0.2.0"),
        ("run_name", run_name),
        ("reach_mode", reach_mode),
        ("reach_field", reach_field or ""),
    ]
    config_table = create_config_table(gdb, run_output_name(run_id, "run_params"), config_rows, overwrite)

    return {
        "output_gdb": gdb,
        "prepared_stream": prepared_stream,
        "clipped_dem": clipped_dem,
        "processing_boundary": processing_boundary,
        "project_config": config_table,
    }
