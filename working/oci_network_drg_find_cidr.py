# OCI Python Script template
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides ....<basic documenation>.....

# Usage: python oci-python-xxx-yyy.py

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry, pagination

# OCI Clients and models (import as necessary)
from oci.core import VirtualNetworkClient
from oci.core.models import DrgAttachment
from oci.identity import IdentityClient
from oci.identity.models import Compartment

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

# Threaded function - get attachments
def get_attachments_compartment(comp: Compartment) -> list[DrgAttachment]:
    
    try:
        attachments = vn_client.list_drg_attachments(
            compartment_id=comp.id,
            drg_id=drg.id
        ).data

        # Parse Data
        for attachment in attachments:
            logger.debug(f"(th)Att: {attachment.display_name} Compartment: {comp.name}")

        return attachments

    except ServiceError as ex:
        logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
        logger.debug(f"Full Exception Detail: {ex}")
        return []

# Threaded function - get attachments
def get_attachment_cidr(attachment: DrgAttachment) -> tuple:
    
    try:
        vcn = vn_client.get_vcn(
            vcn_id=attachment.network_details.id
        ).data

        # Get the compartment
        comp = id_client.get_compartment(
            compartment_id=vcn.compartment_id
        ).data

        # Return a tuple (DrgAttachment, VCN, Compartment)
        return (ocid_region, attachment, vcn, comp)

    except ServiceError as ex:
        logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
        logger.debug(f"Full Exception Detail: {ex}")
        return []


# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    #parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("-d", "--drgocid", help="DRG OCID, required.  Multiple DRGs space separated", nargs='+', required=True)
    parser.add_argument("-m", "--markdown", help="Output Markdown (directory)")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose  # Boolean
    profile = args.profile  # String
    use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
    #region = args.region # Region to use with Instance Principal, if not default
    drg_ocids = args.drgocid # [String]
    threads = args.threads
    markdown = args.markdown

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')
    logger.info(f"DRG OCID: {drg_ocids}")

    # PHASE 2 - Main Script Execution

    compartments_list: list = []
    results_list: list = []

    # Iterate DRG listing
    for drg_ocid in drg_ocids:

        logger.info(f"Processing DRG {drg_ocid}...")

        # We need to parse the region out and create a client for that region
        garb1, ocid_type, garb2, ocid_region, garb3 = drg_ocid.split('.')
        if not ocid_type == "drg":
            logger.warning(f"OCID of {drg_ocid} not a DRG.  Continuing")
            continue

        logger.info(f"Continue with valid DRG {drg_ocid}...")
        # Connect to OCI with DEFAULT or defined profile
        try:

        # Client creation
            if use_instance_principals:
                logger.info(f"Using Instance Principal Authentication")

                signer = InstancePrincipalsSecurityTokenSigner()
                config_ip = {}
                if ocid_region:
                    config_ip={"region": ocid_region}
                    logger.info(f"Changing region to {ocid_region}")

                # Example of client
                vn_client = VirtualNetworkClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
                id_client = IdentityClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

                # Tenancy OCID
                tenancy_ocid = signer.tenancy_id
            else:
                # Use a profile (must be defined)
                logger.info(f"Using Profile Authentication: {profile}")
                configu = config.from_file(profile_name=profile)

                # Tenancy OCID
                tenancy_ocid = configu["tenancy"]
                if ocid_region:
                    configu["region"] = ocid_region
                    logger.info(f"Changing region to {ocid_region}")

                # Create the OCI Client to use
                vn_client = VirtualNetworkClient(configu, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
                id_client = IdentityClient(configu, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

        except ClientError as ex:
            logger.critical(f"Failed to connect to OCI: {ex}")

        if len(compartments_list) == 0:
            # Get compartments
            logger.debug(f"Getting compartments list")
            compartments_list = pagination.list_call_get_all_results(
                id_client.list_compartments,
                compartment_id_in_subtree=True,
                compartment_id=tenancy_ocid,
                limit=1000
            ).data
        else:
            logger.debug(f"Using existing compartments list")

        # Process DRG
        try:
            drg = vn_client.get_drg(
                drg_id=drg_ocid
            ).data # DRG

            logger.info(f"Looking at DRG: {drg.display_name} with OCID: {drg.id}")
            comp_ocid = drg.compartment_id

            # Thread Pool with execution based on incoming list of OCIDs
            with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
                results = executor.map(get_attachments_compartment, compartments_list)
                logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

            # Build a list of attachments from the threaded results
            attachments = []
            for res in results:
                # Print to resulting list
                for att in res:
                    attachments.append(att)

            # Thread Pool with execution based on incoming list of attachments - gets the VCN Details
            with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
                temp_results = executor.map(get_attachment_cidr, attachments)
                logger.info(f"Kicked off {threads} threads for parallel execution (attachments) - adjust as necessary")

            # Add to overall list
            results_list.extend(temp_results)

        except ServiceError as ex:
            logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
            logger.debug(f"Full Exception Detail: {ex}")

        # Deal with Markdown
        if markdown:
            with open(f'{markdown}/drg_attachments_latest.md', 'w') as f:
                f.write(f"Report generated: {date.today()}\n")
                f.write(f"|Region|Attachment Name|CIDR Range|Compartment|\n")
                f.write(f"|:---|:---|:---|:---:|\n")
                for res in results_list:
                    # Print out
                    att: DrgAttachment
                    reg, att, vcn, comp = res
                    
                    f.write(f"{reg} | {att.display_name} | {vcn.cidr_block} | {comp.name} |\n")
        else:
            for res in results:
                # Print out
                att: DrgAttachment
                att, vcn, comp = res
                
                logger.info(f"Attachment: {att.display_name} CIDR: {vcn.cidr_block} Compartment: {comp.name}")
