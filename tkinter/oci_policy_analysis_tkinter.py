# UI
import tkinter as tk
#import tkinter.ttk as ttk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

# Python
import json
from pathlib import Path
import os
import logging
from threading import Lock, Thread
import time
# 3rd Party
import pyperclip
import argparse

# Local Class
from dynamic import DynamicGroupAnalysis
from policy import PolicyAnalysis
from progress import Progress

###############################################################################################################
# Global variables and Helper
###############################################################################################################

progressbar_val = None

###############################################################################################################
# Main Functions (UI and helper)
###############################################################################################################

def load_policy_analysis_thread():
    # Load Statements
    policy_analysis.load_policies_from_client()

def load_policy_analysis_from_client():
    
    # Initialize client
    policy_analysis.initialize_client(profile=profile.get(),
                                      use_instance_principal=use_instance_principal.get(),
                                      use_cache=use_cache.get(),
                                      use_recursion=use_recursion.get())

    # Start background thread to load policies
    bg_thread = Thread(target=load_policy_analysis_thread)
    bg_thread.start()

    # Load Dynamic Groups
    dyn_group_analysis.initialize_client(profile.get(), 
                                      use_instance_principal=use_instance_principal.get())
    dyn_group_analysis.load_all_dynamic_groups(use_cache=use_cache.get())

    # if success:
    # Light up filter widgets
    entry_subj.config(state=tk.NORMAL)
    entry_loc.config(state=tk.NORMAL)
    entry_res.config(state=tk.NORMAL)
    entry_verb.config(state=tk.NORMAL)
    entry_policy_loc.config(state=tk.NORMAL)
    entry_condition.config(state=tk.NORMAL)
    btn_update.config(state=tk.ACTIVE)
    btn_clear.config(state=tk.ACTIVE)
    btn_copy.config(state=tk.ACTIVE)
    # input_my_user.config(state=tk.ACTIVE)
    # input_my_compartment.config(state=tk.ACTIVE)

    # Dynamic Groups
    dg_entry_ocid.config(state=tk.NORMAL)
    dg_entry_type.config(state=tk.NORMAL)
    dg_btn_clear.config(state=tk.ACTIVE)
    dg_btn_update.config(state=tk.ACTIVE)

    # Display populate
    update_output(default_open=False)
    update_output_dg()

def select_instance_principal():
    '''Update variable in class'''
    # Disable UI for selection of profile
    if use_instance_principal.get():
        logger.info("Using Instance Principal - disable profile")
        input_profile.config(state=tk.DISABLED)
    else:
        logger.info("Using Config")
        input_profile.config(state=tk.ACTIVE)

def clear_filters():
    '''Clears the Policy filters and updates the UI'''
    logger.info(f"Clearing Filters")
    entry_subj.delete(0, tk.END)
    entry_verb.delete(0, tk.END)
    entry_res.delete(0, tk.END)
    entry_loc.delete(0, tk.END)
    entry_condition.delete(0, tk.END)
    entry_policy_loc.delete(0, tk.END)
    # show_only_my_compartment.set(False)
    # show_only_my_user.set(False)

    # Update the output
    update_output()

def clear_filters_dg():
    '''Clears the Dynamic Group Filters and updates the UI'''
    logger.info(f"Clearing DG Filters")
    dg_entry_type.delete(0, tk.END)
    dg_entry_ocid.delete(0, tk.END)

    # Update the output
    update_output_dg()

def copy_selected():
    selections = tree_policies.selection()
    logger.debug(f"Copy selection: {selections}")
    copied_string = ""
    for it,row in enumerate(selections):
        if it>0:
            # Add a newline if multi row
            copied_string += "\n"
        logger.debug(f"Copy row: {row}")

        values = tree_policies.item(row, 'text')  # get values for each selected row
        #values = tree_policies.item(row)  # get values for each selected row

        for item in values:
            copied_string += f"{item}"

    # Grab from char 13 onward - jsut the value
    pyperclip.copy(copied_string[12:])
    logger.info(f"Copied value: {copied_string[12:]}")

