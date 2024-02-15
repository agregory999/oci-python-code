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

# OCI Clients and models (import as necessary)
from oci.database import DatabaseClient

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging

# PHASE 1 - Parsing of Arguments, Python Logging
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
parser.add_argument("-o", "--compartmentocid", help="Compartment OCID, required", required=True)

args = parser.parse_args()
verbose = args.verbose  # Boolean
profile = args.profile  # String
use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
region = args.region # Region to use with Instance Principal, if not default
comp_ocid = args.compartmentocid # String

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')
logger.debug(f"debug test - compartment OCID: {comp_ocid}")

# PHASE 2 - Creation of OCI Client(s) 

# Connect to OCI with DEFAULT or defined profile
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
        database_client = DatabaseClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        database_client = DatabaseClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

except ClientError as ex:
    logger.critical(f"Failed to connect to OCI: {ex}")

# Create any necessary Clients
db_client = DatabaseClient(config)

# PHASE 3 - Main Script Execution

# Get PDBs Example
try:
    databases = database_client.list_pluggable_databases(
        compartment_id=comp_ocid, 
        limit=1000
    ).data # List of DatabaseSummary

    # Parse Data
    for pdb in databases:
        logger.info(f"PDB: {pdb.pdb_name} OCI: {pdb.id}, Status: {pdb.lifecycle_state}")
        logger.debug(f"Full Details: {pdb}")
except ServiceError as ex:
    logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
    logger.debug(f"Full Exception Detail: {ex}")
