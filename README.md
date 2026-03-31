# TAT-C MCP Server

An MCP (Model Context Protocol) server that provides satellite ground track generation using the TAT-C library. The project is intentionally server-first: it exposes a standalone MCP server that can be used with any MCP-compatible LLM client and returns a consistent telemetry payload for downstream tools.

**Use Cases:**

- **Easy Data Gathering**: Use natural language to request satellite ground tracks (e.g., "give me the ISS ground track for the next hour")
- **Visualization Ready**: The generated data can be passed to downstream visualization tools and map/globe frontends
- **LLM Integration**: Works with any MCP-compatible LLM client

## Features

- **Satellite Metadata + TLE Fetching**: Resolves satellite identity and fetches current metadata/TLE data from CelesTrak
- **Ground Track Generation**: Computes satellite ground tracks over specified time periods
- **Structured Output**: Outputs stable telemetry objects with position and optional geometry fields
- **LLM-Agnostic**: Works with any MCP-compatible LLM client

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

The core dependency set pins `numpy<2.2` as a compatibility safeguard for environments that resolve `numba 0.61.x`, which does not support NumPy 2.2+.

### Running the Server

```bash
python -m tatc_mcp.server
```

The server listens for MCP protocol messages on stdin/stdout. Configure your LLM client to run this command to use the server from the project root.

## Available Tools

### `generate_ground_track`

Generates ground track for a satellite.

**Parameters:**

- `satellite_identifier` (required): Satellite name (e.g., "ISS") or NORAD ID
- `start_time` (optional): Start time in ISO-8601 format, `"now"`, or relative forms such as `"in one hour"` (default: `"now"`)
- `duration` (optional): Duration (e.g., `"1 hour"` or `"one hour"`, default: `"1 hour"`)
- `step_interval` (optional): Time step (e.g., "1 minute", default: "1 minute")

**Returns:** Array of telemetry objects with `id`, `time`, `position_lla` (lat/lon/alt), and optional `footprint_geojson` when geometry is available.

### `get_satellite_info`

Fetches satellite information including TLE data from CelesTrak.

**Parameters:**

- `satellite_identifier` (required): Satellite name or NORAD ID

**Returns:** Dictionary with `norad_id`, `name`, `tle_line1`, and `tle_line2`.

### `search_satellites`

Search for satellites by name in the CelesTrak database.

**Parameters:**

- `query` (required): Satellite name or partial name (e.g., "Starlink", "GPS")
- `limit` (optional): Maximum results (default: 10)

**Returns:** List of satellite dictionaries with NORAD ID, name, object type, country, and launch date.

## Example Prompts

- "give the ISS ground track for the next hour at 1 minute steps"
- "show me the Hubble Space Telescope ground track for the next 2 hours with 5 minute intervals"
- "get satellite info for NORAD ID 25544"
- "search for Starlink satellites"

## Supported Satellite Names

The server supports:

- **NORAD IDs**: Direct numeric IDs like `"25544"`
- **Exact/common names**: `"ISS"`, `"Hubble"`, `"James Webb"`, `"NOAA-19"`
- **Search-first workflows**: for broad or ambiguous terms such as `"Starlink"` or `"GPS"`, use `search_satellites` first and then pass the exact name or NORAD ID to the other tools

## Output Format

The server returns an array of telemetry objects shaped like:

```json
{
  "id": "25544",
  "time": "2024-01-15T12:00:00Z",
  "position_lla": {
    "lat_deg": 51.6432,
    "lon_deg": -0.1234,
    "alt_m": 408000.0
  },
  "footprint_geojson": { ... }
}
```

Field summary:

- `id`: stable satellite identifier
- `time`: ISO-8601 UTC timestamp
- `position_lla.lat_deg`: latitude in degrees
- `position_lla.lon_deg`: longitude in degrees
- `position_lla.alt_m`: altitude in meters
- `footprint_geojson`: optional GeoJSON polygon for visualization

## Troubleshooting

**MCP SDK Errors:**

```bash
pip install mcp
```

**CelesTrak API Errors:**

- Check internet connection
- Verify satellite name/NORAD ID is correct
- CelesTrak may be temporarily unavailable

## License

This project uses the TAT-C library (BSD-3-Clause). See the [TAT-C repository](https://github.com/code-lab-org/tatc) for details.

## Acknowledgments

- **TAT-C Library**: [code-lab-org/tatc](https://github.com/code-lab-org/tatc)
- **CelesTrak**: [celestrak.org](https://celestrak.org)
- **MCP Protocol**: Model Context Protocol by Anthropic