def update_output(default_open: bool = False):

    # Apply Filters
    regular_statements_filtered = policy_analysis.filter_policy_statements(subj_filter=entry_subj.get(),
                                                                           verb_filter=entry_verb.get(),
                                                                           resource_filter=entry_res.get(),
                                                                           location_filter=entry_loc.get(),
                                                                           hierarchy_filter=entry_policy_loc.get(),
                                                                           condition_filter=entry_condition.get())

    # Clean output and Update Count
    label_loaded.config(text=f"Statements Loaded (With Filter): {len(regular_statements_filtered)} statements")
    for row in tree_policies.get_children():
        tree_policies.delete(row)

    # Dynamically add output
    if chk_show_special.get():

        # Add to tree
        special_tree = tree_policies.insert("", tk.END, text="Special Statements")
        logger.debug("========Summary Special==============")
        for index, statement in enumerate(policy_analysis.special_statements, start=1):
            logger.debug(f"Statement #{index}: {statement[0]} | Policy: {statement[2]}")
            # Add with lineage
            special_tree_policy = tree_policies.insert(special_tree, tk.END, open=default_open, text=f"Statement : {statement[0]}")
            tree_policies.insert(special_tree_policy, tk.END, text=f'Compartment: {f"(Root)" if not statement[1] else statement[1]}',iid="sp"+str(index)+"c")
            tree_policies.insert(special_tree_policy, tk.END, text=f"Policy Name: {statement[2]}",iid="sp"+str(index)+"n")
            tree_policies.insert(special_tree_policy, tk.END, text=f"Policy OCID: {statement[3]}",iid="sp"+str(index)+"o")

    # Combined UI Flow
    if chk_show_service.get():
        logger.debug("========Service==============")
        service_tree = tree_policies.insert("", tk.END, text="Service Statements")
    if chk_show_dynamic.get():
        logger.debug("========Dynamic Group==============")
        dynamic_tree = tree_policies.insert("", tk.END, text="Dynamic Group Statements")    
    if chk_show_regular.get():
        logger.debug("========Regular==============")
        regular_tree = tree_policies.insert("", tk.END, text="Regular Statements", open=True)
        any_tree = tree_policies.insert("", tk.END, text="Any User/Group Statements", open=True)
    if verbose:
        logger.debug("========Invalid==============")
        invalid_tree = tree_policies.insert("", tk.END, text="Invalid Statements", open=True)

    # Combined Iterate
    for index, statement in enumerate(regular_statements_filtered, start=1):
        
        logger.debug(f"Statement #{index}: {statement[4]} | Policy: {statement[3]}{statement[0]}")
        # Check type
        if chk_show_dynamic.get() and (statement[6] == "dynamic-group" or statement[6] == "dynamicgroup"):
            tree_to_use = dynamic_tree
        elif chk_show_service.get() and statement[6] == "service":
            tree_to_use = service_tree
        elif chk_show_regular.get() and (statement[6] == "any-user" or statement[6] == "any-group"):
            tree_to_use = any_tree
        elif not statement[5]:
            tree_to_use = invalid_tree
            if not verbose:
                continue
        elif chk_show_regular.get() and statement[6] == "group":
            tree_to_use = regular_tree
        else:
            logger.debug(f"Not showing statement {index}: {statement[4]}")
            continue

        tree_policy = tree_policies.insert(tree_to_use, tk.END, text=f"Statement : {statement[4]}")
        # Details (Comp, Pol)
        tree_policies.insert(tree_policy, tk.END, open=default_open, text=f'Compartment: {f"(Root)" if not statement[3] else statement[3]}',iid="r"+str(index)+"c")
        tree_policies.insert(tree_policy, tk.END, open=default_open, text=f"Policy Name: {statement[0]}",iid="r"+str(index)+"n")
        tree_policies.insert(tree_policy, tk.END, open=default_open, text=f"Policy OCID: {statement[1]}",iid="r"+str(index)+"o")
        if statement[13] != "":
            tree_policies.insert(tree_policy, tk.END, open=default_open, text=f"Conditions: {statement[13]}",iid="r"+str(index)+"co")
        if statement[14] != "":
            tree_policies.insert(tree_policy, tk.END, open=default_open, text=f"Comments: {statement[14]}",iid="r"+str(index)+"op")

        # Additional Info if DG
        if statement[6] == "dynamic-group" or statement[6] == "dynamicgroup":
            dgs = dyn_group_analysis.dynamic_groups
            for dg in dgs:
                #logger.info(f"DG: {dg[0]} Subject: {statement[7]}")
                if dg[0].casefold() in statement[7].casefold():
                    # If the DG is in the DG List, print parts of it
                    tree_policies.insert(tree_policy, tk.END, text=f"Dynamic Group matching rules: {dg[2]}")

