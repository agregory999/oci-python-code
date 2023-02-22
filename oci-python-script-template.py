# OCI Python Script template
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# This script provides ....<basic documenation>.....

# Usage: python oci-python-xxx-yyy.py

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.database import DatabaseClient
from oci.database.models import DatabaseSummary

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging

# PHASE 1 - Parsing of Arguments, Python Logging
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
parser.add_argument("-o", "--compartmentocid", help="Compartment OCID, required", required=True)
parser.add_argument("-t", "--valuewithtype", help="Value with type", type=int)

args = parser.parse_args()
verbose = args.verbose  # Boolean
profile = args.profile  # String
comp_ocid = args.compartmentocid # String
frame_tag = args.someothervalue # String with default value if not provided
some_int = args.valuewithtype # int

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('script-name')
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')
logger.debug(f"debug test - some_int: {some_int}")

# PHASE 2 - Creation of OCI Client(s) 

# Connect to OCI with DEFAULT or defined profile
try:
    config = config.from_file(profile_name=profile)
    logger.debug(f"Profile Detail: {config}")
except ClientError as ex:
    logger.critical(f"Failed to connect to OCI: {ex}")

# Create any necessary Clients
db_client = DatabaseClient(config)

# PHASE 3 - Main Script Execution

# Get PDBs Example
try:
    databases = db_client.list_pluggable_databases(
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
