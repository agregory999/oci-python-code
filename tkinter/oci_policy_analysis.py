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
# This example shows how the API can be used to build and analyze OCI Policies in a tenancy.
# The script recursively builds (and caches) a list of policy statements with provenance
# across a tenancy.  Because policies can be located in sub-compartments, it is generally harder
# to find which policies apply to a resource, a group, a compartment, and such.
# By running this script, you build a list of all statements in the tenancy, regardless of where they
# are located, and then you use the filtering commands to retrieve what you want.
# Please look at the argument parsing section or run with --help to see what is possible

from oci import config
from oci.identity import IdentityClient
from oci.identity.models import Compartment
from oci import loggingingestion

import argparse
import json
import logging
import datetime

from policy import PolicyAnalysis
from dynamic import DynamicGroupAnalysis

# Define Logger for module
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger('oci-policy-analysis')


########################################
# Main Code
# Pre-and Post-processing
########################################

if __name__ == "__main__":
    # Parse Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-sf", "--subjectfilter", help="Filter all statement subjects by this text")
    parser.add_argument("-vf", "--verbfilter", help="Filter all verbs (inspect,read,use,manage) by this text")
    parser.add_argument("-rf", "--resourcefilter", help="Filter all resource (eg database or stream-family etc) subjects by this text")
    parser.add_argument("-lf", "--locationfilter", help="Filter all location (eg compartment name)")
    parser.add_argument("-hf", "--hierarchyfilter", help="Filter by compartment hierarchy (eg compartment in tree)")
    parser.add_argument("-cf", "--conditionfilter", help="Filter by Condition")
    parser.add_argument("-pf", "--policynamefilter", help="Filter by Policy Name")
    parser.add_argument("-r", "--recurse", help="Recursion or not (default True)", action="store_true")
    parser.add_argument("-c", "--usecache", help="Load from local cache (if it exists)", action="store_true")
    parser.add_argument("-w", "--writejson", help="Write filtered output to JSON", action="store_true")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-lo", "--logocid", help="Use an OCI Log - provide OCID")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=1)
    args = parser.parse_args()
    verbose = args.verbose
    use_cache = args.usecache
    profile = args.profile
    threads = args.threads
    sub_filter = args.subjectfilter
    verb_filter = args.verbfilter
    resource_filter = args.resourcefilter
    location_filter = args.locationfilter
    hierarchy_filter = args.hierarchyfilter
    condition_filter = args.conditionfilter
    policy_name_filter = args.policynamefilter
    recursion = args.recurse
    write_json_output = args.writejson
    use_instance_principals = args.instanceprincipal
    log_ocid = None if not args.logocid else args.logocid

    # Update Logging Level
    if verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logging.INFO)

    logger.info(f'Using {"profile" + profile if not use_instance_principals else "instance principals"} with Logging level {"DEBUG" if verbose else "INFO"}')

    # Create the class
    policy_analysis = PolicyAnalysis(progress=None, 
                                     verbose=verbose)

    # Instruct it to do stuff
    policy_analysis.initialize_client(profile=profile,
                                     use_instance_principal=use_instance_principals,
                                     use_cache=use_cache,
                                     use_recursion=recursion
                                     )
    # Load the policies
    policy_analysis.load_policies_from_client()

    # Apply Filters
    filtered_statements = policy_analysis.filter_policy_statements(subj_filter=sub_filter if sub_filter else "",
                                                                   verb_filter=verb_filter if verb_filter else "",
                                                                   resource_filter=resource_filter if resource_filter else "",
                                                                   location_filter=location_filter if location_filter else "",
                                                                   hierarchy_filter=hierarchy_filter if hierarchy_filter else "",
                                                                   condition_filter=condition_filter if condition_filter else "",
                                                                   text_filter="",
                                                                   policy_filter=policy_name_filter if policy_name_filter else "")
    
    json_pol = json.dumps(filtered_statements, indent=2)
    logger.info(json_pol)

    # # Initialize DG
    # dynamic_group_analysis = DynamicGroupAnalysis(progress=None,
    #                                               verbose=verbose)
    
    # dynamic_group_analysis.initialize_client(profile=profile,
    #                                          use_instance_principal=use_instance_principals)
    
    # dynamic_group_analysis.load_all_dynamic_groups(use_cache=use_cache)

    # json_dg = json.dumps(dynamic_group_analysis.dynamic_groups, indent=2)
    # logger.info(json_dg)


    # # To output file if required
    if write_json_output:
        save_details = { "save-date" : str(datetime.datetime.now()),
                    "subject-filter" : sub_filter,
                    "verb-filter": verb_filter,
                    "resource-filter": resource_filter,
                    "location-filter": location_filter,
                    "hierarchy-filter": hierarchy_filter,
                    "condition-filter": condition_filter,
                    "text-filter": "",
                    "policy-name-filter": policy_name_filter,
                    "filtered-policy-statements": filtered_statements
    }

        json_object = json.dumps(filtered_statements, indent=2)
        with open(f"policyoutput-{policy_analysis.tenancy_ocid}.json", "w") as outfile:
            outfile.write(json_object)

    logger.info(f"-----Complete ({len(filtered_statements)})--------")