def update_output_dg(default_open: bool = False):
    dynamic_groups = dyn_group_analysis.dynamic_groups  
    regular_statements = policy_analysis.regular_statements
    dynamic_groups_filtered = []
    dg_type_filter = dg_entry_type.get()
    split_dg_type_filter = dg_type_filter.split(sep='|')
    # logger.info(f"Type filter length: {len(split_dg_type_filter)}")

    # logger.info(f"DG: {split_dg_type_filter}. Before: {len(dynamic_groups)} Dynamic Groups")
    # for filt in split_dg_type_filter:
    #     dynamic_groups_filtered.extend(list(filter(lambda statement: filt.casefold() in statement[7].casefold(), dynamic_groups)))
    # logger.info(f"DG: {len(dynamic_groups_filtered)} Dynamic Groups")

    # dg_tree = tree_policies.insert("", tk.END, text="Special Statements")

    # Clean output and Update Count
    #label_loaded.config(text=f"Statements Loaded (With Filter): {len(regular_statements_filtered)} statements")
    for row in tree_dg.get_children():
        tree_dg.delete(row)

    logger.debug("========Summary DG==============")
    for index, dg in enumerate(dynamic_groups, start=1):
        logger.debug(f"DG #{index}: {dg[0]} | Rules: {dg[3]}")
        # dg_detail = tree_dg.insert('', tk.END, text=f'Name: {dg[0]} {"(Not in Use)" if not dg[4] else ""}')
        dg_detail = tree_dg.insert('', tk.END, text="Dynamic Group Name", values=(f'{dg[0]} {"(Not in Use)" if not dg[4] else ""}'))
        # tree_dg.insert(dg_detail, tk.END, text=f"ID: {dg[1]}")
        tree_dg.insert(dg_detail, tk.END, text="OCID", values=(dg[1]))
        dg_rule_detail = tree_dg.insert(dg_detail, tk.END, text="Matching Rule", values=(dg[2]))
        for rule in dg[3]:
            # tree_dg.insert(dg_rule_detail, tk.END, text=f"Rule: {rule}")
            tree_dg.insert(dg_rule_detail, tk.END, text="Rule Component", values=(f"{rule}"))
        # Show Policies using this DG
        for statement in regular_statements:
            if dg[0].casefold() == statement[7].casefold():
                dg_rule_statement_detail = tree_dg.insert(dg_rule_detail, tk.END, text=f"Policy Referenced", values=(f'{statement[3] if statement[3] else "(Root)/"}{statement[0]}'))
                logger.info(f"Statement[4]: {statement[4]}")
                tree_dg.insert(dg_rule_statement_detail, tk.END, text="Policy Statement",values=[statement[4]])

def update_load_options():
    # Control the load button
    if use_cache.get():
        # Use Cache
        btn_load.config(text="Load tenancy policies from cached values on disk")
        input_recursion.config(state=tk.DISABLED)
    elif use_recursion.get():
        # Load recursively
        input_cache.config(state=tk.DISABLED)
        btn_load.config(text="Load policies from all compartments")
    else:
        input_cache.config(state=tk.ACTIVE)
        input_recursion.config(state=tk.ACTIVE)
        btn_load.config(text="Load policies from ROOT compartment only")

