
from oci.config import validate_config
from oci.config import from_file
from oci.identity import IdentityClient
from oci.core import ComputeClient
from oci.core import BlockstorageClient
from oci.object_storage import ObjectStorageClient

### HELPERS ###
def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

### MAIN CODE ###
# Grabs the default region
config = from_file(profile_name="WINDSTREAM")
#config = from_file()
validate_config(config)

tenancy_id = config["tenancy"]
identity = IdentityClient(config)

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
        
        compartment_id = config["tenancy"]
        compartments = identity.list_compartments (tenancy_id,compartment_id_in_subtree=True).data
        for compartment in compartments:
            print(f" Compartment: {compartment.name}", flush=True)

            buckets = object_storage.list_buckets(compartment_id=compartment.id,namespace_name=os_ns, limit=1000).data
            for bucket in buckets:
                bucket_details = object_storage.get_bucket(namespace_name=os_ns, bucket_name=bucket.name, fields=["approximateSize"]).data
                print(f"  Bucket Name: {bucket.name} Size: {sizeof_fmt(bucket_details.approximate_size)}")

except Exception as e:
    raise RuntimeError("\nError - " + str(e))

