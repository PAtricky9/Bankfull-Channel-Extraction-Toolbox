"""DEM profile sampling for cross sections."""

from __future__ import annotations

import os

from .io_utils import add_field, add_message, add_text_field, add_warning, delete_if_allowed


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


def _add_profile_schema(dataset: str, include_geometry_values: bool = True) -> None:
    add_field(dataset, "xsec_id", "LONG")
    add_field(dataset, "station_id", "LONG")
    add_text_field(dataset, "reach_id", 128)
    add_field(dataset, "chain_m", "DOUBLE")
    add_field(dataset, "pt_order", "LONG")
    add_field(dataset, "dist_left", "DOUBLE")
    add_field(dataset, "dist_ctr", "DOUBLE")
    if include_geometry_values:
        add_field(dataset, "x", "DOUBLE")
        add_field(dataset, "y", "DOUBLE")
    add_field(dataset, "elev_m", "DOUBLE")
    add_field(dataset, "slope_deg", "DOUBLE")
    add_field(dataset, "dem_nodata", "SHORT")


def _create_slope_raster(dem_raster: str, output_workspace: str, overwrite: bool) -> str:
    arcpy = _arcpy()
    slope_raster = os.path.join(output_workspace, "dem_slope_deg")
    delete_if_allowed(slope_raster, overwrite=overwrite)
    add_message("Creating slope raster in degrees.")
    from arcpy.sa import Slope  # type: ignore

    arcpy.CheckOutExtension("Spatial")
    Slope(dem_raster, "DEGREE").save(slope_raster)
    return slope_raster


def _sample_rasters_to_points(
    profile_points: str,
    dem_raster: str,
    slope_raster: str | None,
) -> None:
    arcpy = _arcpy()
    try:
        from arcpy.sa import ExtractMultiValuesToPoints  # type: ignore

        arcpy.CheckOutExtension("Spatial")
        rasters = [[dem_raster, "tmp_elev"]]
        if slope_raster:
            rasters.append([slope_raster, "tmp_slope"])
        ExtractMultiValuesToPoints(profile_points, rasters, "NONE")
        fields = ["tmp_elev", "elev_m", "dem_nodata"]
        if slope_raster:
            fields.insert(1, "tmp_slope")
            fields.insert(3, "slope_deg")
        with arcpy.da.UpdateCursor(profile_points, fields) as cursor:
            for row in cursor:
                if slope_raster:
                    tmp_elev, tmp_slope, elev, slope, _flag = row
                    elev = tmp_elev
                    slope = tmp_slope
                    cursor.updateRow((tmp_elev, tmp_slope, elev, slope, 1 if elev is None else 0))
                else:
                    tmp_elev, elev, _flag = row
                    elev = tmp_elev
                    cursor.updateRow((tmp_elev, elev, 1 if elev is None else 0))
        for field_name in ("tmp_elev", "tmp_slope"):
            if field_name in [field.name for field in arcpy.ListFields(profile_points)]:
                arcpy.management.DeleteField(profile_points, field_name)
    except Exception as exc:
        add_warning(
            "ExtractMultiValuesToPoints failed. Falling back to per-point "
            f"GetCellValue sampling, which is slower. Details: {exc}"
        )
        _sample_rasters_slow(profile_points, dem_raster, slope_raster)


def _get_cell_value(raster: str, x: float, y: float):
    arcpy = _arcpy()
    result = arcpy.management.GetCellValue(raster, f"{x} {y}")
    value = result.getOutput(0)
    if value in ("NoData", "", None):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _sample_rasters_slow(
    profile_points: str,
    dem_raster: str,
    slope_raster: str | None,
) -> None:
    arcpy = _arcpy()
    with arcpy.da.UpdateCursor(
        profile_points, ["x", "y", "elev_m", "slope_deg", "dem_nodata"]
    ) as cursor:
        for x, y, _elev, _slope, _nodata in cursor:
            elev = _get_cell_value(dem_raster, x, y)
            slope = _get_cell_value(slope_raster, x, y) if slope_raster else None
            cursor.updateRow((x, y, elev, slope, 1 if elev is None else 0))


def _populate_nodata_flag(profile_points: str) -> None:
    arcpy = _arcpy()
    with arcpy.da.UpdateCursor(profile_points, ["elev_m", "dem_nodata"]) as cursor:
        for elev, _flag in cursor:
            cursor.updateRow((elev, 1 if elev is None else 0))


def _copy_points_to_profile_table(profile_points: str, profile_table: str, overwrite: bool) -> str:
    arcpy = _arcpy()
    workspace, name = os.path.split(profile_table)
    delete_if_allowed(profile_table, overwrite=overwrite)
    arcpy.management.CreateTable(workspace, name)
    _add_profile_schema(profile_table, include_geometry_values=True)

    with arcpy.da.SearchCursor(profile_points, PROFILE_FIELDS) as search_cursor:
        with arcpy.da.InsertCursor(profile_table, PROFILE_FIELDS) as insert_cursor:
            for row in search_cursor:
                insert_cursor.insertRow(row)
    return profile_table


def sample_dem_profiles(
    cross_sections: str,
    dem_raster: str,
    sample_spacing_m: float,
    slope_raster: str | None,
    create_slope_if_missing: bool,
    output_profile_points: str,
    output_profile_table: str,
    overwrite: bool = True,
) -> dict[str, str | None]:
    """Densify cross sections and sample DEM elevation and optional slope."""
    arcpy = _arcpy()
    if sample_spacing_m <= 0:
        raise ValueError("Sample spacing must be greater than zero.")

    workspace, name = os.path.split(output_profile_points)
    spatial_ref = arcpy.Describe(cross_sections).spatialReference
    delete_if_allowed(output_profile_points, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(
        workspace, name, "POINT", spatial_reference=spatial_ref
    )
    _add_profile_schema(output_profile_points, include_geometry_values=True)

    if not slope_raster and create_slope_if_missing:
        slope_raster = _create_slope_raster(dem_raster, workspace, overwrite)

    add_message("Creating profile sample points.")
    cross_fields = ["SHAPE@", "xsec_id", "station_id", "reach_id", "chain_m"]
    insert_fields = ["SHAPE@"] + PROFILE_FIELDS
    point_count = 0
    with arcpy.da.InsertCursor(output_profile_points, insert_fields) as insert_cursor:
        with arcpy.da.SearchCursor(cross_sections, cross_fields) as cross_cursor:
            for geom, xsec_id, station_id, reach_id, chainage in cross_cursor:
                if not geom or geom.length <= 0:
                    continue
                steps = max(1, int(round(geom.length / sample_spacing_m)))
                for point_order in range(steps + 1):
                    distance = min(point_order * sample_spacing_m, geom.length)
                    if point_order == steps:
                        distance = geom.length
                    point_geom = geom.positionAlongLine(distance)
                    point = point_geom.firstPoint
                    dist_ctr = distance - (geom.length / 2.0)
                    insert_cursor.insertRow(
                        (
                            point_geom,
                            xsec_id,
                            station_id,
                            reach_id,
                            chainage,
                            point_order,
                            distance,
                            dist_ctr,
                            point.X,
                            point.Y,
                            None,
                            None,
                            1,
                        )
                    )
                    point_count += 1

    add_message(f"Created {point_count} profile sample points.")
    _sample_rasters_to_points(output_profile_points, dem_raster, slope_raster)
    _populate_nodata_flag(output_profile_points)
    _copy_points_to_profile_table(output_profile_points, output_profile_table, overwrite)

    return {
        "profile_points": output_profile_points,
        "profile_table": output_profile_table,
        "slope_raster": slope_raster,
    }
