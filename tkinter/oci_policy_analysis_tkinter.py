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
from threading import Lock, Thread

lock = Lock()
loaded = 0
to_load = 0

def progress_indicator(future):
    global lock, loaded, to_load

    # obtain the lock
    with lock:
        # Increase loaded
        loaded += 1

        # Figure completion
        comp_step = int(loaded / to_load * 100)
        logger.info(f"Completed {loaded} of {to_load} for a step of {comp_step}")

        # report progress
        #print(f'{future} completed',flush=True)
        #progressbar.set(comp_step)
        progressbar_val.set(comp_step)

 
class PolicyAnalysis:

    dynamic_group_statements = []
    service_statements = []
    regular_statements = []
    special_statements = []

    # Default threads
    threads = 5

    # tenancy_ocid, identity_client recursion
    def __init__(self, verbose: bool):
        # Create a logger
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
        self.logger = logging.getLogger('oci-policy-analysis-class')
        self.logger.info(f"Init of class")
        if verbose:
            self.logger.setLevel(logging.DEBUG)

    def initialize_client(self, profile: str, use_instance_principal: bool) -> bool:
        if use_instance_principal:
            self.logger.info(f"Using Instance Principal Authentication")
            try:
                signer = InstancePrincipalsSecurityTokenSigner()
                
                # Create the OCI Client to use
                self.identity_client = IdentityClient(config={}, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)
                self.tenancy_ocid = signer.tenancy_id
            except Exception as exc:
                self.logger.fatal(f"Unable to use IP Authentication: {exc}")
                return False 
        else:
            self.logger.info(f"Using Profile Authentication: {profile}")
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


    def load_policies_from_client(self, use_cache: bool, use_recursion: bool) -> bool:
        # Requirements
        # Logger (self)
        # IdentityClient (self)

        if use_cache:
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
            self.logger.info(f"---Starting Policy Load for tenant: {self.tenancy_ocid} with recursion {use_recursion} and {self.threads} threads---")

            # Load the policies
            # Start with list of compartments
            comp_list = []

            # Get root compartment into list
            root_comp = self.identity_client.get_compartment(compartment_id=self.tenancy_ocid).data 
            comp_list.append(root_comp)

            if use_recursion:
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

            self.logger.info(f'Loaded {len(comp_list)} Compartments.  {"Using recursion" if use_recursion else "No Recursion, only root-level policies"}')
            
            # We know the compartment count now - set up progress
            global loaded, to_load
            to_load = len(comp_list)

            with ThreadPoolExecutor(max_workers = self.threads, thread_name_prefix="thread") as executor:
                # results = executor.map(self.load_policies, comp_list)
                results = [executor.submit(self.load_policies, c) for c in comp_list]
                self.logger.info(f"Kicked off {self.threads} threads for parallel execution - adjust as necessary")

                for future in results:
                    future.add_done_callback(progress_indicator)

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
        
        # Return true to incidate success
        return True

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

def load_policy_analysis_thread():
    logger.info(f"Loading via cache: {use_cache.get()}")
    # Load class
    success = policy_analysis.load_policies_from_client(use_cache=use_cache.get(),
                                              use_recursion=True)
    
    if success:
        # Light up filter widgets
        entry_subj.config(state=tk.NORMAL)
        entry_loc.config(state=tk.NORMAL)
        entry_res.config(state=tk.NORMAL)
        entry_verb.config(state=tk.NORMAL)
        btn_update.config(state=tk.ACTIVE)

def load_policy_analysis_from_client():
    
    # Initialize client
    policy_analysis.initialize_client(profile.get(), 
                                      use_instance_principal=use_instance_principal.get())

    # Move Progress bar
    progressbar.step(2)

    #progressbar_val.set(comp_step)

    # Start background thread to load policies
    Thread(target=load_policy_analysis_thread).start()

    # Move Progress bar to completed
    progressbar_val.set(0.0)

    # Display
    update_output()

def select_instance_principal():
    # Update variable in class
    # Disable UI for selection of profile
    if use_instance_principal.get():
        logger.info("Using Instance Principal - disable profile")
        input_profile.config(state=tk.DISABLED)
    else:
        logger.info("Using Config")
        input_profile.config(state=tk.ACTIVE)



