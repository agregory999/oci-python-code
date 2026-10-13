# OCI Python Script template
# Copyright (c) 2024, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

# Basic OCI Access script with options

# Usage: python oci-basic-script.py
# Valid switches
# -v/--verbose for verbose/debug
# -ip/--instanceprincipal for Instance Principal (only on OCI VM)
# -r/--region for alternate region
# -pr/--profile for using a non-DEFAULT named OCI Profile

# Only import required code from OCI
from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry

# OCI Clients and models (import as necessary)
from oci.identity import IdentityClient

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
import time # Script Timing

# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-r", "--region", help="Use alternate region")

    args = parser.parse_args()
    verbose = args.verbose  # Boolean
    profile = args.profile  # String
    use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
    region = args.region # Region to use with Instance Principal, if not default

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
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
            tenancy_ocid = signer.tenancy_id
            # Create the OCI Client to use
            identity_client = IdentityClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)
            if region:
                config["region"] = region
                logger.info(f"Changing region to {region}")
            tenancy_ocid = config["tenancy"]
            # Create the OCI Client to use
            identity_client = IdentityClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # PHASE 3 - Main Script Execution

    # Start timer
    start_time = time.time()

    try:
        # Do something
        comps = identity_client.list_compartments(compartment_id=tenancy_ocid,
                                                compartment_id_in_subtree=False,
                                                sort_by="NAME",
                                                limit=10000).data
        
        for i,comp in enumerate(comps, start=1):
            logger.info(f"Compartment {i}: {comp.name}")
            logger.debug(f"Compartment OCID {i}: {comp.id}")
        logger.info(f"Listed {i} compartments")
    except ServiceError as exc:
        logger.error(f"{exc.message}")
        logger.debug(f"{exc}")
    except ValueError as exc:
        logger.error(f"{exc}")
    # End timer
    end_time = time.time()

    # Print time with 2 digits
    logger.info(f"Finished Script in {end_time-start_time:.2f}s")
