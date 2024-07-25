from io import BytesIO
import datetime
import json

from oci import config
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci import retry

# OCI Clients and models (import as necessary)
from oci.log_analytics import LogAnalyticsClient
from oci.log_analytics.models import ExportDetails, TimeRange

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging

# PHASE 1 - Parsing of Arguments, Python Logging
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
parser.add_argument("-ns", "--nsname", help="namespace", required=True)
parser.add_argument("-o", "--compartmentocid", help="Compartment OCID, required", required=True)


args = parser.parse_args()
verbose = args.verbose  # Boolean
profile = args.profile  # String
use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
region = args.region # Region to use with Instance Principal, if not default
ns_name = args.nsname # String
comp_ocid = args.compartmentocid # String

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')
logger.debug(f"debug test - Namespace: {ns_name}")

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
        logan_client = LogAnalyticsClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        logan_client = LogAnalyticsClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

except ClientError as ex:
    logger.critical(f"Failed to connect to OCI: {ex}")

# PHASE 3 - Main Script Execution

# All logs for a week, certain types
# 'Entity Type' in ('Oracle Database Listener', 'Automatic Storage Management Instance', 'Oracle Database Instance') | sort Time | fields Time, Entity, 'Log Origin', 'Problem Priority', Label, Message
# Sme thing, problems only
# 'Entity Type' in ('Oracle Database Listener', 'Automatic Storage Management Instance', 'Oracle Database Instance') and 'Problem Priority' != null | sort Time | fields Time, Entity, 'Log Origin', 'Problem Priority', Label, Message
# Not null and in clause
# 'Entity Type' in ('Oracle Database Listener', 'Automatic Storage Management Instance', 'Oracle Database Instance') and Message != null and Message not like in ('*service_update*') | sort Time | fields Time, Entity, 'Log Origin', 'Problem Priority', Label, Message
# Log Analytics Export
exp_details = ExportDetails(
    compartment_id=comp_ocid,
    sub_system='LOG',
    query_string=f"'Entity Type' in ('Oracle Database Listener', 'Automatic Storage Management Instance', 'Oracle Database Instance') and Message != null  | sort Time | fields Time, Entity, 'Log Origin', 'Problem Priority', Label, Message",
    output_format="JSON",
    time_filter=TimeRange(
            time_start=datetime.datetime.strptime(
                "2024-05-20T00:00:00",
                "%Y-%m-%dT%H:%M:%S"),
            time_end=datetime.datetime.strptime(
                "2024-05-23T09:00:00",
                "%Y-%m-%dT%H:%M:%S"),
            time_zone="UTC-04:00"),
            max_total_count=1000000,
            should_include_columns=True
)
try:
    exp = logan_client.export_query_result(
        namespace_name=ns_name,
        export_details=exp_details,
    )
    f = BytesIO(exp.data.content)
    # bb: bytearray = []
    rows = 0
    for l in f:
        rows += 1
    #     # Convert to string
    #     row = l.decode()
    # #     #logger.info(f"row: {row}")

    raw_json = json.loads(f.getvalue())
    full_json = json.dumps(raw_json, indent=2)
    logger.debug(f"JSON: {full_json}")
    logger.info(f"Rows: {rows}")

    with open("log_analytics.json", "w") as outfile:
        outfile.write(full_json)
        
    logger.info(f"Wrote file: {rows}")

except ServiceError as ex:
    logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
    logger.debug(f"Full Exception Detail: {ex}")
