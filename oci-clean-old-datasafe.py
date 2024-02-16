from oci.exceptions import ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.data_safe import DataSafeClient
from oci.data_safe.models import UserAssessment, SecurityAssessment
from oci import config, pagination
from oci.exceptions import ServiceError
import argparse
import logging
import json
import datetime
from concurrent.futures import ThreadPoolExecutor

# Global Counts
sa_delete_count = 0
ua_delete_count = 0

# Threaded function
def ua_function(assessment: UserAssessment) -> bool:

    logging.debug(f"UA: {assessment}")
    logging.info(f"UA Found {assessment.display_name} / {assessment.time_created} / {assessment.lifecycle_state} / {assessment.type} / {assessment.id}")

    # Check for age (older than XX)
    #obj_time = i.time_created.replace(tzinfo=datetime.timezone.utc)
    if (assessment.time_created + datetime.timedelta(days=days) < datetime.datetime.now(tz=datetime.timezone.utc) and assessment.lifecycle_state == "SUCCEEDED"):
        logging.info(f"Deleting due to creation older than {days} days: {assessment.time_created}")

        try:
            datasafe_client.delete_security_assessment(assessment.id)
            logging.info(f"SA Deleted {assessment.display_name} / {assessment.time_created}")
            global ua_delete_count
            ua_delete_count += 1
        except ServiceError as e:
            logging.warning(f"Failed to delete {assessment.display_name}: {e.message}")
            logging.debug(f"Stack: {e}")
            return False
    logging.debug("--------------------------")
    return True

# Threaded function
def sa_function(assessment: SecurityAssessment) -> bool:

    logging.debug(f"SA: {assessment}")
    logging.info(f"SA Found {assessment.display_name} / {assessment.time_created} / {assessment.lifecycle_state} / {assessment.type} / {assessment.id}")
    if (assessment.time_created + datetime.timedelta(days=days) < datetime.datetime.now(tz=datetime.timezone.utc)):
        logging.info(f"Deleting due to creation older than {days} days: {assessment.time_created}")
        try:
            datasafe_client.delete_user_assessment(assessment.id)
            logging.info(f"SA Deleted {assessment.display_name} / {assessment.time_created}")
            global sa_delete_count
            sa_delete_count += 1
        except ServiceError as e:
            logging.warning(f"Failed to delete {assessment.display_name}: {e.message}")
            logging.debug(f"Stack: {e}")
            return False
    logging.debug("--------------------------")
    return True


#########################################################################################################

# Only if called in Main
if __name__ == "__main__":

    # Main Routine
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-dryrun", help="Don't actually do it, just show what you'd do", action="store_true")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-o", "--ocid", help="OCID of compartment (if not passed, will use tenancy OCID from profile)", default="TENANCY")
    parser.add_argument("-d", "--days", help="Age in days to delete (older than X days). Default 90", type=int, default=90)
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    dryrun = args.dryrun
    use_instance_principals = args.instanceprincipal
    compartment_ocid = args.ocid
    days = args.days
    threads = args.threads

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    # Only allow subtree if we are going to use tenancy
    use_subtree = True if compartment_ocid == "TENANCY" else False

    # Set up Config
    if use_instance_principals:
        logger.info(f"Using Instance Principal Authentication")
        signer = InstancePrincipalsSecurityTokenSigner()
        datasafe_client = DataSafeClient(config={}, signer=signer)
        if compartment_ocid == "TENANCY":
            compartment_ocid = signer.tenancy_id
            logging.info(f"Signer: {signer}")

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)
        if compartment_ocid == "TENANCY":
            print(f'Using tenancy OCID from profile: {config["tenancy"]}')
            compartment_ocid = config["tenancy"]
            logging.debug(f"Config: {config}")
        # Create the OCI Client to use
        datasafe_client = DataSafeClient(config)

    logger.info(f"------Starting Security Assessments-----")
    # Security Assessments
    data_safe_resp = datasafe_client.list_security_assessments(
        compartment_id=compartment_ocid,
        compartment_id_in_subtree=use_subtree,
        sort_order="ASC",
        sort_by="timeCreated",
        lifecycle_state="SUCCEEDED",
        type="SAVED",
        #time_created_less_than="2023-01-01T00:00:00Z"
        limit=500
    ).data

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(sa_function, data_safe_resp)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

    # Process results
    for result in results:
        logger.debug(f"Result: {result}")

    logger.info(f"------Starting User Assessments-----")
    # BUG UA Listing won't allow lifecycle to be selected if type = SAVED
    # User Assessments
    data_safe_resp = datasafe_client.list_user_assessments(
        compartment_id=compartment_ocid,
        compartment_id_in_subtree=use_subtree,
        sort_order="ASC",
        sort_by="timeCreated",
        # lifecycle_state="SUCCEEDED",
        type="SAVED",
        #time_created_less_than="2023-01-01T00:00:00Z"
        limit=500
    ).data

    # Thread Pool with execution based on incoming list of OCIDs
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(ua_function, data_safe_resp)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

    # Process results
    for result in results:
        logger.debug(f"Result: {result}")

    logging.info(f"Summary: {sa_delete_count} Security Assessments removed, {ua_delete_count} User Assessments removed")
