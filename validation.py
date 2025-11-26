"""Validation utilities for satellite data and parameters."""

from datetime import datetime, timedelta
from typing import Tuple, Optional


def validate_norad_id(norad_id: int) -> int:
    """
    Validate NORAD ID.
    
    Args:
        norad_id: NORAD catalog number
        
    Returns:
        Validated NORAD ID
        
    Raises:
        ValueError: If NORAD ID is invalid
    """
    if not isinstance(norad_id, int):
        try:
            norad_id = int(norad_id)
        except (ValueError, TypeError):
            raise ValueError(f"NORAD ID must be an integer, got {type(norad_id)}")
    
    if norad_id < 1 or norad_id > 99999:
        raise ValueError(f"NORAD ID must be between 1 and 99999, got {norad_id}")
    
    return norad_id


def validate_tle_format(tle_line1: str, tle_line2: str) -> Tuple[str, str]:
    """
    Validate TLE format.
    
    Args:
        tle_line1: First TLE line
        tle_line2: Second TLE line
        
    Returns:
        Tuple of validated TLE lines
        
    Raises:
        ValueError: If TLE format is invalid
    """
    if not isinstance(tle_line1, str) or not isinstance(tle_line2, str):
        raise ValueError("TLE lines must be strings")
    
    tle_line1 = tle_line1.strip()
    tle_line2 = tle_line2.strip()
    
    if len(tle_line1) < 69:
        raise ValueError(f"TLE line 1 too short: {len(tle_line1)} characters (minimum 69)")
    
    if len(tle_line2) < 69:
        raise ValueError(f"TLE line 2 too short: {len(tle_line2)} characters (minimum 69)")
    
    if not tle_line1.startswith('1 '):
        raise ValueError("TLE line 1 must start with '1 '")
    
    if not tle_line2.startswith('2 '):
        raise ValueError("TLE line 2 must start with '2 '")
    
    # Basic checksum validation
    try:
        checksum1 = int(tle_line1[-1])
        checksum2 = int(tle_line2[-1])
    except ValueError:
        raise ValueError("TLE checksums must be digits")
    
    return tle_line1, tle_line2


def validate_time_range(
    start_time: datetime,
    end_time: datetime,
    max_duration: Optional[timedelta] = None
) -> Tuple[datetime, datetime]:
    """
    Validate time range.
    
    Args:
        start_time: Start time
        end_time: End time
        max_duration: Maximum allowed duration (optional)
        
    Returns:
        Tuple of validated (start_time, end_time)
        
    Raises:
        ValueError: If time range is invalid
    """
    if not isinstance(start_time, datetime):
        raise ValueError(f"start_time must be a datetime object, got {type(start_time)}")
    
    if not isinstance(end_time, datetime):
        raise ValueError(f"end_time must be a datetime object, got {type(end_time)}")
    
    if end_time <= start_time:
        raise ValueError(f"end_time must be after start_time: {start_time} >= {end_time}")
    
    duration = end_time - start_time
    
    if max_duration is not None and duration > max_duration:
        raise ValueError(
            f"Duration {duration} exceeds maximum allowed duration {max_duration}"
        )
    
    # Check for reasonable duration (not more than 30 days)
    max_reasonable = timedelta(days=30)
    if duration > max_reasonable:
        raise ValueError(
            f"Duration {duration} is unreasonably long (maximum {max_reasonable})"
        )
    
    return start_time, end_time


def validate_step_interval(step_seconds: float, min_step: float = 1.0, max_step: float = 3600.0) -> float:
    """
    Validate step interval.
    
    Args:
        step_seconds: Step interval in seconds
        min_step: Minimum step in seconds (default: 1 second)
        max_step: Maximum step in seconds (default: 1 hour)
        
    Returns:
        Validated step interval
        
    Raises:
        ValueError: If step interval is invalid
    """
    if not isinstance(step_seconds, (int, float)):
        try:
            step_seconds = float(step_seconds)
        except (ValueError, TypeError):
            raise ValueError(f"step_seconds must be a number, got {type(step_seconds)}")
    
    if step_seconds < min_step:
        raise ValueError(f"Step interval {step_seconds}s is too small (minimum {min_step}s)")
    
    if step_seconds > max_step:
        raise ValueError(f"Step interval {step_seconds}s is too large (maximum {max_step}s)")
    
    return float(step_seconds)


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
    if not isinstance(lat_deg, (int, float)):
        raise ValueError(f"Latitude must be a number, got {type(lat_deg)}")
    
    if not isinstance(lon_deg, (int, float)):
        raise ValueError(f"Longitude must be a number, got {type(lon_deg)}")
    
    lat_deg = float(lat_deg)
    lon_deg = float(lon_deg)
    
    if not (-90 <= lat_deg <= 90):
        raise ValueError(f"Latitude {lat_deg} is out of valid range [-90, 90]")
    
    # Normalize longitude to [-180, 180]
    if lon_deg < -180 or lon_deg > 180:
        lon_deg = ((lon_deg + 180) % 360) - 180
    
    return lat_deg, lon_deg


def validate_altitude(alt_m: float, min_alt: float = -100000.0, max_alt: float = 1000000.0) -> float:
    """
    Validate altitude.
    
    Args:
        alt_m: Altitude in meters
        min_alt: Minimum altitude in meters (default: -100km)
        max_alt: Maximum altitude in meters (default: 1000km)
        
    Returns:
        Validated altitude
        
    Raises:
        ValueError: If altitude is out of valid range
    """
    if not isinstance(alt_m, (int, float)):
        raise ValueError(f"Altitude must be a number, got {type(alt_m)}")
    
    alt_m = float(alt_m)
    
    if alt_m < min_alt:
        raise ValueError(f"Altitude {alt_m}m is below minimum {min_alt}m")
    
    if alt_m > max_alt:
        raise ValueError(f"Altitude {alt_m}m is above maximum {max_alt}m")
    
    return alt_m

