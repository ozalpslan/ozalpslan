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
        self.days = [{"date": d.isoformat(), "contributionCount": 0} for d in profile.dates_ending(self.end)]
        self.now = datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc)
        self.data = {"username": "ozalpslan", "updated": self.now.isoformat(), "days": self.days}

    def test_31_days_cross_year_and_leap_day(self):
        self.assertEqual(self.days[0]["date"], "2025-12-16")
        leap_days = profile.dates_ending(date(2024, 3, 1))
        self.assertEqual(len(leap_days), 31)
        self.assertIn(date(2024, 2, 29), leap_days)

    def test_sorts_dates_and_rejects_incomplete_window(self):
        self.assertEqual(profile.normalize_days(list(reversed(self.days)), self.end), self.days)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            profile.normalize_days(self.days[:-1], self.end)

    def test_rejects_duplicates_and_invalid_counts(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            profile.normalize_days(self.days + [self.days[0]], self.end)
        for value in (-1, "3", True, 1.5):
            bad = [dict(item) for item in self.days]
            bad[0]["contributionCount"] = value
            with self.assertRaises(ValueError):
                profile.normalize_days(bad, self.end)

    def test_zero_activity_is_a_real_chart_not_pending(self):
        for theme in profile.THEMES:
            content = profile.activity(theme, self.data)
            ET.fromstring(content)
            self.assertIn("0 contributions / 31 days", content)
            self.assertNotIn("pending", content)
            self.assertNotIn("nan", content.lower())
            self.assertIn("2025-12-16", content)
            self.assertIn("2026-01-15", content)

    def test_missing_data_is_explicitly_pending(self):
        content = profile.activity("dark")
        self.assertIn("Activity data pending first refresh", content)
        self.assertNotIn("0 contributions", content)

    def test_spike_fits_chart_and_total_matches(self):
        self.days[7]["contributionCount"] = 1001
        content = profile.activity("light", self.data)
        self.assertIn("1,001 contributions / 31 days", content)
        root = ET.fromstring(content)
        marks = root.findall(".//{http://www.w3.org/2000/svg}circle")
        self.assertEqual(len(marks), 31)
        self.assertTrue(all(60 <= float(mark.attrib["cy"]) <= 173 for mark in marks))

    def test_graphql_uses_date_window_and_counts(self):
        body = {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [{"contributionDays": self.days}]}}}}}
        with patch.object(profile.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as fetch:
            result = profile.fetch_activity("ozalpslan", "test-token", self.now)
        request = fetch.call_args.args[0]
        variables = json.loads(request.data)["variables"]
        self.assertEqual(variables["from"], "2025-12-16T00:00:00+00:00")
        self.assertEqual(variables["login"], "ozalpslan")
        self.assertEqual(result["days"], self.days)

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
            self.assertIn("12s", animated)
            self.assertIn("prefers-reduced-motion", animated)
            self.assertNotIn("@keyframes", static)
            self.assertNotIn("<script", animated)
            self.assertNotIn("foreignObject", animated)


if __name__ == "__main__":
    unittest.main()
