# OCI Python Code

A collection of python scripts that I have built, to do things using the API.  These are not OCI functions, but could be.  If so, these can go into a functions subdirectory.

## OCI Policy Analysis

Script to pull all IAM policies from a tenancy and organize them by
- Dynamic Group Policies
- Service Policies
- Regular Policies

The script attempts to parse each statement into a list of tuples.  Each tuple looks like:

`(Subject) (Verb) (Resource) (Location) (Conditions)`

Tuples should make it easier to sort later.

## OCI List Bucket Sizes

Script iterates Regions and Compartments, lists OSS buckets, and formats the approximate size.

## OCI FSS Backup

Script originally written for a customer.  Has its own README.
