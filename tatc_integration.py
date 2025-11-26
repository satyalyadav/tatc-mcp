"""TAT-C library integration for satellite operations."""

from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional, Dict, Any
import math

# Constants
DEFAULT_STEP_SECONDS = 60.0  # Default time step for ground track generation
DEFAULT_FOV_DEGREES = 60.0  # Default field of view for footprint calculation
FOOTPRINT_POLYGON_POINTS = 16  # Number of points in circular footprint polygon
EARTH_RADIUS_M = 6371000.0  # Earth radius in meters for footprint calculations

try:
    from tatc.schemas import TwoLineElements
    from skyfield.api import wgs84
    TATC_AVAILABLE = True
except ImportError:
    TATC_AVAILABLE = False
    TwoLineElements = None


def _ensure_utc(time: datetime) -> datetime:
    """Convert datetime to UTC timezone-aware."""
    if time.tzinfo is None:
        return time.replace(tzinfo=timezone.utc)
    return time.astimezone(timezone.utc)


def _extract_lla(subpoint) -> Tuple[float, float, float]:
    """Extract lat/lon/alt from Skyfield subpoint."""
    return (
        float(subpoint.latitude.degrees),
        float(subpoint.longitude.degrees),
        float(subpoint.elevation.m)
    )


def create_satellite_from_tle(tle_line1: str, tle_line2: str) -> Any:
    """
    Create a satellite object from TLE data using TAT-C.
    
    Args:
        tle_line1: First line of TLE
        tle_line2: Second line of TLE
        
    Returns:
        TAT-C TwoLineElements object
        
    Raises:
        ImportError: If TAT-C is not installed
        ValueError: If TLE data is invalid
    """
    if not TATC_AVAILABLE:
        raise ImportError(
            "TAT-C library is not installed. Install it with: "
            "pip install git+https://github.com/code-lab-org/tatc.git"
        )
    
    try:
        tle = TwoLineElements(tle=[tle_line1, tle_line2])
        return tle
    except Exception as e:
        raise ValueError(f"Failed to create satellite from TLE: {e}")


def propagate_satellite(
    satellite: Any,
    time: datetime
) -> Tuple[float, float, float]:
    """
    Propagate satellite to a specific time and get LLA coordinates.
    
    Args:
        satellite: TAT-C TwoLineElements object
        time: Target time (UTC, must be timezone-aware)
        
    Returns:
        Tuple of (latitude_deg, longitude_deg, altitude_m)
    """
    if not TATC_AVAILABLE:
        raise ImportError("TAT-C library is not installed")
    
    try:
        time = _ensure_utc(time)
        track = satellite.get_orbit_track(time)  # Get orbit position at time
        subpoint = wgs84.subpoint(track)  # Get ground point directly below satellite
        return _extract_lla(subpoint)
    except Exception as e:
        raise ValueError(f"Failed to propagate satellite: {e}")


