import tkinter as tk
import tkinter.ttk as ttk
from tkinter.filedialog import askopenfilename, asksaveasfilename

from oci import config
from oci.identity import IdentityClient
from oci.identity.models import Compartment
from oci import loggingingestion
from oci import pagination
from oci.retry import DEFAULT_RETRY_STRATEGY
from oci.exceptions import ConfigFileNotFound

from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.loggingingestion.models import PutLogsDetails, LogEntry, LogEntryBatch

import argparse
import json
import os
import datetime
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor

class PolicyAnalysis:

    dynamic_group_statements = []
    service_statements = []
    regular_statements = []
    special_statements = []

    # tenancy_ocid, identity_client recursion
    def __init__(self, verbose: bool):
        # Create a logger
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
        self.logger = logging.getLogger('oci-policy-analysis-class')
        self.logger.info(f"Init of class")
        if verbose:
            self.logger.setLevel(logging.DEBUG)

    def initialize_client(self, profile: str):
        self.logger.info(f"Using Profile Authentication: {profile}")
        try:
            self.config = config.from_file(profile_name=profile)
            self.logger.info(f'Using tenancy OCID from profile: {self.config["tenancy"]}')
            self.tenancy_ocid = self.config["tenancy"]

            # Create the OCI Client to use
            self.identity_client = IdentityClient(self.config, retry_strategy=DEFAULT_RETRY_STRATEGY)
        except ConfigFileNotFound as exc:
            self.logger.fatal(f"Unable to use Profile Authentication: {exc}")
        # Set up recursion
        self.recursion = True
        self.threads = 8

        self.logger.info(f"Recursion: {self.recursion}, Threads: {self.threads}")
       
    # Print Statement
    def print_statement(self, statement_tuple):
        a, b, c, d, e = statement_tuple
        self.logger.debug(f"Subject: {a}, Verb: {b}, Resource: {c}, Location: {d}, Condition: {e}")

    def parse_statement(self, statement, comp_string, policy):
        # Parse tuple and partition
        # (subject, verb, resource, location, condition)
        # Pass 1 - where condition
        # Pass 2 - group subject
        # Pass 3 - location
        # Pass 4 - verb and resource
        pass1 = statement.casefold().partition(" where ")
        condition = pass1[2]
        pass2a = pass1[0].partition("allow ")
        pass2b = pass2a[2].partition(" to ")
        subject = pass2b[0]
        pass3 = pass2b[2].partition(" in ")
        location = pass3[2]
        pass4 = pass3[0].partition(" ")
        verb = pass4[0]
        resource = pass4[2]

        # Location Update
        # If compartment name, use hierarchy, if id then leave alone
        if "compartment id" in location:
            pass
        elif "tenancy" in location:
            pass
        else:
            sub_comp = location.partition("compartment ")[2]
            if comp_string == "":
                # if root, then leave compartment alone
                # location = f"compartment {comp_name}"
                pass
            else:
                location = f"compartment {comp_string}:{sub_comp}"

        # Build tuple based on modified location
        statement_tuple = (subject, verb, resource, location, condition,
                        f"{comp_string}", policy.name, policy.id, policy.compartment_id, statement)
        return statement_tuple

    # Recursive Compartments / Policies
    def get_compartment_path(self, compartment: Compartment, level, comp_string) -> str:

        # Top level forces fall back through
        self.logger.debug(f"Compartment Name: {compartment.name} ID: {compartment.id} Parent: {compartment.compartment_id}") 
        if not compartment.compartment_id:
            self.logger.debug(f"Top of tree. Path is {comp_string}")
            return comp_string
        parent_compartment = self.identity_client.get_compartment(compartment_id=compartment.compartment_id).data    

        # Recurse until we get to top
        self.logger.debug(f"Recurse. Path is {comp_string}")
        return self.get_compartment_path(parent_compartment, level+1, compartment.name + "/" + comp_string)

    # Threadable policy loader - per compartment
    def load_policies(self, compartment: Compartment):
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

                # Root out "special" statements (endorse / define / as)
                if str.startswith(statement, "endorse") or str.startswith(statement, "admit") or str.startswith(statement, "define"):
                    # Special statement tuple
                    statement_tuple = (statement,
                                    f"{path}", policy.name, policy.id, policy.compartment_id)

                    self.special_statements.append(statement_tuple)
                    continue

                # Helper returns tuple with policy statement and lineage
                statement_tuple = self.parse_statement(
                    statement=statement,
                    comp_string=path,
                    policy=policy
                )

                if statement_tuple[0] is None or statement_tuple[0] == "":
                    self.logger.debug(f"****Statement {statement} resulted in bad tuple: {statement_tuple}")

                if "dynamic-group " in statement_tuple[0]:
                    self.dynamic_group_statements.append(statement_tuple)
                elif "service " in statement_tuple[0]:
                    self.service_statements.append(statement_tuple)
                else:
                    self.regular_statements.append(statement_tuple)

    def load_policies_from_client(self, from_cache: bool):
        # Requirements
        # Logger (self)
        # IdentityClient (self)

        if from_cache:
            self.logger.info(f"---Starting Policy Load for tenant: {self.tenancy_ocid} from cached files---")
            if os.path.isfile(f'./.policy-special-cache-{self.tenancy_ocid}.dat'):
                with open(f'./.policy-special-cache-{self.tenancy_ocid}.dat', 'r') as filehandle:
                    self.special_statements = json.load(filehandle)
            if os.path.isfile(f'./.policy-dg-cache-{self.tenancy_ocid}.dat'):
                with open(f'./.policy-dg-cache-{self.tenancy_ocid}.dat', 'r') as filehandle:
                    self.dynamic_group_statements = json.load(filehandle)
            if os.path.isfile(f'.policy-svc-cache-{self.tenancy_ocid}.dat'):
                with open(f'./.policy-svc-cache-{self.tenancy_ocid}.dat', 'r') as filehandle:
                    self.service_statements = json.load(filehandle)
            if os.path.isfile(f'.policy-statement-cache-{self.tenancy_ocid}.dat'):
                with open(f'./.policy-statement-cache-{self.tenancy_ocid}.dat', 'r') as filehandle:
                    self.regular_statements = json.load(filehandle)
        else:
            # If set from main() it is ok, otherwise take from function call
            self.logger.info(f"---Starting Policy Load for tenant: {self.tenancy_ocid} with recursion {self.recursion} and {self.threads} threads---")

            # Load the policies
            # Start with list of compartments
            comp_list = []

            # Get root compartment into list
            root_comp = self.identity_client.get_compartment(compartment_id=self.tenancy_ocid).data 
            comp_list.append(root_comp)

            if self.recursion:
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

            self.logger.info(f'Loaded {len(comp_list)} Compartments.  {"Using recursion" if self.recursion else "No Recursion, only root-level policies"}')
            with ThreadPoolExecutor(max_workers = self.threads, thread_name_prefix="thread") as executor:
                results = executor.map(self.load_policies, comp_list)
                self.logger.info(f"Kicked off {self.threads} threads for parallel execution - adjust as necessary")
            for res in results:
                self.logger.debug(f"Result: {res}")
            self.logger.info(f"---Finished Policy Load from client---")

            # Dump in local cache for later

            with open(f'.policy-special-cache-{self.tenancy_ocid}.dat', 'w') as filehandle:
                json.dump(self.special_statements, filehandle)
            with open(f'.policy-dg-cache-{self.tenancy_ocid}.dat', 'w') as filehandle:
                json.dump(self.dynamic_group_statements, filehandle)
            with open(f'.policy-svc-cache-{self.tenancy_ocid}.dat', 'w') as filehandle:
                json.dump(self.service_statements, filehandle)
            with open(f'.policy-statement-cache-{self.tenancy_ocid}.dat', 'w') as filehandle:
                json.dump(self.regular_statements, filehandle)

    def get_policy_counts(self):
        return (len(self.special_statements), len(self.regular_statements))

