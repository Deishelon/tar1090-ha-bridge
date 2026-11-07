import math
from dataclasses import dataclass
from typing import Callable

from ha_core import DeviceClass, StateClass
from ha_entity import HaEntity


# readsb writes r_dst as nautical miles: receiver_distance / 1852.
NMI_TO_KM = 1.852


@dataclass
class PollContext:
    stats: dict
    outline: dict | None = None
    receiver_lat: float | None = None
    receiver_lon: float | None = None
    aircraft: list | None = None


def dig(data: dict, dotted: str):
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def as_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def number_at(dotted: str) -> Callable[[PollContext], int | float | None]:
    def extract(ctx: PollContext):
        return as_number(dig(ctx.stats, dotted))

    return extract


def kilometers_at(dotted: str) -> Callable[[PollContext], float | None]:
    def extract(ctx: PollContext):
        meters = as_number(dig(ctx.stats, dotted))
        if meters is None:
            return None
        return float(meters) / 1000.0

    return extract


def aircraft_now(ctx: PollContext):
    with_position = as_number(ctx.stats.get("aircraft_with_pos"))
    without_position = as_number(ctx.stats.get("aircraft_without_pos"))
    if with_position is None and without_position is None:
        return None
    return int(with_position or 0) + int(without_position or 0)


def aircraft_type(type_name: str) -> Callable[[PollContext], int | None]:
    def extract(ctx: PollContext):
        counts = ctx.stats.get("aircraft_count_by_type")
        if not isinstance(counts, dict):
            return None
        value = as_number(counts.get(type_name))
        if value is None:
            return 0
        return int(value)

    return extract


def aircraft_other_types(ctx: PollContext):
    counts = ctx.stats.get("aircraft_count_by_type")
    if not isinstance(counts, dict):
        return None
    total = 0
    for type_name, value in counts.items():
        if type_name == "adsb_icao":
            continue
        number = as_number(value)
        if number is not None:
            total += int(number)
    return total


def signal_to_noise(ctx: PollContext):
    signal = as_number(dig(ctx.stats, "last1min.local.signal"))
    noise = as_number(dig(ctx.stats, "last1min.local.noise"))
    if signal is None or noise is None:
        return None
    return float(signal) - float(noise)


def messages_per_second(ctx: PollContext):
    messages = as_number(dig(ctx.stats, "last1min.messages"))
    start = as_number(dig(ctx.stats, "last1min.start"))
    end = as_number(dig(ctx.stats, "last1min.end"))
    if messages is None or start is None or end is None:
        return None
    window = float(end) - float(start)
    if window <= 0:
        return None
    return float(messages) / window


def receiver_uptime(ctx: PollContext):
    start = as_number(dig(ctx.stats, "total.start"))
    end = as_number(dig(ctx.stats, "total.end"))
    if start is None or end is None:
        return None
    return max(0.0, float(end) - float(start))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def outline_points(ctx: PollContext):
    if not isinstance(ctx.outline, dict):
        return None
    points = dig(ctx.outline, "actualRange.last24h.points")
    if not isinstance(points, list) or not points:
        return None
    return points


def max_distance_24h(ctx: PollContext):
    if ctx.receiver_lat is None or ctx.receiver_lon is None:
        return None
    points = outline_points(ctx)
    if points is None:
        return None
    best = None
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lat = as_number(point[0])
        lon = as_number(point[1])
        if lat is None or lon is None:
            continue
        distance = haversine_km(ctx.receiver_lat, ctx.receiver_lon, float(lat), float(lon))
        if best is None or distance > best:
            best = distance
    return best


def aircraft_distance_km(aircraft: dict, ctx: PollContext) -> float | None:
    reported = as_number(aircraft.get("r_dst"))
    if reported is not None and reported >= 0:
        return float(reported) * NMI_TO_KM
    if ctx.receiver_lat is None or ctx.receiver_lon is None:
        return None
    lat = as_number(aircraft.get("lat"))
    lon = as_number(aircraft.get("lon"))
    if lat is None or lon is None:
        return None
    return haversine_km(ctx.receiver_lat, ctx.receiver_lon, float(lat), float(lon))


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def aircraft_bearing_degrees(aircraft: dict, ctx: PollContext) -> float | None:
    reported = as_number(aircraft.get("r_dir"))
    if reported is not None:
        return float(reported) % 360.0
    if ctx.receiver_lat is None or ctx.receiver_lon is None:
        return None
    lat = as_number(aircraft.get("lat"))
    lon = as_number(aircraft.get("lon"))
    if lat is None or lon is None:
        return None
    return bearing_degrees(ctx.receiver_lat, ctx.receiver_lon, float(lat), float(lon))


