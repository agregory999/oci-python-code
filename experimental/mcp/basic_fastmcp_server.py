#!/usr/bin/env python3
"""Basic FastMCP server example with TypedDict request/response models."""

from __future__ import annotations

import argparse
import datetime
import logging
from typing import Literal, TypedDict

from fastmcp import FastMCP

LOGGER = logging.getLogger(__name__)


class EchoRequest(TypedDict):
    """Request payload for the echo/transform operation.

    Attributes:
        message: Input text to transform.
        transform: Transformation mode.
    """

    message: str
    transform: Literal["none", "upper", "lower", "title"]


class EchoResponse(TypedDict):
    """Response payload for the echo/transform operation.

    Attributes:
        original_message: Original input text.
        transformed_message: Output text after transformation.
        transform: Applied transform mode.
        processed_at_utc: UTC timestamp of processing.
    """

    original_message: str
    transformed_message: str
    transform: str
    processed_at_utc: str


MCP = FastMCP("basic-fastmcp-server")


def build_response(request: EchoRequest) -> EchoResponse:
    """Build transformed response for an input request.

    Args:
        request: Echo request payload.

    Returns:
        EchoResponse: Transformed response payload.
    """
    message = request["message"]
    transform = request["transform"]

    if transform == "upper":
        transformed = message.upper()
    elif transform == "lower":
        transformed = message.lower()
    elif transform == "title":
        transformed = message.title()
    else:
        transformed = message

    return EchoResponse(
        original_message=message,
        transformed_message=transformed,
        transform=transform,
        processed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


@MCP.tool()
def echo_transform(message: str, transform: Literal["none", "upper", "lower", "title"] = "none") -> EchoResponse:
    """Transform a message and return structured output.

    Args:
        message: Input text.
        transform: Text transform operation.

    Returns:
        EchoResponse: Structured transformation result.
    """
    request = EchoRequest(message=message, transform=transform)
    response = build_response(request)
    LOGGER.info("Processed message using transform=%s", transform)
    return response


@MCP.tool()
def health_check() -> dict[str, str]:
    """Return a simple health payload.

    Returns:
        dict[str, str]: Health status metadata.
    """
    return {
        "status": "ok",
        "service": "basic-fastmcp-server",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run a basic FastMCP server in stdio or streamable-http mode."
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport mode (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP listen host.")
    parser.add_argument("--port", type=int, default=9000, help="HTTP listen port.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether to enable debug-level logging.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def main() -> int:
    """Run the FastMCP server.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)

    LOGGER.info("Starting FastMCP server with transport=%s", args.transport)
    if args.transport == "streamable-http":
        MCP.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        MCP.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