def generate_ground_track(
    satellite: Any,
    start_time: datetime,
    end_time: datetime,
    step_seconds: float = DEFAULT_STEP_SECONDS
) -> List[Tuple[datetime, float, float, float]]:
    """
    Generate ground track for a satellite over a time range.
    
    Args:
        satellite: TAT-C TwoLineElements object
        start_time: Start time (UTC)
        end_time: End time (UTC)
        step_seconds: Time step in seconds
        
    Returns:
        List of tuples: (time, lat_deg, lon_deg, alt_m)
    """
    if not TATC_AVAILABLE:
        raise ImportError("TAT-C library is not installed")
    
    start_time = _ensure_utc(start_time)
    end_time = _ensure_utc(end_time)
    
    # Generate time sequence
    times = []
    current_time = start_time
    while current_time <= end_time:
        times.append(current_time)
        current_time += timedelta(seconds=step_seconds)
    
    # Try batch propagation (faster than individual calls)
    try:
        track = satellite.get_orbit_track(times)
        
        # Handle both single object and collection responses
        try:
            track_points = list(track)
        except (TypeError, AttributeError):
            track_points = [track]
        
        ground_track = []
        for i, time in enumerate(times):
            try:
                # Use corresponding point or last point if index out of range
                point = track_points[i] if i < len(track_points) else track_points[-1]
                subpoint = wgs84.subpoint(point)
                lat_deg, lon_deg, alt_m = _extract_lla(subpoint)
                
                # Convert to naive UTC (timezone removed) for compatibility
                ground_track.append((time.replace(tzinfo=None), lat_deg, lon_deg, alt_m))
            except Exception as e:
                print(f"Warning: Failed to extract coordinates at {time}: {e}")
                continue
        
        return ground_track
        
    except Exception as e:
        # Fallback: propagate one at a time if batch fails
        print(f"Warning: Batch propagation failed, using individual propagation: {e}")
        ground_track = []
        for time in times:
            try:
                lat_deg, lon_deg, alt_m = propagate_satellite(satellite, time)
                ground_track.append((time.replace(tzinfo=None), lat_deg, lon_deg, alt_m))
            except Exception as e:
                print(f"Warning: Failed to propagate at {time}: {e}")
                continue
        
        return ground_track


def calculate_footprint(
    satellite: Any,
    time: datetime,
    fov_degrees: Optional[float] = None
) -> Optional[List[List[float]]]:
    """
    Calculate satellite footprint using circular approximation.
    
    Args:
        satellite: TAT-C TwoLineElements object
        time: Time for footprint calculation (UTC)
        fov_degrees: Field of view in degrees (default: 60 degrees)
        
    Returns:
        List of [lon, lat] coordinates forming the footprint polygon, or None if calculation fails
    """
    if not TATC_AVAILABLE:
        raise ImportError("TAT-C library is not installed")
    
    try:
        # Get satellite position first
        lat_deg, lon_deg, alt_m = propagate_satellite(satellite, time)
        return _calculate_circular_footprint(lat_deg, lon_deg, alt_m, fov_degrees)
    except Exception as e:
        print(f"Warning: Footprint calculation failed: {e}")
        return None


def _calculate_circular_footprint(
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
    fov_degrees: Optional[float] = None
) -> List[List[float]]:
    """
    Calculate a simple circular footprint approximation.
    
    Args:
        lat_deg: Satellite latitude
        lon_deg: Satellite longitude
        alt_m: Satellite altitude in meters
        fov_degrees: Field of view in degrees (default: 60 degrees)
        
    Returns:
        List of [lon, lat] coordinates forming a circular polygon
    """
    if fov_degrees is None:
        fov_degrees = DEFAULT_FOV_DEGREES
    
    # Calculate footprint radius on Earth's surface using geometric approximation
    fov_rad = math.radians(fov_degrees / 2.0)
    if alt_m > 0:
        # Account for satellite altitude in footprint radius calculation
        footprint_radius_rad = math.asin(
            (EARTH_RADIUS_M + alt_m) * math.sin(fov_rad) / EARTH_RADIUS_M
        ) - fov_rad
    else:
        footprint_radius_rad = fov_rad
    
    footprint_radius_deg = math.degrees(footprint_radius_rad)
    
    # Generate circular polygon by sampling points around the center
    coords = []
    for i in range(FOOTPRINT_POLYGON_POINTS + 1):  # +1 to close the polygon
        angle = 2 * math.pi * i / FOOTPRINT_POLYGON_POINTS
        # Calculate lat/lon offset (simplified approximation)
        dlat = footprint_radius_deg * math.cos(angle)
        dlon = footprint_radius_deg * math.sin(angle) / math.cos(math.radians(lat_deg))
        
        # Normalize coordinates to valid ranges
        new_lat = max(-90, min(90, lat_deg + dlat))
        new_lon = ((lon_deg + dlon + 180) % 360) - 180
        
        coords.append([new_lon, new_lat])
    
    return coords