def closest_positioned_aircraft(ctx: PollContext) -> dict | str | None:
    """Nearest aircraft with a position.

    None means the aircraft list was not fetched. An empty string means it was
    fetched and no aircraft has a distance, so Home Assistant clears the value.
    """
    if ctx.aircraft is None:
        return None
    best_aircraft = None
    best_distance = None
    for aircraft in ctx.aircraft:
        if not isinstance(aircraft, dict):
            continue
        distance = aircraft_distance_km(aircraft, ctx)
        if distance is None:
            continue
        if best_distance is None or distance < best_distance:
            best_aircraft = aircraft
            best_distance = distance
    if best_aircraft is None:
        return ""
    return best_aircraft


def closest_aircraft_km(ctx: PollContext):
    found = closest_positioned_aircraft(ctx)
    if not isinstance(found, dict):
        return found
    return aircraft_distance_km(found, ctx)


def closest_aircraft_bearing(ctx: PollContext):
    found = closest_positioned_aircraft(ctx)
    if not isinstance(found, dict):
        return found
    return aircraft_bearing_degrees(found, ctx)


def outline_max_altitude_ft(ctx: PollContext):
    points = outline_points(ctx)
    if points is None:
        return None
    best = None
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 3:
            continue
        altitude = as_number(point[2])
        if altitude is None:
            continue
        if best is None or altitude > best:
            best = altitude
    return best


@dataclass(frozen=True)
class SensorDef:
    component_id: str
    name: str
    extract: Callable[[PollContext], int | float | None]
    unit: str = ""
    device_class: DeviceClass = DeviceClass.NONE
    state_class: StateClass = StateClass.measurement
    precision: int | None = None
    icon: str | None = None
    entity_category: str | None = None

    def to_entity(self, ctx: PollContext, availability_topic: str) -> HaEntity:
        def lookup(extract=self.extract, context=ctx):
            return extract(context)

        return HaEntity(
            component_id=self.component_id,
            name=self.name,
            device_class=self.device_class,
            state_class=self.state_class,
            unit=self.unit,
            lookup=lookup,
            suggested_display_precision=self.precision,
            icon=self.icon,
            entity_category=self.entity_category,
            availability_topic=availability_topic,
        )


