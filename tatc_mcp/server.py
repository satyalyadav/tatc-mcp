"""MCP server for satellite ground track generation using TAT-C."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import anyio
from dateutil import parser as date_parser
import mcp_types as types
from mcp.server import Server, ServerRequestContext

from tatc_mcp.celestrak_client import get_satellite_info, search_satellites_by_name
from tatc_mcp.schema_formatter import format_ground_track_response
from tatc_mcp.tatc_integration import (
    calculate_footprint_from_position,
    create_satellite_from_tle,
    generate_ground_track,
)
from tatc_mcp.validation import validate_step_interval, validate_time_range

SERVER_NAME = "tatc-mcp-server"
SERVER_VERSION = "0.2.0rc1"
TOOL_CACHE_TTL_MS = 300_000


# Time unit normalization mapping
_TIME_UNITS = {
    "second": "seconds",
    "sec": "seconds",
    "secs": "seconds",
    "minute": "minutes",
    "min": "minutes",
    "mins": "minutes",
    "hour": "hours",
    "hr": "hours",
    "hrs": "hours",
    "day": "days",
}

_UNIT_TO_DELTA = {
    "seconds": lambda amount: timedelta(seconds=amount),
    "minutes": lambda amount: timedelta(minutes=amount),
    "hours": lambda amount: timedelta(hours=amount),
    "days": lambda amount: timedelta(days=amount),
}

_WORD_NUMBERS = {
    "a": 1,
    "an": 1,
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def _utcnow_naive() -> datetime:
    """Return the current UTC time as a naive datetime for TAT-C compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

_GROUND_TRACK_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "satellite_identifier": {
            "type": "string",
            "description": "Satellite name (e.g., 'ISS', 'Hubble') or NORAD ID",
        },
        "start_time": {
            "type": "string",
            "description": "Start time (ISO-8601 or 'now', default: now)",
        },
        "duration": {
            "type": "string",
            "description": "Duration (e.g., '1 hour', '60 minutes', default: 1 hour)",
        },
        "step_interval": {
            "type": "string",
            "description": (
                "Time step interval between data points. Use this whenever the user specifies "
                "steps or intervals, such as '10 seconds', '30 sec', '1 minute', or '5 mins'. "
                "Default: '1 minute' only if the user does not specify any time step."
            ),
        },
    },
    "required": ["satellite_identifier"],
}

_SATELLITE_IDENTIFIER_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "satellite_identifier": {
            "type": "string",
            "description": "Satellite name (e.g., 'ISS') or NORAD ID",
        }
    },
    "required": ["satellite_identifier"],
}

_SEARCH_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Satellite name or partial name to search for",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results to return",
            "default": 10,
            "minimum": 1,
            "maximum": 50,
        },
    },
    "required": ["query"],
}

_POSITION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "lat_deg": {"type": "number"},
        "lon_deg": {"type": "number"},
        "alt_m": {"type": "number"},
    },
    "required": ["lat_deg", "lon_deg", "alt_m"],
}

_TELEMETRY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "time": {"type": "string", "format": "date-time"},
        "position_lla": _POSITION_SCHEMA,
        "lookpoint_lla": _POSITION_SCHEMA,
        "footprint_geojson": {"type": "object"},
        "state_flags": {"type": "array", "items": {"type": "string"}},
        "trajectory_batches": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["id", "time", "position_lla"],
}

_GROUND_TRACK_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "data": {
            "type": "array",
            "items": _TELEMETRY_SCHEMA,
        }
    },
    "required": ["data"],
}

_SATELLITE_INFO_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "norad_id": {"type": ["integer", "string"]},
        "name": {"type": "string"},
        "tle_line1": {"type": "string"},
        "tle_line2": {"type": "string"},
    },
    "required": ["norad_id", "name", "tle_line1", "tle_line2"],
}

_SEARCH_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "data": {
            "type": "array",
            "items": {"type": "object"},
        }
    },
    "required": ["data"],
}