# def update_show_my_details():
#     if show_only_my_user.get():
#         # Update the filter for me and re-run
#         entry_subj.delete(0,tk.END)
#         logger.info(f"Loading groups: {policy_analysis.tenancy_ocid} : {policy_analysis.config["user"]}")
#         # Load my groups
#         idc = policy_analysis.identity_client
#         # my_groups = idc.list_user_group_memberships(
#         #     compartment_id=policy_analysis.tenancy_ocid,
#         #     #user_id=policy_analysis.config["user"]
#         # ).data        
#         my_groups = idc.list_groups(
#             compartment_id=policy_analysis.tenancy_ocid,
#             #user_id=policy_analysis.config["user"]
#         ).data
#         for g in my_groups:
#             logger.info(f"Group: {g.name}")
#             my_groups = idc.list_user_group_memberships(
#                 compartment_id=policy_analysis.tenancy_ocid,
#                 group_id=g.id
#             ).data 
#             for ug in my_groups:
#                 logger.info(f"User Group: {ug.user_id} / {ug.group_id}")
#         entry_subj.insert(0,"cloud-engineering-users|some-group")
#         update_output()

#     if show_only_my_compartment.get():
#         entry_loc.delete(0,tk.END)
#         entry_loc.insert(0,"agregory")
#         update_output()

def analyze_dynamic_group():
    # Get name of DG from policy
    selections = tree_policies.selection()
    logger.debug(f"DG selection: {selections}")
    copied_string = ""
    for it,row in enumerate(selections):
        logger.debug(f"DG row: {row}")
        values = tree_policies.item(row, 'text')  # get values for each selected row

        for item in values:
            copied_string += f"{item}"

    logger.info(f"Called Dynamic Group analysis: {copied_string}")

    # Parse Statement Again

def run_dynamic_group_inuse_analysis():
    # Set Statements
    dyn_group_analysis.set_statements(policy_analysis.regular_statements)
    # Run the anlaysis
    dyn_group_analysis.run_dg_in_use_analysis()

    update_output_dg()
    logger.info(f"Ran DG In Use Analysis from UI")

def run_dynamic_group_ocid_analysis():
    # Set Statements
    dyn_group_analysis.set_statements(policy_analysis.regular_statements)
    # Run the anlaysis
    dyn_group_analysis.run_deep_analysis()

    update_output_dg()
    logger.info(f"Ran DG OCID Analysis from UI")

