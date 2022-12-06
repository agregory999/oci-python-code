# OCI Python Code

A collection of python scripts that I have built, to do things using the API.  These are not OCI functions, but could be.  If so, these can go into a functions subdirectory.

## OCI Policy Analysis

Script to pull all IAM policies from a tenancy and organize them by
- Special Policies (admit/define/endorse)
- Dynamic Group Policies
- Service Policies
- Regular Policies

The script attempts to parse each statement into a list of tuples.  Each tuple looks like:

`(Subject) (Verb) (Resource) (Location) (Conditions)`

Tuples should make it easier to filter.

The script starts wherever you tell it in the compartment hierarchy and recurses through all compartments.  To run it at the tenancy root, give -o <tenancy ocid>

Optionally, if you use profiles in your OCI config (eg other than DEFAULT), pass in -pr/--profile to set that.  Omit if you only have a default

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

## OCI FSS Backup

Script originally written for a customer.  Has its own README.
