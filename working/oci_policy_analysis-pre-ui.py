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
from oci import pagination
from oci.retry import DEFAULT_RETRY_STRATEGY
from oci.exceptions import ConfigFileNotFound

from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.loggingingestion.models import PutLogsDetails, LogEntry, LogEntryBatch

import argparse
import json
import os
import datetime
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor

# Define Logger for module
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger('oci-policy-analysis')

# Global
global identity_client

# Lists
dynamic_group_statements = []
service_statements = []
regular_statements = []
special_statements = []

########################################
# Helper Methods


def print_statement(statement_tuple):
    a, b, c, d, e = statement_tuple
    logger.debug(f"Subject: {a}, Verb: {b}, Resource: {c}, Location: {d}, Condition: {e}")


def parse_statement(statement, comp_string, policy):
    # Parse tuple and partition
    # (subject, verb, resource, location, condition)
    # Pass 1 - where condition
    # Pass 2 - group subject
    # Pass 3 - location
    # Pass 4 - verb and resource
    pass1 = statement.casefold().partition(" where ")
    condition = pass1[2]
    pass2a = pass1[0].partition("allow ")
    pass2b = pass2a[2].partition(" to ")
    subject = pass2b[0]
    pass3 = pass2b[2].partition(" in ")
    location = pass3[2]
    pass4 = pass3[0].partition(" ")
    verb = pass4[0]
    resource = pass4[2]

    # Location Update
    # If compartment name, use hierarchy, if id then leave alone
    if "compartment id" in location:
        pass
    elif "tenancy" in location:
        pass
    else:
        sub_comp = location.partition("compartment ")[2]
        if comp_string == "":
            # if root, then leave compartment alone
            # location = f"compartment {comp_name}"
            pass
        else:
            location = f"compartment {comp_string}:{sub_comp}"

    # Build tuple based on modified location
    statement_tuple = (subject, verb, resource, location, condition,
                       f"{comp_string}", policy.name, policy.id, policy.compartment_id, statement)
    return statement_tuple

# Recursive Compartments / Policies
def get_compartment_path(compartment: Compartment, level, comp_string) -> str:

    # Top level forces fall back through
    logger.debug(f"Compartment Name: {compartment.name} ID: {compartment.id} Parent: {compartment.compartment_id}") 
    if not compartment.compartment_id:
        logger.debug(f"Top of tree. Path is {comp_string}")
        return comp_string
    parent_compartment = identity_client.get_compartment(compartment_id=compartment.compartment_id).data    

    # Recurse until we get to top
    logger.debug(f"Recurse. Path is {comp_string}")
    return get_compartment_path(parent_compartment, level+1, compartment.name + "/" + comp_string)

# Threadable policy loader - per compartment
def load_policies(compartment: Compartment):
    logger.debug(f"Compartment: {compartment.id}")

    # Get policies First
    list_policies_response = identity_client.list_policies(
        compartment_id=compartment.id,
        limit=1000
    ).data

    logger.debug(f"Pol: {list_policies_response}")
    # Nothing to do if no policies
    if len(list_policies_response) == 0:
        logger.debug("No policies. return")
        return
    
    # Load recursive structure of path (only if there are policies)
    path = get_compartment_path(compartment, 0, "")
    logger.debug(f"Compartment Path: {path}")

    for policy in list_policies_response:
        logger.debug(f"() Policy: {policy.name} ID: {policy.id}")
        for index, statement in enumerate(policy.statements, start=1):
            logger.debug(f"-- Statement {index}: {statement}")

            # Make lower case
            statement = str.casefold(statement)

            # Root out "special" statements (endorse / define / as)
            if str.startswith(statement, "endorse") or str.startswith(statement, "admit") or str.startswith(statement, "define"):
                # Special statement tuple
                statement_tuple = (statement,
                                   f"{path}", policy.name, policy.id, policy.compartment_id)

                special_statements.append(statement_tuple)
                continue

            # Helper returns tuple with policy statement and lineage
            statement_tuple = parse_statement(
                statement=statement,
                comp_string=path,
                policy=policy
            )

            if statement_tuple[0] is None or statement_tuple[0] == "":
                logger.debug(f"****Statement {statement} resulted in bad tuple: {statement_tuple}")

            if "dynamic-group " in statement_tuple[0]:
                dynamic_group_statements.append(statement_tuple)
            elif "service " in statement_tuple[0]:
                service_statements.append(statement_tuple)
            else:
                regular_statements.append(statement_tuple)
    logger.debug(f"confused")

