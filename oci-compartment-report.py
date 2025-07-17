# OCI Python Script template
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides ....<basic documenation>.....

# Usage: python oci-python-xxx-yyy.py

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry
from oci.pagination import list_call_get_all_results

# OCI Clients and models (import as necessary)
from oci.identity import IdentityClient
from oci.identity.models import Compartment

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
import csv

# PHASE 1 - Parsing of Arguments, Python Logging
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
# parser.add_argument("-o", "--compartmentocid", help="Compartment OCID, required", required=True)

args = parser.parse_args()
verbose = args.verbose  # Boolean
profile = args.profile  # String
use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
region = args.region # Region to use with Instance Principal, if not default
# comp_ocid = args.compartmentocid # String

identity_client:IdentityClient

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

# PHASE 2 - Creation of OCI Client(s) 

# Connect to OCI with DEFAULT or defined profile
try:

   # Client creation
    if use_instance_principals:
        logger.info(f"Using Instance Principal Authentication")

        signer = InstancePrincipalsSecurityTokenSigner()
        signer.federation_client
        config_ip = {}
        if region:
            config_ip={"region": region}
            logger.info(f"Changing region to {region}")

        # Example of client
        identity_client = IdentityClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        identity_client = IdentityClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

except ClientError as ex:
    logger.critical(f"Failed to connect to OCI: {ex}")

# PHASE 3 - Main Script Execution

# Read CSV
input_filename = 'int03_comp_details_input.csv'
output_filename = 'int03_comp_details_output.csv'
field_comp_ocid = 'OCIDs'
field_creator_tag = 'Compartment Creator Tag'
field_created_on = 'Created On'
# value_to_find = 'Pending'
# new_value = 'Completed'
# id_column = 'OrderID'
# target_id = 'ORD123' # Example: update status for this OrderID

updated_rows = []
all_compartments = {}

try:
    compartments = list_call_get_all_results(identity_client.list_compartments, compartment_id=config['tenancy'], compartment_id_in_subtree=True).data

    # Parse Data
    for comp in compartments:

        # logger.info(f"All Detail: {comp}")
        if comp.defined_tags and comp.defined_tags.get("Oracle-Tags"):
        #     logger.debug(f"Oracle Tags {comp.defined_tags["Oracle-Tags"]}")
            oracle_tags = comp.defined_tags.get("Oracle-Tags")
            created_by =oracle_tags.get("CreatedBy") if oracle_tags.get("CreatedBy") else ""
            created_on =oracle_tags.get("CreatedOn") if oracle_tags.get("CreatedOn") else comp.time_created
            all_compartments[comp.id] = {"CreatedBy":created_by,"CreatedOn":created_on}
        else:
            logger.info(f"No tags for compartment {comp.name} / {comp.id}")
            all_compartments[comp.id] = {"CreatedBy":"No Detail","CreatedOn":comp.time_created}


except ServiceError as ex:
    logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
    logger.debug(f"Full Exception Detail: {ex}")

logger.debug(f"All Compartment Data: {all_compartments}")

with open(input_filename, mode='r', newline='') as infile:
    reader = csv.DictReader(infile)
    fieldnames = reader.fieldnames # Get header row
    logger.info(f"Header Row: {fieldnames}")
    for row in reader:
        comp_ocid = row[field_comp_ocid] 
        logger.debug(f"Operating on compartment OCID: {comp_ocid}")

        # OCI Lookup to get compartment details
        if all_compartments.get(comp_ocid):
            logger.info(f"found detail for {comp_ocid}")
            row[field_creator_tag] = all_compartments.get(comp_ocid)["CreatedBy"]
            row[field_created_on] = all_compartments.get(comp_ocid)["CreatedOn"]
        else:
            logger.info(f"Did not find detail for {comp_ocid}")
        # if row[id_column] == target_id and row[field_to_update] == value_to_find:
        #     row[field_to_update] = new_value
        updated_rows.append(row)

# Write CSV
with open(output_filename, mode='w', newline='') as outfile:
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader() # Write the header row
    writer.writerows(updated_rows)

# Get All Compartment



# input_filename = 'data.csv'
# output_filename = 'updated_data.csv'
# field_to_update = 'Status'
# value_to_find = 'Pending'
# new_value = 'Completed'
# id_column = 'OrderID'
# target_id = 'ORD123' # Example: update status for this OrderID

# updated_rows = []

# with open(input_filename, mode='r', newline='') as infile:
#     reader = csv.DictReader(infile)
#     fieldnames = reader.fieldnames # Get header row
#     for row in reader:
#         if row[id_column] == target_id and row[field_to_update] == value_to_find:
#             row[field_to_update] = new_value
#         updated_rows.append(row)

# # Do something

# with open(output_filename, mode='w', newline='') as outfile:
#     writer = csv.DictWriter(outfile, fieldnames=fieldnames)
#     writer.writeheader() # Write the header row
#     writer.writerows(updated_rows)

# print(f"CSV file '{input_filename}' updated and saved to '{output_filename}'.")