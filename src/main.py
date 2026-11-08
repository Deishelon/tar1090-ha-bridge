import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from ha_device import HaDevice
from http_json import fetch_json
from mqtt_paho import MqttClient
from stats_catalog import CATALOG, PollContext, as_number, format_state

logger = logging.getLogger("tar1090-ha-bridge")
REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_INTERVAL_SEC = 600


def load_env_file(path: Path, override: bool = False):
    """Load KEY=value lines from a .env file. Existing variables win unless override is set."""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or (key in os.environ and not override):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def resolve_env_path(argv: list[str]) -> Path | None:
    if len(argv) > 2:
        raise SystemExit("Usage: python src/main.py [env-file]")
    if len(argv) == 2:
        path = Path(argv[1]).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    default = REPO_ROOT / ".env"
    if default.is_file():
        return default
    return None


DEFAULT_BASE_URL = "http://tar1090.local/data"


def data_url(base_url: str, filename: str) -> str:
    return base_url.rstrip("/") + "/" + filename


def device_id_for(base_url: str, prefix: str) -> str:
    host = urlparse(base_url).hostname or "receiver"
    safe_host = re.sub(r"[^a-zA-Z0-9_-]+", "-", host).strip("-") or "receiver"
    if prefix and not prefix.endswith("-"):
        prefix = prefix + "-"
    return f"{prefix}{safe_host}"


def availability_topic(discovery_prefix: str, device_id: str) -> str:
    return f"{discovery_prefix}/sensor/{device_id}/availability"


def receiver_model(receiver: dict | None) -> str | None:
    if not isinstance(receiver, dict):
        return None
    version = receiver.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def receiver_position(receiver: dict | None) -> tuple[float | None, float | None]:
    if not isinstance(receiver, dict):
        return None, None
    lat = as_number(receiver.get("lat"))
    lon = as_number(receiver.get("lon"))
    if lat is None or lon is None:
        return None, None
    return float(lat), float(lon)


def env_coordinate(name: str, low: float, high: float) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s is not a number: %s", name, raw)
        return None
    if not low <= value <= high:
        logger.warning("%s is outside %.0f..%.0f: %s", name, low, high, raw)
        return None
    return value


def publish_states(mqtt: MqttClient, device: HaDevice, discovery_prefix: str):
    for entity in device.entities:
        try:
            value = entity.lookup()
            if value is None:
                continue
            payload = format_state(value, entity.suggested_display_precision)
        except Exception as err:
            logger.error(f"Failed to lookup entity {entity.component_id}: {err}")
            continue
        mqtt.publish(
            topic=entity.state_topic(device.device_id, discovery_prefix),
            payload=payload,
            retain=True,
        )


async def fetch_optional(url: str, timeout: float, label: str) -> dict | None:
    if not url:
        return None
    try:
        return await asyncio.to_thread(fetch_json, url, timeout)
    except Exception as err:
        logger.warning(f"Failed to fetch {label}: {err}")
        return None


async def poll_once(stats_url: str, timeout: float) -> dict | None:
    try:
        return await asyncio.to_thread(fetch_json, stats_url, timeout)
    except Exception as err:
        logger.error(f"Failed to fetch stats: {err}")
        return None


