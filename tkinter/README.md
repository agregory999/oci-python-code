# Policy and Dynamic Group Analysis

This tool is python-based utility that can run either via command line or with a UI.  The main purpose of this tool set is to load, filter, and analyze both OCI Policy Statements and Dynamic Groups.  It is possible to determine many things by using these tools:
* What permissions a group or dynamic group has
* Where in the compartment hierarchy are all relevant statements that meet the search criteria
* What additional policies exist for cross-tenancy enablement
* What permissions are granted to services, and in which compartments
* Whether the components of any or all dynamic groups point to valid OCIDs
* If any dynamic groups have no policy statements attached (means they are unused)
The UI is written using tkinter, tkbootstrap, and tksheets, all of which are required to use the UI.  

## Installation and Setup

Python 3.9 and tkinter were tested and are required for the UI.

Once installed, it is recommended to run in a virtual environment, using the included requirements.txt file to install any required packages via `pip`.  If TKinter is properly installed on the host system, the widgets should look good no matter which OS the code is run from.

### Authentication

The utility can take advantage of either profile-based (API-key) or Instance Principal.  If you are running from your desktop or have no desire to use Instance Principals, simply use an existing or new OCI Profile.  By default, if you have enabled OCI CLI, you have a profile named `DEFAULT` that authhenticates and runs using the configured User OCID.  This means that you need to be covered by a policy statement that, at a minimum, has the following:

```
allow group <your group name> to inspect policies in tenancy
allow group <your group name> to inspect dynamic-groups in tenancy
allow group <your group name> to inspect compartments in tenancy

``` 

To run using instance principals, you must ensure that there is a dynamic group containing either the Instance OCID or the Instance Compartment OCID for the instance you plan to run from.  Then you need a policy statement somewhere, which grants read permission on the policy and dynamic groups:

```
allow dynamic-group <your group name> to inspect policies in tenancy
allow dynamic-group <your group name> to inspect dynamic-groups in tenancy
allow dynamic-group <your group name> to inspect compartments in tenancy

```
## Profile Selection

Instance principals do not support the ability to operate on tenancies other than the one where the Instance is running.  However, since OCI API-key or profile-based auth allows you to have multiple entries in your `$HOME/.oci/config` file, the UI and CLI version allow you to select which profile to operate with.  This can be handy for administrators who work on multiple tenancies.

The docs for each version explain how to do profile selection.

## Caching

Using the UI or the CLI version begins with choosing where to load policies and dynamic groups from.  The tool supports a cached (offline) mode, in which policy statements and dynamic groups from a previous (non-cached) run are saved into a local cache file, per tenancy OCID analyzed.  What this means is that if no changes occur, you can work using cached policies instead of calling the OCI API potentiallly 1000s of times to load the data.  At any time, you can simply run again against the actual tenancy and the results will populate from fresh data, again updating the cache for subsequent work.

It is completely fine to operate with multiple tenancies, as cache files are keyed from the tenancy OCID.  Therefore, you can have multiple tenancies with cached policies locally, and select ar runtime on which to operate. 

## Filtering

One of the main features of the tool set is the ability to filter a large list of policy statements.  In OCI, statements are organized into policies, which can have up to 50 statements by default.  Policies are located in compartments (often not the tenancy root), and thus valid statements for a given group or dynamic group can exist in multiple compartments and in multiple policies.  Therefore, the total set of permissions granted to a group is the union of all valid statements, and is evaluated each time an API call is made.   Without a tool that can load and organize ALL statements, it is very difficult to quickly determine whether permission to "do something" exists, and if so, whether it is too much.  

A simple example of filtering might be to load 3000 total statements and then ask the tool to filter out a specific group and verb.  For example, group `InstanceAdmins` and vwreb `manage`.  You could filter on both of these at the same time, and derive a list of all policy statements that have both of these characteristcs.  Results will also include the name and location in compartment hierarchy of the containing policy.

### Filter Chaining

Filtering for policies can be done via 8 possible ways:  
- Subject (group or dynamic-group name)
- Verb (inspect. read, use, manage)
- Resource (ie instance-family or subnets)
- Location (compartment name)
- Compartment Hierarchy (compartment name anywhere in hierarchy)
- Conditions (anything in where clause)
- Text (anything in the statement text)
- Policy Name (to see a specific policy)
Individual filters support an | (OR) within the filter, and are chained using AND.  This means that if we define a filter for subject as `abc|def` and we also define a verb filter of `read|use`, the combined filter will give policy statements where `abc` OR `def` appears in the group name AND `read` OR `use` is the verb.   As more filters are refined, the list of statements is reduced to the relevant ones only.

There are more advanced filter examples, as well as more documentation on what is valid, further below.

### Load, Save, Clear

The UI includes convenience buttons to clear all filters, as well as buttons to save the filtered output to 

## Display Options

The UI version of the tool supports additional output filtering.  For example, once the list of policies has been filtered by subject, verb, etc, the UI allows you to further filter the display by policy type.  This can be helpful if you want to see just dynamic-group statements or service statements.  These are implemented as checkboxes, so you can see all or some of the available policy statements that came from the filtered output.

Additionally the UI will display both the total number of statements from the aggregate filter operation, as well as the number of statements actually being shown at the moment, based on display filters.

Finally, the UI has a checkbox option for "Extended View", which shows all information that it was able to parse from all statements that are currently displayed.  This contains full OCIDs, policy comments, and parsed fields for each filter-able category, such as subject, verb, resource, location, and conditions.

### Copy / Paste

The UI display grid supports copy and paste.  To copy, simply click on any result cell (or multiple, using ctrl or shift), and then copy with ctrl-C or a right click.  The text is able to be pasted.

## Usage (CLI)

Using the CLI

## Usage (UI)

Using the UI begins with choosing where to load policies and dynamic groups from.  The tool supports a cached (offline) mode, in which policy statements and dynamic groups from a previous (non-cached) run are saved into a local cache file, per tenancy OCID analyzed.  What this means is that if no changes occur, you can work using cached policies instead of callign the OCI API potentiallly 1000s of times to load the data
