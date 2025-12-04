"""Format TAT-C outputs to match SCHEMA.txt specification."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from tatc_mcp.validation import validate_coordinates as _validate_coordinates


def validate_coordinates(lat_deg: float, lon_deg: float) -> Tuple[float, float]:
    """
    Validate and normalize coordinates.

    Args:
        lat_deg: Latitude in degrees
        lon_deg: Longitude in degrees

    Returns:
        Tuple of (validated_lat, validated_lon)

    Raises:
        ValueError: If coordinates are out of valid range
    """
    return _validate_coordinates(lat_deg, lon_deg)


def format_timestamp(time: datetime) -> str:
    """
    Format datetime to ISO-8601 UTC string with trailing 'Z'.

    Args:
        time: Datetime object (assumed to be UTC)

    Returns:
        ISO-8601 UTC string with trailing 'Z'
    """
    # Ensure timezone-aware UTC
    if time.tzinfo is None:
        # Assume UTC if timezone-naive
        from datetime import timezone

        time = time.replace(tzinfo=timezone.utc)

    # Format as ISO-8601 with 'Z' suffix
    iso_str = time.isoformat()
    if iso_str.endswith("+00:00"):
        iso_str = iso_str[:-6] + "Z"
    elif not iso_str.endswith("Z"):
        iso_str = iso_str + "Z"

    return iso_str


def format_position_lla(lat_deg: float, lon_deg: float, alt_m: float) -> Dict[str, float]:
    """
    Format position as LLA object per SCHEMA.txt.

    Args:
        lat_deg: Latitude in degrees
        lon_deg: Longitude in degrees
        alt_m: Altitude in meters

    Returns:
        Dictionary with lat_deg, lon_deg, alt_m
    """
    lat_deg, lon_deg = validate_coordinates(lat_deg, lon_deg)

    return {
        "lat_deg": float(lat_deg),
        "lon_deg": float(lon_deg),
        "alt_m": float(alt_m),
    }


def format_footprint_geojson(coordinates: List[List[float]]) -> Optional[Dict[str, Any]]:
    """
    Format footprint coordinates as GeoJSON Feature<Polygon> per SCHEMA.txt.

    Args:
        coordinates: List of [lon, lat] coordinate pairs

    Returns:
        GeoJSON Feature<Polygon> dictionary, or None if coordinates are invalid
    """
    if not coordinates or len(coordinates) < 3:
        return None

    # Validate and normalize coordinates
    validated_coords = []
    for coord in coordinates:
        if len(coord) < 2:
            continue
        lon, lat = coord[0], coord[1]
        try:
            lat, lon = validate_coordinates(lat, lon)
            validated_coords.append([lon, lat])
        except ValueError:
            continue

    if len(validated_coords) < 3:
        return None

    # Ensure polygon is closed (first point == last point)
    if validated_coords[0] != validated_coords[-1]:
        validated_coords.append(validated_coords[0])

    # Create GeoJSON Feature<Polygon>
    # Per SCHEMA.txt: coordinates in [lon, lat] (WGS84), properties must be {}
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [validated_coords],  # Polygon coordinates are wrapped in an array
        },
        "properties": {},
    }


def format_trajectory_batch(
    ground_track: List[Tuple[datetime, float, float, float]]
) -> List[Dict[str, Any]]:
    """
    Format ground track as trajectory_batches array per SCHEMA.txt.

    Args:
        ground_track: List of (time, lat_deg, lon_deg, alt_m) tuples

    Returns:
        List of trajectory batch objects
    """
    batches = []
    for time, lat_deg, lon_deg, alt_m in ground_track:
        try:
            batches.append(
                {
                    "time": format_timestamp(time),
                    "position_lla": format_position_lla(lat_deg, lon_deg, alt_m),
                }
            )
        except ValueError as e:
            # Skip invalid coordinates
            print(f"Warning: Skipping invalid trajectory point: {e}")
            continue

    return batches


def format_telemetry_message(
    satellite_id: str,
    time: datetime,
    position_lla: Tuple[float, float, float],
    footprint_coords: Optional[List[List[float]]] = None,
    trajectory_batches: Optional[List[Tuple[datetime, float, float, float]]] = None,
    lookpoint_lla: Optional[Tuple[float, float, float]] = None,
    state_flags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Format a complete telemetry message per SCHEMA.txt.

    Args:
        satellite_id: Stable satellite/platform identifier
        time: Authoritative message epoch (UTC)
        position_lla: Tuple of (lat_deg, lon_deg, alt_m)
        footprint_coords: Optional list of [lon, lat] coordinates for footprint
        trajectory_batches: Optional ground track data
        lookpoint_lla: Optional boresight target (lat_deg, lon_deg, alt_m)
        state_flags: Optional list of state flag strings

    Returns:
        Dictionary matching SCHEMA.txt format
    """
    if not satellite_id or not satellite_id.strip():
        raise ValueError("satellite_id must be a non-empty string")

    lat_deg, lon_deg, alt_m = position_lla

    # Build base message
    message = {
        "id": str(satellite_id).strip(),
        "time": format_timestamp(time),
        "position_lla": format_position_lla(lat_deg, lon_deg, alt_m),
    }

    # Add optional lookpoint_lla
    if lookpoint_lla is not None:
        look_lat, look_lon, look_alt = lookpoint_lla
        message["lookpoint_lla"] = format_position_lla(look_lat, look_lon, look_alt)

    # Add optional footprint_geojson
    if footprint_coords is not None:
        footprint_geojson = format_footprint_geojson(footprint_coords)
        if footprint_geojson is not None:
            message["footprint_geojson"] = footprint_geojson

    # Add optional state_flags
    if state_flags is not None and len(state_flags) > 0:
        message["state_flags"] = [str(flag) for flag in state_flags]

    # Add optional trajectory_batches
    if trajectory_batches is not None:
        message["trajectory_batches"] = format_trajectory_batch(trajectory_batches)

    return message


def format_ground_track_response(
    satellite_id: str,
    ground_track: List[Tuple[datetime, float, float, float]],
    footprints: Optional[List[Optional[List[List[float]]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Format a complete ground track response as an array of telemetry messages.

    Args:
        satellite_id: Stable satellite/platform identifier
        ground_track: List of (time, lat_deg, lon_deg, alt_m) tuples
        footprints: Optional list of footprint coordinates (one per ground track point)

    Returns:
        List of telemetry message dictionaries
    """
    messages = []

    for i, (time, lat_deg, lon_deg, alt_m) in enumerate(ground_track):
        footprint_coords = None
        if footprints is not None and i < len(footprints):
            footprint_coords = footprints[i]

        try:
            message = format_telemetry_message(
                satellite_id=satellite_id,
                time=time,
                position_lla=(lat_deg, lon_deg, alt_m),
                footprint_coords=footprint_coords,
            )
            messages.append(message)
        except ValueError as e:
            print(f"Warning: Skipping invalid telemetry point at {time}: {e}")
            continue

    return messages


