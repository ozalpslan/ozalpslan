import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("profile_artwork", Path(__file__).resolve().parents[1] / "scripts/profile.py")
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.end = date(2026, 1, 15)
        self.days = [{"date": (self.end-timedelta(days=368-i)).isoformat(), "contributionCount": 0} for i in range(369)]
        self.now = datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc)
        self.data = {"username": "ozalpslan", "updated": self.now.isoformat(), "period": "last_year", "totalContributions": 0, "days": self.days}

    def test_preserves_native_year_window_and_leap_day(self):
        self.assertEqual(profile.normalize_days(self.days), self.days)
        leap_days = [{"date": (date(2023, 3, 1)+timedelta(days=i)).isoformat(), "contributionCount": 0} for i in range(367)]
        self.assertEqual(profile.normalize_days(leap_days), leap_days)
        self.assertIn("2024-02-29", [entry["date"] for entry in leap_days])

    def test_sorts_dates_and_rejects_incomplete_window(self):
        self.assertEqual(profile.normalize_days(list(reversed(self.days))), self.days)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            profile.normalize_days(self.days[:100]+self.days[101:])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            profile.normalize_days(self.days[-31:])

    def test_rejects_duplicates_and_invalid_counts(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            profile.normalize_days(self.days + [self.days[0]])
        for value in (-1, "3", True, 1.5):
            bad = [dict(item) for item in self.days]
            bad[0]["contributionCount"] = value
            with self.assertRaises(ValueError):
                profile.normalize_days(bad)

    def test_zero_activity_is_a_real_chart_not_pending(self):
        for theme in profile.THEMES:
            content = profile.activity(theme, self.data)
            ET.fromstring(content)
            self.assertIn("0 contributions in the last year", content)
            self.assertNotIn("pending", content)
            self.assertNotIn("nan", content.lower())
            self.assertIn(self.days[0]["date"], content)
            self.assertIn("2026-01-15", content)

    def test_missing_data_is_explicitly_pending(self):
        content = profile.activity("dark")
        self.assertIn("Yearly contributions pending first refresh", content)
        self.assertNotIn("0 contributions", content)

    def test_spike_fits_chart_and_total_matches(self):
        self.days[7]["contributionCount"] = 1001
        self.data["totalContributions"] = 1001
        content = profile.activity("light", self.data)
        self.assertIn("1,001 contributions in the last year", content)
        root = ET.fromstring(content)
        marks = root.findall(".//{http://www.w3.org/2000/svg}circle")
        self.assertEqual(len(marks), len(profile.weekly_totals(self.days)))
        self.assertTrue(all(63 <= float(mark.attrib["cy"]) <= 173 for mark in marks))

    def test_graphql_uses_native_calendar_instead_of_shorter_custom_range(self):
        body = {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 0, "weeks": [{"contributionDays": self.days}]}}}}}
        with patch.object(profile.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as fetch:
            result = profile.fetch_activity("ozalpslan", "test-token", self.now)
        request = fetch.call_args.args[0]
        variables = json.loads(request.data)["variables"]
        self.assertEqual(variables, {"login": "ozalpslan"})
        self.assertNotIn("contributionsCollection(from:", json.loads(request.data)["query"])
        self.assertEqual(result["days"], self.days)

    def test_weekly_aggregation_preserves_all_contributions_in_partial_weeks(self):
        for index, entry in enumerate(self.days):
            entry["contributionCount"] = index % 6
        weeks = profile.weekly_totals(self.days)
        self.assertEqual(sum(w["contributionCount"] for w in weeks), sum(d["contributionCount"] for d in self.days))
        self.assertEqual(weeks[0]["date"], self.days[0]["date"])
        self.assertEqual(weeks[-1]["end"], self.days[-1]["date"])
        self.assertTrue(all((date.fromisoformat(w["end"])-date.fromisoformat(w["date"])).days <= 6 for w in weeks))

    def test_inconsistent_api_total_and_old_cache_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "total does not match"):
            profile.validated_calendar({**self.data, "totalContributions": 461})
        with self.assertRaisesRegex(ValueError, "Refresh the cached"):
            profile.validated_calendar({"days": self.days[-31:]})

    def test_graphql_errors_do_not_become_zero_counts(self):
        for body in ({"errors": [{"message": "Rate limited"}]}, {"data": {"user": None}}, {"data": None}, []):
            with patch.object(profile.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(body).encode())):
                with self.assertRaises(ValueError):
                    profile.fetch_activity("ozalpslan", "test-token", self.now)

    def test_failed_refresh_preserves_existing_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            paths = [assets / "activity-light.svg", assets / "activity-dark.svg", assets / "activity.json"]
            for path in paths:
                path.write_text("last successful output")
            with patch.object(profile, "ASSETS", assets), patch.dict(profile.os.environ, {"GH_TOKEN": "test"}), patch.object(profile, "fetch_activity", side_effect=ValueError("API unavailable")), patch("sys.argv", ["profile.py", "refresh"]), patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(profile.main(), 1)
            self.assertTrue(all(p.read_text() == "last successful output" for p in paths))

    def test_rejects_invalid_svg_before_replacing_any_output(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.svg"
            first.write_text("last successful output")
            with self.assertRaises(ET.ParseError):
                profile.write_outputs({first: "<svg/>", Path(directory) / "second.svg": "broken"})
            self.assertEqual(first.read_text(), "last successful output")


class HeaderTests(unittest.TestCase):
    def test_both_themes_have_static_and_animated_versions(self):
        for theme in profile.THEMES:
            animated = profile.header(theme)
            static = profile.header(theme, animated=False)
            ET.fromstring(animated)
            ET.fromstring(static)
            self.assertIn("3s", animated)
            self.assertIn("Linux &amp; DevOps", animated)
            self.assertNotIn("<rect", animated)
            self.assertNotIn("bash", animated)
            self.assertNotIn("alper@devops", animated)
            self.assertIn("prefers-reduced-motion", animated)
            self.assertNotIn("@keyframes", static)
            self.assertNotIn("<script", animated)
            self.assertNotIn("foreignObject", animated)


if __name__ == "__main__":
    unittest.main()
