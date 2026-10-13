#!/usr/bin/env python3
"""OCI limits discovery and availability checker.

This script can:
- List limit definitions (useful for discovering category/service/name)
- List current limit values for one or many services
- Check resource availability for a specific service + limit name
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

import oci
from oci import pagination, retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, RequestException, ServiceError
from oci.limits import LimitsClient
from oci.util import to_dict

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="OCI Limits discovery and checker tool.")

    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument("-pr", "--profile", help="OCI config profile (default: DEFAULT).")
    auth_group.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication.",
    )

    parser.add_argument("--region", help="Optional region override.")
    parser.add_argument(
        "--compartment-id",
        help="Compartment OCID to query (defaults to tenancy OCID).",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--list-definitions",
        action="store_true",
        help="List limit definitions (category/service/name style discovery).",
    )
    mode_group.add_argument(
        "--list-values",
        action="store_true",
        help="List current limit values for service(s).",
    )
    mode_group.add_argument(
        "--check-limit",
        action="store_true",
        help="Check availability for a specific service + limit name.",
    )

    parser.add_argument("--service", help="Service name filter (example: identity, compute).")
    parser.add_argument("--limit-name", help="Limit name for --check-limit mode.")
    parser.add_argument(
        "--all-services",
        action="store_true",
        help="For --list-values, discover services from definitions and query each.",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Optional row limit for display (0 means no limit).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")

    args = parser.parse_args()

    if args.check_limit and (not args.service or not args.limit_name):
        parser.error("--check-limit requires --service and --limit-name")

    if args.list_values and not args.service and not args.all_services:
        parser.error("--list-values requires --service or --all-services")

    if args.max_rows < 0:
        parser.error("--max-rows must be >= 0")

    return args


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether to enable debug logging.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def create_limits_client(args: argparse.Namespace) -> tuple[LimitsClient, str]:
    """Create LimitsClient and determine default compartment/tenancy OCID.

    Args:
        args: Parsed CLI args.

    Returns:
        tuple[LimitsClient, str]: Limits client and default tenancy OCID.

    Raises:
        ClientError: If client initialization fails.
    """
    if args.instance_principal:
        signer = InstancePrincipalsSecurityTokenSigner()
        client_config: dict[str, str] = {}
        if args.region:
            client_config["region"] = args.region
        client = LimitsClient(
            config=client_config,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )
        return client, signer.tenancy_id

    profile_name = args.profile or "DEFAULT"
    config_data = oci.config.from_file(profile_name=profile_name)
    if args.region:
        config_data["region"] = args.region
    client = LimitsClient(config_data, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
    return client, config_data["tenancy"]


def extract_field(record: dict[str, Any], *candidates: str) -> Any:
    """Extract first existing field value from a dict.

    Args:
        record: Data row dictionary.
        *candidates: Candidate field names.

    Returns:
        Any: First matching value, or None when missing.
    """
    for key in candidates:
        if key in record and record[key] is not None:
            return record[key]
    return None


def list_limit_definitions(client: LimitsClient, compartment_id: str, service: str | None) -> list[dict[str, Any]]:
    """List all limit definitions.

    Args:
        client: OCI Limits client.
        compartment_id: Compartment OCID context.
        service: Optional service filter.

    Returns:
        list[dict[str, Any]]: Limit definition rows.
    """
    kwargs: dict[str, Any] = {}
    if service:
        kwargs["service_name"] = service

    response = pagination.list_call_get_all_results(
        client.list_limit_definitions,
        compartment_id,
        **kwargs,
    )
    return [to_dict(item) for item in response.data]


def derive_services_from_definitions(definitions: list[dict[str, Any]]) -> list[str]:
    """Derive service names from definitions.

    Args:
        definitions: Limit definition rows.

    Returns:
        list[str]: Unique discovered service names.
    """
    services = {
        str(extract_field(item, "service_name", "service", "serviceName"))
        for item in definitions
        if extract_field(item, "service_name", "service", "serviceName")
    }
    return sorted(services)


def list_limit_values_for_service(
    client: LimitsClient,
    compartment_id: str,
    service: str,
) -> list[dict[str, Any]]:
    """List limit values for one service.

    Args:
        client: OCI Limits client.
        compartment_id: Compartment OCID.
        service: Service name.

    Returns:
        list[dict[str, Any]]: Limit value rows.
    """
    response = pagination.list_call_get_all_results(
        client.list_limit_values,
        compartment_id,
        service,
    )
    rows = [to_dict(item) for item in response.data]
    for row in rows:
        row.setdefault("service_name", service)
    return rows


def check_limit_availability(
    client: LimitsClient,
    compartment_id: str,
    service: str,
    limit_name: str,
) -> dict[str, Any]:
    """Check availability for one service/limit pair.

    Args:
        client: OCI Limits client.
        compartment_id: Compartment OCID.
        service: Service name.
        limit_name: Limit name.

    Returns:
        dict[str, Any]: Availability result.
    """
    response = client.get_resource_availability(
        service_name=service,
        limit_name=limit_name,
        compartment_id=compartment_id,
    )
    result = to_dict(response.data)
    result.setdefault("service_name", service)
    result.setdefault("name", limit_name)
    return result


def normalize_rows_for_display(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize row keys for readable table output.

    Args:
        rows: Raw OCI row dictionaries.

    Returns:
        list[dict[str, Any]]: Normalized rows.
    """
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized_row = dict(row)
        normalized_row.setdefault("category", extract_field(row, "scope_type", "category"))
        normalized_row.setdefault("service_name", extract_field(row, "service_name", "service"))
        normalized_row.setdefault("name", extract_field(row, "name", "limit_name"))
        normalized.append(normalized_row)
    return normalized


