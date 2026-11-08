import json
import logging
import os
from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("tar1090-ha-bridge")


def normalize_hex(value) -> str | None:
    if not isinstance(value, str):
        return None
    hex_id = value.strip().lower()
    if not hex_id:
        return None
    return hex_id


def system_timezone() -> tzinfo:
    """IANA timezone for this machine, so midnight follows DST while the process stays up."""
    tz_env = os.environ.get("TZ", "").strip()
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except ZoneInfoNotFoundError:
            logger.warning("TZ is not a known timezone: %s", tz_env)
    localtime = Path("/etc/localtime")
    if localtime.exists():
        parts = localtime.resolve().parts
        if "zoneinfo" in parts:
            name = "/".join(parts[parts.index("zoneinfo") + 1:])
            try:
                return ZoneInfo(name)
            except ZoneInfoNotFoundError:
                logger.warning("Could not use system timezone %s", name)
    return datetime.now().astimezone().tzinfo


def resolve_timezone(name: str | None) -> tzinfo:
    """Timezone for the midnight reset. An empty name uses the machine timezone."""
    if name is None or not name.strip():
        return system_timezone()
    try:
        return ZoneInfo(name.strip())
    except ZoneInfoNotFoundError:
        logger.warning("AIRCRAFT_TODAY_TZ is not a known timezone: %s", name)
        return system_timezone()


class DailyAircraftTracker:
    """Distinct aircraft hexes seen since local midnight.

    The set is stored on disk so a bridge restart does not clear the day.
    """

    def __init__(self, path: Path, tz: tzinfo | None = None, now: datetime | None = None):
        self.path = Path(path)
        self.tz = tz or system_timezone()
        self._day: str | None = None
        self._hexes: set[str] = set()
        self.load()
        self.roll(now)

    def load(self) -> None:
        self._day = None
        self._hexes = set()
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as err:
            logger.warning("Ignoring unreadable aircraft-today state %s: %s", self.path, err)
            return
        if not isinstance(payload, dict):
            return
        day = payload.get("day")
        hexes = payload.get("hexes")
        if not isinstance(day, str) or not day:
            return
        loaded: set[str] = set()
        if isinstance(hexes, list):
            for item in hexes:
                hex_id = normalize_hex(item)
                if hex_id:
                    loaded.add(hex_id)
        self._day = day
        self._hexes = loaded

    def save(self) -> None:
        payload = {"day": self._day, "hexes": sorted(self._hexes)}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as err:
            logger.warning("Failed to save aircraft-today state %s: %s", self.path, err)

    def local_day(self, now: datetime | None = None) -> str:
        current = now or datetime.now(self.tz)
        if current.tzinfo is None:
            current = current.replace(tzinfo=self.tz)
        else:
            current = current.astimezone(self.tz)
        return current.date().isoformat()

    def roll(self, now: datetime | None = None) -> None:
        day = self.local_day(now)
        if self._day == day:
            return
        if self._day is not None:
            logger.info("Aircraft today reset for %s", day)
        self._day = day
        self._hexes = set()
        self.save()

    def observe(self, aircraft: list | None, now: datetime | None = None) -> int:
        self.roll(now)
        if isinstance(aircraft, list):
            changed = False
            for item in aircraft:
                if not isinstance(item, dict):
                    continue
                hex_id = normalize_hex(item.get("hex"))
                if hex_id is None or hex_id in self._hexes:
                    continue
                self._hexes.add(hex_id)
                changed = True
            if changed:
                self.save()
        return len(self._hexes)

    @property
    def count(self) -> int:
        return len(self._hexes)
