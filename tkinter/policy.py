# Python
import logging
import re
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from oci import config, pagination
from oci.retry import DEFAULT_RETRY_STRATEGY
from oci.exceptions import ConfigFileNotFound, ServiceError
from oci.identity import IdentityClient
from oci.identity.models import Compartment, Policy, UpdatePolicyDetails
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.identity_domains import IdentityDomainsClient

# Local
from progress import Progress

###############################################################################################################
# Constants
###############################################################################################################

THREADS = 8
POLICY_REGEX = r'^\s*?(allow|endorse)\s+(?P<subjecttype>service|any-user|any-group|dynamic-group|dynamicgroup|group|resource)\s*(?P<subject>([\w\/\'\.\\, +-]|,)+?)?\s+(to\s+)?((?P<verb>read|inspect|use|manage)\s+(?P<resource>[\w-]+)|(?P<perm>{[\s*\w\s*|\s*\w\s*,\s*]+}))\s+in\s+(?P<locationtype>any-tenancy|tenancy|compartment\s+id|compartment)\s*(?P<location>[\w\':.-]+)?(?:\s+where\s+(?P<condition>.+))?(?:(?P<optional>\s*\/\/.+))?$'

###############################################################################################################
# PolicyAnalysis class
###############################################################################################################


class PolicyAnalysis:

    regular_statements = []

    # Use like a global to indicate if it is running a threaded load.  When finished, this goes to True, and then
    # the main class does an update and sets this back to false.  Probably a better way
    finished = False

    # tenancy_ocid, identity_client recursion
    def __init__(self, progress: Progress, verbose: bool):
        """Initialize the class"""

        # Create a logger
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
        self.logger = logging.getLogger('oci-policy-analysis-policies')
        self.logger.info("Init of class")
        if verbose:
            self.logger.setLevel(logging.DEBUG)

        # Reference to progress object in main
        self.progress = progress

    # Class Initializer
    def initialize_client(self, profile: str, use_instance_principal: bool, use_recursion: bool, use_cache: bool) -> bool:
        """Set up the OCI client (Identity)"""

        # Grab variables required
        self.use_recursion = use_recursion
        self.use_cache = use_cache
        self.use_instance_principal = use_instance_principal
        self.profile = profile

        if self.use_instance_principal:
            self.logger.info("Using Instance Principal Authentication")
            try:
                signer = InstancePrincipalsSecurityTokenSigner()

                # Create the OCI Client to use
                self.identity_client = IdentityClient(config={}, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
                self.idm_client = IdentityDomainsClient(config={}, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
                self.tenancy_ocid = signer.tenancy_id
            except Exception as exc:
                self.logger.fatal(f"Unable to use IP Authentication: {exc}")
                return False
        else:
            self.logger.info(f"Using Profile Authentication: {self.profile}")
            try:
                self.config = config.from_file(profile_name=self.profile)
                self.logger.info(f'Using tenancy OCID from profile: {self.config["tenancy"]}')

                # Create the OCI Client to use
                self.identity_client = IdentityClient(self.config, retry_strategy=DEFAULT_RETRY_STRATEGY)
                self.idm_client = IdentityDomainsClient(config=self.config,
                                                        service_endpoint="https://idcs-aea17de1f62a467cbc60239f8851911c.identity.oraclecloud.com",
                                                        retry_strategy=DEFAULT_RETRY_STRATEGY)

                self.tenancy_ocid = self.config["tenancy"]
            except ConfigFileNotFound as exc:
                self.logger.fatal(f"Unable to use Profile Authentication: {exc}")
                return False
        self.logger.info(f"Set up Identity Client for tenancy: {self.tenancy_ocid}")
        return True

    def parse_statement(self, statement: str, comp_string: str, policy: Policy) -> list:
        '''Parses policy statement into list
           0 - policy name
           1 - id
           2 - compartment id
           3 - hierarchy
           4 - statement text
           5 - valid-bool
           6 - subject-type (group,resource, etc)
           7 - subject
           8 - verb
           9 - resource
           10 - permissions
           11 - location-type
           12 - location
           13 - conditions
           14 - optional (Comments at end)
           15 - created time
        '''

        # Grab the creation time in string
        time_created = policy.time_created.strftime("%m/%d/%Y %H:%M:%S")

        # Use case-insensitive and multi-line
        result = re.search(pattern=POLICY_REGEX,
                           string=statement,
                           flags=re.IGNORECASE|re.MULTILINE
                           )
        if result:
            self.logger.debug(f"Statement: {statement} : {result.groups()}")
            try:
                # policy name, id, compartment id, hierarchy, statement text, valid-bool, subj-type, subject, verb, resource, perms, loc-type, location, conditions, optional) 
                statement_list = [policy.name, policy.id, policy.compartment_id, f"{comp_string}", statement, True if result else False, 
                                result.group('subjecttype'), 
                                result.group('subject') if result.group('subject') else "", 
                                result.group('verb') if result.group('verb') else "", 
                                "" if not result.group('resource') else result.group('resource'), 
                                result.group('perm'),
                                result.group('locationtype'), 
                                result.group('location') if result.group('location') else "", 
                                result.group('condition') if result.group('condition') else "", 
                                result.group('optional') if result.group('optional') else "",
                                time_created
                ]
                # Post-process any-user / any-group
                if statement_list[6] == "any-user" or statement_list[6] == "any-group":
                    statement_list[7] = statement_list[6]
                # Hierarchy ROOT so searchable
                if not statement_list[3] or statement_list[3] == "":
                    statement_list[3] = "ROOT"

                # Statement list return
                return statement_list
            except Exception as e:
                self.logger.warning(f"Failed to parse result: {e}")
                statement_list = [policy.name, policy.id, policy.compartment_id, f"{comp_string}", statement,
                                   False, "other", "", "", "", False, "", "", "", "", time_created]
                return statement_list
        else:
            # Return less populated tuple
            self.logger.info(f"No regex result: {statement}")
            if statement.startswith("define"):
                statement_list = [policy.name, policy.id, policy.compartment_id, f"{comp_string}", statement, 
                                  True, "define", "", "", "", False, "", "", "", "", time_created]
            else:
                statement_tuple = [policy.name, policy.id, policy.compartment_id, f"{comp_string}", statement,
                                   True, "other", "", "", "", False, "", "", "", "", time_created]
            return statement_list      

    # Recursive Compartments / Policies
    def get_compartment_path(self, compartment: Compartment, level, comp_string) -> str:
        """Create the hierarchical path back to tenancy root"""

        # Top level forces fall back through
        self.logger.debug(f"Compartment Name: {compartment.name} ID: {compartment.id} Parent: {compartment.compartment_id}") 
        if not compartment.compartment_id:
            self.logger.debug(f"Top of tree. Path is {comp_string}")
            return comp_string
        parent_compartment = self.identity_client.get_compartment(compartment_id=compartment.compartment_id).data    

        # Recurse until we get to top
        self.logger.debug(f"Recurse. Path is {comp_string}")
        return self.get_compartment_path(parent_compartment, level+1, compartment.name + "/" + comp_string)

    # Post-process - determine if DGs are invalid
    def check_for_invalid_dynamic_groups(self, dynamic_groups: list):
        """Loop through DG policies and ensure DGs exist"""

        statements_analyzed = 0
        for st in self.regular_statements:
            if st[6] == "dynamic-group":
                self.logger.debug(f"Validatiing statement for group {st[7]}")
                valid = False
                for dg in dynamic_groups:
                    if st[7].casefold() == dg[0].casefold():
                        self.logger.debug(f"We have a match: {dg[0]}")
                        valid = True
                st[5] = valid
                statements_analyzed += 1
        self.logger.info(f"Completed validation for {statements_analyzed} Dynamic Group statments")

    # Threadable policy loader - per compartment
    def load_policies(self, compartment: Compartment):
        '''Runs as a thread - load all policies in a compartment and parse them into internal list representation'''

        self.logger.debug(f"Compartment: {compartment.id}")

        # Get policies First
        list_policies_response = self.identity_client.list_policies(
            compartment_id=compartment.id,
            limit=1000
        ).data

        self.logger.debug(f"Pol: {list_policies_response}")
        # Nothing to do if no policies
        if len(list_policies_response) == 0:
            self.logger.debug("No policies. return")
            return
        
        # Load recursive structure of path (only if there are policies)
        path = self.get_compartment_path(compartment, 0, "")
        self.logger.debug(f"Compartment Path: {path}")

        for policy in list_policies_response:
            self.logger.debug(f"() Policy: {policy.name} ID: {policy.id}")
            for index, statement in enumerate(policy.statements, start=1):
                self.logger.debug(f"-- Statement {index}: {statement}")

                # Make lower case
                statement = str.casefold(statement)

                # Helper returns tuple with policy statement and lineage
                statement_tuple = self.parse_statement(
                    statement=statement,
                    comp_string=path,
                    policy=policy
                )

                self.logger.debug(f"Tuple from main: {statement_tuple}")
                self.regular_statements.append(statement_tuple)

    # Incoming call from outside (Entry Point)
    def load_policies_from_client(self) -> bool:
        # Requirements
        # Logger (self)
        # IdentityClient (self)

        # Start fresh
        # self.dynamic_group_statements = []
        # self.service_statements = []
        self.regular_statements = []

        # If cached, load that and be done
        if self.use_cache:
            self.logger.info(f"---Starting Policy Load for tenant: {self.tenancy_ocid} from cached files---")
            if os.path.isfile(f'.policy-statement-cache-{self.tenancy_ocid}.dat'):
                with open(f'./.policy-statement-cache-{self.tenancy_ocid}.dat', 'r') as filehandle:
                    self.regular_statements = json.load(filehandle)
        else:
            # If set from main() it is ok, otherwise take from function call
            self.logger.info(f"---Starting Policy Load for tenant: {self.tenancy_ocid} with recursion {self.use_recursion} and {THREADS} threads---")

            # Load the policies
            # Start with list of compartments
            comp_list = []

            # Time the process (Wall time)
            tic = time.perf_counter()

            # Get root compartment into list
            root_comp = self.identity_client.get_compartment(compartment_id=self.tenancy_ocid).data 
            comp_list.append(root_comp)

            if self.use_recursion:
                # Get all compartments (we don't know the depth of any), tenancy level
                # Using the paging API
                paginated_response = pagination.list_call_get_all_results(
                    self.identity_client.list_compartments,
                    self.tenancy_ocid,
                    access_level="ACCESSIBLE",
                    sort_order="ASC",
                    compartment_id_in_subtree=True,
                    lifecycle_state="ACTIVE",
                    limit=1000)
                comp_list.extend(paginated_response.data)

                self.logger.info(f'Loaded {len(comp_list)} Compartments.  {"Using recursion" if self.use_recursion else "No Recursion, only root-level policies"}')

                # We know the compartment count now - set up progress, if warranted
                if self.progress:
                    self.progress.set_to_load(len(comp_list))
                    self.logger.info(f"Progress Bar set total: {len(comp_list)}")

                # Use multiple threads at once
                with ThreadPoolExecutor(max_workers = THREADS, thread_name_prefix="thread") as executor:
                    # results = executor.map(self.load_policies, comp_list)
                    results = [executor.submit(self.load_policies, c) for c in comp_list]
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
                if self.progress:
                    self.progress.progressbar_val = 0.0

                # Stop timer
                toc = time.perf_counter()
                self.logger.info(f"Loaded {len(self.regular_statements)} regular policy statements on {THREADS} threads in {toc-tic:.2f}s")

            else:
                self.logger.info(f"Loading policies on main thread")
                for c in comp_list:
                    self.load_policies(compartment=c)
                toc = time.perf_counter()
                self.logger.info(f"Loaded /{len(self.regular_statements)} regular policy statements on main thread in {toc-tic:.2f}s")

            self.logger.info(f"---Finished Policy Load from client---")

            # Dump in local cache for later
            with open(f'.policy-statement-cache-{self.tenancy_ocid}.dat', 'w') as filehandle:
                json.dump(self.regular_statements, filehandle)
        
        # Return true to incidate success
        # Poor man's event
        self.finished = True
        return True

    # Filter Output
    def filter_policy_statements(self, subj_filter: str, verb_filter: str, resource_filter: str, location_filter: str, 
                                 hierarchy_filter: str, condition_filter: str, text_filter: str, policy_filter: str) -> list:
        '''Returns a list of filtered regular statements'''
        regular_statements = self.regular_statements  
        regular_statements_filtered = []

        # Split
        split_subj_filter = subj_filter.split(sep='|')
        self.logger.debug(f"Subject filter length: {len(split_subj_filter)}")
        split_verb_filter = verb_filter.split(sep='|')
        self.logger.debug(f"Verb filter length: {len(split_verb_filter)}")
        split_res_filter = resource_filter.split(sep='|')
        self.logger.debug(f"Resource filter length: {len(split_res_filter)}")
        split_loc_filter = location_filter.split(sep='|')
        self.logger.debug(f"Location filter length: {len(split_loc_filter)}")
        split_hierarchy_filter = hierarchy_filter.split(sep='|')
        self.logger.debug(f"Hierarchy filter length: {len(split_loc_filter)}")
        split_condition_filter = condition_filter.split(sep='|')
        self.logger.debug(f"Condition filter length: {len(split_condition_filter)}")
        split_text_filter = text_filter.split(sep='|')
        self.logger.debug(f"Text filter length: {len(split_condition_filter)}")
        split_policy_filter = policy_filter.split(sep='|')
        self.logger.debug(f"Policy Name filter length: {len(split_policy_filter)}")

        self.logger.debug(f"Filtering subject(B): {split_subj_filter}. Before: {len(regular_statements)} Reg statements")
        for filt in split_subj_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[7].casefold(), regular_statements)))
        self.logger.debug(f"Filtering subject(A): {len(regular_statements_filtered)} Reg statements")

        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        self.logger.debug(f"Filtering Verb(B): {split_verb_filter}. Before: {len(regular_statements_filtered_prev)} Reg statements")
        for filt in split_verb_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[8].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering Verb(A): {len(regular_statements_filtered)} Reg statements")
        
        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        self.logger.debug(f"Filtering Resource(B): {split_res_filter}. {len(regular_statements_filtered_prev)} DG/SVC/Reg statements")
        for filt in split_res_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[9].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering Resource(A): {len(regular_statements_filtered)} DG/SVC/Reg statements")

        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        self.logger.debug(f"Filtering Location(B): {len(regular_statements_filtered_prev)} DG/SVC/Reg statements")
        for filt in split_loc_filter:
            if "tenancy" == filt:
                self.logger.info("tenancy filter")
                regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[11].casefold(), regular_statements_filtered_prev)))
            else:    
                regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[12].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering Location(A): {len(regular_statements_filtered)} Reg statements")

        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        # Hierarchy
        self.logger.debug(f"Filtering hierarchy(B): {split_hierarchy_filter}. Before: {len(regular_statements_filtered_prev)} Reg statements")
        for filt in split_hierarchy_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[3].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering hierarchy(A): {len(regular_statements_filtered)} Reg statements")

        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        # Condition
        self.logger.debug(f"Filtering Conditions(B): {split_condition_filter}. Before: {len(regular_statements_filtered_prev)} Reg statements")
        for filt in split_condition_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[13].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering Conditions(A): {len(regular_statements_filtered)} Reg statements")

        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        # Policy Text
        self.logger.debug(f"Filtering Conditions(B): {split_text_filter}. Before: {len(regular_statements_filtered_prev)} Reg statements")
        for filt in split_text_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[4].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering Conditions(A): {len(regular_statements_filtered)} Reg statements")

        # Reset filter
        regular_statements_filtered_prev = regular_statements_filtered
        regular_statements_filtered = []

        # Policy Name
        self.logger.debug(f"Filtering Conditions(B): {split_policy_filter}. Before: {len(regular_statements_filtered_prev)} Reg statements")
        for filt in split_policy_filter:
            regular_statements_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[0].casefold(), regular_statements_filtered_prev)))
        self.logger.debug(f"Filtering Conditions(A): {len(regular_statements_filtered)} Reg statements")

        # Return
        self.logger.info(f"After filters applied: {len(regular_statements_filtered)} Reg statements")
        return regular_statements_filtered

    # Get a policy for the purpose of updating one of the statements
    def get_policies_for_edit(self, policy_ocids: list[str]) -> list[tuple]:
        """Given a policy we want to edit, return the policy""" 

        # Get a list for returned policies
        policies_returned = []

        for ocid in policy_ocids:
            pol_resp = self.identity_client.get_policy(policy_id=ocid)
            self.logger.info(f'Policy: {pol_resp.data.name} Etag: {pol_resp.headers["ETag"]}')
            # self.logger.info(f"Full Policy: {pol_resp.data}")
            policies_returned.append((pol_resp.headers["ETag"], pol_resp.data))
        
        # Return a list of policies that are tuple(etag, policy)
        self.logger.info(f"Policies returned: {len(policies_returned)}")
        return (policies_returned)

    def update_policies(self, policies_to_update: list[tuple]) -> bool:
        """Update the policy with optimistic concurrency, to ensure it wasn't mucked with"""

        updated_policies = []
        for item in policies_to_update:

            etag, policy_to_update = item
            self.logger.info(f"Updating Policy: {policy_to_update}")
            try:
                self.identity_client.update_policy(policy_id=policy_to_update.id, 
                                                update_policy_details=UpdatePolicyDetails(description=policy_to_update.description,
                                                                                            statements=policy_to_update.statements,
                                                                                            defined_tags=policy_to_update.defined_tags,
                                                                                            freeform_tags=policy_to_update.freeform_tags),
                                                if_match=etag)
                self.logger.info(f"Updated Policy: {policy_to_update}")
                ret = (policy_to_update, True)
            except ServiceError as se:
                if se.code == "NoEtagMatch":
                    self.logger.warning(f"Could not update due to etag mismatch")
                ret = (policy_to_update, False)
            except Exception as e:
                self.logger.warning(f"Could not update due to error: {e}")
                ret = (policy_to_update, False)
        updated_policies.append(ret)
            

# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
#     logger = logging.getLogger('oci-policy')
#     logger.info(f"Policy Main")

#     a = PolicyAnalysis(None, False)
#     a.initialize_client("DEFAULT", False, False, True)
#     a.load_policies_from_client()

#     pol = a.get_policies_for_edit(["ocid1.policy.oc1..aaaaaaaahyfaqwlgcfa3umh7qvii5or2axu5zwbzrp6wozrfjahd57nxowwq","ocid1.policy.oc1..aaaaaaaalg77zmpk7sabowkklzd6dmpy5dfwumvkhckeodia3j2eob2nllza"])
#     for i, ed in enumerate(pol):
#         etag, policy = ed
#         policy.statements.append(f"allow group foo{i} to read object-family in compartment agregory")

#     time.sleep(8)
#     a.update_policies(pol)
#     logger.info(f"Policy: {pol}")
