from oci import config
from oci.usage_api import UsageapiClient
from oci.usage_api.models import RequestSummarizedUsagesDetails,Filter,Dimension,Tag
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, ResourceSummary

import os
import argparse
import logging
import json
import datetime

# Constant - Number of resources search can handle per query
BATCH_SIZE = 50

# This variation of the script is designed to take a specific tag NS/Key/Value and do the following:
# 1) Get all cost data by tag filter and services needed (compute, boot, block, backups, file store, bucket)
# 2) Augment the data using Search Result - name of resource
# 3) Apply the returned daily costs to the resource output

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-o", "--ocid", help="Resource OCID", required=True)
parser.add_argument("-sd", "--startdate", help="Start Date YYYY-MM-DD")
parser.add_argument("-ed", "--enddate", help="Start Date YYYY-MM-DD (give next day to include previous day)")
parser.add_argument("-r", "--range", help="Predefined Range: Only MTD Supported")
parser.add_argument("-g", "--granularity", help="DAILY or MONTHLY", default="DAILY")

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
granularity = args.granularity
resource_ocid = args.ocid
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

# First set the log level
if verbose:
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.getLogger().setLevel(logging.INFO)

logging.info(f"Using profile {profile}.")
logging.info(f"Using Date range {start_date} - {end_date}")
logging.info(f"Using Resource {resource_ocid}")

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Get Tenancy OCID
tenancy_ocid = config["tenancy"]

# Clients to use
usage_client = UsageapiClient(config,timeout=600)

# Do resource search first, by tags
results = []

# Dimension filter based on resource OCID
dim_filter = Filter(
                dimensions=[Dimension(
                    key="resourceId",
                    value=resource_ocid
                )],
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
    group_by=["resourceId","service","skuName"],
    filter=dim_filter
)

logging.info(f'Cost query: {cost_query}')

# Usage query
usage_query = RequestSummarizedUsagesDetails(
    tenant_id=tenancy_ocid,
    query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_USAGE,
    compartment_depth=6.0,
    time_usage_started=f'{start_date}',
    time_usage_ended=f'{end_date}',
    is_aggregate_by_time=True,
    granularity=granularity,
    group_by=["resourceId","service","skuName","unit"],
    #group_by=["service"],
    filter=dim_filter
)

logging.info(f'Usage query: {usage_query}')

############ Part 1 - Cost and Usage Query based on tags ####################
# Run the cost query
cost_summary = usage_client.request_summarized_usages(
    request_summarized_usages_details=cost_query
).data
logging.info(f'Cost Report: {cost_summary}')

# Run the usage query
usage_summary = usage_client.request_summarized_usages(
    request_summarized_usages_details=usage_query
).data
logging.debug(f'Usage Report: {usage_summary}')

# Empty list of all OCIDs we need to get resource name details for.
ocid_list = []

logging.info(f"Cost: {cost_summary}")
logging.info(f"Usage: {usage_summary}")



# # Write to file
# datestring = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
# filename = f'cost2-data-{"-".join(tag_values)}-{granularity}-{datestring}.json'
# with open(filename,"w") as outfile:
#     outfile.write(json.dumps(results, indent=2))

# logging.info(f"Script complete - write JSON to {filename}.")