# Load the policies (main function)
def load_policy_analysis(id_client:IdentityClient, tenancy_ocid: str, recursion: bool, threads:int):
    # Requirements
    # Logger (should be set somewhere)
    # IdentityClient
         # If set from main() it is ok, otherwise take from function call
    global identity_client
    identity_client = id_client
    logger.info(f"---Starting Policy Load---")

    # Load the policies
    # Start with list of compartments
    comp_list = []

    # Get root compartment into list
    root_comp = identity_client.get_compartment(compartment_id=tenancy_ocid).data 
    comp_list.append(root_comp)

    if recursion:
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

    logger.info(f'Loaded {len(comp_list)} Compartments.  {"Using recursion" if recursion else "No Recursion, only root-level policies"}')
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(load_policies, comp_list)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")
    for res in results:
        logger.debug(f"Result: {res}")
    logger.info(f"---Finished Policy Load---")



########################################
# Main Code
# Pre-and Post-processing
########################################

if __name__ == "__main__":
    # Parse Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    #parser.add_argument("-o", "--ocid", help="OCID of compartment (if not passed, will use tenancy OCID from profile)", default="TENANCY")
    parser.add_argument("-sf", "--subjectfilter", help="Filter all statement subjects by this text")
    parser.add_argument("-vf", "--verbfilter", help="Filter all verbs (inspect,read,use,manage) by this text")
    parser.add_argument("-rf", "--resourcefilter", help="Filter all resource (eg database or stream-family etc) subjects by this text")
    parser.add_argument("-lf", "--locationfilter", help="Filter all location (eg compartment name) subjects by this text")
    parser.add_argument("-r", "--recurse", help="Recursion or not (default True)", action="store_true")
    parser.add_argument("-c", "--usecache", help="Load from local cache (if it exists)", action="store_true")
    parser.add_argument("-w", "--writejson", help="Write filtered output to JSON", action="store_true")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-lo", "--logocid", help="Use an OCI Log - provide OCID")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=1)
    args = parser.parse_args()
    verbose = args.verbose
    use_cache = args.usecache
    #ocid = args.ocid
    profile = args.profile
    threads = args.threads
    sub_filter = args.subjectfilter
    verb_filter = args.verbfilter
    resource_filter = args.resourcefilter
    location_filter = args.locationfilter
    recursion = args.recurse
    write_json_output = args.writejson
    use_instance_principals = args.instanceprincipal
    log_ocid = None if not args.logocid else args.logocid

    # Update Logging Level
    if verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logging.INFO)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    if use_instance_principals:
        logger.info("Using Instance Principal Authentication")
        signer = InstancePrincipalsSecurityTokenSigner()
        identity_client = IdentityClient(config={}, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
        loggingingestion_client = loggingingestion.LoggingClient(config={}, signer=signer)
        tenancy_ocid = signer.tenancy_id
    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        try:
            config = config.from_file(profile_name=profile)
            logger.info(f'Using tenancy OCID from profile: {config["tenancy"]}')
            tenancy_ocid = config["tenancy"]

            # Create the OCI Client to use
            identity_client = IdentityClient(config, retry_strategy=DEFAULT_RETRY_STRATEGY)
            loggingingestion_client = loggingingestion.LoggingClient(config)
        except ConfigFileNotFound as exc:
            logger.fatal(f"Unable to use Profile Authentication: {exc}")
            exit(1)

    # Load from cache (if exists)
    if use_cache:
        logger.info("Loading Policy statements from cache")

        if os.path.isfile(f'./.policy-special-cache-{tenancy_ocid}.dat'):
            with open(f'./.policy-special-cache-{tenancy_ocid}.dat', 'r') as filehandle:
                special_statements = json.load(filehandle)
        if os.path.isfile(f'./.policy-dg-cache-{tenancy_ocid}.dat'):
            with open(f'./.policy-dg-cache-{tenancy_ocid}.dat', 'r') as filehandle:
                dynamic_group_statements = json.load(filehandle)
        if os.path.isfile(f'.policy-svc-cache-{tenancy_ocid}.dat'):
            with open(f'./.policy-svc-cache-{tenancy_ocid}.dat', 'r') as filehandle:
                service_statements = json.load(filehandle)
        if os.path.isfile(f'.policy-statement-cache-{tenancy_ocid}.dat'):
            with open(f'./.policy-statement-cache-{tenancy_ocid}.dat', 'r') as filehandle:
                regular_statements = json.load(filehandle)
    else:
        # Call using function that is designed as a module function to be called from outside of this code
        load_policy_analysis(id_client=identity_client,
                             tenancy_ocid=tenancy_ocid,
                             recursion=recursion,
                             threads=threads)


    # Write to local cache (per type)
    with open(f'.policy-special-cache-{tenancy_ocid}.dat', 'w') as filehandle:
        json.dump(special_statements, filehandle)
    with open(f'.policy-dg-cache-{tenancy_ocid}.dat', 'w') as filehandle:
        json.dump(dynamic_group_statements, filehandle)
    with open(f'.policy-svc-cache-{tenancy_ocid}.dat', 'w') as filehandle:
        json.dump(service_statements, filehandle)
    with open(f'.policy-statement-cache-{tenancy_ocid}.dat', 'w') as filehandle:
        json.dump(regular_statements, filehandle)

    # Perform Filtering
    if sub_filter:
        logger.info(f"Filtering subject: {sub_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: sub_filter.casefold() in statement[0].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: sub_filter.casefold() in statement[0].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: sub_filter.casefold() in statement[0].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    if verb_filter:
        logger.info(f"Filtering verb: {verb_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    if resource_filter:
        logger.info(f"Filtering resource: {resource_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    if location_filter:
        logger.info(f"Filtering location: {location_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    # Print Special
    entries = []
    logger.info("========Summary Special==============")
    for index, statement in enumerate(special_statements, start=1):
        logger.info(f"Statement #{index}: {statement[0]} | Policy: {statement[2]}")
        entries.append(LogEntry(id=str(uuid.uuid1()),
                                data=f"Statement #{index}: {statement}"))
    logger.info(f"Total Special statement in tenancy: {len(special_statements)}")

    # Create Log Batch
    special_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.utcnow(),
                                  source="oci-policy-analysis",
                                  type="special-statement",
                                  entries=entries)

    # Print Dynamic Groups
    entries = []
    logger.info("========Summary DG==============")
    for index, statement in enumerate(dynamic_group_statements, start=1):
        logger.info(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}")
        entries.append(LogEntry(id=str(uuid.uuid1()),
                                data=f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}"))
    logger.info(f"Total Service statement in tenancy: {len(dynamic_group_statements)}")

    # Create Log Batch
    dg_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.utcnow(),
                             source="oci-policy-analysis",
                             type="dynamic-group-statement",
                             entries=entries)

    # Print Service
    entries = []
    logger.info("========Summary SVC==============")
    for index, statement in enumerate(service_statements, start=1):
        logger.info(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}")
        entries.append(LogEntry(id=str(uuid.uuid1()),
                                data=f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}"))
    logger.info(f"Total Service statement in tenancy: {len(service_statements)}")

    # Create Log Batch
    service_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.utcnow(),
                                  source="oci-policy-analysis",
                                  type="service-statement",
                                  entries=entries)

    # Print Regular
    entries = []
    logger.info("========Summary Reg==============")
    for index, statement in enumerate(regular_statements, start=1):
        logger.info(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}{statement[6]}")
        entries.append(LogEntry(id=str(uuid.uuid1()),
                                data=f"Statement #{index}: {statement[9]} | Policy: {statement[5]}{statement[6]}"))
    logger.info(f"Total Regular statements in tenancy: {len(regular_statements)}")

    # Create Log Batch
    regular_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.now(datetime.timezone.utc),
                                  source="oci-policy-analysis",
                                  type="regular-statement",
                                  entries=entries)

    # Write batches to OCI Logging
    if log_ocid:
        put_logs_response = loggingingestion_client.put_logs(
            log_id=log_ocid,
            put_logs_details=PutLogsDetails(
                specversion="1.0",
                log_entry_batches=[special_batch, dg_batch, service_batch, regular_batch]
            )
        )

    # To output file if required
    if write_json_output:
        # Empty Dictionary
        statements_list = []
        for i, s in enumerate(special_statements):
            statements_list.append({"type": "special", "statement": s[0],
                                    "lineage": {"policy-compartment-ocid": s[4], "policy-relative-hierarchy": s[1],
                                                "policy-name": s[2], "policy-ocid": s[3]}
                                    })
        for i, s in enumerate(dynamic_group_statements):
            statements_list.append({"type": "dynamic-group", "subject": s[0], "verb": s[1],
                                    "resource": s[2], "location": s[3], "conditions": s[4],
                                    "lineage": {"policy-compartment-ocid": s[8], "policy-relative-hierarchy": s[5],
                                                "policy-name": s[6], "policy-ocid": s[7], "policy-text": s[9]}
                                    })
        for i, s in enumerate(service_statements):
            statements_list.append({"type": "service", "subject": s[0], "verb": s[1],
                                    "resource": s[2], "location": s[3], "conditions": s[4],
                                    "lineage": {"policy-compartment-ocid": s[8], "policy-relative-hierarchy": s[5],
                                                "policy-name": s[6], "policy-ocid": s[7], "policy-text": s[9]}
                                    })
        for i, s in enumerate(regular_statements):
            statements_list.append({"type": "regular", "subject": s[0], "verb": s[1],
                                    "resource": s[2], "location": s[3], "conditions": s[4],
                                    "lineage": {"policy-compartment-ocid": s[8], "policy-relative-hierarchy": s[5],
                                                "policy-name": s[6], "policy-ocid": s[7], "policy-text": s[9]}
                                    })
        # Serializing json
        json_object = json.dumps(statements_list, indent=2)

        # Writing to sample.json
        with open(f"policyoutput-{tenancy_ocid}.json", "w") as outfile:
            outfile.write(json_object)
    logger.debug(f"-----Complete--------")