def render_table(rows: list[dict[str, Any]]) -> str:
    """Render rows as readable pipe-separated table.

    Args:
        rows: Data rows.

    Returns:
        str: Table text output.
    """
    if not rows:
        return "No rows returned."

    preferred_columns = [
        "category",
        "service_name",
        "name",
        "value",
        "available",
        "used",
        "fractional_availability",
        "effective_quota_value",
    ]

    all_keys = set().union(*(row.keys() for row in rows))
    columns = [column for column in preferred_columns if column in all_keys]
    columns.extend(sorted(all_keys - set(columns)))

    width_by_col: dict[str, int] = {}
    for col in columns:
        max_len = max(len(str(row.get(col, ""))) for row in rows)
        width_by_col[col] = min(max(len(col), max_len), 48)

    def format_row(row: dict[str, Any]) -> str:
        cells: list[str] = []
        for col in columns:
            cell = str(row.get(col, ""))
            if len(cell) > width_by_col[col]:
                cell = cell[: width_by_col[col] - 3] + "..."
            cells.append(cell.ljust(width_by_col[col]))
        return "| " + " | ".join(cells) + " |"

    header = format_row({col: col for col in columns})
    separator = "|" + "|".join("-" * (width_by_col[col] + 2) for col in columns) + "|"
    body = "\n".join(format_row(row) for row in rows)
    return f"{header}\n{separator}\n{body}"


def apply_row_limit(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    """Apply optional row cap for output.

    Args:
        rows: Row data.
        max_rows: Max rows (0 means no cap).

    Returns:
        list[dict[str, Any]]: Possibly truncated rows.
    """
    if max_rows == 0:
        return rows
    return rows[:max_rows]


def main() -> int:
    """Run CLI workflow.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)

    try:
        client, tenancy_ocid = create_limits_client(args)
    except (ClientError, ValueError) as exc:
        LOGGER.critical("Client initialization failed: %s", exc)
        return 2

    compartment_id = args.compartment_id or tenancy_ocid
    LOGGER.info("Using compartment OCID: %s", compartment_id)

    try:
        rows: list[dict[str, Any]]
        if args.list_definitions:
            rows = list_limit_definitions(client, compartment_id, args.service)
        elif args.list_values:
            if args.service:
                rows = list_limit_values_for_service(client, compartment_id, args.service)
            else:
                definitions = list_limit_definitions(client, compartment_id, service=None)
                services = derive_services_from_definitions(definitions)
                LOGGER.info("Discovered %d services from definitions.", len(services))
                rows = []
                for service_name in services:
                    try:
                        rows.extend(list_limit_values_for_service(client, compartment_id, service_name))
                    except ServiceError as exc:
                        LOGGER.warning(
                            "Skipping service '%s' due to API error: %s", service_name, exc
                        )
        else:
            rows = [
                check_limit_availability(
                    client,
                    compartment_id,
                    args.service,
                    args.limit_name,
                )
            ]
    except (ServiceError, RequestException, ValueError) as exc:
        LOGGER.error("Limit operation failed: %s", exc)
        return 1

    normalized_rows = normalize_rows_for_display(rows)
    limited_rows = apply_row_limit(normalized_rows, args.max_rows)

    if args.output == "json":
        print(json.dumps(limited_rows, indent=2, default=str))
    else:
        print(render_table(limited_rows))

    LOGGER.info("Rows returned: %d (displayed: %d)", len(normalized_rows), len(limited_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
