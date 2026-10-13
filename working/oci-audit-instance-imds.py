#!/usr/bin/env python3
"""Read-only IMDS audit of Compute instances in all subscribed OCI regions.

Install: python3 -m pip install oci
Run:     python3 oci-audit-instance-imds.py --profile DEFAULT --csv imds-audit.csv

Requires permission to list region subscriptions and read instances across the
tenancy. Resource Search returns only resources visible to the caller and may
lag recent changes. This checks API configuration, not guest endpoint behavior.
Exit codes: 0 = all discovered instances PASS; 1 = FAIL found; 2 = incomplete
audit (errors, unknown settings, or no instances).
"""

import argparse
import csv
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import oci


def error_text(exc):
    if isinstance(exc, oci.exceptions.ServiceError):
        return f"{exc.status} {exc.code}: {exc.message}"
    return str(exc)


def scan_region(config, region):
    # Each worker owns its clients; never mutate the shared profile configuration.
    regional_config = dict(config, region=region)
    client_options = {"retry_strategy": oci.retry.DEFAULT_RETRY_STRATEGY}
    rows = []
    errors = []
    try:
        search = oci.resource_search.ResourceSearchClient(regional_config, **client_options)
        compute = oci.core.ComputeClient(regional_config, **client_options)
        resources = oci.pagination.list_call_get_all_results(
            search.search_resources,
            oci.resource_search.models.StructuredSearchDetails(
                query="query instance resources"
            ),
        ).data
        for resource in resources:
            row = {
                "region": region,
                "instance_name": resource.display_name or "(unnamed)",
                "instance_ocid": resource.identifier,
                "compartment_ocid": resource.compartment_id,
                "lifecycle_state": resource.lifecycle_state,
                "legacy_imds_disabled": "unknown",
                "imds": "UNKNOWN",
                "result": "UNKNOWN",
                "detail": "",
                "checked_at_utc": "",
            }
            try:
                instance = compute.get_instance(resource.identifier).data
                row["instance_name"] = instance.display_name or "(unnamed)"
                row["lifecycle_state"] = instance.lifecycle_state
                disabled = getattr(
                    instance.instance_options, "are_legacy_imds_endpoints_disabled", None
                )
                if disabled is True:
                    row.update(legacy_imds_disabled="true", imds="v2 only", result="PASS")
                elif disabled is False:
                    row.update(legacy_imds_disabled="false", imds="v1 + v2", result="FAIL")
                else:
                    row["detail"] = "API did not return the legacy IMDS setting"
            except Exception as exc:
                row.update(result="ERROR", detail=error_text(exc))
            row["checked_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows.append(row)
    except Exception as exc:
        errors.append(f"{region}: {error_text(exc)}")
    return rows, errors


def print_table(headers, rows):
    # Keep names with embedded newlines from breaking the report layout.
    cells = [[" ".join(str(value).split()) for value in row] for row in rows]
    widths = [max(len(title), *(len(row[i]) for row in cells)) for i, title in enumerate(headers)]
    print("  ".join(title.ljust(width) for title, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in cells:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-pr", "--profile", default="DEFAULT", help="OCI config profile (default: DEFAULT)")
    parser.add_argument("--config-file", default=oci.config.DEFAULT_LOCATION, help="OCI config file")
    parser.add_argument("--workers", type=int, default=4, help="Parallel region scans (default: 4; use 1 for sequential)")
    parser.add_argument("--csv", metavar="PATH", help="Save per-instance evidence to CSV")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    try:
        config = oci.config.from_file(file_location=args.config_file, profile_name=args.profile)
        identity = oci.identity.IdentityClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        subscriptions = oci.pagination.list_call_get_all_results(
            identity.list_region_subscriptions, config["tenancy"]
        ).data
    except Exception as exc:
        print(f"Unable to load profile or discover regions: {error_text(exc)}", file=sys.stderr)
        return 2

    regions = sorted({subscription.region_name for subscription in subscriptions})
    print("OCI instance IMDS audit (read-only)")
    print(f"Profile: {args.profile} | Tenancy: {config['tenancy']}")
    print(f"Started (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"Subscribed regions: {', '.join(regions) or '(none)'}")
    print("Scope: instances visible to this profile through Resource Search.")
    print("PASS requires are_legacy_imds_endpoints_disabled=true.\n", flush=True)

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(scan_region, config, region): region for region in regions}
        for future in as_completed(futures):
            region_rows, region_errors = future.result()
            rows.extend(region_rows)
            errors.extend(region_errors)
            print(f"Scanned {futures[future]}: {len(region_rows)} instance(s)"
                  + (" — ERROR" if region_errors else ""), flush=True)

    rows.sort(key=lambda row: (row["region"], row["instance_name"], row["instance_ocid"]))
    print()
    if rows:
        print_table(
            ["REGION", "INSTANCE", "STATE", "IMDS", "RESULT", "INSTANCE OCID"],
            [[row[key] for key in ("region", "instance_name", "lifecycle_state", "imds", "result", "instance_ocid")] for row in rows],
        )
    else:
        print("No instances discovered; IMDSv2-only compliance cannot be established.")

    for row in rows:
        if row["detail"]:
            print(f"\n{row['result']} {row['region']} / {row['instance_ocid']}: {row['detail']}")
    for error in errors:
        print(f"\nREGION ERROR: {error}")

    if args.csv:
        try:
            with open(args.csv, "w", newline="", encoding="utf-8") as output:
                fields = ["region", "instance_name", "instance_ocid", "compartment_ocid",
                          "lifecycle_state", "legacy_imds_disabled", "imds", "result",
                          "detail", "checked_at_utc"]
                writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\nCSV evidence: {args.csv}")
        except OSError as exc:
            errors.append(f"CSV export: {exc}")
            print(f"\nCSV ERROR: {exc}", file=sys.stderr)

    counts = Counter(row["result"] for row in rows)
    print(f"\nSummary: {len(rows)} instances | {counts['PASS']} PASS | "
          f"{counts['FAIL']} FAIL | {counts['UNKNOWN']} UNKNOWN | "
          f"{counts['ERROR']} ERROR | {len(errors)} scan/export error(s)")
    if errors or counts["UNKNOWN"] or counts["ERROR"] or not rows:
        print("INCOMPLETE: cannot confirm every instance is IMDSv2-only.")
        return 2
    if counts["FAIL"]:
        print("FAIL: some instances still allow legacy IMDSv1 endpoints.")
        return 1
    print("PASS: all discovered instances are configured for IMDSv2 only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
