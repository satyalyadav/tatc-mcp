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

This release targets Python 3.10+, the final `2026-07-28` MCP specification, and the stable MCP Python SDK `mcp==2.0.0`. The core dependency set also pins `numpy<2.2` as a compatibility safeguard for TAT-C/Numba environments.

### Running the Server

```bash
python -m tatc_mcp.server
```

By default, the server listens for MCP protocol messages on stdin/stdout. Configure your LLM client to run this command to use the server from the project root.

For remote clients, run the stateless Streamable HTTP transport:

```bash
python -m tatc_mcp.server --transport streamable-http --host 127.0.0.1 --port 8000
```

The v2 SDK handles `server/discover`, per-request protocol metadata, `resultType` fields, required Streamable HTTP routing headers, and backwards compatibility with pre-2026 clients. For list-valued tools, MCP `2026-07-28` clients receive a native array schema and array-valued `structuredContent`; legacy clients receive an object-root `{ "data": [...] }` compatibility envelope. Both protocol versions receive the returned value as human-readable JSON text. The HTTP server uses the sessionless `2026-07-28` path and configures the legacy path as stateless because these tools do not need a server-to-client backchannel.

For a public listener, explicitly allow the externally visible Host header (and any browser Origin that will call it):

```bash
python -m tatc_mcp.server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8000 \
  --allowed-host mcp.example.com \
  --allowed-origin https://chat.example.com
```

Non-local listeners fail closed without `--allowed-host`. The escape hatch `--disable-dns-rebinding-protection` is intended only for a trusted reverse proxy that enforces equivalent Host and Origin checks. Public deployments should also terminate TLS and enforce authentication at the application or proxy layer.

## Available Tools

### `generate_ground_track`

Generates ground track for a satellite.

**Parameters:**

- `satellite_identifier` (required): Satellite name (e.g., "ISS") or NORAD ID
- `start_time` (optional): Start time in ISO-8601 format, `"now"`, or relative forms such as `"in one hour"` (default: `"now"`)
- `duration` (optional): Duration (e.g., `"1 hour"` or `"one hour"`, default: `"1 hour"`)
- `step_interval` (optional): Time step (e.g., "1 minute", default: "1 minute")

**Returns:** Array of telemetry objects with `id`, `time`, `position_lla` (lat/lon/alt), and optional `footprint_geojson` when geometry is available.

MCP `2026-07-28` clients receive a native array in `structuredContent`. Legacy clients receive the same list in the compatibility envelope `{ "data": [...] }`. Both clients also receive the list as human-readable JSON text.

### `get_satellite_info`

Fetches satellite information including TLE data from CelesTrak.

**Parameters:**

- `satellite_identifier` (required): Satellite name or NORAD ID

**Returns:** Dictionary with `norad_id`, `name`, `tle_line1`, and `tle_line2`.

MCP clients receive this as both human-readable JSON text and object-valued `structuredContent`.

### `search_satellites`

Search for currently orbiting satellites by name in the CelesTrak database. Historical objects with a recorded decay date are omitted so returned IDs can be passed to the TLE-backed tools.

**Parameters:**

- `query` (required): Satellite name or partial name (e.g., "Starlink", "GPS")
- `limit` (optional): Maximum results (default: 10)

**Returns:** List of satellite dictionaries with NORAD ID, name, object type, country, and launch date.

MCP `2026-07-28` clients receive a native array in `structuredContent`. Legacy clients receive the same list in the compatibility envelope `{ "data": [...] }`. Both clients also receive the list as human-readable JSON text.

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

List-valued tools return a native JSON array to MCP `2026-07-28` clients. Legacy clients receive the same list under the `data` key in `{ "data": [...] }`. The text content contains the JSON array in both modes. Each telemetry object is shaped like:

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

## Using With MCP Clients

### Codex CLI

Codex supports both local STDIO servers and remote Streamable HTTP servers. The official configuration file is `~/.codex/config.toml`.

In the current Windows + WSL setup used for this project, this local STDIO configuration is working:

```toml
[mcp_servers.tatc]
command = "wsl.exe"
args = ["bash", "-lc", "cd /home/satyal/tatc-mcp && python3 -m tatc_mcp.server"]
startup_timeout_sec = 30
tool_timeout_sec = 120
enabled = true

[features]
mcp_2026_07_28 = true
```

