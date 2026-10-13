#!/usr/bin/env python3
"""OAuth/Bearer gateway example for protecting a streamable HTTP MCP server."""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any, TypedDict

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

LOGGER = logging.getLogger(__name__)
APP = FastAPI(title="MCP OAuth Gateway Example")


class OAuthIntrospectionResult(TypedDict):
    """OAuth token introspection result structure.

    Attributes:
        active: Whether the token is valid/active.
        subject: Subject/user identifier.
        scope: Space-delimited scope string.
    """

    active: bool
    subject: str
    scope: str


class ProxyEnvelope(TypedDict):
    """Response wrapper returned by this gateway.

    Attributes:
        proxied: Indicates forwarding was performed.
        upstream_status: HTTP status from MCP upstream.
        upstream_body: Parsed JSON or fallback text body from upstream.
    """

    proxied: bool
    upstream_status: int
    upstream_body: Any


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether DEBUG-level logs should be enabled.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def introspect_token_locally(access_token: str) -> OAuthIntrospectionResult:
    """Validate bearer token with a local stub implementation.

    Args:
        access_token: Bearer access token string.

    Returns:
        OAuthIntrospectionResult: Validation and identity metadata.
    """
    expected_token = os.getenv("MCP_BEARER_TOKEN", "change-me")
    if access_token != expected_token:
        return OAuthIntrospectionResult(active=False, subject="", scope="")

    return OAuthIntrospectionResult(
        active=True,
        subject=os.getenv("MCP_BEARER_SUBJECT", "local-user"),
        scope=os.getenv("MCP_BEARER_SCOPE", "mcp.invoke"),
    )


def extract_bearer_token(authorization_header: str | None) -> str:
    """Extract bearer token from Authorization header.

    Args:
        authorization_header: Raw Authorization header value.

    Returns:
        str: Extracted token value.

    Raises:
        HTTPException: If header is missing or malformed.
    """
    if not authorization_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Expected Bearer token")

    return parts[1].strip()


def ensure_scope(introspection: OAuthIntrospectionResult, required_scope: str) -> None:
    """Ensure token carries required scope.

    Args:
        introspection: Introspection result.
        required_scope: Required scope name.

    Raises:
        HTTPException: If token is inactive or missing required scope.
    """
    if not introspection["active"]:
        raise HTTPException(status_code=401, detail="Invalid token")

    scopes = set(introspection["scope"].split())
    if required_scope not in scopes:
        raise HTTPException(status_code=403, detail="Insufficient scope")


@APP.get("/health")
def health() -> dict[str, str]:
    """Return gateway health response.

    Returns:
        dict[str, str]: Health metadata.
    """
    return {"status": "ok", "service": "mcp-oauth-gateway-example"}


@APP.post("/mcp")
async def proxy_mcp_request(
    request: Request,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Validate bearer token and forward request to MCP upstream.

    Args:
        request: Incoming FastAPI request object.
        authorization: Authorization header value.

    Returns:
        JSONResponse: Proxied upstream response envelope.

    Raises:
        HTTPException: For auth or forwarding failures.
    """
    token = extract_bearer_token(authorization)
    introspection = introspect_token_locally(token)
    ensure_scope(introspection, required_scope=os.getenv("MCP_REQUIRED_SCOPE", "mcp.invoke"))

    upstream_url = os.getenv("MCP_UPSTREAM_URL", "http://127.0.0.1:9000/mcp")
    payload = await request.body()
    content_type = request.headers.get("content-type", "application/json")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream_response = await client.post(
                upstream_url,
                content=payload,
                headers={"content-type": content_type},
            )
    except httpx.HTTPError as exc:
        LOGGER.error("Upstream proxy error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Upstream MCP unavailable: {exc}") from exc

    try:
        upstream_body: Any = upstream_response.json()
    except ValueError:
        upstream_body = upstream_response.text

    envelope = ProxyEnvelope(
        proxied=True,
        upstream_status=upstream_response.status_code,
        upstream_body=upstream_body,
    )
    return JSONResponse(content=envelope, status_code=upstream_response.status_code)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run OAuth/Bearer gateway in front of streamable HTTP MCP server."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Listen host for gateway.")
    parser.add_argument("--port", type=int, default=9100, help="Listen port for gateway.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    """Run gateway web server.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)
    uvicorn.run(APP, host=args.host, port=args.port, log_level="debug" if args.verbose else "info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
