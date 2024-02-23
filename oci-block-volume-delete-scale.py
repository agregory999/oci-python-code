# Block Volume detection and deletion
# Runs in region with instance Principal
# Runs additional region with profile
# Added Multi-threading

# Written by Andrew Gregory
# 2/14/2024 v1

# Generic Imports
import argparse
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import datetime
import json

# OCI Imports
from oci import config
from oci.core import BlockstorageClient
from oci.core.models import UpdateVolumeDetails, DetachedVolumeAutotunePolicy, PerformanceBasedAutotunePolicy, BootVolume, Volume
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, ResourceSummary
from oci.exceptions import ServiceError
from oci.exceptions import ConfigFileNotFound

import oci

# Constants
DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"

# Global
total_gb = 0

def total_backup_no_expiration(b_id: str):
    # Get all boot backups 
    if "bootvolumebackup" in b_id:
        backup = volume_client.get_boot_volume_backup(boot_volume_backup_id=b_id).data
    else:
        backup = volume_client.get_volume_backup(volume_backup_id=b_id).data
    
    logger.info(f"Backup Expiration: {backup.expiration_time}")
    # if not backup.expiration_time:
    global total_gb
    total_gb = total_gb + backup.size_in_gbs

# Helper function
def wait_for_available(v_id: str):

    if dryrun:
        logger.debug("Not waiting for AVAILABLE")
        return
    
    if "bootvolume" in v_id:
        volume = volume_client.get_boot_volume(boot_volume_id=v_id)
        get_v_response = volume_client.get_boot_volume(v_id)
    else:
        volume = volume_client.get_volume(volume_id=v_id)
        get_v_response = volume_client.get_volume(v_id)

    # Waiting for AVAILABLE
    oci.wait_until(volume_client, get_v_response, 'lifecycle_state', 'AVAILABLE')

    vol = get_v_response.data
    logger.debug(f"Volume: {vol.display_name} AVAILABLE")


# Threaded function
def volume_work(v_id: str):

    if "bootvolume" in v_id:
        volume = volume_client.get_boot_volume(
            boot_volume_id=v_id
            ).data
    else:
        volume = volume_client.get_volume(
            volume_id=v_id
            ).data
    
    if isinstance(volume, BootVolume):
        logger.info(f"Boot Volume")
        
    else:
        logger.info(f"Block Volume")

    if volume.volume_group_id:
        logger.info(f"Part of Volume Group {volume.volume_group_id}")

    # Get Initial Lifecycle to return to afterwards
    volume_initial_lifecycle_state = volume.lifecycle_state
    
    # Get Tuned number
    tuned_vpu = volume.auto_tuned_vpus_per_gb if volume.auto_tuned_vpus_per_gb else volume.vpus_per_gb

    # # Return Val
    did_work = {}
    did_work["Detail"] = {"Name": f"{volume.display_name}", "OCID": f"{volume.id}", "Size": f"{volume.size_in_gbs}", "VPU": f"{volume.vpus_per_gb}({volume.auto_tuned_vpus_per_gb})"}

    # Now try it
    try:
        # Show before
        logger.info(f"----{v_id}----Examine ({volume.display_name})----------")
        logger.debug(f'Size: {volume.size_in_gbs} VPU: {volume.vpus_per_gb}({volume.auto_tuned_vpus_per_gb})')

        logger.info(f"Volume {volume.display_name} VPU: {volume.vpus_per_gb}({tuned_vpu})")
        logger.debug(f"Policy count: {len(volume.autotune_policies)}")
        if len(volume.autotune_policies) == 0:

            # Implement auto-tuning (rules)
            # Always do detached
            # Performance 0 -> None, 10 -> 20, 20 -> None, 30 -> 120
            
            if volume.vpus_per_gb == 0:
                update_volume_details=UpdateVolumeDetails(
                    autotune_policies=[DetachedVolumeAutotunePolicy()]
                )                
            elif volume.vpus_per_gb == 10:
                update_volume_details=UpdateVolumeDetails(
                    autotune_policies=[DetachedVolumeAutotunePolicy(),
                                        PerformanceBasedAutotunePolicy(max_vpus_per_gb=20)]
                )                
            elif volume.vpus_per_gb == 20:
                update_volume_details=UpdateVolumeDetails(
                    autotune_policies=[DetachedVolumeAutotunePolicy()]
                )                
            elif volume.vpus_per_gb >= 30:
                update_volume_details=UpdateVolumeDetails(
                    autotune_policies=[DetachedVolumeAutotunePolicy(max_vpus_per_gb=120)]
                )     
            # Actual Work
            logger.info(f"Update to {volume.display_name} : {len(update_volume_details.autotune_policies)}")

            if not dryrun:               
                if isinstance(volume, BootVolume):
                    logger.debug(f"Boot Volume update")
                    volume_client.update_boot_volume(
                        boot_volume_id=v_id,
                        update_boot_volume_details=update_volume_details
                    )
                else:
                    logger.debug(f"Block Volume Update")
                    volume_client.update_volume(
                        volume_id=v_id,
                        update_volume_details=update_volume_details
                    )
            wait_for_available(v_id)
        logger.info(f"----{v_id}----Complete ({volume.display_name})----------")
        return did_work
    except ServiceError as exc:
        logger.error(f"Failed to complete action for Volume: {volume.display_name} \nReason: {exc}")
        did_work["Error"] = {"Exception": exc.message}
    
    return did_work    
    # End main function

