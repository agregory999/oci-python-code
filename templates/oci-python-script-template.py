#!/usr/bin/env python3
"""Self-contained OCI script template with argparse, logging, validation, and error handling."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from typing import Any

from oci import config as oci_config
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database import DatabaseClient
from oci.exceptions import ClientError, ServiceError

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Starter template for OCI scripts. "
            "Demonstrates auth options, input validation, verbose logging, and API error handling."
        )
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument("-r", "--region", help="Optional region override.")
    parser.add_argument(
        "-c",
        "--compartment-ocid",
        required=True,
        help="Compartment OCID for the sample work function.",
    )

    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "-pr",
        "--profile",
        help="OCI config profile to use (defaults to DEFAULT when omitted).",
    )
    auth_group.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication.",
    )

    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether DEBUG-level logs should be enabled.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def validate_compartment_ocid(compartment_ocid: str) -> bool:
    """Validate an OCI compartment OCID format.

    Args:
        compartment_ocid: Compartment OCID to validate.

    Returns:
        bool: True when the OCID appears valid.
    """
    return bool(re.match(r"^ocid1\.compartment\.oc1\..+", compartment_ocid))


def create_database_client(args: argparse.Namespace) -> DatabaseClient:
    """Create a DatabaseClient from selected authentication mode.

    Args:
        args: Parsed command-line arguments.

    Returns:
        DatabaseClient: Initialized OCI database client.

    Raises:
        ClientError: If authentication or client construction fails.
    """
    if args.instance_principal:
        LOGGER.info("Using instance principal authentication.")
        signer = InstancePrincipalsSecurityTokenSigner()
        config_data: dict[str, Any] = {}
        if args.region:
            config_data["region"] = args.region
        return DatabaseClient(
            config=config_data,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )

    profile_name = args.profile or "DEFAULT"
    LOGGER.info("Using OCI config profile: %s", profile_name)
    config_data = oci_config.from_file(profile_name=profile_name)
    if args.region:
        config_data["region"] = args.region

    return DatabaseClient(config_data, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)


def work(compartment_ocid: str, database_client: DatabaseClient) -> tuple[list[str], list[str]]:
    """Run example OCI work and return results with aggregated errors.

    Args:
        compartment_ocid: Target compartment OCID.
        database_client: Initialized OCI database client.

    Returns:
        tuple[list[str], list[str]]: (result summaries, error messages).
    """
    results: list[str] = []
    errors: list[str] = []

    try:
        response = database_client.list_pluggable_databases(
            compartment_id=compartment_ocid,
            limit=1000,
        )
        for pdb in response.data:
            summary = f"PDB={pdb.pdb_name} OCID={pdb.id} STATE={pdb.lifecycle_state}"
            results.append(summary)
            LOGGER.info(summary)
            LOGGER.debug("Full PDB object: %s", pdb)
    except ServiceError as exc:
        error_message = (
            "list_pluggable_databases "
            f"service={exc.target_service} op={exc.operation_name} "
            f"status={exc.status} code={exc.code} message={exc.message}"
        )
        LOGGER.error(error_message)
        errors.append(error_message)
    except Exception as exc:  # pylint: disable=broad-except
        error_message = f"unexpected_error message={exc}"
        LOGGER.error(error_message)
        errors.append(error_message)

    return results, errors


def main() -> int:
    """Execute script workflow.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)

    if not validate_compartment_ocid(args.compartment_ocid):
        LOGGER.critical("Invalid compartment OCID format: %s", args.compartment_ocid)
        return 2

    try:
        database_client = create_database_client(args)
    except (ClientError, ValueError) as exc:
        LOGGER.critical("Client initialization failed: %s", exc)
        return 2

    results, errors = work(args.compartment_ocid, database_client)
    LOGGER.info("Completed work: results=%d errors=%d", len(results), len(errors))

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
