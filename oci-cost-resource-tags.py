from oci import config, retry
from oci.usage_api import UsageapiClient
from oci.usage_api.models import RequestSummarizedUsagesDetails,Filter,Dimension,Tag
from oci.exceptions import ClientError,ServiceError
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
import os
import datetime
import argparse
import logging

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-t", "--costtrackingtagvalue", help="Cost Tracking tag value", required=False)
parser.add_argument("-ns", "--costtrackingns", help="Cost Tracking tag namespace", required=False)
parser.add_argument("-k", "--costtrackingkey", help="Cost Tracking tag key", required=False)
parser.add_argument("-sd", "--startdate", help="Start Date YYYY-MM-DD", required=False)
parser.add_argument("-ed", "--enddate", help="Start Date YYYY-MM-DD (give next day to include previous day)", required=False)
parser.add_argument("-o", "--ocid", help="Resource OCID", required=True)
parser.add_argument("-o2", "--ocid2", help="Resource OCID2", required=True)
parser.add_argument("-r", "--range", help="Predefined Range: Only MTD Supported")
parser.add_argument("-g", "--granularity", help="DAILY or MONTHLY", default="DAILY")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
tagns = args.costtrackingns
tagkey = args.costtrackingkey
tagvalue = args.costtrackingtagvalue
start_date = args.startdate
end_date = args.enddate
resource_ocid = args.ocid
resource_ocid2 = args.ocid2
granularity = args.granularity
use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
region = args.region # Region to use with Instance Principal, if not default

if args.range:
    range = args.range
    # Process as MTD for example (hard code)
    if range == 'MTD':
        month = datetime.datetime.now().month
        year = datetime.datetime.now().year
        start_date = f"{year}-{month:0>2}-01T00:00:00+00:00"
        end_date = f"{year}-{month+1:0>2}-01T00:00:00+00:00"
    else:
        # undefined - use this month
        start_date = "2024-02-01T00:00:00+00:00"
        end_date = "2024-03-01T00:00:00+00:00"
else:
    if not args.startdate or not args.enddate:
        logging.critical("Must include start and end date in form YYYY-MM-DDTHH:MI:SSZ")
        exit(1)
    start_date = args.startdate
    end_date = args.enddate

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
if verbose:
    logger.setLevel(logging.DEBUG)

logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')
logger.debug(f"debug test - Resource OCID: {resource_ocid}")

logger.info(f"Using profile {profile}.")
logger.info(f"Using Date range {start_date} - {end_date}")
logger.info(f"Using Resource {resource_ocid}")
if tagns:
    logger.info(f"Using Tag NS: {tagns}")


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
        usage_client = UsageapiClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

    else:
        # Use a profile (must be defined)
        logger.info(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        usage_client = UsageapiClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)

        # Get Tenancy OCID
        tenancy_ocid = config["tenancy"]


except ClientError as ex:
    logger.critical(f"Failed to connect to OCI: {ex}")

# Generate Query

# Dimension filter based on resource OCID
dim_filter = Filter(
                dimensions=[
                    Dimension(key="resourceId", value=resource_ocid),
                    Dimension(key="resourceId", value=resource_ocid2)
                ],
                operator=Filter.OPERATOR_OR
            )

# Now the query(s) - Cost
cost_query = RequestSummarizedUsagesDetails(
    tenant_id=tenancy_ocid,
    query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_COST,
    compartment_depth=6.0,
    time_usage_started=f'{start_date}',
    time_usage_ended=f'{end_date}',
    is_aggregate_by_time=True,
    granularity=granularity,
    #group_by=["service"],
    group_by=["service","skuName"],
    #group_by_tag=[{"namespace":tagns, "key":tagkey}],
    filter=dim_filter
)
logging.info(f'Cost query: {cost_query}')

# Run the cost query
cost_summary = usage_client.request_summarized_usages(
    request_summarized_usages_details=cost_query
).data
logging.info(f'Cost Report: {cost_summary}')
