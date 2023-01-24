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

## OCI Metrics Alarm History

Script to show metrics history and specifically call out when a metric goes over and under a specific threshold.  Alarms that watch multiple metric streams may stay in FIRING state (not good) for a long time.  This doesn't provide details of when each stream crossed the threshold set by the alarm (over or under).  This script does that.  It looks at XX days of history, takes a metrics query, and a threshold value (similar to alarm).  Then it pulls all data and only shows when it exceeds or falls below the thresold.

### Usage

Provide the required params as such:

```
prompt> oci-python-code % python3 ./oci-metrics-alarm-history.py --help                    
usage: oci-metrics-alarm-history.py [-h] [-v] [-pr PROFILE] -c COMPARTMENTOCID -n NAMESPACE
                                    [-r RESOURCEGROUP] [-d DAYS] -q QUERY -t THRESHOLD

options:
  -h, --help            show this help message and exit
  -v, --verbose         increase output verbosity
  -pr PROFILE, --profile PROFILE
                        Config Profile, named
  -c COMPARTMENTOCID, --compartmentocid COMPARTMENTOCID
                        Metrics Compartment OCID
  -n NAMESPACE, --namespace NAMESPACE
                        Metrics Namespace
  -r RESOURCEGROUP, --resourcegroup RESOURCEGROUP
                        Resource Group
  -d DAYS, --days DAYS  Days of data to analyze
  -q QUERY, --query QUERY
                        Full metric query
  -t THRESHOLD, --threshold THRESHOLD
                        Numeric threshold when crossed (will check value
```

### Example

Example, providing a profile (OCI Config), and a complex query

```
prompt> python3 ./oci-metrics-alarm-history.py -c ocid1.compartment.oc1..xxx -n oracle_appmgmt -t 95 -r host -d 60 -q 'FilesystemUtilization[6h]{fileSystemName !~ "/*ora002|/*ora003|/*ora004|/*ora005|/*ora006|/*ora007|/*ora008|/*ora009"}.mean()' -pr YYY

Using profile YYY.
Using 60 days of data
Using ocid1.compartment.oc1..xxx / oracle_appmgmt / host / FilesystemUtilization[6h]{fileSystemName !~ "/*ora002|/*ora003|/*ora004|/*ora005|/*ora006|/*ora007|/*ora008|/*ora009"}.mean() / threshold 95
Metrics Query: {
  "end_time": "2023-01-24T11:20:29.554533Z",
  "namespace": "oracle_appmgmt",
  "query": "FilesystemUtilization[6h]{fileSystemName !~ \"/*ora002|/*ora003|/*ora004|/*ora005|/*ora006|/*ora007|/*ora008|/*ora009\"}.mean()",
  "resolution": null,
  "resource_group": "host",
  "start_time": "2022-11-25T11:20:29.554533Z"
}
Metrics Result Size: 480
Host XXX File System /fwr/addr exceeded threshold ( t: 95 / val: 99.35100000000017 ) at 2023-01-13 17:00:00+00:00
Host YYY File System /epy/ora_export exceeded threshold ( t: 95 / val: 97.61499999999987 ) at 2023-01-13 17:00:00+00:00
Host ZZZ File System /u00 exceeded threshold ( t: 95 / val: 97.75488757396457 ) at 2023-01-13 17:00:00+00:00
Host ZZZ File System /u00 went below threshold ( t: 95 / val: 75.79682500000013 ) at 2023-01-17 23:00:00+00:00
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
