"""MCP server for satellite ground track generation using TAT-C."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List, Dict, Callable
from dateutil import parser as date_parser

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: MCP SDK is not installed. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

from celestrak_client import get_satellite_info, search_satellites_by_name
from tatc_integration import create_satellite_from_tle, generate_ground_track
from schema_formatter import format_ground_track_response
from validation import validate_time_range, validate_step_interval


# Initialize server
server = Server("tatc-mcp-server")


# Time unit normalization mapping
_TIME_UNITS = {
    "second": "seconds", "sec": "seconds", "secs": "seconds",
    "minute": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hours", "hr": "hours", "hrs": "hours",
    "day": "days"
}

# Time unit to timedelta parameter mapping
_UNIT_TO_DELTA = {
    "seconds": lambda amount: timedelta(seconds=amount),
    "minutes": lambda amount: timedelta(minutes=amount),
    "hours": lambda amount: timedelta(hours=amount),
    "days": lambda amount: timedelta(days=amount),
}


def _parse_time_unit(unit: str) -> Optional[str]:
    """Normalize time unit string."""
    return _TIME_UNITS.get(unit.lower(), unit.lower() if unit.lower() in _UNIT_TO_DELTA else None)


def _unit_to_timedelta(unit: str, amount: float) -> timedelta:
    """Convert normalized unit and amount to timedelta."""
    converter = _UNIT_TO_DELTA.get(unit)
    if not converter:
        raise ValueError(f"Unknown time unit: {unit}")
    return converter(amount)


def _parse_relative_time(time_str: str) -> Optional[datetime]:
    """Parse relative time expressions like 'in 1 hour'."""
    if not time_str.startswith("in "):
        return None
    
    try:
        parts = time_str[3:].split()
        if len(parts) < 2:
            return None
        
        amount = int(parts[0])
        unit = _parse_time_unit(parts[1])
        if not unit:
            return None
        
        return datetime.utcnow() + _unit_to_timedelta(unit, amount)
    except (ValueError, IndexError):
        return None


def parse_time_input(time_str: str) -> datetime:
    """
    Parse time input string to datetime.
    
    Supports:
    - ISO-8601 format
    - Relative times like "now", "in 1 hour"
    - Natural language (via dateutil)
    
    Args:
        time_str: Time string to parse
        
    Returns:
        datetime object (UTC)
    """
    time_str = time_str.strip().lower()
    
    if time_str in ("now", "current"):
        return datetime.utcnow()
    
    # Try relative time parsing
    relative = _parse_relative_time(time_str)
    if relative:
        return relative
    
    # Use dateutil for more complex parsing
    try:
        dt = date_parser.parse(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=None)  # Return naive UTC for compatibility
    except Exception as e:
        raise ValueError(f"Could not parse time string '{time_str}': {e}")


def parse_duration(duration_str: str) -> timedelta:
    """
    Parse duration string to timedelta.
    
    Args:
        duration_str: Duration string (e.g., "1 hour", "60 minutes")
        
    Returns:
        timedelta object
    """
    duration_str = duration_str.strip().lower()
    
    # Try to parse as number (assume minutes)
    try:
        return timedelta(minutes=int(duration_str))
    except ValueError:
        pass
    
    # Parse with units
    try:
        parts = duration_str.split()
        if len(parts) < 2:
            raise ValueError("Duration must include a unit")
        
        amount = float(parts[0])
        unit = _parse_time_unit(parts[1])
        if not unit:
            raise ValueError(f"Unknown time unit: {parts[1]}")
        
        return _unit_to_timedelta(unit, amount)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Could not parse duration string '{duration_str}': {e}")


async def handle_generate_ground_track(
    satellite_identifier: str,
    start_time: Optional[str] = None,
    duration: Optional[str] = None,
    step_interval: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Generate ground track for a satellite.
    
    Args:
        satellite_identifier: Satellite name or NORAD ID
        start_time: Start time (default: now)
        duration: Duration (default: 1 hour)
        step_interval: Time step interval. Supports seconds, minutes, or hours. Default: 1 minute.
        
    Returns:
        List of telemetry messages per SCHEMA.txt
    """
    # Parse parameters with defaults
    start_time_dt = datetime.utcnow() if start_time is None else parse_time_input(start_time)
    duration_delta = timedelta(hours=1) if duration is None else parse_duration(duration)
    step_seconds = 60.0 if step_interval is None else parse_duration(step_interval).total_seconds()
    
    end_time_dt = start_time_dt + duration_delta
    
    # Validate
    start_time_dt, end_time_dt = validate_time_range(start_time_dt, end_time_dt)
    step_seconds = validate_step_interval(step_seconds)
    
    # Get satellite info
    sat_info = get_satellite_info(satellite_identifier)
    
    # Generate ground track
    satellite = create_satellite_from_tle(sat_info["tle_line1"], sat_info["tle_line2"])
    ground_track = generate_ground_track(satellite, start_time_dt, end_time_dt, step_seconds)
    
    # Format response
    return format_ground_track_response(str(sat_info["norad_id"]), ground_track, None)