# Get the progress value back into UI scope
def update_progress():
    #global progressbar_val
    progressbar_val.set(progress.progressbar_val)
    logger.debug(f"Progress: {progressbar_val.get()}")

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

    # Update Logging Level
    if verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logging.INFO)

    # Grab Profiles
    profile_list = []
    # string to search in file
    try:
        with open(Path.home() / ".oci" / "config", 'r') as fp:
            # read all lines using readline()
            lines = fp.readlines()
            for row in lines:
                if row.find('[') != -1 and row.find(']') != -1:
                    profile_list.append(row[1:-2])
    except FileNotFoundError as e:
        logger.warning(f"Config File not found, must use instance principal: {e}")
        profile_list.append("[NONE]")
    logger.info(f"Profiles: {profile_list}")

    # UI Componentry

    window = tk.Tk()
    window.title("Policy and Dynamic Group Analysis")
    
    # Main Window has 2 rows, top and bottom
    # Top is inputs to load policies
    # Bottom is tabbed display
    window.rowconfigure(2, minsize=800, weight=1)
    window.columnconfigure(0, minsize=800, weight=1)

    # Tab Control (Bottom)
    # User tab - about current user (or search another)
    tab_control = ttk.Notebook(window)
    tab_policy = ttk.Frame(tab_control)
    tab_dg = ttk.Frame(tab_control)

    tab_control.add(tab_policy, text='Policy View')
    tab_control.add(tab_dg, text='Dynamic Groups')

    # Frames
    frm_init = ttk.Frame(window, borderwidth=2)
    frm_policy_top = ttk.Frame(tab_policy, borderwidth=2)
    frm_policy_bottom = ttk.Frame(tab_policy, borderwidth=2)
    frm_filter = ttk.Frame(frm_policy_top, borderwidth=2)
    frm_output = ttk.Frame(frm_policy_top, borderwidth=2)
    frm_actions = ttk.Frame(frm_policy_top, borderwidth=2)
    frm_policy = ttk.Frame(frm_policy_bottom, borderwidth=2)
    frm_dyn_group_filter = ttk.Frame(tab_dg, borderwidth=2)
    frm_dyn_group_actions = ttk.Frame(tab_dg, borderwidth=2)
    frm_dyn_group_output = ttk.Frame(tab_dg, borderwidth=2)

    # Inputs
    use_instance_principal = tk.BooleanVar()
    input_use_ip = ttk.Checkbutton(frm_init, text='Instance Principal', variable=use_instance_principal, command=select_instance_principal)
    input_use_ip.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=3)

    # Profile drop-down
    label_profile = tk.Label(master=frm_init, text="Choose Profile")
    label_profile.grid(row=1, column=0, sticky="ew", padx=10, pady=3)

    # If no profiles, force instance
    profile = tk.StringVar(window)
    profile.set(profile_list[0]) 
    input_profile = ttk.OptionMenu(frm_init, profile, *profile_list)
    if "NONE" in profile_list[0]:
        use_instance_principal.set(True)
        input_profile.config(state=tk.DISABLED)
    input_profile.grid(row=1, column=1, sticky="ew", padx=10, pady=3)

    #Caching
    use_cache = tk.BooleanVar()
    input_cache = ttk.Checkbutton(frm_init, text='Use Cache?', variable=use_cache, command=update_load_options)
    input_cache.grid(row=0, column=2, columnspan=2, sticky="ew", padx=25, pady=3)

    # Recursion
    use_recursion = tk.BooleanVar()
    input_recursion= ttk.Checkbutton(frm_init, text='Recursion?', variable=use_recursion, command=update_load_options)
    input_recursion.grid(row=1, column=2, columnspan=2, sticky="ew", padx=25, pady=3)

    # Init Button
    btn_load = ttk.Button(frm_init, width=50, text="Load policies from ROOT compartment only", command=load_policy_analysis_from_client)
    btn_load.grid(row=0, column=4, columnspan=2, rowspan=2, sticky="ew", padx=25)

    # Progress Bar
    # global progressbar_val
    progressbar_val = tk.IntVar()
    progressbar = ttk.Progressbar(orient=tk.HORIZONTAL, length=400, mode="determinate", maximum=100,variable=progressbar_val)
    progressbar.place(x=450, y=50)

    # Filters
    label_filter = tk.Label(master=frm_filter, text="Filters (Each filter supports | as OR) - Policy Syntax: allow <subject> to <verb> <resource> in <location> where <conditions>")
    label_filter.grid(row=0, column=0, sticky="ew", columnspan=4, padx=5, pady=3)

    label_subj = ttk.Label(master=frm_filter, text="Subject\n(group name)")
    label_subj.grid(row=1, column=0, sticky="ew", padx=5, pady=3)
    entry_subj = ttk.Entry(master=frm_filter, state=tk.DISABLED, width=50)
    entry_subj.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

    label_verb = ttk.Label(master=frm_filter, text="Verb\n(inspect/read/use/manage)")
    label_verb.grid(row=1, column=2, sticky="ew", padx=5, pady=3)
    entry_verb = ttk.Entry(master=frm_filter, state=tk.DISABLED, width=50)
    entry_verb.grid(row=1, column=3, sticky="ew", padx=5, pady=3)

    label_res = ttk.Label(master=frm_filter, text="Resource\n(name/family)")
    label_res.grid(row=2, column=0, sticky="ew", padx=5, pady=3)
    entry_res = ttk.Entry(master=frm_filter, state=tk.DISABLED, width=50)
    entry_res.grid(row=2, column=1, sticky="ew", padx=5, pady=3)

    label_loc = ttk.Label(master=frm_filter, text="Location\n(within statement)")
    label_loc.grid(row=2, column=2, sticky="ew", padx=5, pady=3)
    entry_loc = ttk.Entry(master=frm_filter, state=tk.DISABLED)
    entry_loc.grid(row=2, column=3, sticky="ew", padx=5, pady=3)

    label_policy_loc = ttk.Label(master=frm_filter, text="Compartment\n(policy location)")
    label_policy_loc.grid(row=3, column=0, sticky="ew", padx=5, pady=3)
    entry_policy_loc = ttk.Entry(master=frm_filter, state=tk.DISABLED, width=50)
    entry_policy_loc.grid(row=3, column=1, sticky="ew", padx=5, pady=3)
   
    label_condition = ttk.Label(master=frm_filter, text="Conditions\n(where clause)")
    label_condition.grid(row=3, column=2, sticky="ew", padx=5, pady=3)
    entry_condition = ttk.Entry(master=frm_filter, state=tk.DISABLED, width=50)
    entry_condition.grid(row=3, column=3, sticky="ew", padx=5, pady=3)

    btn_update = ttk.Button(frm_filter, text="Update Filter", state=tk.DISABLED, command=update_output)
    btn_update.grid(row=4, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
    btn_clear = ttk.Button(frm_filter, text="Clear Filters", state=tk.DISABLED, command=clear_filters)
    btn_clear.grid(row=4, column=2, columnspan=2, sticky="ew", padx=5, pady=3)

    # Show my permissions - essentially a filter on my groups or location
    # show_only_my_user = tk.BooleanVar()
    # show_only_my_compartment = tk.BooleanVar()
    # input_my_user = ttk.Checkbutton(frm_filter, text='Show My Policies', variable=show_only_my_user, state=tk.DISABLED, command=update_show_my_details)
    # input_my_user.grid(row=3, column=0, columnspan=2, sticky="ew", padx=25, pady=3)
    # input_my_compartment = ttk.Checkbutton(frm_filter, text='Show My Compartment', variable=show_only_my_compartment, state=tk.DISABLED, command=update_show_my_details)
    # input_my_compartment.grid(row=3, column=2, columnspan=2, sticky="ew", padx=25, pady=3)


    # Output Show
    label_loaded = ttk.Label(master=frm_output, text="Statements Loaded (No Filter): ")
    label_loaded.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
    chk_show_special = tk.BooleanVar()
    chk_show_dynamic = tk.BooleanVar()
    chk_show_service = tk.BooleanVar()
    chk_show_resource = tk.BooleanVar()
    chk_show_regular = tk.BooleanVar(value=True)
    show_special = ttk.Checkbutton(frm_output, text='Show Special', variable=chk_show_special, command=update_output)
    show_dynamic = ttk.Checkbutton(frm_output, text='Show Dynamic', variable=chk_show_dynamic, command=update_output)
    show_service = ttk.Checkbutton(frm_output, text='Show Service', variable=chk_show_service, command=update_output)
    show_resource = ttk.Checkbutton(frm_output, text='Show Resource', variable=chk_show_resource, command=update_output)
    show_regular = ttk.Checkbutton(frm_output, text='Show Regular', variable=chk_show_regular, command=update_output)
    show_special.grid(row=0, column=2, sticky="ew", padx=15, pady=3)
    show_dynamic.grid(row=0, column=3, sticky="ew", padx=15, pady=3)
    show_service.grid(row=0, column=4, sticky="ew", padx=15, pady=3)
    show_resource.grid(row=0, column=5, sticky="ew", padx=15, pady=3)
    show_regular.grid(row=0, column=6, sticky="ew", padx=15, pady=3)

    # Policy Window

    btn_copy = ttk.Button(master=frm_output, text="Copy Selected", state=tk.DISABLED, command=copy_selected)
    btn_copy.grid(row=0, column=7, sticky="ew", padx=5, pady=3)    
    
    # Define dg button but don't place it
    btn_dg = ttk.Button(master=frm_actions, text="Analyze Dynamic Group", state=tk.ACTIVE, command=analyze_dynamic_group)

    # Dynamic Groups Tab

    # Filters
    dg_label_filter = ttk.Label(master=frm_dyn_group_filter, text="Filters (Each filter supports | as OR) - Dynamic Group has Name and matching statements")
    dg_label_filter.grid(row=0, column=0, sticky="ew", columnspan=4, padx=5, pady=3)

    dg_label_type = ttk.Label(master=frm_dyn_group_filter, text="Statement type")
    dg_label_type.grid(row=1, column=0, sticky="ew", padx=5, pady=3)
    dg_entry_type = tk.Entry(master=frm_dyn_group_filter, state=tk.DISABLED, width=50)
    dg_entry_type.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

    dg_label_ocid = ttk.Label(master=frm_dyn_group_filter, text="Statement OCID")
    dg_label_ocid.grid(row=1, column=2, sticky="ew", padx=5, pady=3)
    dg_entry_ocid = tk.Entry(master=frm_dyn_group_filter, state=tk.DISABLED, width=50)
    dg_entry_ocid.grid(row=1, column=3, sticky="ew", padx=5, pady=3)

    dg_btn_update = ttk.Button(frm_dyn_group_filter, text="Update Filter", state=tk.DISABLED, command=update_output_dg)
    dg_btn_update.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
    dg_btn_clear = ttk.Button(frm_dyn_group_filter, text="Clear Filters", state=tk.DISABLED, command=clear_filters_dg)
    dg_btn_clear.grid(row=2, column=2, columnspan=2, sticky="ew", padx=5, pady=3)

    btn_dyn_group_inuse_analysis = ttk.Button(master=frm_dyn_group_actions, text="Run In Use Analysis", command=run_dynamic_group_inuse_analysis)
    btn_dyn_group_ocid_analysis = ttk.Button(master=frm_dyn_group_actions, text="Run OCID Analysis", command=run_dynamic_group_ocid_analysis)
    
    # text_dg = tk.Text(master=frm_dyn_group_output)
    btn_dyn_group_inuse_analysis.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
    btn_dyn_group_ocid_analysis.grid(row=0, column=2, columnspan=2, sticky="ew", padx=5, pady=3)

    tree_dg = ttk.Treeview(master=frm_dyn_group_output, show=ttk.TREEHEADINGS, style='info.Treeview')
    tree_dg.pack(expand=True, fill=tk.BOTH)

    # Columns
    tree_dg["columns"] = ("Value")
    tree_dg.column("#0", stretch=False, width=220)
    tree_dg.column("Value", stretch=True)
    tree_dg.heading("#0", text="Name / Type", anchor=tk.W)
    tree_dg.heading("Value", text="Value (Copy-able)", anchor=tk.W)

    tree_policies = ttk.Treeview(master=frm_policy,show='tree')
    tree_policies.pack(expand=True, fill=tk.BOTH, side= tk.TOP)

    # Insert to main window
    frm_init.pack(expand=False, fill=tk.X, side=tk.TOP)
    frm_filter.grid(row=0, column=0, sticky="nsew")
    frm_output.grid(row=1, column=0, sticky="nsew")
    #frm_actions.grid(row=2, column=0, sticky="nsew")
    frm_policy.pack(expand=True, fill=tk.BOTH)
    frm_policy_top.pack(expand=False, fill=tk.BOTH)
    frm_policy_bottom.pack(expand=True, fill=tk.BOTH, side=tk.TOP)
    frm_dyn_group_filter.pack(expand=False, fill=tk.BOTH)
    frm_dyn_group_actions.pack(expand=False, fill=tk.BOTH)
    frm_dyn_group_output.pack(expand=True, fill=tk.BOTH)
 
    # Add tabs
    tab_control.pack(expand=True, fill=tk.BOTH)

    # Create the classes
    #progressbar_val = tk.IntVar()
    progress = Progress(progress_val=progressbar_val.get())
    policy_analysis = PolicyAnalysis(progress=progress,
                                     verbose=verbose)
    dyn_group_analysis = DynamicGroupAnalysis(progress=progress, verbose=False)

    # Start UI
    # window.mainloop()
    while True:
        update_progress()

        # Poor man's event
        if policy_analysis.finished:
            update_output()
            policy_analysis.finished = False
            progressbar_val.set(0)
        window.update_idletasks()
        window.update()
        time.sleep(0.1)