def _parse_time_unit(unit: str) -> Optional[str]:
    """Normalize time unit string."""
    normalized = unit.lower()
    return _TIME_UNITS.get(
        normalized, normalized if normalized in _UNIT_TO_DELTA else None
    )


def _unit_to_timedelta(unit: str, amount: float) -> timedelta:
    """Convert normalized unit and amount to timedelta."""
    converter = _UNIT_TO_DELTA.get(unit)
    if not converter:
        raise ValueError(f"Unknown time unit: {unit}")
    return converter(amount)


def _parse_amount_phrase(amount_str: str) -> float:
    """Parse a numeric or simple word-number amount."""
    normalized = amount_str.strip().lower().replace("-", " ")
    if not normalized:
        raise ValueError("Amount is required")

    try:
        return float(normalized)
    except ValueError:
        pass

    total = 0
    for token in normalized.split():
        if token not in _WORD_NUMBERS:
            raise ValueError(f"Unknown amount token: {token}")
        total += _WORD_NUMBERS[token]

    return float(total)


def _parse_relative_time(time_str: str) -> Optional[datetime]:
    """Parse relative time expressions like 'in 1 hour' or 'in one hour'."""
    if not time_str.startswith("in "):
        return None

    try:
        parts = time_str[3:].split()
        if len(parts) < 2:
            return None

        amount = _parse_amount_phrase(" ".join(parts[:-1]))
        unit = _parse_time_unit(parts[-1])
        if not unit:
            return None

        return _utcnow_naive() + _unit_to_timedelta(unit, amount)
    except (ValueError, IndexError):
        return None


def parse_time_input(time_str: str) -> datetime:
    """
    Parse a time input string to a naive UTC datetime.

    Supports ISO-8601 format, "now", "current", and relative expressions like
    "in 1 hour" or "in one hour".
    """
    normalized = time_str.strip().lower()

    if normalized in ("now", "current"):
        return _utcnow_naive()

    relative = _parse_relative_time(normalized)
    if relative:
        return relative

    try:
        dt = date_parser.parse(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=None)
    except Exception as exc:
        raise ValueError(f"Could not parse time string '{time_str}': {exc}") from exc


def parse_duration(duration_str: str) -> timedelta:
    """Parse a duration string such as "1 hour", "one hour", or "60 minutes"."""
    normalized = duration_str.strip().lower()

    try:
        return timedelta(minutes=int(normalized))
    except ValueError:
        pass

    try:
        parts = normalized.split()
        if len(parts) < 2:
            raise ValueError("Duration must include a unit")

        amount = _parse_amount_phrase(" ".join(parts[:-1]))
        unit = _parse_time_unit(parts[-1])
        if not unit:
            raise ValueError(f"Unknown time unit: {parts[-1]}")

        return _unit_to_timedelta(unit, amount)
    except (ValueError, IndexError) as exc:
        raise ValueError(
            f"Could not parse duration string '{duration_str}': {exc}"
        ) from exc


async def handle_generate_ground_track(
    satellite_identifier: str,
    start_time: Optional[str] = None,
    duration: Optional[str] = None,
    step_interval: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generate ground track telemetry for a satellite."""
    start_time_dt = (
        _utcnow_naive() if start_time is None else parse_time_input(start_time)
    )
    duration_delta = (
        timedelta(hours=1) if duration is None else parse_duration(duration)
    )
    step_seconds = (
        60.0 if step_interval is None else parse_duration(step_interval).total_seconds()
    )

    end_time_dt = start_time_dt + duration_delta
    start_time_dt, end_time_dt = validate_time_range(start_time_dt, end_time_dt)
    step_seconds = validate_step_interval(step_seconds)

    sat_info = get_satellite_info(satellite_identifier)
    satellite = create_satellite_from_tle(sat_info["tle_line1"], sat_info["tle_line2"])
    ground_track = generate_ground_track(
        satellite, start_time_dt, end_time_dt, step_seconds
    )
    footprints = [
        calculate_footprint_from_position(lat_deg, lon_deg, alt_m)
        for _, lat_deg, lon_deg, alt_m in ground_track
    ]

    return format_ground_track_response(
        str(sat_info["norad_id"]), ground_track, footprints
    )


async def handle_get_satellite_info(satellite_identifier: str) -> Dict[str, Any]:
    """Get satellite information including TLE data."""
    info = get_satellite_info(satellite_identifier)
    return {
        "norad_id": info["norad_id"],
        "name": info["name"],
        "tle_line1": info["tle_line1"],
        "tle_line2": info["tle_line2"],
    }


async def handle_search_satellites(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search for satellites by name."""
    return search_satellites_by_name(query, limit=limit)


def _json_tool_result(result: Any) -> types.CallToolResult:
    # MCP output schemas must have an object at their root. Keep the text
    # representation unchanged for clients that consume it as JSON, and wrap
    # list values only in the schema-validated structured content.
    structured_content = {"data": result} if isinstance(result, list) else result
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result, indent=2))],
        structured_content=structured_content,
    )


