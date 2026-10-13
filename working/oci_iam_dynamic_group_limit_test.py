"""Create and optionally delete many OCI Identity Domain dynamic groups for limit testing."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

from oci import config as oci_config
from oci import retry
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ClientError, ServiceError
from oci.identity import IdentityClient
from oci.identity_domains import IdentityDomainsClient
from oci.identity_domains.models import DynamicResourceGroup

LOGGER = logging.getLogger(__name__)
SCIM_DRG_SCHEMA = "urn:ietf:params:scim:schemas:oracle:idcs:DynamicResourceGroup"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Create N dynamic groups in an OCI identity domain for scale/limit testing, "
            "then optionally delete them."
        )
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument("-pr", "--profile", default="DEFAULT", help="OCI config profile name.")
    parser.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication instead of local OCI config.",
    )
    parser.add_argument("-r", "--region", help="Override OCI region.")
    parser.add_argument(
        "-d",
        "--domain-id",
        required=True,
        help="Identity Domain OCID (ocid1.domain...).",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=50,
        help="Number of dynamic groups to create (default: 50).",
    )
    parser.add_argument(
        "--name-prefix",
        default="dg-limit-test",
        help="Display name prefix for generated dynamic groups.",
    )
    parser.add_argument(
        "--matching-rule",
        required=True,
        help="Dynamic group matching rule to use for each created group.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause between API calls (default: 0).",
    )
    parser.add_argument(
        "--ids-file",
        default="dg_limit_test_ids.txt",
        help=(
            "Path to store created dynamic group IDs. "
            "Used as input when running --delete-only."
        ),
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--create-only",
        action="store_true",
        help="Only create dynamic groups, do not delete in the same run.",
    )
    mode_group.add_argument(
        "--delete-only",
        action="store_true",
        help="Only delete dynamic groups read from --ids-file.",
    )

    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1.")

    return args


def configure_logging(verbose: bool) -> None:
    """Configure logger format and level.

    Args:
        verbose: Whether to enable DEBUG logs.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def create_identity_clients(args: argparse.Namespace) -> tuple[IdentityClient, dict[str, Any]]:
    """Create an IdentityClient and base client configuration.

    Args:
        args: Parsed command line arguments.

    Returns:
        tuple[IdentityClient, dict[str, Any]]: Identity client and base config dictionary.

    Raises:
        ClientError: If OCI client initialization fails.
    """
    if args.instance_principal:
        LOGGER.info("Using instance principal authentication.")
        signer = InstancePrincipalsSecurityTokenSigner()
        base_config: dict[str, Any] = {}
        if args.region:
            base_config["region"] = args.region
            LOGGER.info("Overriding region to %s.", args.region)
        identity_client = IdentityClient(
            config=base_config,
            signer=signer,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )
        base_config["_signer"] = signer
        return identity_client, base_config

    LOGGER.info("Using local OCI config profile: %s", args.profile)
    base_config = oci_config.from_file(profile_name=args.profile)
    if args.region:
        base_config["region"] = args.region
        LOGGER.info("Overriding region to %s.", args.region)

    identity_client = IdentityClient(
        base_config,
        retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
    )
    return identity_client, base_config


def create_identity_domains_client(
    identity_client: IdentityClient,
    base_config: dict[str, Any],
    domain_id: str,
) -> IdentityDomainsClient:
    """Create IdentityDomainsClient with the correct domain service endpoint.

    Args:
        identity_client: Initialized OCI identity client.
        base_config: Base OCI config dictionary.
        domain_id: Identity domain OCID.

    Returns:
        IdentityDomainsClient: Configured domains client.

    Raises:
        ServiceError: If domain lookup fails.
    """
    domain = identity_client.get_domain(domain_id=domain_id).data
    LOGGER.info("Using identity domain endpoint: %s", domain.url)

    signer = base_config.get("_signer")
    if signer:
        return IdentityDomainsClient(
            config={k: v for k, v in base_config.items() if not k.startswith("_")},
            signer=signer,
            service_endpoint=domain.url,
            retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
        )

    return IdentityDomainsClient(
        base_config,
        service_endpoint=domain.url,
        retry_strategy=retry.DEFAULT_RETRY_STRATEGY,
    )


