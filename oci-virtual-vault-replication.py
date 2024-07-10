import argparse   # Argument Parsing
import oci

parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Increased Verbosity, boolean", action="store_true")
parser.add_argument("-pr", "--profile", help="Named Config Profile, from OCI Config", default="DEFAULT")
parser.add_argument("-vid", "--vaultocid", help="Vault OCID", required=True)

args = parser.parse_args()
verbose = args.verbose  # Boolean
profile = args.profile  # String
vault_ocid = args.vaultocid  # Required OCID

config = oci.config.from_file(profile_name=profile)

key_management_client = oci.key_management.KmsVaultClient(config)

# Validate Vault
try:
    vault = key_management_client.get_vault(
        vault_id=vault_ocid
    ).data
    print(f"Vault: {vault}")
except oci.exceptions.ServiceError as e:
    print(f"Error getting vault: {e}")
    exit(1)

create_vault_replica_response = key_management_client.create_vault_replica(
    vault_id=vault_ocid,
    create_vault_replica_details=oci.key_management.models.CreateVaultReplicaDetails(
        replica_region="us-phoenix-1"
    )
)