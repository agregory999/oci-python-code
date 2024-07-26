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
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails
from oci.identity.models import Compartment
from oci.identity import IdentityClient

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor, Future

global total
total = 0

# Finish Callback
def finish(future: Future):
    logger.debug(f"Future: {future.result()}")
    
    global total
    total += future.result()
    pass

# Threaded function - Network - public IP
def work_function(comp: Compartment) -> int:
    # ADB Example
    try:
        ips = vcn_client.list_public_ips(
            compartment_id=comp.id,
            scope="REGION",
            lifetime="RESERVED"
        ).data

        for ip in ips:
            logger.info(f"IP: {ip.ip_address} OCID: {ip.id} Assigned OCID: {ip.assigned_entity_id} Compartment: {comp.name} Created {ip.time_created}")
        
        return len(ips)
    except ServiceError as ex:
        logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
        logger.debug(f"Full Exception Detail: {ex}")


# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=8)

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
            tenancy_ocid = ""
        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            # Create the OCI Client to use
            vcn_client = VirtualNetworkClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            identity_client = IdentityClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)
            tenancy_ocid = config["tenancy"]

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # PHASE 3 - Main Script Execution (threaded)

    comp_list = []

    # Get root compartment into list
    root_comp = identity_client.get_compartment(compartment_id=tenancy_ocid).data 
    comp_list.append(root_comp)

    # Get all compartments (we don't know the depth of any), tenancy level
    # Using the paging API
    paginated_response = pagination.list_call_get_all_results(
        identity_client.list_compartments,
        tenancy_ocid,
        access_level="ACCESSIBLE",
        sort_order="ASC",
        compartment_id_in_subtree=True,
        lifecycle_state="ACTIVE",
        limit=1000)
    comp_list.extend(paginated_response.data)

    logger.info(f'Loaded {len(comp_list)} Compartments.')

    # Thread Pool with execution based on incoming list of Compartments
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = [executor.submit(work_function, c) for c in comp_list]
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")


        # # Add callbacks to report
        for future in results:
            # future.add_done_callback(print)
            future.add_done_callback(finish)

    logger.info(f"Finsihed - {total} results")