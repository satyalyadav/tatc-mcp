import asyncio
import json
from datetime import datetime

from mcp import Client

from tatc_mcp import server as server_module


def run(coro):
    return asyncio.run(coro)


def test_modern_client_discovers_tools():
    async def scenario():
        async with Client(server_module.server, mode="2026-07-28") as client:
            tools_result = await client.list_tools()

            assert client.protocol_version == "2026-07-28"
            assert tools_result.result_type == "complete"
            assert tools_result.ttl_ms == server_module.TOOL_CACHE_TTL_MS
            assert tools_result.cache_scope == "public"
            assert [tool.name for tool in tools_result.tools] == [
                "generate_ground_track",
                "get_satellite_info",
                "search_satellites",
            ]
            assert all(
                tool.input_schema["type"] == "object" for tool in tools_result.tools
            )
            assert all(tool.output_schema is not None for tool in tools_result.tools)

    run(scenario())


def test_search_satellites_returns_structured_content(monkeypatch):
    expected = [
        {
            "norad_id": 25544,
            "name": "ISS (ZARYA)",
            "object_type": "PAYLOAD",
        }
    ]

    monkeypatch.setattr(
        server_module,
        "search_satellites_by_name",
        lambda query, limit=10: expected,
    )

    async def scenario():
        async with Client(server_module.server, mode="2026-07-28") as client:
            result = await client.call_tool(
                "search_satellites", {"query": "ISS", "limit": 1}
            )

            assert result.result_type == "complete"
            assert result.structured_content == expected
            assert json.loads(result.content[0].text) == expected

    run(scenario())


def test_generate_ground_track_returns_telemetry_structured_content(monkeypatch):
    monkeypatch.setattr(
        server_module,
        "get_satellite_info",
        lambda satellite_identifier: {
            "norad_id": 25544,
            "name": "ISS (ZARYA)",
            "tle_line1": "line 1",
            "tle_line2": "line 2",
        },
    )
    monkeypatch.setattr(
        server_module, "create_satellite_from_tle", lambda line1, line2: object()
    )
    monkeypatch.setattr(
        server_module,
        "generate_ground_track",
        lambda satellite, start, end, step: [
            (datetime(2026, 1, 1, 0, 0, 0), 51.5, -0.12, 408000.0)
        ],
    )
    monkeypatch.setattr(
        server_module,
        "calculate_footprint_from_position",
        lambda lat, lon, alt: None,
    )

    async def scenario():
        async with Client(server_module.server, mode="2026-07-28") as client:
            result = await client.call_tool(
                "generate_ground_track",
                {
                    "satellite_identifier": "ISS",
                    "start_time": "2026-01-01T00:00:00Z",
                    "duration": "1 minute",
                    "step_interval": "1 minute",
                },
            )

            telemetry = result.structured_content
            assert telemetry == [
                {
                    "id": "25544",
                    "time": "2026-01-01T00:00:00Z",
                    "position_lla": {
                        "lat_deg": 51.5,
                        "lon_deg": -0.12,
                        "alt_m": 408000.0,
                    },
                }
            ]
            assert json.loads(result.content[0].text) == telemetry

    run(scenario())
