# TAT-C MCP Server

An MCP (Model Context Protocol) server that provides satellite ground track generation using the TAT-C (Tradespace Analysis Toolkit for Constellations) library. This server is **LLM-agnostic** and works with any LLM client that supports the MCP protocol (e.g., Claude Desktop, custom MCP clients, etc.). It communicates via stdio using the standard MCP protocol, allowing you to use your choice of LLM.

## Features

- **TLE Data Fetching**: Automatically fetches Two-Line Element (TLE) data from CelesTrak
- **Ground Track Generation**: Computes satellite ground tracks over specified time periods
- **Schema Compliance**: Outputs data in the format specified by SCHEMA.txt
- **LLM Integration**: Works with any MCP-compatible LLM client to interpret natural language prompts like "give the ISS ground track for the next hour at 1 minute steps"

## Prerequisites

- Python 3.8 or higher
- pip package manager

## Installation

### 1. Clone or Navigate to the Project Directory

```bash
cd tatc-mcp
```

### 2. Create a Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install base dependencies
pip install -r requirements.txt

# Install TAT-C library from GitHub
pip install git+https://github.com/code-lab-org/tatc.git

# Install MCP SDK
pip install mcp
```

Alternatively, install everything at once:

```bash
pip install mcp requests python-dateutil
pip install git+https://github.com/code-lab-org/tatc.git
```

## Usage

### Running the Server

The server can be run directly:

```bash
python server.py
```

The server will listen for MCP protocol messages on stdin/stdout.

### Using with Your Choice of LLM

This MCP server is **LLM-agnostic** and works with any LLM client that supports the MCP protocol. The server communicates via stdio using the standard MCP protocol, so you can use it with:

- **Claude Desktop**: Configure the server in your MCP settings
- **Custom MCP clients**: Any client that implements the MCP protocol
- **Other LLM platforms**: Any platform that supports MCP servers

To use this server, configure your LLM client to run:

```bash
python /path/to/tatc-mcp/server.py
```

The server will automatically handle tool registration and execution through the MCP protocol. No LLM-specific code or dependencies are required.

### Available Tools

#### 1. `generate_ground_track`

Generates ground track for a satellite.

**Parameters:**

- `satellite_identifier` (required): Satellite name (e.g., "ISS") or NORAD ID
- `start_time` (optional): Start time in ISO-8601 format or "now" (default: "now")
- `duration` (optional): Duration (e.g., "1 hour", "60 minutes", default: "1 hour")
- `step_interval` (optional): Time step (e.g., "1 minute", default: "1 minute")

**Returns:**
Array of telemetry objects matching SCHEMA.txt format, each containing:

- `id`: Satellite identifier (NORAD ID)
- `time`: ISO-8601 UTC timestamp
- `position_lla`: {lat_deg, lon_deg, alt_m}
- `footprint_geojson` (optional): GeoJSON Feature<Polygon>
- `trajectory_batches` (optional): Array of position/time pairs

#### 2. `get_satellite_info`

Fetches satellite information including TLE data from CelesTrak.

**Parameters:**

- `satellite_identifier` (required): Satellite name (e.g., "ISS") or NORAD ID

**Returns:**
Dictionary with:

- `norad_id`: NORAD catalog number
- `name`: Satellite name
- `tle_line1`: First TLE line
- `tle_line2`: Second TLE line

#### 3. `search_satellites`

Search for satellites by name in the CelesTrak database. Useful when you don't know the exact satellite name or NORAD ID.

**Parameters:**

- `query` (required): Satellite name or partial name to search for (e.g., "Starlink", "GPS", "NOAA")
- `limit` (optional): Maximum number of results to return (default: 10, max recommended: 50)

**Returns:**
List of satellite dictionaries, each containing:

- `norad_id`: NORAD catalog number
- `name`: Full satellite name
- `object_type`: Type of object (e.g., "PAYLOAD", "DEBRIS")
- `country`: Country of origin
- `launch_date`: Launch date

### Example Prompts for LLM

The server is designed to work with natural language prompts processed by an LLM. Examples:

1. **"give the ISS ground track for the next hour at 1 minute steps"**

   - Extracts: satellite="ISS", duration="1 hour", step="1 minute"

2. **"show me the Hubble Space Telescope ground track for the next 2 hours with 5 minute intervals"**

   - Extracts: satellite="Hubble", duration="2 hours", step="5 minutes"

3. **"get satellite info for NORAD ID 25544"**

   - Extracts: satellite_identifier="25544"

4. **"search for Starlink satellites"**
   - Extracts: query="Starlink"
   - Returns list of matching satellites with their NORAD IDs

### Supported Satellite Names

The server automatically searches the CelesTrak database for any satellite name you provide. You can use:

- **Common names**: "ISS", "Hubble", "TESS", "James Webb", "NOAA-19", etc.
- **Partial names**: "Starlink", "GPS", "NOAA" (will find matching satellites)
- **NORAD IDs**: Direct numeric IDs like "25544", "20580", etc.

The server includes a fast lookup for common satellites, and automatically falls back to searching the CelesTrak SATCAT database (with over 30,000 satellites) if the name isn't in the local cache. This means you can use virtually any satellite name from the database without needing to know the exact NORAD ID.

**Examples of supported queries:**

- "ISS" or "International Space Station" → Automatically finds NORAD ID 25544
- "Starlink" → Searches database and returns matching Starlink satellites
- "GPS" → Finds GPS satellites
- "NOAA-18" → Finds NOAA-18 satellite
- "25544" → Direct NORAD ID lookup

If a satellite name isn't found, the server will suggest similar matches to help you find the right satellite.

## Output Format

The server outputs data according to the SCHEMA.txt specification:

```json
{
  "id": "25544",
  "time": "2024-01-15T12:00:00Z",
  "position_lla": {
    "lat_deg": 51.6432,
    "lon_deg": -0.1234,
    "alt_m": 408000.0
  },
  "footprint_geojson": {
    "type": "Feature",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[lon1, lat1], [lon2, lat2], ...]]
    },
    "properties": {}
  },
  "trajectory_batches": [
    {
      "time": "2024-01-15T12:00:00Z",
      "position_lla": {"lat_deg": 51.6432, "lon_deg": -0.1234, "alt_m": 408000.0}
    }
  ]
}
```

## Project Structure

```
tatc-mcp/
├── server.py              # Main MCP server implementation
├── celestrak_client.py    # CelesTrak API client for TLE data
├── tatc_integration.py    # TAT-C library wrapper functions
├── schema_formatter.py   # SCHEMA.txt format conversion
├── validation.py         # Input validation utilities
├── SCHEMA.txt            # Telemetry schema specification
├── pyproject.toml        # Project configuration
├── requirements.txt      # Python dependencies
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Error Handling

