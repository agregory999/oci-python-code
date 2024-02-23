

# Generic Imports
import argparse
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
import time
import datetime
import json

# OCI Imports
from oci import config
from oci import database
from oci import identity
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database.models import UpdateAutonomousDatabaseDetails
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, FreeTextSearchDetails
from oci.exceptions import ServiceError

import oci

# Constants
DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"



# Only if called in Main
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal
    region = args.region

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger('oci-scale-atp')
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    # Client creation
    if use_instance_principals:
        logger.info(f"Using Instance Principal Authentication")

        signer = InstancePrincipalsSecurityTokenSigner()
        config_ip = {}
        if region:
            config_ip={"region": region}
            logger.info(f"Changing region to {region}")
        search_client = ResourceSearchClient(config=config_ip, signer=signer)

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        search_client = ResourceSearchClient(config)


    # Get ATP (Search)
    res = search_client.search_resources(

        # search_details=FreeTextSearchDetails(
        #     type="FreeText",
        #     text="query DISWorkspace resource"
        # ),


        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query Instance, DbSystem, VmCluster, AutonomousDatabase, InstancePool, GoldenGateDeployment, OdaInstance, AnalyticsInstance, IntegrationInstance, disworkspace resources \
                where     definedTags.namespace != "Schedule" &&\
                    ( lifecycleState = "Active" ||  lifecycleState = "Running" || lifecycleState = "Stopped" || lifecycleState = "Available" )  && compartmentId  != "ocid1.compartment.oc1..aaaaaaaaxz5oqc63fn4pgtdit3yzpilf4ryia7tn4aq3i4mtfzfgxhxgqqsq" && compartmentId  = "ocid1.compartment.oc1..aaaaaaaawu6tgzbkxckc4sm4bjnqkmutar3sxapwlbpvntn3lweevuzdzjna"'
            # query = "query DISWorkspace resources"
        ),
        
        limit=1000
    ).data

    for i in res.items:
        logger.info(i)