#!/usr/bin/env python3
"""List direct child compartments for a given OCI compartment OCID.

The script prints each sub-compartment name and OCID, then prints the total
number of sub-compartments found.

Code written by Codex and Andrew Gregory in May 2026.

Usage:
    python3 oci-list-subcompartments.py --compartment-id ocid1.compartment...
    python3 oci-list-subcompartments.py --no-pagination --compartment-id ocid1.compartment...
    python3 oci-list-subcompartments.py --profile MYPROFILE --compartment-id ocid1.tenancy...
    python3 oci-list-subcompartments.py --instance-principal --compartment-id ocid1.compartment...
"""

import argparse
import sys
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="List direct child compartments for a given OCI compartment OCID."
    )
    parser.add_argument(
        "-c",
        "--compartment-id",
        required=True,
        help="Parent compartment OCID. Use the tenancy OCID to list top-level compartments.",
    )
    parser.add_argument(
        "-p",
        "--profile",
        default="DEFAULT",
        help="OCI config profile name from ~/.oci/config. Default: DEFAULT.",
    )
    parser.add_argument(
        "-ip",
        "--instance-principal",
        action="store_true",
        help="Use instance principal authentication instead of an OCI config profile.",
    )
    parser.add_argument(
        "-r",
        "--region",
        help="Optional region override.",
    )
    parser.add_argument(
        "--include-deleted",
        action="store_true",
        help="Include deleted/deleting compartments in the output.",
    )
    parser.add_argument(
        "--no-pagination",
        action="store_true",
        help="Use one direct Identity list_compartments call instead of the OCI paginator.",
    )
    return parser.parse_args()


def build_identity_client(
    profile: str,
    use_instance_principal: bool,
    region: str | None,
) -> Any:
    """Create an OCI Identity client.

    Args:
        profile: OCI config profile name to use when profile authentication is enabled.
        use_instance_principal: Whether to use instance principal authentication.
        region: Optional region override.

    Returns:
        Configured OCI Identity client.

    Raises:
        Exception: If the OCI config, signer, or client cannot be loaded.
    """
    from oci import config as oci_config
    from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
    from oci.identity import IdentityClient

    if use_instance_principal:
        signer = InstancePrincipalsSecurityTokenSigner()
        client_config: dict[str, Any] = {}
        if region:
            client_config["region"] = region
        return IdentityClient(config=client_config, signer=signer)

    client_config = oci_config.from_file(profile_name=profile)
    if region:
        client_config["region"] = region
    return IdentityClient(client_config)


def list_subcompartments(
    identity_client: Any,
    compartment_id: str,
    include_deleted: bool,
    use_pagination: bool,
) -> list[Any]:
    """List direct child compartments under a parent compartment.

    Args:
        identity_client: OCI Identity client.
        compartment_id: Parent compartment OCID.
        include_deleted: Whether to include deleted/deleting compartments.
        use_pagination: Whether to use the OCI pagination helper.

    Returns:
        Direct child compartments sorted by name.

    Raises:
        Exception: If the Identity service request fails.
    """
    list_args = {
        "compartment_id": compartment_id,
        "compartment_id_in_subtree": False,
        "access_level": "ACCESSIBLE",
        "sort_by": "NAME",
        # "limit": 99,  # 25 is new limit?
    }

    if use_pagination:
        from oci.pagination import list_call_get_all_results

        compartments = list_call_get_all_results(
            identity_client.list_compartments,
            **list_args,
        ).data
    else:
        compartments = identity_client.list_compartments(**list_args).data

    if include_deleted:
        return compartments

    return [
        compartment
        for compartment in compartments
        if compartment.lifecycle_state == "ACTIVE"
    ]


def print_compartments(compartments: list[Any]) -> None:
    """Print compartment names, OCIDs, and total count.

    Args:
        compartments: Compartments to print.
    """
    print(f"{'NAME':<40}  OCID")
    print("-" * 120)

    for compartment in compartments:
        print(f"{compartment.name:<40}  {compartment.id}")

    print("-" * 120)
    print(f"Sub-compartment count: {len(compartments)}")


def main() -> None:
    """Run the sub-compartment listing program."""
    args = parse_args()

    try:
        identity_client = build_identity_client(
            profile=args.profile,
            use_instance_principal=args.instance_principal,
            region=args.region,
        )
        compartments = list_subcompartments(
            identity_client=identity_client,
            compartment_id=args.compartment_id,
            include_deleted=args.include_deleted,
            use_pagination=not args.no_pagination
        )
    except ModuleNotFoundError as exc:
        if exc.name != "oci":
            raise
        print(
            "The OCI Python SDK is not installed in this environment. "
            "Install it with: python3 -m pip install oci",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        service_code = getattr(exc, "code", None)
        service_message = getattr(exc, "message", None)
        if service_code and service_message:
            print(
                f"Failed to list compartments: {service_code} - {service_message}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Failed to create OCI Identity client: {exc}", file=sys.stderr)
        sys.exit(1)

    print_compartments(compartments)


if __name__ == "__main__":
    main()
