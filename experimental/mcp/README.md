# MCP Examples (Experimental)

This directory contains simple **FastMCP** examples for local experimentation.

[Back to Experimental README](../README.md)

## Additional Install Requirements

These examples require extra Python packages beyond the base OCI scripts:

```bash
pip3 install -r experimental/mcp/requirements.txt
```

## Files

- `basic_fastmcp_server.py`
  - A minimal FastMCP server with typed request/response models (`TypedDict`)
  - Supports both transports:
    - `stdio`
    - `streamable-http`

- `mcp_oauth_gateway_example.py`
  - A lightweight OAuth/Bearer-style gateway example in front of MCP HTTP
  - Validates bearer token and required scope, then proxies requests to upstream MCP
  - Designed as a starting point for real OAuth introspection/JWKS integration

- `legacy/`
  - Previous MCP experiments moved here for reference

## Run: Basic FastMCP Server

### 1) STDIO mode

```bash
python3 experimental/mcp/basic_fastmcp_server.py --transport stdio
```

### 2) Streamable HTTP mode

```bash
python3 experimental/mcp/basic_fastmcp_server.py --transport streamable-http --host 127.0.0.1 --port 9000
```

## Run: OAuth/Bearer Gateway Example

Start MCP server first in streamable HTTP mode on port `9000`, then run:

```bash
export MCP_BEARER_TOKEN='change-me'
export MCP_REQUIRED_SCOPE='mcp.invoke'
export MCP_BEARER_SCOPE='mcp.invoke'
export MCP_UPSTREAM_URL='http://127.0.0.1:9000/mcp'
python3 experimental/mcp/mcp_oauth_gateway_example.py --host 127.0.0.1 --port 9100
```

Then clients call the gateway endpoint:

- URL: `http://127.0.0.1:9100/mcp`
- Header: `Authorization: Bearer change-me`

## Notes

- The gateway currently uses a local stub (`MCP_BEARER_TOKEN`) for validation.
- For production, replace this with real OAuth introspection/JWKS verification and stronger policy checks.
