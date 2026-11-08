import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stats_catalog import CATALOG, FT_TO_M, PollContext, bearing_degrees, format_state, haversine_km


STATS = {
    "aircraft_with_pos": 2,
    "aircraft_without_pos": 1,
    "gain_db": 49.6,
    "estimated_ppm": 10.25,
    "aircraft_count_by_type": {"adsb_icao": 2, "mode_s": 1, "mlat": 0},
    "last1min": {
        "start": 0.0,
        "end": 60.0,
        "messages": 37,
        "max_distance": 1000,
        "local": {"signal": -20.0, "noise": -36.0, "strong_signals": 2},
        "tracks": {"all": 3, "single_message": 1},
    },
    "last15min": {
        "messages": 100,
        "max_distance": 18520,
        "tracks": {"all": 8, "single_message": 2},
    },
    "total": {
        "start": 1000.0,
        "end": 4600.0,
        "messages": 500,
        "position_count_total": 40,
        "max_distance": 37040,
        "tracks": {"all": 20, "single_message": 4},
        "local": {"samples_dropped": 7, "strong_signals": 9},
    },
}

OUTLINE = {
    "actualRange": {
        "last24h": {
            "points": [
                [0.0, 1.0, 10000],
                [0.0, 0.5, 38000],
            ]
        }
    }
}


class StatsCatalogTest(unittest.TestCase):
    def context(self):
        return PollContext(
            stats=STATS,
            outline=OUTLINE,
            receiver_lat=0.0,
            receiver_lon=0.0,
            aircraft=[
                {"r_dst": 10.0, "r_dir": 10.0},
                {"hex": "abc", "r_dst": 3.0, "r_dir": 90.0},
            ],
            aircraft_today=2,
        )

    def values(self):
        ctx = self.context()
        return {sensor.component_id: sensor.extract(ctx) for sensor in CATALOG}

    def test_ids_are_unique(self):
        ids = [sensor.component_id for sensor in CATALOG]
        self.assertEqual(len(ids), len(set(ids)))

    def test_snapshot_values(self):
        values = self.values()
        self.assertEqual(values["aircraft_now"], 3)
        self.assertEqual(values["aircraft_today"], 2)
        self.assertEqual(values["aircraft_with_position"], 2)
        self.assertEqual(values["aircraft_adsb_icao"], 2)
        self.assertEqual(values["aircraft_other"], 1)
        self.assertEqual(values["tracks_15min"], 8)
        self.assertEqual(values["messages_1min"], 37)
        self.assertAlmostEqual(values["messages_per_second"], 37 / 60)
        self.assertEqual(values["max_distance_15min"], 18.52)
        self.assertEqual(values["max_distance_since_start"], 37.04)
        self.assertEqual(values["receiver_uptime"], 3600)
        self.assertEqual(values["snr"], 16)
        self.assertEqual(values["samples_dropped_since_start"], 7)
        self.assertAlmostEqual(values["max_distance_24h"], haversine_km(0, 0, 0, 1), places=3)
        self.assertAlmostEqual(values["outline_max_altitude_24h"], 38000 * FT_TO_M)
        self.assertAlmostEqual(values["closest_aircraft"], 3 * 1.852)
        self.assertEqual(values["closest_aircraft_bearing"], 90)
        self.assertTrue(all(value is not None for value in values.values()))

    def test_closest_aircraft_uses_position_when_r_dst_is_missing(self):
        ctx = PollContext(
            stats=STATS,
            receiver_lat=0.0,
            receiver_lon=0.0,
            aircraft=[
                {"hex": "far", "lat": 0.0, "lon": 1.0},
                {"hex": "near", "lat": 0.0, "lon": 0.2},
                {"hex": "nopos"},
            ],
        )
        distance = next(s for s in CATALOG if s.component_id == "closest_aircraft").extract(ctx)
        bearing = next(s for s in CATALOG if s.component_id == "closest_aircraft_bearing").extract(ctx)
        self.assertAlmostEqual(distance, haversine_km(0, 0, 0, 0.2), places=3)
        self.assertAlmostEqual(bearing, bearing_degrees(0, 0, 0, 0.2), places=3)
        self.assertAlmostEqual(bearing_degrees(0, 0, 0, 1), 90, places=3)
        self.assertAlmostEqual(bearing_degrees(0, 0, 1, 0), 0, places=3)

    def test_aircraft_today_is_empty_until_the_tracker_fills_it(self):
        ctx = PollContext(stats=STATS, aircraft=[{"hex": "abc"}])
        value = next(s for s in CATALOG if s.component_id == "aircraft_today").extract(ctx)
        self.assertIsNone(value)

    def test_closest_aircraft_clears_when_none_have_a_position(self):
        ctx = PollContext(stats=STATS, aircraft=[{"hex": "abc"}])
        distance = next(s for s in CATALOG if s.component_id == "closest_aircraft").extract(ctx)
        bearing = next(s for s in CATALOG if s.component_id == "closest_aircraft_bearing").extract(ctx)
        self.assertEqual(distance, "")
        self.assertEqual(bearing, "")

    def test_outline_distance_needs_receiver_position(self):
        ctx = PollContext(stats=STATS, outline=OUTLINE)
        self.assertIsNone(next(s for s in CATALOG if s.component_id == "max_distance_24h").extract(ctx))
        self.assertEqual(
            next(s for s in CATALOG if s.component_id == "outline_max_altitude_24h").extract(ctx),
            38000 * FT_TO_M,
        )

    def test_format_state_uses_precision(self):
        self.assertEqual(format_state(18.5200001, 1), "18.5")
        self.assertEqual(format_state(3, None), "3")
        self.assertEqual(format_state(3600.0, 0), "3600")


if __name__ == "__main__":
    unittest.main()