def _tools() -> List[types.Tool]:
    return [
        types.Tool(
            name="generate_ground_track",
            title="Generate Ground Track",
            description=(
                "Generate ground track for a satellite over a specified time period with configurable "
                "time steps. Supports start times like 'now', ISO-8601 timestamps, or relative "
                "phrases like 'in one hour'. Returns telemetry objects with position_lla and "
                "optional footprint geometry."
            ),
            input_schema=_GROUND_TRACK_INPUT_SCHEMA,
            output_schema=_GROUND_TRACK_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="get_satellite_info",
            title="Get Satellite Info",
            description="Get satellite metadata and TLE data from CelesTrak.",
            input_schema=_SATELLITE_IDENTIFIER_INPUT_SCHEMA,
            output_schema=_SATELLITE_INFO_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="search_satellites",
            title="Search Satellites",
            description=(
                "Search for satellites by name in the CelesTrak database. Use this when the exact "
                "satellite name or NORAD ID is unknown."
            ),
            input_schema=_SEARCH_INPUT_SCHEMA,
            output_schema=_SEARCH_OUTPUT_SCHEMA,
        ),
    ]


async def list_tools(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """List available tools in deterministic order with cache hints."""
    return types.ListToolsResult(
        tools=_tools(),
        ttl_ms=TOOL_CACHE_TTL_MS,
        cache_scope="public",
    )


async def call_tool(
    ctx: ServerRequestContext, params: types.CallToolRequestParams
) -> types.CallToolResult:
    """Handle MCP tool calls."""
    arguments = params.arguments or {}

    if params.name == "generate_ground_track":
        result = await handle_generate_ground_track(
            satellite_identifier=arguments.get("satellite_identifier"),
            start_time=arguments.get("start_time"),
            duration=arguments.get("duration"),
            step_interval=arguments.get("step_interval"),
        )
        return _json_tool_result(result)

    if params.name == "get_satellite_info":
        result = await handle_get_satellite_info(
            satellite_identifier=arguments.get("satellite_identifier")
        )
        return _json_tool_result(result)

    if params.name == "search_satellites":
        result = await handle_search_satellites(
            query=arguments.get("query"),
            limit=arguments.get("limit", 10),
        )
        return _json_tool_result(result)

    raise ValueError(f"Unknown tool: {params.name}")


server = Server(
    SERVER_NAME,
    version=SERVER_VERSION,
    title="TAT-C MCP Server",
    description="Satellite metadata lookup and TAT-C ground track generation tools.",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def _run_stdio() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the TAT-C MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="Transport to serve. Defaults to stdio for local MCP clients.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for streamable HTTP.")
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for streamable HTTP."
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="Use JSON responses for streamable HTTP instead of response streams.",
    )
    args = parser.parse_args(argv)

    if args.transport == "streamable-http":
        import uvicorn

        uvicorn.run(
            server.streamable_http_app(
                stateless_http=True,
                json_response=args.json_response,
                host=args.host,
            ),
            host=args.host,
            port=args.port,
        )
        return 0

    anyio.run(_run_stdio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
