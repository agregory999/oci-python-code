"""Offline regression checks for monthly/YTD reporting and result pagination."""

import importlib.util
import io
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import oci

spec = importlib.util.spec_from_file_location(
    "report", Path(__file__).resolve().parents[1] / "working/oci_cost_by_sku_compartment.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def date(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def item(month, compartment="A", quantity=4, cost=12):
    return oci.usage_api.models.UsageSummary(
        time_usage_started=date(f"2026-{month:02}-01"),
        compartment_id=f"ocid.{compartment}", compartment_name=compartment,
        computed_quantity=quantity, computed_amount=cost, unit="GB Months", currency="USD",
    )


def page(items, token=None):
    return SimpleNamespace(data=SimpleNamespace(items=items), next_page=token)


class ReportTests(unittest.TestCase):
    def test_calendar_boundaries(self):
        self.assertEqual(report.month_bounds(now=date("2026-01-07")),
                         (date("2025-12-01"), date("2026-01-01")))
        self.assertEqual(report.month_bounds(now=date("2024-03-01")),
                         (date("2024-02-01"), date("2024-03-01")))
        self.assertEqual(report.report_bounds(ytd=True, now=date("2026-11-06")),
                         (date("2026-01-01"), date("2026-11-06")))
        for invalid in ("2026-1", "2026-13", "2026-11"):
            with self.assertRaises(ValueError):
                report.month_bounds(invalid, now=date("2026-11-06"))

    def test_ytd_preserves_months_and_paginates_both_queries(self):
        client = Mock()
        client.request_summarized_usages.side_effect = [
            page([item(2, "B"), item(1)], "monthly-2"),
            page([item(2)]), page([item(11)], "daily-2"),
            page([item(11, "B", quantity=0)]),
        ]
        rows = report.report_rows(client, "tenancy", "B91628",
                                  date("2026-01-01"), date("2026-11-06"))
        self.assertEqual([(r["compartment_name"], r["month"]) for r in rows],
                         [("A", "2026-01"), ("A", "2026-02"), ("A", "2026-11"),
                          ("B", "2026-02"), ("B", "2026-11")])
        self.assertEqual(rows[0]["effective_unit_cost"], Decimal(3))
        self.assertIsNone(rows[-1]["effective_unit_cost"])
        calls = client.request_summarized_usages.call_args_list
        self.assertEqual(calls[1].kwargs["page"], "monthly-2")
        self.assertEqual(calls[3].kwargs["page"], "daily-2")
        monthly, daily = calls[0].args[0], calls[2].args[0]
        self.assertEqual(monthly.granularity, "MONTHLY")
        self.assertFalse(monthly.is_aggregate_by_time)
        self.assertEqual(monthly.time_usage_ended, date("2026-11-01"))
        self.assertEqual(daily.granularity, "DAILY")
        self.assertTrue(daily.is_aggregate_by_time)
        self.assertEqual(daily.time_usage_started, date("2026-11-01"))
        self.assertEqual(daily.time_usage_ended, date("2026-11-06"))
        self.assertEqual(monthly.filter.dimensions[0].value, "B91628")

    def test_single_month_and_first_of_month(self):
        client = Mock()
        client.request_summarized_usages.return_value = page([item(10)])
        rows = report.report_rows(client, "tenancy", "B91628",
                                  date("2026-10-01"), date("2026-11-01"))
        self.assertEqual(rows[0]["month"], "2026-10")
        client.request_summarized_usages.assert_called_once()

    def test_january_first_has_no_completed_days(self):
        client = Mock()
        start, end = report.report_bounds(ytd=True, now=date("2026-01-01"))
        rows = report.report_rows(client, "tenancy", "B91628", start, end)
        self.assertEqual(rows, [])
        client.request_summarized_usages.assert_not_called()
        stream = io.StringIO()
        report.write_csv(rows, stream)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