# Add a sensor by appending a SensorDef. `extract` receives one poll of stats.json
# plus any derived values already filled on PollContext.
CATALOG: list[SensorDef] = [
    SensorDef(
        component_id="aircraft_now",
        name="Aircraft Now",
        extract=aircraft_now,
        icon="mdi:airplane",
    ),
    SensorDef(
        component_id="aircraft_with_position",
        name="Aircraft With Position",
        extract=number_at("aircraft_with_pos"),
        icon="mdi:airplane-marker",
    ),
    SensorDef(
        component_id="aircraft_without_position",
        name="Aircraft Without Position",
        extract=number_at("aircraft_without_pos"),
        icon="mdi:airplane-off",
    ),
    SensorDef(
        component_id="aircraft_adsb_icao",
        name="Aircraft ADS-B",
        extract=aircraft_type("adsb_icao"),
        icon="mdi:airplane",
    ),
    SensorDef(
        component_id="aircraft_other",
        name="Aircraft Other Types",
        extract=aircraft_other_types,
        icon="mdi:airplane-alert",
    ),
    SensorDef(
        component_id="closest_aircraft",
        name="Closest Aircraft",
        extract=closest_aircraft_km,
        unit="km",
        device_class=DeviceClass.DISTANCE,
        precision=1,
        icon="mdi:map-marker-radius",
    ),
    SensorDef(
        component_id="closest_aircraft_bearing",
        name="Closest Aircraft Bearing",
        extract=closest_aircraft_bearing,
        unit="°",
        state_class=StateClass.NONE,
        precision=0,
        icon="mdi:compass",
    ),
    SensorDef(
        component_id="max_distance_24h",
        name="Max Distance (24 h)",
        extract=max_distance_24h,
        unit="km",
        device_class=DeviceClass.DISTANCE,
        precision=1,
        icon="mdi:map-marker-distance",
    ),
    SensorDef(
        component_id="outline_max_altitude_24h",
        name="Outline Max Altitude (24 h)",
        extract=outline_max_altitude_ft,
        unit="ft",
        precision=0,
        icon="mdi:arrow-expand-up",
    ),
    SensorDef(
        component_id="tracks_15min",
        name="Aircraft Tracks (15 min)",
        extract=number_at("last15min.tracks.all"),
        icon="mdi:airplane-clock",
    ),
    SensorDef(
        component_id="messages_1min",
        name="Messages (1 min)",
        extract=number_at("last1min.messages"),
        icon="mdi:message-text",
    ),
    SensorDef(
        component_id="messages_per_second",
        name="Messages per Second",
        extract=messages_per_second,
        unit="messages/s",
        precision=2,
        icon="mdi:speedometer",
    ),
    SensorDef(
        component_id="messages_15min",
        name="Messages (15 min)",
        extract=number_at("last15min.messages"),
        icon="mdi:message-text",
    ),
    SensorDef(
        component_id="max_distance_15min",
        name="Max Distance (15 min)",
        extract=kilometers_at("last15min.max_distance"),
        unit="km",
        device_class=DeviceClass.DISTANCE,
        precision=1,
        icon="mdi:map-marker-distance",
    ),
    SensorDef(
        component_id="tracks_since_start",
        name="Aircraft Tracks Since Start",
        extract=number_at("total.tracks.all"),
        state_class=StateClass.total_increasing,
        icon="mdi:airplane-clock",
    ),
    SensorDef(
        component_id="messages_since_start",
        name="Messages Since Start",
        extract=number_at("total.messages"),
        state_class=StateClass.total_increasing,
        icon="mdi:message-text",
    ),
    SensorDef(
        component_id="positions_since_start",
        name="Positions Since Start",
        extract=number_at("total.position_count_total"),
        state_class=StateClass.total_increasing,
        icon="mdi:crosshairs-gps",
    ),
    SensorDef(
        component_id="max_distance_since_start",
        name="Max Distance Since Start",
        extract=kilometers_at("total.max_distance"),
        unit="km",
        device_class=DeviceClass.DISTANCE,
        precision=1,
        icon="mdi:map-marker-distance",
    ),
    SensorDef(
        component_id="receiver_uptime",
        name="Receiver Uptime",
        extract=receiver_uptime,
        unit="s",
        device_class=DeviceClass.DURATION,
        precision=0,
        icon="mdi:timer-outline",
    ),
    SensorDef(
        component_id="single_message_tracks_since_start",
        name="Single Message Tracks Since Start",
        extract=number_at("total.tracks.single_message"),
        state_class=StateClass.total_increasing,
        icon="mdi:airplane-remove",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="signal",
        name="Signal (1 min)",
        extract=number_at("last1min.local.signal"),
        unit="dB",
        precision=1,
        icon="mdi:signal",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="noise",
        name="Noise (1 min)",
        extract=number_at("last1min.local.noise"),
        unit="dB",
        precision=1,
        icon="mdi:waveform",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="snr",
        name="Signal to Noise (1 min)",
        extract=signal_to_noise,
        unit="dB",
        precision=1,
        icon="mdi:signal-variant",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="gain",
        name="Tuner Gain",
        extract=number_at("gain_db"),
        unit="dB",
        precision=1,
        icon="mdi:amplifier",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="frequency_error",
        name="Frequency Error",
        extract=number_at("estimated_ppm"),
        unit="ppm",
        precision=1,
        icon="mdi:sine-wave",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="strong_signals_1min",
        name="Strong Signals (1 min)",
        extract=number_at("last1min.local.strong_signals"),
        icon="mdi:flash",
        entity_category="diagnostic",
    ),
    SensorDef(
        component_id="samples_dropped_since_start",
        name="Samples Dropped Since Start",
        extract=number_at("total.local.samples_dropped"),
        state_class=StateClass.total_increasing,
        icon="mdi:trash-can-outline",
        entity_category="diagnostic",
    ),
]


def format_state(value, precision: int | None) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("Cannot format an empty state")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if precision is not None:
            return f"{value:.{precision}f}"
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)