def create_dynamic_groups(
    client: IdentityDomainsClient,
    count: int,
    name_prefix: str,
    matching_rule: str,
    pause_seconds: float,
) -> tuple[list[str], list[str]]:
    """Create dynamic groups and collect any API errors.

    Args:
        client: Identity domains client.
        count: Number of groups to create.
        name_prefix: Prefix for dynamic group display names.
        matching_rule: SCIM dynamic group rule.
        pause_seconds: Pause between API calls.

    Returns:
        tuple[list[str], list[str]]: (created IDs, error messages).
    """
    created_ids: list[str] = []
    errors: list[str] = []

    for index in range(count):
        display_name = f"{name_prefix}-{index}"
        try:
            response = client.create_dynamic_resource_group(
                dynamic_resource_group=DynamicResourceGroup(
                    display_name=display_name,
                    matching_rule=matching_rule,
                    schemas=[SCIM_DRG_SCHEMA],
                )
            )
            dynamic_group = response.data
            created_ids.append(dynamic_group.id)
            LOGGER.info("Created DG %s: %s", display_name, dynamic_group.id)
        except ServiceError as exc:
            error_line = (
                f"create index={index} name={display_name} "
                f"service={exc.target_service} op={exc.operation_name} "
                f"status={exc.status} code={exc.code} message={exc.message}"
            )
            LOGGER.error(error_line)
            errors.append(error_line)
        except Exception as exc:  # pylint: disable=broad-except
            error_line = f"create index={index} name={display_name} error={exc}"
            LOGGER.error(error_line)
            errors.append(error_line)

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return created_ids, errors


def delete_dynamic_groups(
    client: IdentityDomainsClient,
    dynamic_group_ids: list[str],
    pause_seconds: float,
) -> list[str]:
    """Delete dynamic groups and collect any API errors.

    Args:
        client: Identity domains client.
        dynamic_group_ids: Dynamic group IDs to delete.
        pause_seconds: Pause between API calls.

    Returns:
        list[str]: Error message list.
    """
    errors: list[str] = []
    for index, dynamic_group_id in enumerate(dynamic_group_ids):
        try:
            client.delete_dynamic_resource_group(dynamic_resource_group_id=dynamic_group_id)
            LOGGER.info("Deleted DG %d: %s", index, dynamic_group_id)
        except ServiceError as exc:
            error_line = (
                f"delete index={index} id={dynamic_group_id} "
                f"service={exc.target_service} op={exc.operation_name} "
                f"status={exc.status} code={exc.code} message={exc.message}"
            )
            LOGGER.error(error_line)
            errors.append(error_line)
        except Exception as exc:  # pylint: disable=broad-except
            error_line = f"delete index={index} id={dynamic_group_id} error={exc}"
            LOGGER.error(error_line)
            errors.append(error_line)

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return errors


def write_ids_file(path: Path, dynamic_group_ids: list[str]) -> None:
    """Write dynamic group IDs to a file.

    Args:
        path: Output file path.
        dynamic_group_ids: IDs to write.
    """
    path.write_text("\n".join(dynamic_group_ids) + ("\n" if dynamic_group_ids else ""), encoding="utf-8")
    LOGGER.info("Wrote %d dynamic group IDs to %s", len(dynamic_group_ids), path)


def read_ids_file(path: Path) -> list[str]:
    """Read dynamic group IDs from a file.

    Args:
        path: Input file path.

    Returns:
        list[str]: Parsed dynamic group IDs.
    """
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line]


def main() -> int:
    """Run the dynamic group limit test utility.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)

    start_time = time.time()
    ids_file_path = Path(args.ids_file)
    create_errors: list[str] = []
    delete_errors: list[str] = []
    created_ids: list[str] = []

    try:
        identity_client, base_config = create_identity_clients(args)
        domains_client = create_identity_domains_client(
            identity_client=identity_client,
            base_config=base_config,
            domain_id=args.domain_id,
        )
    except (ClientError, ServiceError, ValueError) as exc:
        LOGGER.critical("Failed to initialize OCI clients: %s", exc)
        return 2

    if args.delete_only:
        if not ids_file_path.exists():
            LOGGER.critical("--delete-only requested but IDs file is missing: %s", ids_file_path)
            return 2
        target_ids = read_ids_file(ids_file_path)
        if not target_ids:
            LOGGER.warning("IDs file is empty: %s", ids_file_path)
        delete_errors = delete_dynamic_groups(domains_client, target_ids, args.pause_seconds)
    else:
        created_ids, create_errors = create_dynamic_groups(
            client=domains_client,
            count=args.count,
            name_prefix=args.name_prefix,
            matching_rule=args.matching_rule,
            pause_seconds=args.pause_seconds,
        )
        write_ids_file(ids_file_path, created_ids)

        if not args.create_only:
            delete_errors = delete_dynamic_groups(domains_client, created_ids, args.pause_seconds)

    elapsed_seconds = time.time() - start_time
    LOGGER.info(
        "Run complete in %.2fs. created=%d create_errors=%d delete_errors=%d",
        elapsed_seconds,
        len(created_ids),
        len(create_errors),
        len(delete_errors),
    )

    if create_errors or delete_errors:
        LOGGER.warning("Failures encountered; see logs for all create/delete API errors.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
