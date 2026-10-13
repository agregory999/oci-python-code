
from oci.config import validate_config
from oci.config import from_file
from oci.apigateway import ApiGatewayClient, DeploymentClient

import argparse


### MAIN CODE ###
# Parse Args
# Parse Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-c", "--compartment", help="Comaprtment OCID", required=True)
args = parser.parse_args()
verbose = args.verbose
profile = args.profile
comp_ocid = args.compartment

# Create / Validate Config
config = from_file(profile_name=profile)
validate_config(config)

apigw_client = ApiGatewayClient(config)
dep_client = DeploymentClient(config)

try:

    deployments = dep_client.list_deployments(
        compartment_id=comp_ocid,
        lifecycle_state="ACTIVE"
    ).data

    for dep in deployments.items:

        print(f"--=--Deployment: {dep}")
        spec = dep_client.get_deployment(deployment_id=dep.id).data.specification
        print(f"--=--Spec: {spec}")


except Exception as e:
    raise RuntimeError("\nError - " + str(e))

