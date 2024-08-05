# Python
import os
import logging
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

# OCI
from oci import config, pagination
from oci.retry import DEFAULT_RETRY_STRATEGY
from oci.identity import IdentityClient
from oci.identity.models import DynamicGroup
from oci.core import ComputeClient
from oci.database import DatabaseClient
from oci.functions import FunctionsManagementClient
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.exceptions import ConfigFileNotFound, ServiceError

# Local
from progress import Progress

###############################################################################################################
# Constants
###############################################################################################################

STATEMENT_REGEX = r'[\w.]+\s*=\s*\'[\w\s.]+\''
THREADS = 8

###############################################################################################################
# DynamicGroupAnalysis class
###############################################################################################################


class DynamicGroupAnalysis:

    dynamic_groups = []
    clients = []

    def __init__(self, progress: Progress, verbose: bool):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
        self.logger = logging.getLogger('oci-policy-analysis-dynamic-groups')
        self.logger.info("Init of class")
        if verbose:
            self.logger.setLevel(logging.DEBUG)

        self.logger.info("Initialized DynamicGroupAnalysis ")

        # Reference to progress object in main
        self.progress = progress

    # Just the Identity Client for now
    def initialize_client(self, profile: str, use_instance_principal: bool) -> bool:
        """Initialize the Identity Client"""

        if use_instance_principal:
            self.logger.info("Using Instance Principal Authentication")
            self.config = {}
            try:
                self.signer = InstancePrincipalsSecurityTokenSigner()

                # Create the OCI Client to use
                self.identity_client = IdentityClient(config={}, signer=self.signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
                self.tenancy_ocid = self.signer.tenancy_id
            except Exception as exc:
                self.logger.fatal(f"Unable to use IP Authentication: {exc}")
                return False
        else:
            self.logger.info(f"Using Profile Authentication: {profile}")
            self.signer = None
            try:
                self.config = config.from_file(profile_name=profile)
                self.logger.info(f'Using tenancy OCID from profile: {self.config["tenancy"]}')

                # Create the OCI Client to use
                self.identity_client = IdentityClient(self.config, retry_strategy=DEFAULT_RETRY_STRATEGY)
                self.tenancy_ocid = self.config["tenancy"]
            except ConfigFileNotFound as exc:
                self.logger.fatal(f"Unable to use Profile Authentication: {exc}")
                return False
        self.logger.info(f"Set up Identity Client for tenancy: {self.tenancy_ocid}")
        return True

    # Creation and caching of regional clients, needed for OCID validation in other regions
    def regional_client(self, region, type):
        """Create and cache a regional OCI Client for any type or region"""

        # Get base config
        localconfig = self.config
        localconfig["region"] = region
        self.logger.debug(f"Using config: {localconfig}")

        if "instance" in type:
            # Check clients first (any one we have)
            for client in self.clients:
                if region == client[0] and isinstance(client[1], ComputeClient):
                    self.logger.debug(f"Matching client {region} / {type}")
                    return client[1]
            # Create compute
            cl = (region, ComputeClient(config=localconfig, region=region, retry_strategy=DEFAULT_RETRY_STRATEGY))
            self.clients.append(cl)
            self.logger.info(f"Created client {region} / {type}")
            return cl[1]
        elif "dbsystem" in type or "autonomousdatabase" in type or "dbnode" in type or "cloudvmcluster" in type:
            # Check clients first (any one we have)
            for client in self.clients:
                if region == client[0] and isinstance(client[1], DatabaseClient):
                    self.logger.debug(f"Matching client {region} / {type}")
                    return client[1]
            cl = (region, DatabaseClient(config=localconfig, region=region, retry_strategy=DEFAULT_RETRY_STRATEGY))
            self.clients.append(cl)
            self.logger.info(f"Created client {region} / {type}")
            return cl[1]
        elif "fnfunc" in type or "fnapp" in type:
            # Check clients first (any one we have)
            for client in self.clients:
                if region == client[0] and isinstance(client[1], FunctionsManagementClient):
                    self.logger.debug(f"Matching client {region} / {type}")
                    return client[1]
            cl = (region, FunctionsManagementClient(config=localconfig, region=region, retry_strategy=DEFAULT_RETRY_STRATEGY))
            self.clients.append(cl)
            self.logger.info(f"Created client {region} / {type}")
            return cl[1]
        else:
            return None

    # OCID Checker - Return False if the object is not valid, True otherwise and if we cannot tell
    def validate_ocid(self, ocid: str) -> bool:
        '''Check the OCID and return False if it isn't a thing any more'''

        # Parse the OCID into pieces - compartments are missing a region - we also only care about some parts
        garb1, ocid_type, garb2, ocid_region, garb3 = ocid.split('.')

        # Need to get a client per the region of the OCID element
        try:
            # Based on type, use the configured client to see if it comes back with anything
            if "compartment" in ocid_type or "tenancy" in ocid_type:
                self.identity_client.get_compartment(compartment_id=ocid)
            elif "instance" in ocid_type:
                cl = self.regional_client(ocid_region, ocid_type)
                cl.get_instance(instance_id=ocid)
            elif "dbsystem" in ocid_type:
                cl = self.regional_client(ocid_region, ocid_type)
                cl.get_db_system(db_system_id=ocid)
            elif "autonomousdatabase" in ocid_type:
                cl = self.regional_client(ocid_region, ocid_type)
                cl.get_autonomous_database(autonomous_database_id=ocid)
            elif "cloudvmcluster" in ocid_type:
                cl = self.regional_client(ocid_region, ocid_type)
                cl.get_cloud_vm_cluster(cloud_vm_cluster_id=ocid)
            elif "fnfunc" in ocid_type:
                cl = self.regional_client(ocid_region, ocid_type)
                cl.get_function(function_id=ocid)
            elif "fnapp" in ocid_type:
                cl = self.regional_client(ocid_region, ocid_type)
                cl.get_application(application_id=ocid)
            # elif "dbnode" in ocid_type:
            #     a = self.database_client[ocid_region].get_db_node(db_node_id=ocid)
            elif False:
                pass
                # To do
                # datacatalog
                # cloudexadatainfrastructure
                # devopsbuildpipeline, devopsrepository, devopsdeploypipeline
                # apigateway
                # vault
            else:
                self.logger.warning(f"Type of OCID not supported: {ocid_type}")
        except ServiceError as exc:
            # Expected
            self.logger.debug(f"Caught error: {exc.message}")
            return False
        except KeyError as exc:
            self.logger.error(f"Caught error - unable to determine: {exc}")
            return True
        except AttributeError as exc:
            self.logger.error(f"Caught error - unable to determine: {exc}")
            return True
        return True

    # Check a single DG for in use (requires PolicyAnalysis instance)
    def dg_in_use(self, dg: DynamicGroup) -> bool:
        """Determine if a DG is in use within any policy statement"""

        for statement in self.policies:
            if dg[0].casefold() in statement[4].casefold():
                self.logger.debug(f"DG {dg[0]} referenced by statement {statement}")
                return True
        # No match so return False
        return False

    # See if any DG isn't in use by any policy
    def run_dg_in_use_analysis(self) -> list:
        """Use the policy statements to generate a list of delete-able DG"""

        unused_dynamic_groups = []
        # Iterate rules to look for broken OCIDs and add to tuple
        for i, dg in enumerate(self.dynamic_groups):
            self.logger.debug(f"Validate DG {dg[0]}")
            valid_dg = self.dg_in_use(dg=dg)
            self.logger.info(f"Valid: {dg[0]}: {valid_dg}")

            # Set in existing DG
            dg[4] = valid_dg

            # If false, add to return list
            if not valid_dg:
                unused_dynamic_groups.append(dg)

        # Return the invalid list
        self.logger.info(f"Finished DG in Use analysis, found {len(unused_dynamic_groups)} unused groups")
        return unused_dynamic_groups

    # Threadable method to take a DG list (our object) and populate the invalid ocids
    def invalid_ocid_check(self, dg: list):
        """Given a DG (as internal list representation), update it if any OCID is invalid. Run as a thread"""

        self.logger.debug(f"Thread Started on {dg[0]}")

        # Could be multiple rules and thus multiple OCIDs
        for i, rule in enumerate(dg[3]):
            ocid_regex = r"ocid1\.\w+\.\w+\.\w*\.\w+"
            ocid = re.search(ocid_regex, rule)
            if ocid and ocid.group(0):

                # To do threading here, add to ocid_list
                # then we'd need to run threads against the validation
                # Each future would then need to be processed.
                is_ocid_valid = self.validate_ocid(ocid.group(0))
                self.logger.debug(f"Rule {i}: {dg[0]} ({is_ocid_valid}): {ocid.group(0)}")
                if not is_ocid_valid:
                    self.logger.debug(f"Marking {ocid.group(0)} as invalid")
                    dg[5].append(ocid.group(0))
        self.logger.debug(f"Thread finished on {dg[0]}")

    # Process all DG Matching rules and look all valid OCIDs
    def run_deep_analysis(self):
        """Control the threaded process of checking each Dynamic Group for invalid OCIDs"""

        # We know the DG count now - set up progress
        self.progress.set_to_load(len(self.dynamic_groups))

        # new_dynamic_groups = []

        # Start timer
        tic = time.perf_counter()

        # # Iterate rules to look for broken OCIDs and add to DG tuple
        # for i, dg in enumerate(self.dynamic_groups):
        #     rule = dg[2]
        #     self.logger.debug(f"\n---Rule: {dg[0]} Rule{i}: {dg[2]}")

        with ThreadPoolExecutor(max_workers=THREADS, thread_name_prefix="thread") as executor:
            # results = executor.map(self.load_policies, comp_list)
            results = [executor.submit(self.invalid_ocid_check, dg) for dg in self.dynamic_groups]
            self.logger.info(f"Kicked off {THREADS} threads for parallel execution - adjust as necessary")

            # Add callbacks to report
            for future in results:
                # future.add_done_callback(print)
                if self.progress:
                    future.add_done_callback(self.progress.progress_indicator)

        # Process Threaded Results
        for future in results:
            self.logger.debug(f"Result: {future}")
            try:
                future.result()
            except Exception as exc:
                self.logger.error(f"Executor Exception: {exc}")

        # Set progress back to 0
        self.progress.progressbar_val = 0.0

        # Stop Timer
        toc = time.perf_counter()

        # Replace DGs with new list of tuples
        # self.dynamic_groups = new_dynamic_groups
        self.logger.info(f"Finished deep analysis in {toc-tic}s")

    # Parse Dynamic Group into tuple
    def parse_dynamic_group(self, dynamic_group: DynamicGroup) -> tuple:
        """Parse an OCI Dynamic Group into the various components for the internal representation
        Name
        OCID
        Matching Rules
        In Use (bool)
        Invalid OCIDs (list)
        time_created
        """

        # Grab the creation time in string
        time_created = dynamic_group.time_created.strftime("%m/%d/%Y %H:%M:%S")

        statements = dynamic_group.matching_rule
        statement_regex = r'[\w.]+\s*=\s*\'[\w\s.]+\''
        rules = re.findall(statement_regex, statements, re.IGNORECASE | re.MULTILINE)
        # Parse matching rule into a list

        # No validity data yet
        return [dynamic_group.name, dynamic_group.id, statements, rules, True, [], time_created]

    # Incoming call from outside (Entry Point)
    def load_all_dynamic_groups(self, use_cache: bool) -> bool:
        """Load all dynamic groups in tenancy, using the configured Identity Client"""

        self.dynamic_groups = []

        if use_cache:
            self.logger.info(f"---Starting DG Load for tenant: {self.tenancy_ocid} from cached files---")
            if os.path.isfile(f'./.dynamic-group-cache-{self.tenancy_ocid}.dat'):
                with open(f'./.dynamic-group-cache-{self.tenancy_ocid}.dat', 'r') as filehandle:
                    self.dynamic_groups = json.load(filehandle)

        else:
            self.logger.info(f"---Starting DG Load for tenant: {self.tenancy_ocid} from client---")
            # Load them all from client
            paginated_response = pagination.list_call_get_all_results(
                self.identity_client.list_dynamic_groups,
                compartment_id=self.tenancy_ocid,
                limit=1000
            ).data

            # Print what we have (if verbose)
            for i, dg in enumerate(paginated_response):
                self.logger.debug(f'Found Dynamic Group {i}: {dg.name} {dg.matching_rule}')
                entry = self.parse_dynamic_group(dynamic_group=dg)
                self.logger.debug(f'Tuple: {entry}')
                self.dynamic_groups.append(entry)
            # # Dump new cache
            with open(f'.dynamic-group-cache-{self.tenancy_ocid}.dat', 'w') as filehandle:
                json.dump(self.dynamic_groups, filehandle)

        # Done
        self.logger.info(f"---Finished DG Load ({len(self.dynamic_groups)}) for tenant: {self.tenancy_ocid} ---")
        return True

    # Set the statements
    def set_statements(self, statements: list):
        """Set the policies in place"""

        self.policies = statements

    # Filter Dynamic Groups for display
    def filter_dynamic_groups(self, name_filter: str, type_filter: str, ocid_filter: str) -> list:
        '''Filter the list of DGs and return what is required'''

        self.logger.debug(f"Filtering DG with name filter: {name_filter}, type filter: {type_filter}, ocid filter: {ocid_filter}")
        filtered_dynamic_groups = []

        # Split Name filter
        split_name_filter = name_filter.split('|')
        split_ocid_filter = ocid_filter.split('|')
        split_type_filter = type_filter.split('|')
        self.logger.debug(f"Filtering: {split_name_filter}. Before: {len(self.dynamic_groups)} Dynamic Groups")

        # Name Filter
        for filt in split_name_filter:
            filtered_dynamic_groups.extend(list(filter(lambda dg: filt.casefold() in dg[0].casefold(), self.dynamic_groups)))
        # filtered_dynamic_groups = self.dynamic_groups
        self.logger.info(f"Filtering Name: {split_name_filter}. After: {len(filtered_dynamic_groups)} Dynamic Groups")

        filtered_dynamic_groups_prev = filtered_dynamic_groups
        filtered_dynamic_groups = []

        # OCID Filter
        for filt in split_ocid_filter:
            filtered_dynamic_groups.extend(list(filter(lambda dg: filt.casefold() in dg[2].casefold(), filtered_dynamic_groups_prev)))
        # filtered_dynamic_groups = self.dynamic_groups
        self.logger.info(f"Filtering OCID: {split_ocid_filter}. After: {len(filtered_dynamic_groups)} Dynamic Groups")

        filtered_dynamic_groups_prev = filtered_dynamic_groups
        filtered_dynamic_groups = []

        # Type Filter
        for filt in split_type_filter:
            filtered_dynamic_groups.extend(list(filter(lambda dg: filt.casefold() in dg[2].casefold(), filtered_dynamic_groups_prev)))
        # filtered_dynamic_groups = self.dynamic_groups
        self.logger.info(f"Filtering Type: {split_ocid_filter}. After: {len(filtered_dynamic_groups)} Dynamic Groups")
        return filtered_dynamic_groups