###############################################################################################################
# Main Functions
###############################################################################################################

def initialize_client():
    # Try to create everything needed from boxes
    #profile = input_profile.get()
    recursion = False
    threads = 0

    # Load class
    policy_analysis.initialize_client(profile.get())
    logger.info(f"initialized clients: {profile.get()}")

def load_policy_analysis_from_client():

    # Load class
    policy_analysis.load_policies_from_client(from_cache=use_cache.get())

    # Counts
    counts = policy_analysis.get_policy_counts()
    #logger.info(f"Loaded Policies: {counts[0]}")

    # Display
    update_output()

def select_instance_principal():
    # Update variable in class
    # Disable UI for selection of profile
    pass

def update_output():

    # Grab from instance to local
    service_statements = policy_analysis.service_statements
    dynamic_group_statements = policy_analysis.dynamic_group_statements
    service_statements = policy_analysis.service_statements
    regular_statements = policy_analysis.regular_statements

    # Apply Filters
    subj_filter = entry_subj.get()
    verb_filter = entry_verb.get()
    if subj_filter:
        logger.info(f"Filtering subject: {subj_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: subj_filter.casefold() in statement[0].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: subj_filter.casefold() in statement[0].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: subj_filter.casefold() in statement[0].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    if verb_filter:
        logger.info(f"Filtering verb: {verb_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    # if resource_filter:
    #     logger.info(f"Filtering resource: {resource_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    #     dynamic_group_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), dynamic_group_statements))
    #     service_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), service_statements))
    #     regular_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), regular_statements))
    #     logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    # if location_filter:
    #     logger.info(f"Filtering location: {location_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    #     dynamic_group_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), dynamic_group_statements))
    #     service_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), service_statements))
    #     regular_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), regular_statements))
    #     logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    # Clean output and Update Count
    label_loaded.config(text=f"Statements Shown: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    text_policies.delete(1.0,tk.END)

    # Dynamically add output
    if chk_show_special.get():
        logger.debug("========Summary Special==============")
        for index, statement in enumerate(policy_analysis.special_statements, start=1):
            logger.debug(f"Statement #{index}: {statement[0]} | Policy: {statement[2]}")
            text_policies.insert(tk.INSERT,f"Statement #{index}: {statement[0]} | Policy: {statement[2]}\n")

    if chk_show_service.get():
        logger.debug("========Service==============")
        for index, statement in enumerate(service_statements, start=1):
            logger.debug(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}")
            text_policies.insert(tk.INSERT,f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}\n")

    if chk_show_dynamic.get():
        logger.debug("========Dynamic Group==============")
        for index, statement in enumerate(dynamic_group_statements, start=1):
            logger.debug(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}")
            text_policies.insert(tk.INSERT,f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}\n")

    if chk_show_regular.get():
        logger.debug("========Dynamic Group==============")
        for index, statement in enumerate(regular_statements, start=1):
            logger.debug(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}{statement[6]}")
            text_policies.insert(tk.INSERT,f"Statement #{index}: {statement[9]} | Policy: {statement[5]}{statement[6]}\n")
        logger.info(f"Total Special statement in tenancy: {len(policy_analysis.special_statements)}")

########################################
# Main Code
# Pre-and Post-processing
########################################

if __name__ == "__main__":

    # Parse Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    # parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    # #parser.add_argument("-o", "--ocid", help="OCID of compartment (if not passed, will use tenancy OCID from profile)", default="TENANCY")
    # parser.add_argument("-sf", "--subjectfilter", help="Filter all statement subjects by this text")
    # parser.add_argument("-vf", "--verbfilter", help="Filter all verbs (inspect,read,use,manage) by this text")
    # parser.add_argument("-rf", "--resourcefilter", help="Filter all resource (eg database or stream-family etc) subjects by this text")
    # parser.add_argument("-lf", "--locationfilter", help="Filter all location (eg compartment name) subjects by this text")
    # parser.add_argument("-r", "--recurse", help="Recursion or not (default True)", action="store_true")
    # parser.add_argument("-c", "--usecache", help="Load from local cache (if it exists)", action="store_true")
    # parser.add_argument("-w", "--writejson", help="Write filtered output to JSON", action="store_true")
    # parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    # parser.add_argument("-lo", "--logocid", help="Use an OCI Log - provide OCID")
    # parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=1)
    args = parser.parse_args()
    verbose = args.verbose
    # use_cache = args.usecache
    # #ocid = args.ocid
    # profile = args.profile
    # threads = args.threads
    # sub_filter = args.subjectfilter
    # verb_filter = args.verbfilter
    # resource_filter = args.resourcefilter
    # location_filter = args.locationfilter
    # recursion = args.recurse
    # write_json_output = args.writejson
    # use_instance_principals = args.instanceprincipal
    # log_ocid = None if not args.logocid else args.logocid

    # Main Logger
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger('oci-policy-analysis-main')

    if verbose:
        logger.setLevel(logging.DEBUG)

    # Create the class
    policy_analysis = PolicyAnalysis(verbose)
    

    # Update Logging Level
    if verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logging.INFO)


    # if use_instance_principals:
    #     logger.info("Using Instance Principal Authentication")
    #     signer = InstancePrincipalsSecurityTokenSigner()
    #     identity_client = IdentityClient(config={}, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
    #     loggingingestion_client = loggingingestion.LoggingClient(config={}, signer=signer)
    #     tenancy_ocid = signer.tenancy_id
    # else:
    #     # Use a profile (must be defined)
    #     logger.info(f"Using Profile Authentication: {profile}")
    #     try:
    #         config = config.from_file(profile_name=profile)
    #         logger.info(f'Using tenancy OCID from profile: {config["tenancy"]}')
    #         tenancy_ocid = config["tenancy"]

    #         # Create the OCI Client to use
    #         identity_client = IdentityClient(config, retry_strategy=DEFAULT_RETRY_STRATEGY)
    #         loggingingestion_client = loggingingestion.LoggingClient(config)
    #     except ConfigFileNotFound as exc:
    #         logger.fatal(f"Unable to use Profile Authentication: {exc}")
    #         exit(1)


    # # Print Special
    # entries = []
    # logger.info("========Summary Special==============")
    # for index, statement in enumerate(special_statements, start=1):
    #     logger.info(f"Statement #{index}: {statement[0]} | Policy: {statement[2]}")
    #     entries.append(LogEntry(id=str(uuid.uuid1()),
    #                             data=f"Statement #{index}: {statement}"))
    # logger.info(f"Total Special statement in tenancy: {len(special_statements)}")

    # # Create Log Batch
    # special_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.utcnow(),
    #                               source="oci-policy-analysis",
    #                               type="special-statement",
    #                               entries=entries)

    # # Print Dynamic Groups
    # entries = []
    # logger.info("========Summary DG==============")
    # for index, statement in enumerate(dynamic_group_statements, start=1):
    #     logger.info(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}")
    #     entries.append(LogEntry(id=str(uuid.uuid1()),
    #                             data=f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}"))
    # logger.info(f"Total Service statement in tenancy: {len(dynamic_group_statements)}")

    # # Create Log Batch
    # dg_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.utcnow(),
    #                          source="oci-policy-analysis",
    #                          type="dynamic-group-statement",
    #                          entries=entries)

    # # Print Service
    # entries = []
    # logger.info("========Summary SVC==============")
    # for index, statement in enumerate(service_statements, start=1):
    #     logger.info(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}")
    #     entries.append(LogEntry(id=str(uuid.uuid1()),
    #                             data=f"Statement #{index}: {statement[9]} | Policy: {statement[5]}/{statement[6]}"))
    # logger.info(f"Total Service statement in tenancy: {len(service_statements)}")

    # # Create Log Batch
    # service_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.utcnow(),
    #                               source="oci-policy-analysis",
    #                               type="service-statement",
    #                               entries=entries)

    # # Print Regular
    # entries = []
    # logger.info("========Summary Reg==============")
    # for index, statement in enumerate(regular_statements, start=1):
    #     logger.info(f"Statement #{index}: {statement[9]} | Policy: {statement[5]}{statement[6]}")
    #     entries.append(LogEntry(id=str(uuid.uuid1()),
    #                             data=f"Statement #{index}: {statement[9]} | Policy: {statement[5]}{statement[6]}"))
    # logger.info(f"Total Regular statements in tenancy: {len(regular_statements)}")

    # # Create Log Batch
    # regular_batch = LogEntryBatch(defaultlogentrytime=datetime.datetime.now(datetime.timezone.utc),
    #                               source="oci-policy-analysis",
    #                               type="regular-statement",
    #                               entries=entries)


    # # To output file if required
    # if write_json_output:
    #     # Empty Dictionary
    #     statements_list = []
    #     for i, s in enumerate(special_statements):
    #         statements_list.append({"type": "special", "statement": s[0],
    #                                 "lineage": {"policy-compartment-ocid": s[4], "policy-relative-hierarchy": s[1],
    #                                             "policy-name": s[2], "policy-ocid": s[3]}
    #                                 })
    #     for i, s in enumerate(dynamic_group_statements):
    #         statements_list.append({"type": "dynamic-group", "subject": s[0], "verb": s[1],
    #                                 "resource": s[2], "location": s[3], "conditions": s[4],
    #                                 "lineage": {"policy-compartment-ocid": s[8], "policy-relative-hierarchy": s[5],
    #                                             "policy-name": s[6], "policy-ocid": s[7], "policy-text": s[9]}
    #                                 })
    #     for i, s in enumerate(service_statements):
    #         statements_list.append({"type": "service", "subject": s[0], "verb": s[1],
    #                                 "resource": s[2], "location": s[3], "conditions": s[4],
    #                                 "lineage": {"policy-compartment-ocid": s[8], "policy-relative-hierarchy": s[5],
    #                                             "policy-name": s[6], "policy-ocid": s[7], "policy-text": s[9]}
    #                                 })
    #     for i, s in enumerate(regular_statements):
    #         statements_list.append({"type": "regular", "subject": s[0], "verb": s[1],
    #                                 "resource": s[2], "location": s[3], "conditions": s[4],
    #                                 "lineage": {"policy-compartment-ocid": s[8], "policy-relative-hierarchy": s[5],
    #                                             "policy-name": s[6], "policy-ocid": s[7], "policy-text": s[9]}
    #                                 })
    #     # Serializing json
    #     json_object = json.dumps(statements_list, indent=2)

    #     # Writing to sample.json
    #     with open(f"policyoutput-{tenancy_ocid}.json", "w") as outfile:
    #         outfile.write(json_object)
    # logger.debug(f"-----Complete--------")

config2 = config.from_file()
logger.info(f"Config: {config2}")

options = []
# string to search in file
with open(r'/Users/agregory/.oci/config', 'r') as fp:
    # read all lines using readline()
    lines = fp.readlines()
    for row in lines:
        if row.find('[') != -1 and row.find(']') != -1:
            print('string exists in file')
            options.append(row[1:-2])
logger.info(f"Profiles: {options}")
# UI Componentry

window = tk.Tk()
window.title("Policy Analysis")

window.rowconfigure(2, minsize=800, weight=1)
window.columnconfigure(0, minsize=800, weight=1)

frm_buttons = tk.Frame(window, relief=tk.RAISED, bd=2)
frm_output = tk.Frame(window, relief=tk.RAISED, bd=2)
frm_policy = tk.Frame(window, relief=tk.RAISED, bd=2)

# Inputs
label_profile = tk.Label(master=frm_buttons, text="Choose Profile")
label_profile.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

# Profile drop-down
profile = tk.StringVar(window)
profile.set(options[0]) 
input_profile = tk.OptionMenu(frm_buttons, profile, *options)
input_profile.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

#Caching
use_cache = tk.BooleanVar()
input_cache = ttk.Checkbutton(frm_buttons, text='Use Cache', variable=use_cache)
input_cache.grid(row=0, column=2, sticky="ew", padx=5, pady=5)

# Buttons
btn_init = tk.Button(frm_buttons, text="Initialize", command=initialize_client)
btn_load = tk.Button(frm_buttons, text="Load Policies", command=load_policy_analysis_from_client)
btn_init.grid(row=1, column=0, sticky="ew", padx=5)
btn_load.grid(row=1, column=1, sticky="ew", padx=5)

# Filters
label_filter = tk.Label(master=frm_buttons, text="Filters")
label_filter.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
btn_update = tk.Button(frm_buttons, text="Update Filter", command=update_output)
btn_update.grid(row=1, column=2, sticky="ew", padx=5, pady=5)

label_subj = tk.Label(master=frm_buttons, text="Subject")
label_subj.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
entry_subj = tk.Entry(master=frm_buttons)
entry_subj.grid(row=2, column=2, sticky="ew", padx=5, pady=5)

label_verb = tk.Label(master=frm_buttons, text="Verb")
label_verb.grid(row=2, column=3, sticky="ew", padx=5, pady=5)
entry_verb = tk.Entry(master=frm_buttons)
entry_verb.grid(row=2, column=4, sticky="ew", padx=5, pady=5)


# Output Show
chk_show_special = tk.BooleanVar()
chk_show_dynamic = tk.BooleanVar()
chk_show_service = tk.BooleanVar()
chk_show_regular = tk.BooleanVar()
show_special = ttk.Checkbutton(frm_output, text='Show Special', variable=chk_show_special, command=update_output)
show_dynamic = ttk.Checkbutton(frm_output, text='Show Dynamic', variable=chk_show_dynamic, command=update_output)
show_service = ttk.Checkbutton(frm_output, text='Show Service', variable=chk_show_service, command=update_output)
show_regular = ttk.Checkbutton(frm_output, text='Show Regular', variable=chk_show_regular, command=update_output)
show_special.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
show_dynamic.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
show_service.grid(row=3, column=2, sticky="ew", padx=5, pady=5)
show_regular.grid(row=3, column=3, sticky="ew", padx=5, pady=5)

# Policy Window

label_loaded = tk.Label(master=frm_policy, text="Statements: ")
label_loaded.pack()

text_policies = tk.Text(master=frm_policy)
#text_policies.grid(row=1, column=0, columnspan=3, sticky="ewsn", padx=5, pady=5)
text_policies.pack(expand=True, fill='both', side=tk.BOTTOM)

# Insert to main window
frm_buttons.grid(row=0, column=0, sticky="nsew")
frm_output.grid(row=1, column=0, sticky="nsew")
frm_policy.grid(row=2, column=0, sticky="nsew")

window.mainloop()