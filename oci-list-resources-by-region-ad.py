#import oci
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

    
        # Loop AD within region
        availability_domains = identity.list_availability_domains(compartment_id=tenancy_id).data

        for ad in availability_domains:
            instances = []
            boot_volumes = []
            block_volumes = []

            print(f"AD: {ad.name}", flush=True)
            
            compartment_id = config["tenancy"]
            compartments = identity.list_compartments (tenancy_id,compartment_id_in_subtree=True).data
            for compartment in compartments:
                print(f" {compartment.name}")

                instances = compute.list_instances(compartment_id=compartment.id,lifecycle_state="RUNNING",availability_domain=ad.name).data
                for instance in instances:
                    print(f"  Instance Name: {instance.display_name} OCID: {instance.id}")
                
                boot_volumes = block_storage.list_boot_volumes(compartment_id=compartment.id,availability_domain=ad.name).data
                for boot_volume in boot_volumes:
                    print(f"   Boot Vol Name: {boot_volume.display_name} OCID: {boot_volume.id}")
                
                block_volumes = block_storage.list_volumes(compartment_id=compartment.id,availability_domain=ad.name).data
                for block_volume in block_volumes:
                    print(f"   Block Vol Name: {block_volume.display_name} OCID: {block_volume.id}")

                buckets = object_storage.list_buckets(compartment_id=compartment.id,namespace_name=os_ns, limit=1000).data
                for bucket in buckets:
                    bucket_details = object_storage.get_bucket(namespace_name=os_ns, bucket_name=bucket.name, fields=["approximateSize"]).data
                    print(f"  Bucket Name: {bucket.name} Size: {sizeof_fmt(bucket_details.approximate_size)}")

except Exception as e:
    raise RuntimeError("\nError - " + str(e))


for region in regions:
  if region.region_name == "us-ashburn-1" or region.region_name == "us-sanjose-1":
    instances = []
    bootVolumes = []
    blockVolumes = []
    config["region"] = region.region_name
    print(f"Region: {region.region_name}")
    identity = oci.identity.IdentityClient(config)
    print(f"Identity: {identity}")
    compartment_id = config["tenancy"]
    #print(f"Compartment ID: {compartment_id}")
    try:
      compartments = identity.list_compartments (config["tenancy"],compartment_id_in_subtree=True,lifecycle_state="ACTIVE").data
    except Exception as e:
      raise RuntimeError("\nError extracting compartments - " + str(e))
      errorLog(f"RuntimeError: {e}\n {compartments}\n\n")
    for compartment in compartments:
      #print(f"  Compartment: {compartment.name}")
      blockStorage = oci.core.BlockstorageClient(config)
      print(f"  Compartment: {compartment.name}  - Region: {region.region_name}")
      try:
        instances = compute.list_instances(compartment.id,lifecycle_state="RUNNING").data
        #print(f"    Instance: {instance.display_name}")
      except Exception as e:
        raise RuntimeError("\nError extracting instances - " + str(e))
        errorLog(f"RuntimeError: {e}\n {instances}\n\n")
      bootVolumes = blockStorage.list_boot_volumes(compartment_id=compartment.id).data
      blockVolumes = blockStorage.list_volumes(compartment_id=compartment.id).data
      for instance in instances:
        failure = 0
        defined_tags = []
        windstreamTagsServer = []
        windstreamTagsVolume = []       
        try:
          windstreamTagsServer = instance.defined_tags['Windstream_Tags']
        except KeyError as e:
          print("\nError - KeyError " + str(e))
          failure = 1
          continue
        print(f"    Instance: {instance.display_name}")


