"""Geometry helpers for station and cross-section generation."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from .io_utils import add_field, add_message, add_text_field, delete_if_allowed


def _arcpy():
    import arcpy  # type: ignore

    return arcpy


@dataclass(frozen=True)
class PointXY:
    x: float
    y: float


def azimuth_degrees(dx: float, dy: float) -> float:
    """Return compass azimuth in degrees for a Cartesian vector."""
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def perpendicular_endpoints(
    center_x: float,
    center_y: float,
    tangent_dx: float,
    tangent_dy: float,
    half_width: float,
) -> tuple[PointXY, PointXY, float]:
    """Create left and right cross-section endpoints from a local tangent."""
    length = math.hypot(tangent_dx, tangent_dy)
    if length == 0:
        raise ValueError("Cannot build a cross section from a zero-length tangent.")

    # The normal vector points left of the downstream tangent.
    nx = -tangent_dy / length
    ny = tangent_dx / length
    left = PointXY(center_x + nx * half_width, center_y + ny * half_width)
    right = PointXY(center_x - nx * half_width, center_y - ny * half_width)
    return left, right, azimuth_degrees(right.x - left.x, right.y - left.y)


def _copy_spatial_reference(source: str):
    arcpy = _arcpy()
    return arcpy.Describe(source).spatialReference


def _make_point_geometry(x: float, y: float, spatial_ref):
    arcpy = _arcpy()
    return arcpy.PointGeometry(arcpy.Point(x, y), spatial_ref)


def _make_polyline(points: list[PointXY], spatial_ref):
    arcpy = _arcpy()
    array = arcpy.Array([arcpy.Point(point.x, point.y) for point in points])
    return arcpy.Polyline(array, spatial_ref)


def generate_station_points(
    prepared_stream: str,
    station_interval_m: float,
    reach_id_field: str | None,
    output_fc: str,
    overwrite: bool = True,
) -> str:
    """Generate evenly spaced station points along each input stream feature."""
    arcpy = _arcpy()
    if station_interval_m <= 0:
        raise ValueError("Station interval must be greater than zero.")

    workspace, name = os.path.split(output_fc)
    spatial_ref = _copy_spatial_reference(prepared_stream)
    delete_if_allowed(output_fc, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(workspace, name, "POINT", spatial_reference=spatial_ref)

    add_field(output_fc, "station_id", "LONG")
    add_text_field(output_fc, "reach_id", 128)
    add_field(output_fc, "chain_m", "DOUBLE")
    add_field(output_fc, "source_id", "LONG")
    add_field(output_fc, "interval_m", "DOUBLE")

    fields = ["OID@", "SHAPE@"]
    if reach_id_field:
        fields.append(reach_id_field)

    station_id = 1
    with arcpy.da.InsertCursor(
        output_fc,
        ["SHAPE@", "station_id", "reach_id", "chain_m", "source_id", "interval_m"],
    ) as insert_cursor:
        with arcpy.da.SearchCursor(prepared_stream, fields) as search_cursor:
            for row in search_cursor:
                source_id = row[0]
                geom = row[1]
                if not geom or geom.length <= 0:
                    continue
                reach_id = str(row[2]) if reach_id_field else str(source_id)
                chainage = 0.0
                while chainage <= geom.length:
                    point_geom = geom.positionAlongLine(chainage)
                    insert_cursor.insertRow(
                        (
                            point_geom,
                            station_id,
                            reach_id,
                            chainage,
                            source_id,
                            station_interval_m,
                        )
                    )
                    station_id += 1
                    chainage += station_interval_m

                if (chainage - station_interval_m) < geom.length:
                    point_geom = geom.positionAlongLine(geom.length)
                    insert_cursor.insertRow(
                        (
                            point_geom,
                            station_id,
                            reach_id,
                            geom.length,
                            source_id,
                            station_interval_m,
                        )
                    )
                    station_id += 1

    add_message(f"Generated {station_id - 1} station points.")
    return output_fc


def _load_stream_geometries(stream_fc: str) -> dict[int, object]:
    arcpy = _arcpy()
    geoms: dict[int, object] = {}
    with arcpy.da.SearchCursor(stream_fc, ["OID@", "SHAPE@"]) as cursor:
        for oid, shape in cursor:
            geoms[int(oid)] = shape
    return geoms


def _local_tangent(stream_geom, chainage: float, tangent_distance: float) -> tuple[float, float]:
    if tangent_distance <= 0:
        tangent_distance = max(stream_geom.length * 0.01, 1.0)
    before_m = max(0.0, chainage - tangent_distance)
    after_m = min(stream_geom.length, chainage + tangent_distance)
    if before_m == after_m:
        before_m = max(0.0, chainage - 1.0)
        after_m = min(stream_geom.length, chainage + 1.0)
    before = stream_geom.positionAlongLine(before_m).firstPoint
    after = stream_geom.positionAlongLine(after_m).firstPoint
    return after.X - before.X, after.Y - before.Y


def generate_cross_sections(
    station_points: str,
    prepared_stream: str,
    half_width_m: float,
    method: str,
    tangent_distance_m: float,
    output_fc: str,
    overwrite: bool = True,
) -> str:
    """Generate fast perpendicular cross sections from station points."""
    arcpy = _arcpy()
    if half_width_m <= 0:
        raise ValueError("Cross section half width must be greater than zero.")
    if method.lower() not in {"fast perpendicular", "fast_perpendicular"}:
        raise ValueError("Version 1 supports only the fast perpendicular method.")

    workspace, name = os.path.split(output_fc)
    spatial_ref = _copy_spatial_reference(station_points)
    delete_if_allowed(output_fc, overwrite=overwrite)
    arcpy.management.CreateFeatureclass(
        workspace, name, "POLYLINE", spatial_reference=spatial_ref
    )
    add_field(output_fc, "xsec_id", "LONG")
    add_field(output_fc, "station_id", "LONG")
    add_text_field(output_fc, "reach_id", 128)
    add_field(output_fc, "chain_m", "DOUBLE")
    add_field(output_fc, "half_w_m", "DOUBLE")
    add_text_field(output_fc, "method", 64)
    add_field(output_fc, "tangent_m", "DOUBLE")
    add_field(output_fc, "azimuth", "DOUBLE")

    stream_geoms = _load_stream_geometries(prepared_stream)
    xsec_id = 1
    station_fields = ["SHAPE@", "station_id", "reach_id", "chain_m", "source_id"]
    with arcpy.da.InsertCursor(
        output_fc,
        [
            "SHAPE@",
            "xsec_id",
            "station_id",
            "reach_id",
            "chain_m",
            "half_w_m",
            "method",
            "tangent_m",
            "azimuth",
        ],
    ) as insert_cursor:
        with arcpy.da.SearchCursor(station_points, station_fields) as station_cursor:
            for point_geom, station_id, reach_id, chainage, source_id in station_cursor:
                stream_geom = stream_geoms.get(int(source_id))
                if stream_geom is None:
                    continue
                center = point_geom.firstPoint
                dx, dy = _local_tangent(stream_geom, float(chainage), tangent_distance_m)
                try:
                    left, right, azimuth = perpendicular_endpoints(
                        center.X, center.Y, dx, dy, half_width_m
                    )
                except ValueError:
                    continue
                polyline = _make_polyline([left, right], spatial_ref)
                insert_cursor.insertRow(
                    (
                        polyline,
                        xsec_id,
                        station_id,
                        reach_id,
                        chainage,
                        half_width_m,
                        "fast_perpendicular",
                        tangent_distance_m,
                        azimuth,
                    )
                )
                xsec_id += 1

    add_message(f"Generated {xsec_id - 1} cross sections.")
    return output_fc
