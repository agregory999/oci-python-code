from oci import config
from oci.usage_api import UsageapiClient
from oci.usage_api.models import RequestSummarizedUsagesDetails,Filter,Dimension,Tag

import os
import argparse
import logging

# Main Routine
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-t", "--costtrackingtag", help="Cost Tracking tag value", required=True)
parser.add_argument("-ns", "--costtrackingns", help="Cost Tracking tag namespace", required=True)
parser.add_argument("-k", "--costtrackingkey", help="Cost Tracking tag key", required=True)
parser.add_argument("-sd", "--startdate", help="Start Date YYYY-MM-DD", required=True)
parser.add_argument("-ed", "--enddate", help="Start Date YYYY-MM-DD (give next day to include previous)", required=True)

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
frame_ns = args.costtrackingns
frame_tag = args.costtrackingtag
frame_key = args.costtrackingkey
start_date = args.startdate
end_date = args.enddate

logging.getLogger('oci').setLevel(logging.DEBUG)

print(f"Using profile {profile}.")

# Initialize service client with default config file
config = config.from_file(profile_name=profile)

# Get Tenancy OCID
tenancy_ocid = config["tenancy"]

# Client to use
usage_client = UsageapiClient(config)
   
# Rack Cost (take defined tag and run report)

cost_query = RequestSummarizedUsagesDetails(
        tenant_id=tenancy_ocid,
        query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_COST,
        compartment_depth=6.0,
        time_usage_started=f'{start_date}T00:00Z',
        time_usage_ended=f'{end_date}T00:00Z',
        is_aggregate_by_time=False,
        granularity=RequestSummarizedUsagesDetails.GRANULARITY_MONTHLY,
        #group_by=["skuPartNumber"],
        #group_by=["service","skuName","resourceId","tag"],
        filter=Filter(
            operator="AND",
            filters=[
                Filter(
                    dimensions=[
                        Dimension(key="service", value="DATABASE")
                        #Dimension(key="service", value="DBMGMT"),
                        #Dimension(key="service", value="OPERATIONS_INSIGHTS")
                    ],
                    operator="OR"
                ),
                Filter(
                    tags=[
                        Tag(namespace=frame_ns, key=frame_key, value=frame_tag)
                    ],
                    operator="OR"
                )
            ]  # filters=
        ) # filter=
    )
if verbose:
    # Print Query
    print(f"Cost Query: {cost_query}")
usage_summary = usage_client.request_summarized_usages(
    request_summarized_usages_details=cost_query
).data
if verbose:
    # Print result
    print(f'Cost Report: {usage_summary.items}')
sum = 0
for i in usage_summary.items:
    if i.computed_amount:
        sum = sum + i.computed_amount
print(f'Total Cost (tag {frame_tag}): ${sum:.2f}')