async def handle_get_satellite_info(satellite_identifier: str) -> Dict[str, Any]:
    """
    Get satellite information including TLE data.
    
    Args:
        satellite_identifier: Satellite name or NORAD ID
        
    Returns:
        Dictionary with satellite information
    """
    info = get_satellite_info(satellite_identifier)
    return {
        "norad_id": info["norad_id"],
        "name": info["name"],
        "tle_line1": info["tle_line1"],
        "tle_line2": info["tle_line2"]
    }


async def handle_search_satellites(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for satellites by name.
    
    Args:
        query: Satellite name or partial name to search for
        limit: Maximum number of results (default: 10)
        
    Returns:
        List of satellite dictionaries with NORAD ID, name, and metadata
    """
    return search_satellites_by_name(query, limit=limit)


def _format_result(result: Any) -> List[TextContent]:
    """Format result as JSON TextContent."""
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# Register tools
@server.list_tools()
async def list_tools() -> List[Tool]:
        """List available tools."""
        return [
            Tool(
                name="generate_ground_track",
                description=(
                    "Generate ground track for a satellite over a specified time period with configurable time steps. "
                    "CRITICAL: When user mentions time steps (e.g., '10 second steps', 'every 30 seconds', '1 minute intervals', '10 sec time step'), "
                    "you MUST extract and include the step_interval parameter. Examples: "
                    "User says '10 second time steps' -> step_interval='10 seconds', "
                    "User says 'every 30 sec' -> step_interval='30 sec', "
                    "User says '1 minute steps' -> step_interval='1 minute'. "
                    "Time steps can be in seconds ('10 seconds', '30 sec'), minutes ('1 minute', '5 mins'), or hours. "
                    "If user does NOT mention time steps, default is '1 minute'. "
                    "Returns telemetry data matching SCHEMA.txt format."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "satellite_identifier": {
                            "type": "string",
                            "description": "Satellite name (e.g., 'ISS', 'Hubble') or NORAD ID"
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start time (ISO-8601 or 'now', default: now)"
                        },
                        "duration": {
                            "type": "string",
                            "description": "Duration (e.g., '1 hour', '60 minutes', default: 1 hour)"
                        },
                        "step_interval": {
                            "type": "string",
                            "description": (
                                "REQUIRED when user specifies a time step. Time step interval between data points. "
                                "Supports: seconds ('10 seconds', '30 sec', '10 sec'), minutes ('1 minute', '5 mins', '1 min'), or hours ('1 hour'). "
                                "Examples: '10 seconds', '30 sec', '1 minute', '5 mins', '1 hour'. "
                                "If user says '10 second time step' or 'every 10 seconds', use '10 seconds'. "
                                "If user says '1 minute steps' or 'every minute', use '1 minute'. "
                                "Default: '1 minute' only if user does not specify any time step."
                            )
                        }
                    },
                    "required": ["satellite_identifier"]
                }
            ),
            Tool(
                name="get_satellite_info",
                description="Get satellite information including TLE data from CelesTrak.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "satellite_identifier": {
                            "type": "string",
                            "description": "Satellite name (e.g., 'ISS') or NORAD ID"
                        }
                    },
                    "required": ["satellite_identifier"]
                }
            ),
            Tool(
                name="search_satellites",
                description=(
                    "Search for satellites by name in the CelesTrak database. "
                    "Useful when you don't know the exact satellite name or NORAD ID. "
                    "Returns a list of matching satellites with their NORAD IDs that can be used for visualization."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Satellite name or partial name to search for (e.g., 'Starlink', 'GPS', 'NOAA', 'Hubble')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10, max recommended: 50)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle tool calls."""
        handlers: Dict[str, Callable[[], Any]] = {
            "generate_ground_track": lambda: handle_generate_ground_track(
                satellite_identifier=arguments.get("satellite_identifier"),
                start_time=arguments.get("start_time"),
                duration=arguments.get("duration"),
                step_interval=arguments.get("step_interval")
            ),
            "get_satellite_info": lambda: handle_get_satellite_info(
                satellite_identifier=arguments.get("satellite_identifier")
            ),
            "search_satellites": lambda: handle_search_satellites(
                query=arguments.get("query"),
                limit=arguments.get("limit", 10)
            )
        }
        
        handler = handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")
        
        result = await handler()
        return _format_result(result)


# Run MCP server
if __name__ == "__main__":
    async def run_server():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    
    asyncio.run(run_server())

