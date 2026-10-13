
from oci.config import validate_config
from oci.config import from_file
from oci.identity import IdentityClient
from oci.core import ComputeClient
from oci.core import BlockstorageClient
from oci.object_storage import ObjectStorageClient

import argparse
### HELPERS ###
def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

### CONSTANT ###
TB = 1024 * 1024 * 1024 * 1024

### MAIN CODE ###
# Parse Args
# Parse Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-t", "--threshold", help="Threshold in TB to show greater than, number", default=10, type=int)
args = parser.parse_args()
verbose = args.verbose
profile = args.profile
show_threshold = args.threshold


# Create / Validate Config
config = from_file(profile_name=profile)
validate_config(config)

tenancy_id = config["tenancy"]
identity = IdentityClient(config)

# Overall counter
total_bytes_tenancy = 0

try:

    regions = identity.list_region_subscriptions(tenancy_id=tenancy_id).data
    for region in regions:

        print(f"Region Name {region.region_name}")

        # Change Region and re-create Clients
        config["region"] = region.region_name
        identity = IdentityClient(config)
        compute = ComputeClient(config)
        block_storage = BlockstorageClient(config)
        object_storage = ObjectStorageClient(config)
        os_ns = object_storage.get_namespace().data

    
        instances = []
        boot_volumes = []
        block_volumes = []

        #print(f"AD: {ad.name}", flush=True)
        
        # Total Counter
        total_bytes = 0

        compartment_id = config["tenancy"]
        compartments = identity.list_compartments (tenancy_id,compartment_id_in_subtree=True).data
        for compartment in compartments:
            if verbose:
                print(f" Compartment: {compartment.name}", flush=True)

            buckets = object_storage.list_buckets(compartment_id=compartment.id,namespace_name=os_ns, limit=1000).data
            for bucket in buckets:
                bucket_details = object_storage.get_bucket(namespace_name=os_ns, bucket_name=bucket.name, fields=["approximateSize","approximateCount"]).data
                
                # Add to counter
                total_bytes += bucket_details.approximate_size
                if verbose or bucket_details.approximate_size > show_threshold * TB:
                    #print(f'  {"***" if bucket_details.approximate_size > show_threshold * TB else ""}Bucket Name: {bucket.name} Size: {sizeof_fmt(bucket_details.approximate_size)} Objects: {bucket_details.object_count}')
                #else:
                #    if bucket_details.approximate_size > 10 * TB:
                    print(f'  *** {compartment.name} / Bucket Name: {bucket.name} Size: {sizeof_fmt(bucket_details.approximate_size)} Objects: {sizeof_fmt(bucket_details.approximate_count)}')

        # Summary Region
        print(f"Storage Total (Region): {sizeof_fmt(total_bytes)}")
        total_bytes_tenancy += total_bytes
    # Summary Tenancy
    print(f"Storage Total (Tenancy): {sizeof_fmt(total_bytes_tenancy)}")

except Exception as e:
    raise RuntimeError("\nError - " + str(e))

