import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daily_aircraft import DailyAircraftTracker, normalize_hex, resolve_timezone


TZ = timezone(timedelta(hours=13))
EVENING = datetime(2026, 11, 8, 23, 50, tzinfo=TZ)
NEXT_DAY = datetime(2026, 11, 9, 0, 0, tzinfo=TZ)


class DailyAircraftTest(unittest.TestCase):
    def test_normalize_hex(self):
        self.assertEqual(normalize_hex(" ABC123 "), "abc123")
        self.assertIsNone(normalize_hex("  "))
        self.assertIsNone(normalize_hex(None))
        self.assertIsNone(normalize_hex(12))

    def test_unique_hexes_persist_until_local_midnight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aircraft_today.json"
            tracker = DailyAircraftTracker(path, tz=TZ, now=EVENING)
            count = tracker.observe(
                [
                    {"hex": "ABC123", "lat": -36.8, "lon": 174.7},
                    {"hex": "abc123"},
                    {"hex": "00FF01"},
                    {"hex": "  "},
                    {"nope": True},
                    "not-a-dict",
                ],
                now=EVENING,
            )
            self.assertEqual(count, 2)
            self.assertEqual(tracker.count, 2)

            reloaded = DailyAircraftTracker(path, tz=TZ, now=EVENING)
            self.assertEqual(reloaded.count, 2)

            rolled = DailyAircraftTracker(path, tz=TZ, now=NEXT_DAY)
            self.assertEqual(rolled.count, 0)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["day"], "2026-11-09")
            self.assertEqual(stored["hexes"], [])

            self.assertEqual(
                rolled.observe([{"hex": "abc123"}, {"hex": "def456"}], now=NEXT_DAY),
                2,
            )

    def test_same_hex_is_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aircraft_today.json"
            tracker = DailyAircraftTracker(path, tz=TZ, now=EVENING)
            tracker.observe([{"hex": "abc123"}], now=EVENING)
            tracker.observe([{"hex": "ABC123"}, {"lat": 1, "lon": 2}], now=EVENING)
            self.assertEqual(tracker.count, 1)

    def test_missing_aircraft_list_keeps_the_day(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aircraft_today.json"
            tracker = DailyAircraftTracker(path, tz=TZ, now=EVENING)
            tracker.observe([{"hex": "abc123"}], now=EVENING)
            self.assertEqual(tracker.observe(None, now=EVENING), 1)

    def test_corrupt_state_starts_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aircraft_today.json"
            path.write_text("{", encoding="utf-8")
            tracker = DailyAircraftTracker(path, tz=TZ, now=EVENING)
            self.assertEqual(tracker.count, 0)
            tracker.observe([{"hex": "abc"}], now=EVENING)
            self.assertEqual(tracker.count, 1)

    def test_naive_now_uses_tracker_timezone(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aircraft_today.json"
            tracker = DailyAircraftTracker(path, tz=TZ, now=EVENING)
            tracker.observe([{"hex": "abc"}], now=datetime(2026, 11, 8, 23, 59))
            self.assertEqual(tracker.count, 1)
            tracker.observe([{"hex": "def"}], now=datetime(2026, 11, 9, 0, 0))
            self.assertEqual(tracker.count, 1)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["hexes"], ["def"])

    def test_resolve_timezone_falls_back(self):
        self.assertEqual(str(resolve_timezone("Pacific/Auckland")), "Pacific/Auckland")
        fallback = resolve_timezone("Not/AZone")
        self.assertIsNotNone(fallback)
        self.assertNotEqual(str(fallback), "Not/AZone")


if __name__ == "__main__":
    unittest.main()