async def run(argv: list[str] | None = None):
    args = sys.argv if argv is None else argv
    env_path = resolve_env_path(args)
    if len(args) > 1 and (env_path is None or not env_path.is_file()):
        logger.error("Env file not found: %s", args[1])
        raise SystemExit(1)
    if env_path is None:
        logger.info("No env file found. Using the process environment and built-in defaults.")
    else:
        load_env_file(env_path, override=len(args) > 1)
        logger.info("Loaded env file %s", env_path)
    base_url = os.getenv("TAR1090_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    stats_url = data_url(base_url, "stats.json")
    outline_url = data_url(base_url, "outline.json")
    receiver_url = data_url(base_url, "receiver.json")
    aircraft_url = data_url(base_url, "aircraft.json")
    timeout = float(os.getenv("TAR1090_TIMEOUT_SEC", "10"))
    poll_interval = float(os.getenv("POLL_INTERVAL_SEC", "20"))

    discovery_prefix = os.getenv("MQTT_HA_PREFIX", "homeassistant")
    device_id = device_id_for(base_url, os.getenv("HA_DEVICE_ID_PREFIX", "tar1090"))
    device_name = os.getenv("HA_DEVICE_NAME", "tar1090")
    availability = availability_topic(discovery_prefix, device_id)

    broker = os.getenv("MQTT_BROKER", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    client_id = os.getenv("MQTT_CLIENT_ID", "tar1090-ha-bridge")
    username = os.getenv("MQTT_USERNAME") or None
    password = os.getenv("MQTT_PASSWORD") or None
    fallback_lat = env_coordinate("TAR1090_LAT", -90, 90)
    fallback_lon = env_coordinate("TAR1090_LON", -180, 180)

    try:
        mqtt = MqttClient(broker, port, client_id, username, password, will_topic=availability)
    except (ConnectionRefusedError, OSError) as err:
        logger.error(f"Failed to connect to MQTT broker: {err}")
        raise SystemExit(1) from err

    device = HaDevice(
        device_id=device_id,
        device_name=device_name,
        model="tar1090",
        manufacturer="readsb",
    )
    last_discovery = 0.0
    last_outline = None
    receiver_lat = None
    receiver_lon = None
    origin_source = None

    try:
        while True:
            started = time.perf_counter()
            stats = await poll_once(stats_url, timeout)
            if stats is None:
                mqtt.publish(availability, "offline", retain=True)
            else:
                outline = await fetch_optional(outline_url, timeout, "outline.json")
                if outline is not None:
                    last_outline = outline
                receiver = await fetch_optional(receiver_url, timeout, "receiver.json")
                lat, lon = receiver_position(receiver)
                source = origin_source
                if lat is not None and lon is not None:
                    receiver_lat, receiver_lon = lat, lon
                    source = "receiver.json"
                elif receiver_lat is None and fallback_lat is not None and fallback_lon is not None:
                    receiver_lat, receiver_lon = fallback_lat, fallback_lon
                    source = "TAR1090_LAT/TAR1090_LON"
                if source != origin_source and receiver_lat is not None and receiver_lon is not None:
                    logger.info("Receiver origin from %s: %.5f, %.5f", source, receiver_lat, receiver_lon)
                    origin_source = source
                model = receiver_model(receiver)
                if model:
                    device.model = model

                aircraft_payload = await fetch_optional(aircraft_url, timeout, "aircraft.json")
                aircraft = None
                if isinstance(aircraft_payload, dict):
                    raw_aircraft = aircraft_payload.get("aircraft")
                    if isinstance(raw_aircraft, list):
                        aircraft = raw_aircraft
                    else:
                        logger.warning("aircraft.json did not contain an aircraft list")

                context = PollContext(
                    stats=stats,
                    outline=last_outline,
                    receiver_lat=receiver_lat,
                    receiver_lon=receiver_lon,
                    aircraft=aircraft,
                )
                entities = [sensor.to_entity(context, availability) for sensor in CATALOG]
                device.set_entities(entities)
                now = time.monotonic()
                if now - last_discovery >= DISCOVERY_INTERVAL_SEC:
                    topic, payload = device.get_discovery(discovery_prefix)
                    mqtt.publish(topic, json.dumps(payload), retain=True)
                    last_discovery = now
                mqtt.publish(availability, "online", retain=True)
                publish_states(mqtt, device, discovery_prefix)
                logger.info(
                    "Published %s entities in %.3f s",
                    len(entities),
                    time.perf_counter() - started,
                )
            await asyncio.sleep(poll_interval)
    finally:
        try:
            mqtt.publish(availability, "offline", retain=True)
        except Exception:
            logger.warning("Failed to publish offline availability")
        mqtt.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Stopping...")