# Only if called in Main
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("-ipr", "--region", help="Use Instance Principal with alt region")
    parser.add_argument("--dryrun", help="Dry Run - no action", action="store_true")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)
    parser.add_argument("-r", "--retention", help="Days of backup retention (def=14)", type=int, default=14)
    parser.add_argument("-w", "--writejson", help="output json", action="store_true")

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal
    region = args.region
    dryrun = args.dryrun
    threads = args.threads
    backup_retention = args.retention
    output_json = args.writejson

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger('oci-block-volume')
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
        volume_client = BlockstorageClient(config=config_ip, signer=signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        search_client = ResourceSearchClient(config=config_ip, signer=signer)
    else:
        # Use a profile (must be defined)
        try:
            logger.info(f"Using Profile Authentication: {profile}")
            config = config.from_file(profile_name=profile)

            # Create the OCI Client to use
            volume_client = BlockstorageClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
            search_client = ResourceSearchClient(config)
        except ConfigFileNotFound as exc:
            logger.fatal(f"Unable to use Profile Authentication: {exc}")
            exit(1)

    # Main routine:q
        
    # Grab all Block Volumes
    # Loop through
    # Ensure:
    # 1) 


    # Get Volume (Search)
    # ocid1.bootvolume.oc1.iad.abuwcljtqnss4dbjiwqu27vx2felf3vhxlf3huhanxkwhhgi6ekzd3hzhqaa
    # ocid1.volume.oc1.iad.abuwcljrf76fwywr7qg6qmhtkjvl5bypvnlnf7ktnciwp5e3mndh6fjv2msq
    # ocid1.compartment.oc1..aaaaaaaa56cet4engnkah7pnrtljo3h55slitvhpmln4lpsi7toeri3qoeqq
    # volumes_res = search_client.search_resources(
    #     search_details=StructuredSearchDetails(
    #         type = "Structured",
    #         query='query bootvolume,volume resources where (compartmentId="ocid1.compartment.oc1..aaaaaaaa56cet4engnkah7pnrtljo3h55slitvhpmln4lpsi7toeri3qoeqq")'
    #     ),
    #     limit=1000
    # ).data

    # # Build a list of IDs
    # v_ocids = []
    # for i,v in enumerate(volumes_res.items, start=1):
    #     v_ocids.append(v.identifier)

    # # NON-Threaded
    # if threads == 0:
    #     for v in v_ocids:
    #         volume_work(v)
    # else:
    #     # Threaded
    #     with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
    #         results = executor.map(volume_work, v_ocids)
    #         logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")


    backups = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query bootvolumebackup,volumebackup resources'
        ),
        limit=1000
    ).data

    # Build a list of backup IDs
    backup_ocids = []
    for i,v in enumerate(backups.items, start=1):
        backup_ocids.append(v.identifier)
    
    # for v in backup_ocids:
    #     total_backup_no_expiration(v)

    # Threaded
    with ThreadPoolExecutor(max_workers = threads, thread_name_prefix="thread") as executor:
        results = executor.map(total_backup_no_expiration, backup_ocids)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")

    logger.info(f"Backups with no exp: {total_gb}")

    # Write to file if desired, else just print
    # if output_json:
    #     datestring = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    #     filename = f'oci-volume-scale-down-{datestring}.json'
    #     with open(filename,"w") as outfile:

    #         for result in results:
    #             outfile.write(json.dumps(result, indent=2))

    #     logging.info(f"Script complete - wrote JSON to {filename}.")
    # else:
    #     for result in results:
    #         logger.debug(f"Result: {result}")