The server includes comprehensive error handling:

- **TLE Validation**: Validates TLE format and checksums
- **Coordinate Validation**: Ensures coordinates are within valid ranges
- **Time Range Validation**: Validates time ranges and step intervals
- **API Error Handling**: Handles CelesTrak API errors gracefully
- **TAT-C Error Handling**: Handles TAT-C library errors gracefully

## Troubleshooting

### TAT-C Import Errors

If you see import errors for TAT-C:

```bash
pip install git+https://github.com/code-lab-org/tatc.git
```

### MCP SDK Errors

If MCP SDK is not found:

```bash
pip install mcp
```

### CelesTrak API Errors

If TLE fetching fails:

- Check your internet connection
- Verify the satellite name or NORAD ID is correct
- CelesTrak may be temporarily unavailable

### Coordinate Validation Errors

If you see coordinate validation errors:

- Ensure latitude is in [-90, 90]
- Longitude will be automatically normalized to [-180, 180]

## Development

### Running Tests

```bash
python -m unittest
```

### Code Style

This project follows PEP 8 style guidelines. Consider using `black` for formatting:

```bash
pip install black
black .
```

## License

This project uses the TAT-C library which is licensed under BSD-3-Clause. See the TAT-C repository for details.

## Acknowledgments

- **TAT-C Library**: [code-lab-org/tatc](https://github.com/code-lab-org/tatc)
- **CelesTrak**: Provides TLE data via [celestrak.org](https://celestrak.org)
- **MCP Protocol**: Model Context Protocol by Anthropic

## Support

For issues related to:

- **TAT-C Library**: See [TAT-C Documentation](https://tatc.readthedocs.io)
- **MCP Protocol**: See [MCP Documentation](https://modelcontextprotocol.io)
- **This Server**: Open an issue in the project repository
