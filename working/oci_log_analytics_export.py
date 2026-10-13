#!/usr/bin/env python3
"""Export OCI Log Analytics query results for an explicit start/end time range."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

from oci import config as oci_config
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, ServiceError
from oci.log_analytics import LogAnalyticsClient
from oci.log_analytics.models import ExportDetails, TimeRange

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Export OCI Log Analytics query results to a file for a fixed time range."
    )

    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "-pr",
        "--profile",
        help="OCI profile name (defaults to DEFAULT when omitted).",
    )
    auth_group.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication.",
    )

    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument(
        "-q",
        "--query",
        help="Log Analytics query string.",
    )
    query_group.add_argument(
        "--query-file",
        help="Path to a text file containing a Log Analytics query.",
    )

    parser.add_argument("-ns", "--namespace", required=True, help="Log Analytics namespace.")
    parser.add_argument(
        "-c",
        "--compartment-ocid",
        required=True,
        help="Compartment OCID for export query.",
    )
    parser.add_argument(
        "-s",
        "--start-time",
        required=True,
        help="Start time in ISO format (e.g. 2026-06-01T00:00:00Z).",
    )
    parser.add_argument(
        "-e",
        "--end-time",
        required=True,
        help="End time in ISO format (e.g. 2026-06-01T12:00:00Z).",
    )
    parser.add_argument("-r", "--region", help="Region override.")
    parser.add_argument(
        "-tz",
        "--timezone",
        default="UTC",
        help="Timezone string for the Log Analytics query (default: UTC).",
    )
    parser.add_argument(
        "-m",
        "--max-records",
        type=int,
        default=1_000_000,
        help="Maximum records to export (default: 1000000).",
    )
    parser.add_argument(
        "-f",
        "--format",
        default="CSV",
        choices=["CSV", "JSON"],
        help="Output format (default: CSV).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="log_analytics_export.csv",
        help="Output file path (default: log_analytics_export.csv).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")

    args = parser.parse_args()
    if args.max_records < 1:
        parser.error("--max-records must be >= 1")
    return args


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether to enable debug logging.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def parse_iso_datetime(value: str) -> datetime.datetime:
    """Parse an ISO-like datetime string.

    Args:
        value: Input datetime string.

    Returns:
        datetime.datetime: Parsed datetime object.

    Raises:
        ValueError: If the datetime string cannot be parsed.
    """
    normalized = value.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(normalized)


def load_query(args: argparse.Namespace) -> str:
    """Load query text from direct argument or file.

    Args:
        args: Parsed CLI arguments.

    Returns:
        str: Query text.

    Raises:
        ValueError: If query is empty.
        OSError: If query file cannot be read.
    """
    if args.query_file:
        query_text = Path(args.query_file).read_text(encoding="utf-8").strip()
    else:
        query_text = (args.query or "").strip()

    if not query_text:
        raise ValueError("Query text cannot be empty.")
    return query_text


def create_client(args: argparse.Namespace) -> LogAnalyticsClient:
    """Create OCI Log Analytics client.

    Args:
        args: Parsed CLI arguments.

    Returns:
        LogAnalyticsClient: Initialized client.

    Raises:
        ClientError: If OCI client creation fails.
    """
    if args.instance_principal:
        signer = InstancePrincipalsSecurityTokenSigner()
        config_data: dict[str, Any] = {}
        if args.region:
            config_data["region"] = args.region
        return LogAnalyticsClient(
            config=config_data,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )

    profile_name = args.profile or "DEFAULT"
    config_data = oci_config.from_file(profile_name=profile_name)
    if args.region:
        config_data["region"] = args.region

    return LogAnalyticsClient(config_data, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)


def run_export(args: argparse.Namespace) -> int:
    """Run the Log Analytics export process.

    Args:
        args: Parsed CLI arguments.

    Returns:
        int: Exit code.
    """
    try:
        query_text = load_query(args)
        start_time = parse_iso_datetime(args.start_time)
        end_time = parse_iso_datetime(args.end_time)
        if start_time >= end_time:
            LOGGER.error("--start-time must be earlier than --end-time")
            return 1
    except (OSError, ValueError) as exc:
        LOGGER.error("Input validation failed: %s", exc)
        return 2

    try:
        client = create_client(args)
    except (ClientError, ValueError) as exc:
        LOGGER.critical("OCI client initialization failed: %s", exc)
        return 2

    export_details = ExportDetails(
        compartment_id=args.compartment_ocid,
        sub_system="LOG",
        query_string=query_text,
        output_format=args.format,
        time_filter=TimeRange(
            time_start=start_time,
            time_end=end_time,
            time_zone=args.timezone,
        ),
        max_total_count=args.max_records,
        should_include_columns=True,
    )

    errors: list[str] = []
    output_path = Path(args.output)

    try:
        start_clock = datetime.datetime.now(datetime.timezone.utc)
        response = client.export_query_result(
            namespace_name=args.namespace,
            export_details=export_details,
        )
        query_done = datetime.datetime.now(datetime.timezone.utc)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.data.content)  # type: ignore[arg-type]
        done = datetime.datetime.now(datetime.timezone.utc)

        LOGGER.info(
            "Export complete: file=%s size=%d query_time=%s write_time=%s",
            output_path,
            output_path.stat().st_size,
            query_done - start_clock,
            done - query_done,
        )
    except ServiceError as exc:
        error_message = (
            f"service={exc.target_service} op={exc.operation_name} "
            f"status={exc.status} code={exc.code} message={exc.message}"
        )
        LOGGER.error(error_message)
        errors.append(error_message)
    except Exception as exc:  # pylint: disable=broad-except
        error_message = f"unexpected_error message={exc}"
        LOGGER.error(error_message)
        errors.append(error_message)

    if errors:
        LOGGER.warning("Export finished with %d errors.", len(errors))
        return 1
    return 0


def main() -> int:
    """Script entrypoint.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)
    return run_export(args)


if __name__ == "__main__":
    sys.exit(main())
