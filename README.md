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

Tuples should make it easier to sort later.

The script starts wherever you tell it in the compartment hierarchy and recurses through all compartments.  To run it at the tenancy root, give -o <tenancy ocid>

Optionally, if you use profiles in your OCI config (eg other than DEFAULT), pass in -pr/--profile to set that.  Omit if you only have a default

Examples
```
python3 oci-policy-analyze-python.py -o ocid1.tenancy.oc1..zzzzzzzzzz

python3 oci-policy-analyze-python.py -o ocid1.compartment.oc1..zzzzzzzzzz

python3 oci-policy-analyze-python.py --profile CUSTOMER -o ocid1.tenancy.oc1..zzzzzzzzz


```

## OCI List Bucket Sizes

Script iterates Regions and Compartments, lists OSS buckets, and formats the approximate size.

## OCI FSS Backup

Script originally written for a customer.  Has its own README.
