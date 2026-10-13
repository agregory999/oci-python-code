# OCI Python Script - Find unused VCN
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
from oci.data_integration import DataIntegrationClient
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, FreeTextSearchDetails

# Additional imports
import argparse   # Argument Parsing
import logging    # Python Logging
import datetime
from datetime import timezone
from concurrent.futures import ThreadPoolExecutor, Future

# Callback
# def thread_completion_callback(future: Future):
#     try:
#         res = future.result()
#         if res:
#             logger.info(f"Result: {res}")
#         else:
#             pass
#             # print(".",end="",flush=True)
#     except Exception as e:
#         logger.error(f"Failed: {e}")

# Threaded function
# def work_function(ocid: str) -> str:
#     # VCN Example
#     try:

#         # Get VCN
#         vcn = vcn_client.get_vcn(
#             vcn_id=ocid
#         ).data

#         logger.debug(f"VCN Name: {vcn.display_name}")
#         logger.debug(f"Full Details: {vcn}")

#         # List subnets
#         subnet_list = vcn_client.list_subnets(
#             compartment_id=vcn.compartment_id,
#             vcn_id=vcn.id
#         ).data
#         logger.debug(f"Subnets in {vcn.display_name}: {subnet_list}")

#         #can_delete=True
#         for i,sn in enumerate(subnet_list):
#             logger.debug(f"Subnet: {sn.display_name}")
#             # Show allocation
#             #alloc = vcn_client.get_subnet_cidr_utilization(subnet_id=sn.id).data
#             alloc = vcn_client.get_subnet_ip_inventory(subnet_id=sn.id).data
#             logger.debug(f"Alloc: {alloc.count} - {alloc.ip_inventory_subnet_resource_summary}")
#             if alloc.count > 0:
#                 # if any subnet is in use, cannot delete
#                 return

#         #logger.info(f"{vcn.display_name}:{vcn.time_created}{vcn.id}")                 
#         if vcn.time_created < datetime.datetime(year=2023, month=12, day=31,tzinfo=timezone.utc):
#             logger.debug(f"{vcn.display_name}:{vcn.id}:{vcn.time_created} -- Empty subnets and older than 2023")
#         else:
#             logger.debug(f"{vcn.display_name}:{vcn.id} -- Empty subnets and newer than 2023")
#         return f"VCN {vcn.display_name}/{vcn.id} is able to be deleted"
#     except ServiceError as ex:
#         logger.error(f"Failed to call OCI.  Target Service/Operation: {ex.target_service}/{ex.operation_name} Code: {ex.code}")
#         logger.debug(f"Full Exception Detail: {ex}")
#         raise ex