def update_output():

    # Grab from instance to local
    service_statements = policy_analysis.service_statements
    dynamic_group_statements = policy_analysis.dynamic_group_statements
    service_statements = policy_analysis.service_statements
    regular_statements = policy_analysis.regular_statements

    # Apply Filters
    subj_filter = entry_subj.get()
    verb_filter = entry_verb.get()
    resource_filter = entry_res.get()
    location_filter = entry_loc.get()

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

    if resource_filter:
        logger.info(f"Filtering resource: {resource_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

    if location_filter:
        logger.info(f"Filtering location: {location_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
        dynamic_group_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), dynamic_group_statements))
        service_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), service_statements))
        regular_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(), regular_statements))
        logger.info(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

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
    args = parser.parse_args()
    verbose = args.verbose

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




# Grab Profiles
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

window.rowconfigure(3, minsize=800, weight=1)
window.columnconfigure(0, minsize=800, weight=1)

frm_init = tk.Frame(window, relief=tk.RAISED, bd=2)
frm_filter = tk.Frame(window, relief=tk.RAISED, bd=2)
frm_output = tk.Frame(window, relief=tk.RAISED, bd=2)
frm_policy = tk.Frame(window, relief=tk.RAISED, bd=2)

# Inputs
use_instance_principal = tk.BooleanVar()
input_use_ip = ttk.Checkbutton(frm_init, text='Instance Principal', variable=use_instance_principal, command=select_instance_principal)
input_use_ip.grid(row=0, column=0, columnspan=2, sticky="ew", padx=25, pady=5)

# Profile drop-down
label_profile = tk.Label(master=frm_init, text="Choose Profile")
label_profile.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

profile = tk.StringVar(window)
profile.set(options[0]) 
input_profile = tk.OptionMenu(frm_init, profile, *options)
input_profile.grid(row=1, column=1, sticky="ew", padx=10, pady=5)

#Caching
use_cache = tk.BooleanVar()
input_cache = ttk.Checkbutton(frm_init, text='Use Cache', variable=use_cache)
input_cache.grid(row=0, column=2, columnspan=2, rowspan=2, sticky="ew", padx=25, pady=5)

# Buttons
#btn_init = tk.Button(frm_init, text="Initialize", command=initialize_client)
btn_load = tk.Button(frm_init, width=50, text="Load Policies", command=load_policy_analysis_from_client)
#btn_init.grid(row=1, column=0, sticky="ew", padx=5)
btn_load.grid(row=0, column=4, columnspan=2, rowspan=2, sticky="ew", padx=25)

# Progress Bar
progressbar_val = tk.IntVar()
progressbar = ttk.Progressbar(orient=tk.HORIZONTAL, length=400, mode="determinate", maximum=100,variable=progressbar_val)
progressbar.place(x=450, y=50)

# Filters
label_filter = tk.Label(master=frm_filter, text="Filters")
label_filter.grid(row=0, column=0, sticky="ew", columnspan=2, padx=5, pady=5)
btn_update = tk.Button(frm_filter, text="Update Filter", state=tk.DISABLED, command=update_output)
btn_update.grid(row=0, column=2, sticky="ew", columnspan=2, padx=5, pady=5)

label_subj = tk.Label(master=frm_filter, text="Subject")
label_subj.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
entry_subj = tk.Entry(master=frm_filter, state=tk.DISABLED)
entry_subj.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

label_verb = tk.Label(master=frm_filter, text="Verb")
label_verb.grid(row=1, column=2, sticky="ew", padx=5, pady=5)
entry_verb = tk.Entry(master=frm_filter, state=tk.DISABLED)
entry_verb.grid(row=1, column=3, sticky="ew", padx=5, pady=5)

label_res = tk.Label(master=frm_filter, text="Resource")
label_res.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
entry_res = tk.Entry(master=frm_filter, state=tk.DISABLED)
entry_res.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

label_loc = tk.Label(master=frm_filter, text="Location")
label_loc.grid(row=2, column=2, sticky="ew", padx=5, pady=5)
entry_loc = tk.Entry(master=frm_filter, state=tk.DISABLED)
entry_loc.grid(row=2, column=3, sticky="ew", padx=5, pady=5)

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
frm_init.grid(row=0, column=0, sticky="nsew")
frm_filter.grid(row=1, column=0, sticky="nsew")
frm_output.grid(row=2, column=0, sticky="nsew")
frm_policy.grid(row=3, column=0, sticky="nsew")

window.mainloop()