In Codex CLI builds where the new protocol is still marked under development, the feature entry above (or `codex --enable mcp_2026_07_28`) is required to negotiate the new stateless protocol. Without it, this server still serves Codex through the legacy handshake path and uses legacy-compatible object-root output envelopes.

You can also add the same server from the CLI:

```bash
codex mcp add tatc -- wsl.exe bash -lc "cd /home/satyal/tatc-mcp && python3 -m tatc_mcp.server"
```

### Codex App

In the current setup, the Codex app is reading the same `~/.codex/config.toml` entry successfully after restart. Use the same `tatc` block shown above.

Official Codex docs explicitly describe shared MCP configuration for the CLI and IDE extension. In this project, the app is also consuming that shared configuration successfully in practice.

### Claude Code

Claude Code supports both local STDIO servers and remote HTTP servers.

From the project root on Linux or WSL, you can add this server with:

```bash
claude mcp add tatc -- python3 -m tatc_mcp.server
```

If you want to add it from outside the repo directory, use:

```bash
claude mcp add tatc -- bash -lc 'cd /home/satyal/tatc-mcp && python3 -m tatc_mcp.server'
```

On native Windows, the same pattern can be run through WSL:

```bash
claude mcp add tatc -- wsl.exe --cd /home/satyal/tatc-mcp python3 -m tatc_mcp.server
```

### Cursor

Cursor supports `stdio`, `SSE`, and `Streamable HTTP` MCP transports. For the current local setup, use a project `.cursor/mcp.json` or global `~/.cursor/mcp.json` with a local STDIO server.

Example `mcp.json` entry for Windows + WSL:

```json
{
  "mcpServers": {
    "tatc": {
      "type": "stdio",
      "command": "wsl.exe",
      "args": ["bash", "-lc", "cd /home/satyal/tatc-mcp && python3 -m tatc_mcp.server"]
    }
  }
}
```

### Web Interfaces

ChatGPT Developer Mode and Claude web custom connectors require a remote MCP server URL. Local STDIO servers are not enough for those web interfaces.

That means this repository can be used locally today with Codex CLI, the current Codex app setup, Claude Code, and Cursor without hosting. To use it with ChatGPT web or Claude web, run the Streamable HTTP transport shown above and host it at a reachable HTTPS URL. SSE is not implemented here because the draft spec deprecates HTTP+SSE in favor of Streamable HTTP.

### References

- Codex MCP: https://developers.openai.com/codex/mcp
- ChatGPT Developer Mode: https://developers.openai.com/api/docs/guides/developer-mode
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Claude custom connectors: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- Cursor MCP: https://docs.cursor.com/en/context/mcp

## Troubleshooting

**LLM API key:**

The MCP server itself never calls an LLM and needs no key. Clients, test
scripts, and harnesses that drive the tools with a model read a generic
key from the environment via `tatc_mcp.llm_config`:

- `LLM_API_KEY` (required): any OpenAI-compatible chat-completions key.
- `LLM_BASE_URL` (optional): defaults to the ASU endpoint
  `https://openai.rc.asu.edu/v1`.
- `LLM_MODEL` (optional): defaults to `llama3-groq-70b-tool-use`.

Put them in the project-root `.env` file (gitignored, see `.env.example`)
or export them in your shell. A variable already in the environment always
wins over `.env`.
**MCP SDK Errors:**

```bash
pip install mcp==2.0.0
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

## MCP 2026-07-28 Compatibility

The project was audited against the final protocol and stable Python SDK, not only the earlier beta announcement. The implementation uses the stateless 2026 protocol path, native array-valued structured output, deterministic cached tool discovery, read-only tool annotations, strict JSON Schema input validation, and model-visible execution errors.

Features such as Tasks, elicitation, prompts, resources, subscriptions, and server-to-client requests are intentionally not advertised because the current satellite tools are short, synchronous, and read-only. They can be added later without changing the core tools contract.

Official sources used for the audit:

- [MCP 2026-07-28 final release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [MCP 2026-07-28 tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Python SDK v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
- [Python SDK low-level server guide](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/)
- [Python SDK deployment and transport security](https://py.sdk.modelcontextprotocol.io/run/deploy/)
- [Official MCP conformance suite](https://github.com/modelcontextprotocol/conformance)
