# This is an automatically generated code sample.
# To make this code sample work in your Oracle Cloud tenancy,
# please replace the values for any parameters whose current values do not fit
# your use case (such as resource IDs, strings containing ‘EXAMPLE’ or ‘unique_id’, and
# boolean, number, and enum parameters with values not fitting your use case).

import oci

# Create a default config using DEFAULT profile in default location
# Refer to
# https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm#SDK_and_CLI_Configuration_File
# for more info
config = oci.config.from_file()


# Initialize service client with default config file
object_storage_client = oci.object_storage.ObjectStorageClient(config)


# Send the request to service, some parameters are not required, see API
# doc for more info
update_object_storage_tier_response = object_storage_client.update_object_storage_tier(
    namespace_name="orasenatdpltintegration01",
    bucket_name="tfcloud-part2-bucket",
    update_object_storage_tier_details=oci.object_storage.models.UpdateObjectStorageTierDetails(
        object_name="feb22",
        storage_tier="InfrequentAccess",
    )
)

# Get the data from response
print(update_object_storage_tier_response.headers)