# Only if called in Main
if __name__ == "__main__":

    # PHASE 1 - Parsing of Arguments, Python Logging
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
    parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose  # Boolean
    profile = args.profile  # String
    use_instance_principals = args.instanceprincipal # Attempt to use instance principals (OCI VM)
    region = args.region # Region to use with Instance Principal, if not default
    threads = args.threads

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
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

            # Example of client
            dis_client = DataIntegrationClient(config=config_ip, signer=signer, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config=config_ip, signer=signer)

        # Connect to OCI with DEFAULT or defined profile
        else:
            # Use a profile (must be defined)
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            # Create the OCI Client to use
            dis_client = DataIntegrationClient(config, retry_strategy=retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)

    except ClientError as ex:
        logger.critical(f"Failed to connect to OCI: {ex}")

    # PHASE 3 - Main Script Execution (threaded)

    # Define DIS Workspaces
    iad_list = ["ocid1.disworkspace.oc1.iad.anuwcljr2ow634ya7fvccyiiam6ex7nojtsxt5bvpcv5af53n63ohowtbn7a",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634yajofjs6rnoerbsugfebqtocfvisx5ocdwyn52erm2tgga",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634yaiq77hkhneqvmo53hd6zvbp2ge6tbswkprreuq7m55x7a",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634ya63ghz63y5dt25wm7bbqaeaeoc5akh4fgxxf5tvytzjqq",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yaoq6aqmwts3b5dssogj5svr37weills4vrkzoazb5zbtq",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yac6nxa3p2ylpo5debf7jjxbz2tngoz45f4mr3ogvquhsa",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634yas3fds4zxbqg3x7g4cedyzjl6wlqbyn4fmsidsrfjstga",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yazhukk6n4zmow5rv3imnriy34ofuqmioopq3bjuddsusq",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yacaae3vxte27ca67dqhceejjgei5et4m64yp7oe7xkhjq",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yae7xja5oo5ajck2oatp2keikwmzqh7qqgojuszf4bb7va",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634ya7gernlzphp7yeavu36f65vu26jqh4cxmdgo2qjti3tgq",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yai25cfonihc5ob63jolsfcgp2mbettr2sbjhu325yiuba",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634yatthsq2bgypimm6gp3bxqqi3zxnokavbdkuje5tujv7ga",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yagd67e6eldxafv7p54tmhd2yx22cxy3tupvoamyc244sa",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yaabgck5n4rvl5bjk36tqpylkw2ngyva5t5qkhzzwdav7q",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634yansng6qfzbnajpgddtksepeb2xl246oa5ynfmtcq5do5a",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yasopljpnz76fvhzsali5msumw3k2cjkv7m2b5grdas44a",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yafbvs3yes7acf4z4llcqucosldaktwlcxdbze53nne4fq",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yaxnakqecd6lzgq36rdbx2mpllfxukvcu7kyvvzzifadoa",
                "ocid1.disworkspace.oc1.iad.anuwcljr2ow634yawozmkphle7xo4vsg6dfrkqgopf73xvvyqbhqnthnxxqa",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yatcxlqsaxlkofe4tm4s65rb3nmcamwf77ozuzhjcdi63a",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yaudv2q6ppbclaf6xxwbq7nrmzarrdplm3tbe6clloxw4q",
                "ocid1.disworkspace.oc1.iad.anuwcljs2ow634yatpkdowjpsi4fbfb45kfbacdq2r24756wqfl3esej7pzq",
                "ocid1.disworkspace.oc1.iad.anuwcljt2ow634yal5a2spb6lfwa6co5qaltweeigi7xq6xr6f6dpathkwtq",
                "ocid1.disworkspace.oc1.iad.amaaaaaaytsgwayaswz2amkcw4ni2n22hthawb5llri36b6lcs7ib2enxwma",
                "ocid1.disworkspace.oc1.iad.amaaaaaaytsgwayalqf5eusmqjgntdfoiwkqntdspv5xgy3frkg5yvn3j5lq",
                "ocid1.disworkspace.oc1.iad.amaaaaaaytsgwayae2i3rde4bjfyjo4v3l5zxa4drrh357ezlsm3gg7xce4a",
                "ocid1.disworkspace.oc1.iad.amaaaaaaytsgwayazpsk5p73dqa7rkrli3nywbzx5adc6leojir4j4xg4qga",
                "ocid1.disworkspace.oc1.iad.amaaaaaaytsgwayaik3kj23wqd4mwkvoxdcxylqu62kqa3rchkzkvw6k7apq"
    ]

    phx_list = ["ocid1.disworkspace.oc1.phx.anyhqljt2ow634ya2kwhcnuam5k5avyi46yafjrcpupfqpqswa7lsrj6ti4q",
                "ocid1.disworkspace.oc1.phx.anyhqljr2ow634yasyqabluw2ox7kc6s4lvcv2htj3b3uaierkx4lt5jswja",
                "ocid1.disworkspace.oc1.phx.anyhqljs2ow634ya5l4rotctxw2rzthka2jzi42u4uwpnkbspt5jw3ytklqa",
                "ocid1.disworkspace.oc1.phx.anyhqljs2ow634yazusloznr4zoyailkbaklmm455garnz2eohujz43zspza",
                "ocid1.disworkspace.oc1.phx.anyhqljt2ow634yat52kss4vkrug7meyaxhd4jo4jvtj5f2mebpspd72rgfq",
                "ocid1.disworkspace.oc1.phx.anyhqljr2ow634yax4tdlz6bg53inxrdyuvts3paulzebekiav7fbsmuzi6a",
                "ocid1.disworkspace.oc1.phx.anyhqljt2ow634yamsqilqqcem5jdgbhq7yivkmm7afesafvbzb56zdkrcqa",
                "ocid1.disworkspace.oc1.phx.anyhqljt2ow634yamn3fiqmhu5hlshrucz7ot4md6do5eqoyr3sszo3jhhaq",
                "ocid1.disworkspace.oc1.phx.anyhqljr2ow634yaxflf56rxu52qkdnj23uvk2uetidx3e5kzlvnio4buqha",
                "ocid1.disworkspace.oc1.phx.anyhqljt2ow634yamtlq4kxug27yoyd4m75kc4tfxiilove5tdj7cgwyjmja",
                "ocid1.disworkspace.oc1.phx.anyhqljs2ow634yaolw2pfyiairw4jgwdjctukwncejegmn3ln42keenk53q",
                "ocid1.disworkspace.oc1.phx.anyhqljt2ow634yanhs4tav4jiyvtmctdfxc6ububrw3jxkfxoj4svn6zvjq",
                "ocid1.disworkspace.oc1.phx.amaaaaaaytsgwayag47yro2d6fmjp6sdlvjqqqcbrodtpkecskzp2juuxmkq"
    ]

    # # Get Resource List via Search
    # all_dis = search_client.search_resources(
    #     search_details=StructuredSearchDetails(
    #         type = "Structured",
    #         query='query DISWorkspace resources'
    #     ),
    #     # search_details=FreeTextSearchDetails(
    #     #     type = "Structured",
    #     #     text='query disworkspace resources sorted by timeCreated asc'
    #     # ),
    #     limit=1000
    # ).data

    # Build a list of OCIDs to operate on
    vcn_ocids = []
    for i,it in enumerate(phx_list, start=1):
        logger.info(f"DIS Workspace: {it}")
        try:
            dis_client.stop_workspace(
                workspace_id=it
            )
            logger.info(f"DIS Workspace Stopped: {it}")
        except ServiceError as se:
            logger.warning(f"DIS Workspace Not Stopped: {se.code}")


    # Thread Pool with execution based on incoming list of OCIDs
    # with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:

    #     results = [executor.submit(work_function, ocid) for ocid in vcn_ocids]
    #     logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

    #     # Add callbacks to report
    #     for future in results:
    #         future.add_done_callback(thread_completion_callback)

    # for res in results:
    #     if res:
    #         logger.info(f"Result: {res}")
    #     else:
    #         logger.debug(f"Result: {res}")