from oci import config
from oci import identity
import argparse

# Lists
dynamic_group_statements = []
service_statements = []
regular_statements = []
special_statements = []

# Helper
def print_statement(statement_tuple):
    a,b,c,d,e = statement_tuple
    print(f"Subject: {a}, Verb: {b}, Resource: {c}, Location: {d}, Condition: {e}")

def parse_statement(statement, comp_string, comp_name):
    # Play with tuple and partition
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
            #location = f"compartment {comp_name}"
            pass
        else:
            location = f"compartment {comp_string}:{sub_comp}"

    # Build tuple based on modified location
    statement_tuple = (subject,verb,resource,location,condition)
    return statement_tuple
    
# Recursive Compartments / Policies
def getNestedCompartment(identity_client, comp_ocid, level, comp_string, verbose):

    # Print something if not verbose
    if not verbose:
        print("c",end='',flush=True)

    # Level Printer
    level_string = ""
    for i in range(level):
        level_string += "|  "

    # Print with level
    get_compartment_response = identity_client.get_compartment(compartment_id=comp_ocid)
    comp = get_compartment_response.data
    if verbose:
        print(f"{level_string}| Compartment Name: {comp.name} ID: {comp_ocid} Hierarchy: {comp_string}")

    # Get policies First
    list_policies_response = identity_client.list_policies(
        compartment_id=comp_ocid,
        limit=1000
    )
    for policy in list_policies_response.data:
        if not verbose:
            print("p",end='',flush=True)
        else:
                print(f"{level_string}| > Policy: {policy.name} ID: {policy.id}")
        for index,statement in enumerate(policy.statements, start=1):
            if not verbose:
                print("s",end='',flush=True)
            else:
                print(f"{level_string}| > -- Statement {index}: {statement}", flush=True)
            
            # Root out "special" statements (endorse / define / as)
            if str.startswith(statement,"endorse") or str.startswith(statement,"admit") or str.startswith(statement,"define"):
                special_statements.append(statement)
                continue

            # Helper returns tuple
            statement_tuple = parse_statement(statement=statement, comp_string=comp_string, comp_name=comp.name)
            if statement_tuple[0] is None or statement_tuple[0] == "":
                if verbose:
                    print(f"****Statement {statement} resulted in bad tuple: {statement_tuple}")

            if "dynamic-group " in statement_tuple[0]:
                dynamic_group_statements.append(statement_tuple)
            elif "service " in statement_tuple[0]:
                service_statements.append(statement_tuple)
            else:
                regular_statements.append(statement_tuple)

    # Where are we? Do we need to recurse?
    list_compartments_response = identity_client.list_compartments(
        compartment_id=comp_ocid,
        limit=1000,
        access_level="ACCESSIBLE",
        compartment_id_in_subtree=False,
        sort_by="NAME",
        sort_order="ASC",
        lifecycle_state="ACTIVE")
    comp_list = list_compartments_response.data
    
    # Iterate and if any have sub-compartments, call recursive until none left
    if len(comp_list) == 0:
        # print(f"fall back level {level}")
        return
    for comp in comp_list:
       
        # Recurse
        if comp_string == "":
            getNestedCompartment(identity_client=identity_client, comp_ocid=comp.id, level=level+1, comp_string=comp_string + comp.name, verbose=verbose)
        else:
            getNestedCompartment(identity_client=identity_client, comp_ocid=comp.id, level=level+1, comp_string=comp_string + ":" + comp.name, verbose=verbose)

# Main Code

# Parse Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-o", "--ocid", help="OCID of compartment or tenancy", required=True)
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-sf", "--subjectfilter", help="Filter all statement subjects by this text")
parser.add_argument("-vf", "--verbfilter", help="Filter all verbs (inspect,read,use,manage) by this text")
parser.add_argument("-rf", "--resourcefilter", help="Filter all resource (eg database or stream-family etc) subjects by this text")
parser.add_argument("-lf", "--locationfilter", help="Filter all location (eg compartment name) subjects by this text")
args = parser.parse_args()
verbose = args.verbose
ocid = args.ocid
profile = args.profile
sub_filter = args.subjectfilter
verb_filter = args.verbfilter
resource_filter = args.resourcefilter
location_filter = args.locationfilter

config = config.from_file(profile_name=profile)
identity_client = identity.IdentityClient(config)

# Initial Recursion
level = 0
print("========Enter Recursion==============")
getNestedCompartment(identity_client=identity_client, comp_ocid=ocid, level=level, comp_string="", verbose=verbose)
print("\n========Exit Recursion==============")

# Perform Filtering
if sub_filter:
    print(f"Filtering subject: {sub_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    dynamic_group_statements = list(filter(lambda statement: sub_filter.casefold() in statement[0].casefold(),dynamic_group_statements))
    service_statements = list(filter(lambda statement: sub_filter.casefold() in statement[0].casefold(),service_statements))
    regular_statements = list(filter(lambda statement: sub_filter.casefold() in statement[0].casefold(),regular_statements))
    print(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

if verb_filter:
    print(f"Filtering verb: {verb_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    dynamic_group_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(),dynamic_group_statements))
    service_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(),service_statements))
    regular_statements = list(filter(lambda statement: verb_filter.casefold() in statement[1].casefold(),regular_statements))
    print(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

if resource_filter:
    print(f"Filtering resource: {resource_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    dynamic_group_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(),dynamic_group_statements))
    service_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(),service_statements))
    regular_statements = list(filter(lambda statement: resource_filter.casefold() in statement[2].casefold(),regular_statements))
    print(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")

if location_filter:
    print(f"Filtering location: {location_filter}. Before: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")
    dynamic_group_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(),dynamic_group_statements))
    service_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(),service_statements))
    regular_statements = list(filter(lambda statement: location_filter.casefold() in statement[3].casefold(),regular_statements))
    print(f"After: {len(dynamic_group_statements)}/{len(service_statements)}/{len(regular_statements)} DG/SVC/Reg statements")


# Print Special 
print("========Summary Special==============")
for index, statement in enumerate(special_statements, start=1):
    print(f"Statement #{index}: {statement}")
print(f"Total Special statement in tenancy: {len(special_statements)}")

# Print Dynamic Groups
print("========Summary DG==============")
for index, statement in enumerate(dynamic_group_statements, start=1):
    print(f"Statement #{index}: {statement}")
print(f"Total Service statement in tenancy: {len(dynamic_group_statements)}")

# Print Service
print("========Summary SVC==============")
for index, statement in enumerate(service_statements, start=1):
    print(f"Statement #{index}: {statement}")
print(f"Total Service statement in tenancy: {len(service_statements)}")

# Print Regular
print("========Summary Reg==============")
for index, statement in enumerate(regular_statements, start=1):
    print(f"Statement #{index}: {statement}")
print(f"Total Regular statement in tenancy: {len(regular_statements)}")