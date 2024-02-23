# coding: utf-8
# Copyright (c) 2016, 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.
#
# @author    : Andrew Gregory
#
# Supports Python 3
#
# DISCLAIMER – This is not an official Oracle application,  It is not supported by Oracle Support
#
# Find dynamic groups that have no policies associated with them
# Need to go through every policy in tenancy and look at statements
# Policies come from the other script - oci-policy-analysis.py - this script writes out its statements into a JSON-based cache file
# Please run this first so that the local cache is populated.

from oci import config
from oci.identity import IdentityClient
from oci.identity.models import UpdateDynamicGroupDetails
from oci.core import ComputeClient
from oci.retry import DEFAULT_RETRY_STRATEGY
from oci.database import DatabaseClient
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import pagination 
from oci.exceptions import ServiceError

import argparse
import json
import os
import logging
import re

# Use Policy Analysis
import oci_policy_analysis

# Lists
dynamic_group_statements = []
compute_client = {}
database_client = {}

# Counters
total_unused = 0
total_invalid = 0

# Global Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger('oci-dynamic-group-analysis')

# Helper functions

# OCID Validator
def validate_ocid(ocid: str) -> bool:
    '''Check the OCID and return False if it isn't a thing any more'''

    # Parse the OCID into pieces - compartments are missing a region - we also only care about some parts
    garb1, ocid_type, garb2, ocid_region, garb3 = ocid.split('.')

    try:
        # Based on type, use the configured client to see if it comes back with anything
        if "compartment" in ocid_type:
            a = identity_client.get_compartment(compartment_id=ocid)
        elif "instance" in ocid_type:
            a = compute_client[ocid_region].get_instance(instance_id=ocid)
        elif "dbsystem" in ocid_type:
            a = database_client[ocid_region].get_db_system(db_system_id=ocid)
        elif "autonomousdatabase" in ocid_type:
            a = database_client[ocid_region].get_autonomous_database(autonomous_database_id=ocid)
        elif "dbnode" in ocid_type:
            a = database_client[ocid_region].get_db_node(db_node_id=ocid)
        else:
            logger.warning(f"Type of OCID not supported: {ocid_type}")
    except ServiceError as exc:
        logger.debug(f"Caught error: {exc.message}")
        return False
    except KeyError as exc:
        logger.debug(f"Caught error - unable to determine: {exc}")
        return True


    return True

###############
# Main Code
###############
if __name__ == "__main__":
    # Parse Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal

    if verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logger.info)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    if use_instance_principals:
        logger.info("Using Instance Principal Authentication")
        signer = InstancePrincipalsSecurityTokenSigner()
        identity_client = IdentityClient(config={}, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
        for r in ["iad","phx"]:
            config = {"region": r}
            compute_client[r] = ComputeClient(config=config, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
            database_client[r] = DatabaseClient(config=config, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
            logger.info(f"Created compute for {r}")
        tenancy_ocid = signer.tenancy_id
        logger.info(f'Using tenancy OCID from Instance Profile: {tenancy_ocid}')
    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)
        identity_client = IdentityClient(config, retry_strategy=DEFAULT_RETRY_STRATEGY)
        for r in ["iad","phx"]:
            config["region"] = r
            compute_client[r] = ComputeClient(config, retry_strategy=DEFAULT_RETRY_STRATEGY)
            database_client[r] = DatabaseClient(config, retry_strategy=DEFAULT_RETRY_STRATEGY)
            logger.info(f"Created compute for {r}")
        logger.info(f'Compute Clients: {compute_client}')

        tenancy_ocid = config["tenancy"]
        logger.info(f'Using tenancy OCID from profile: {tenancy_ocid}')

    # Use the cache for policies
    logger.info('Attempting to load all policies from cache')

    if os.path.isfile(f'./.policy-dg-cache-{tenancy_ocid}.dat'):
        with open(f'./.policy-dg-cache-{tenancy_ocid}.dat', 'r') as filehandle:
            dynamic_group_statements = json.load(filehandle)
    else:
        # Call Policy analysis as module
        # Lists

        logger.info("---Starting Load from Policy Module---")
        
        oci_policy_analysis.load_policy_analysis(id_client=identity_client,
                                                 tenancy_ocid=tenancy_ocid,
                                                 recursion=True,
                                                 threads=9)

        dynamic_group_statements = oci_policy_analysis.dynamic_group_statements
        logger.info("---Finished Loaded from Policy Module---")

    # Load DGs
    dynamic_groups = []

    paginated_response = pagination.list_call_get_all_results(
        identity_client.list_dynamic_groups,
                compartment_id=tenancy_ocid,
                limit=1000
    )
    dynamic_groups.extend(paginated_response.data)

    # Print what we have (if verbose)
    for i, dg in enumerate(dynamic_groups):
        logger.debug(f'Found Dynamic Group {i}: {dg.name} {dg.matching_rule}')

        # Pull Tags
        current_tags = dg.freeform_tags
        # Assume valid until it isnt
        current_tags["VALID"] = "true"

        # OCID Pattern
        match = re.findall(r'ocid1.[a-z]+.oc1.[a-z0-9|-]*.[a-z0-9]+',dg.matching_rule)
        is_valid = True
        for oc in match:
            if not validate_ocid(oc):
                is_valid = False
        if not is_valid:
            logger.info(f"Valid : {is_valid} Dynamic Group: {dg.name} Rule: {dg.matching_rule}")
            current_tags["VALID"] = f"false, {oc}"
            total_invalid = total_invalid + 1

        # Check to see if in any known policy statements
        valid_policy_statements = list(filter(lambda statement: str(dg.name).casefold() in statement[0].casefold(), dynamic_group_statements))
        current_tags["STATEMENTS"] = str(len(valid_policy_statements))
        if len(valid_policy_statements) == 0:
            logger.debug(f"Dynamic Group isn't in any statements: {dg.name}: {dg.id}")
            current_tags["STATEMENTS"] = "Dynamic Group isn't in any statements!"
            total_unused = total_unused + 1
        else:
            current_tags["STATEMENTS"] = ""
            for st in valid_policy_statements:
                current_tags["STATEMENTS"] = f'({st[5]}/{st[6]}): {st[9]}, {current_tags["STATEMENTS"]}'
            current_tags["STATEMENTS"] = current_tags["STATEMENTS"][:255]
        # Update the DG with the freeform tag   
        identity_client.update_dynamic_group(dynamic_group_id=dg.id,
                                                update_dynamic_group_details=UpdateDynamicGroupDetails(
                                                    freeform_tags=current_tags
                                                )
                                            )

    logger.info(f"Finished. Out of {len(dynamic_groups)} in tenancy, there are {total_invalid} with invalid OCIDs and {total_unused} not in any statements.")
