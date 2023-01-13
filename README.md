# OCI Python Code

A collection of python scripts that I have built, to do things using the OCI APIs.  

## General Notes
In order to utilize the OCI API, you must initialize using PIP:

```bash
prompt> pip3 install oci

```

Also, you should have the [OCI Config](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cliconcepts.htm) set up locally.  If you have multiple profiles set up, for example if you use multiple tenancies or user accounts, those named profiles can be used with most of these scripts.  

## OCI ExaCS Analysis

These scripts:
- oci-analyze-exacs-costs-by-database.py
- oci-exacs-storage-used-csv.py

are designed to use a combination of OCI APIs as well as python built-in and 3rd party libraries, in order to "slice and dice" metric data from OCI, specifically `StorageUsed` for a list of databases running on ExaCS.  As additional API calls are added, more information, such as cost analysis data, could be added.

At the moment, with a compartment OCID, the script will do the following:
- Establish an OCI session using OCI Config information on the local machine (profiles supported too)
- Pull high level data for each ExaCS rack in the compartment
- List each database on each rack, and pull `StorageUsed` metric for a number of days
- Average the data over the time period and output to the screen or CSV file

Argument Parsing (`argparse`) and CSV Writing (`csv`) are among the python built-ins used.  

## OCI Policy Analysis

This script (`oci-policy-analyze-python.py`) to pull all IAM policies from a tenancy or compartment hierarchy and organize them by
- Special Policies (admit/define/endorse)
- Dynamic Group Policies
- Service Policies
- Regular Policies

The script attempts to parse each statement into a list of tuples.  Each tuple looks like:

`(Subject) (Verb) (Resource) (Location) (Conditions)`

Tuples make it easier to filter.  The script supports filters via these parameters:
- [-sf SUBJECTFILTER]
- [-vf VERBFILTER]
- [-rf RESOURCEFILTER]
- [-lf LOCATIONFILTER]

The script starts wherever you tell it in the compartment hierarchy and recurses through all compartments.  To run it at the tenancy root, give `-o tenancy ocid` .  To start within a compartment hierarchy, pass in `-o compartment_ocid`.

Optionally, if you use profiles in your OCI config (eg other than DEFAULT), pass in -pr/--profile to set that.  Omit if you only have a `DEFAULT` profile defined.

### Simple Examples
```
python3 oci-policy-analyze-python.py -o ocid1.tenancy.oc1..zzzzzzzzzz
python3 oci-policy-analyze-python.py -o ocid1.compartment.oc1..zzzzzzzzzz
python3 oci-policy-analyze-python.py --profile CUSTOMER -o ocid1.tenancy.oc1..zzzzzzzzz
```

### Filter Examples

The flags below can be used independently or in tandem:
- `-sf/--subjectfilter` Filter all statement subjects by this text
- `-vf/--verbfilter` Filter all verbs (inspect,read,use,manage) by this text
- `-rf/--resourcefilter` Filter all resource (eg database or stream-family etc) subjects by this text
- `-lf/--locationfilter` Filter all location (eg compartment name) subjects by this text

```
# Filter statements by group ABC and verb manage
python3 oci-policy-analyze-python.py -o ocid1.compartment.oc1..zzzzzzzzzz -sf ABC -vf manage
# Filter alternate OCI profile tenancy level by compartment DEF
python3 oci-policy-analyze-python.py --profile CUSTOMER -o ocid1.tenancy.oc1..zzzzzzzzz -lf DEF

```

## OCI List Bucket Sizes

Script iterates Regions and Compartments, lists OSS buckets, and formats the approximate size.

## OCI ExaCS Failed PDB

Script iterates PDBs in a compartment and prints information for the PDB and CDB if it shows as failed.


## OCI FSS Backup

Script originally written for a customer.  Has its own [README](fss-backup/README.md).

## Streaming 

[These scripts](oci-streaming/) are able to use Kafka libraries to produce and consume from OCI Streaming.   This must be enabled on the tenancy, with policy and permission, as well as the setup of Stream Pools and Streams.  See the help that comes out:

```bash
prompt > python3 ./consume-kafka.py                                                                                                                         
usage: consume-kafka.py [-h] [-v] -p STREAMPOOL -u USERNAME -a AUTHTOKEN -t TENANCYNAME -s STREAM [-e ENDPOINT]
consume-kafka.py: error: the following arguments are required: -p/--streampool, -u/--username, -a/--authtoken, -t/--tenancyname, -s/--stream

```
