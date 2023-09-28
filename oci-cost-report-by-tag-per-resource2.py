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
parser.add_argument("-tv", "--tagvalues", nargs="+", help="Tag values as list, like --tv abc def ghi")
parser.add_argument("-tn", "--tagns", help="Tag namespace", required=True)
parser.add_argument("-tk", "--tagkey", help="Tag key", required=True)
parser.add_argument("-sd", "--startdate", help="Start Date YYYY-MM-DD")
parser.add_argument("-ed", "--enddate", help="Start Date YYYY-MM-DD (give next day to include previous day)")
parser.add_argument("-r", "--range", help="Predefined Range: Only MTD Supported")
parser.add_argument("-g", "--granularity", help="DAILY or MONTHLY", default="DAILY")

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
granularity = args.granularity
tag_ns = args.tagns
tag_key = args.tagkey
tag_values = args.tagvalues
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
        start_date = "2023-09-01T00:00:00+00:00"
        end_date = "2023-10-01T00:00:00+00:00"
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
logging.info(f"Using Tag (NS/KEY/VALUE) {tag_ns} / {tag_key} / {tag_values}")

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Get Tenancy OCID
tenancy_ocid = config["tenancy"]

# Clients to use
usage_client = UsageapiClient(config)
search_client = ResourceSearchClient(config)

# Do resource search first, by tags
results = []

# Build cost query filter
tags_list = []
for tag_value in tag_values:
    tags_list.append(Tag(namespace=tag_ns, key=tag_key, value=tag_value))

# Dynamically built tag filter based on program parameter input for multiple tags
tag_filter = Filter(
                tags=tags_list,
                operator=Filter.OPERATOR_OR
            )

# Now the query(s) - Cost
cost_query = RequestSummarizedUsagesDetails(
    tenant_id=tenancy_ocid,
    query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_COST,
    compartment_depth=6.0,
    time_usage_started=f'{start_date}',
    time_usage_ended=f'{end_date}',
    is_aggregate_by_time=False,
    granularity=granularity,
    group_by=["resourceId","service","skuName"],
    filter=tag_filter
)
# Usage query
usage_query = RequestSummarizedUsagesDetails(
    tenant_id=tenancy_ocid,
    query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_USAGE,
    compartment_depth=6.0,
    time_usage_started=f'{start_date}',
    time_usage_ended=f'{end_date}',
    is_aggregate_by_time=False,
    granularity=granularity,
    group_by=["resourceId","service","skuName","unit"],
    filter=tag_filter
)

############ Part 1 - Cost and Usage Query based on tags ####################
# Run the cost query
cost_summary = usage_client.request_summarized_usages(
    request_summarized_usages_details=cost_query
).data
logging.debug(f'Cost Report: {cost_summary}')

# Run the usage query
usage_summary = usage_client.request_summarized_usages(
    request_summarized_usages_details=usage_query
).data
logging.debug(f'Usage Report: {usage_summary}')

# Empty list of all OCIDs we need to get resource name details for.
ocid_list = []

# Iterate results and augment, add to results
for i,cost_detail in enumerate(cost_summary.items, start=1):

    if cost_detail.resource_name:
        logging.info(f"Resource Cost: {cost_detail.resource_name}")
    # Run Search to get details for resource
    search_query_details = StructuredSearchDetails(
        type = "Structured",
        query=f'query all resources where identifier="{cost_detail.resource_id}"'
    )

    # Make results with just cost (fill in rest later)
    # Only do it if cost is there
    if cost_detail.computed_amount:
        # Now Loop through results and if we match, then only append cost
        found = False
        for resource in results:
            if resource["identifier"] == cost_detail.resource_id:
                # Append the cost part only
                resource["cost"].append({"start":str(cost_detail.time_usage_started),"end":str(cost_detail.time_usage_ended), "service_sku_name": f"{cost_detail.service}/{cost_detail.sku_name}", "cost":f"{cost_detail.computed_amount:.2f}"})
                found = True
        if not found:
            newjson = {"resource_name":"Deleted Resource","app_name":"Deleted Resource",\
            "identifier":cost_detail.resource_id,"cost":[{"start":str(cost_detail.time_usage_started), \
            "end":str(cost_detail.time_usage_ended), "service_sku_name": f"{cost_detail.service}/{cost_detail.sku_name}", "cost":f"{cost_detail.computed_amount:.2f}"}],\
            "usage":[]}
            results.append(newjson)
        
        # Building OCID List
        ocid_list.append(f'identifier=="{cost_detail.resource_id}"')

    else:
        logging.warning(f"Skipping {cost_detail.resource_id} as cost is None.")

# Iterate Usage results add to results
for usage_detail in usage_summary.items:

    logging.debug(f"Resource Usage: {usage_detail}")

    # Only add usage if it is there
    if usage_detail.computed_quantity:
        # Loop through and find our resource
        for resource in results:
            if resource["identifier"] == usage_detail.resource_id:
                # We can add it to our result
                resource["usage"].append({"start":str(usage_detail.time_usage_started), \
"end":str(usage_detail.time_usage_ended), "service_sku_name": f"{usage_detail.service}/{usage_detail.sku_name}",\
"usage":f"{usage_detail.computed_quantity:.2f}", "units": usage_detail.unit})

    else:
        logging.warning(f"Skipping {usage_detail.resource_id} as usage is None.")

# Run query in batches, augment results, and reset list
internal_list = []
for i,ocid in enumerate(ocid_list,start=1):
    internal_list.append(ocid)
    if len(internal_list) == BATCH_SIZE or i == len(ocid_list):

        # This part is an iteration to build OCID list for the resource query
        query_string = f'query all resources where ({" || ".join(internal_list)})'

        logging.debug(f"Resource query to run: {query_string}")

        # Run query
        search_results = search_client.search_resources(
            search_details=StructuredSearchDetails(
                type = "Structured",
                query=query_string
            ),
            limit=1000
        ).data
        logging.debug(f"Query results (result size / total queried): {len(search_results.items)} / {len(internal_list)}")

        # Process results
        for search_result in search_results.items:
            # Loop through results 
            for resource in results:
                if resource["identifier"] == search_result.identifier:
                    # Add result details
                    resource["resource_name"] = search_result.display_name
                    resource["app_name"] = search_result.defined_tags[tag_ns][tag_key]
        # Reset Internal OCID List
        internal_list = []
# ### End of main loop

logging.debug(f"Cost Summary: {results}")

# Write to file
datestring = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
filename = f'cost2-data-{"-".join(tag_values)}-{granularity}-{datestring}.json'
with open(filename,"w") as outfile:
    outfile.write(json.dumps(results, indent=2))

logging.info(f"Script complete - write JSON to {filename}.")