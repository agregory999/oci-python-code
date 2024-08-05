# OCI Python Script - Find unused VCN
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides ....<basic documenation>.....

# Usage: python oci-python-xxx-yyy.py

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry

# OCI Clients and models (import as necessary)
from oci.core import VirtualNetworkClient
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
import datetime
from datetime import timezone
from concurrent.futures import ThreadPoolExecutor, Future

# Callback
def thread_completion_callback(future: Future):
    try:
        res = future.result()
        if res:
            logger.info(f"Result: {res}")
        else:
            pass
            # print(".",end="",flush=True)
    except Exception as e:
        logger.error(f"Failed: {e}")

# Threaded function
def work_function(ocid: str) -> str:
    # VCN Example
    try:

        # Get VCN
        vcn = vcn_client.get_vcn(
            vcn_id=ocid
        ).data

        logger.debug(f"VCN Name: {vcn.display_name}")
        logger.debug(f"Full Details: {vcn}")

        # List subnets
        subnet_list = vcn_client.list_subnets(
            compartment_id=vcn.compartment_id,
            vcn_id=vcn.id
        ).data
        logger.debug(f"Subnets in {vcn.display_name}: {subnet_list}")

        #can_delete=True
        for i,sn in enumerate(subnet_list):
            logger.debug(f"Subnet: {sn.display_name}")
            # Show allocation
            #alloc = vcn_client.get_subnet_cidr_utilization(subnet_id=sn.id).data
            alloc = vcn_client.get_subnet_ip_inventory(subnet_id=sn.id).data
            logger.debug(f"Alloc: {alloc.count} - {alloc.ip_inventory_subnet_resource_summary}")
            if alloc.count > 0:
                # if any subnet is in use, cannot delete
                return

        #logger.info(f"{vcn.display_name}:{vcn.time_created}{vcn.id}")                 
        if vcn.time_created < datetime.datetime(year=2023, month=12, day=31,tzinfo=timezone.utc):
            logger.debug(f"{vcn.display_name}:{vcn.id}:{vcn.time_created} -- Empty subnets and older than 2023")
        else:
            logger.debug(f"{vcn.display_name}:{vcn.id} -- Empty subnets and newer than 2023")
        return f"VCN {vcn.display_name}/{vcn.id} is able to be deleted"
    except ServiceError as ex:
        logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
        logger.debug(f"Full Exception Detail: {ex}")
        raise ex


# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose  # Boolean
    profile = args.profile  # String
    use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
    region = args.region # Region to use with Instance Principal, if not default
    threads = args.threads

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    # PHASE 2 - Creation of OCI Client(s) 
    try:

    # Client creation
        if use_instance_principals:
            logger.info(f"Using Instance Principal Authentication")

            signer = InstancePrincipalsSecurityTokenSigner()
            config_ip = {}
            if region:
                config_ip={"region": region}
                logger.info(f"Changing region to {region}")

            # Example of client
            vcn_client = VirtualNetworkClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config=config_ip, signer=signer)

        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            # Create the OCI Client to use
            vcn_client = VirtualNetworkClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # PHASE 3 - Main Script Execution (threaded)

    # Get Resource List via Search
    all_vcns = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query vcn resources sorted by timeCreated asc'
        ),
        limit=1000
    ).data

    # Build a list of OCIDs to operate on
    vcn_ocids = []
    for i,it in enumerate(all_vcns.items, start=1):
        vcn_ocids.append(it.identifier)

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:

        results = [executor.submit(work_function, ocid) for ocid in vcn_ocids]
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

        # Add callbacks to report
        for future in results:
            future.add_done_callback(thread_completion_callback)

    # for res in results:
    #     if res:
    #         logger.info(f"Result: {res}")
    #     else:
    #         logger.debug(f"Result: {res}")