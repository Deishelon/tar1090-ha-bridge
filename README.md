# tar1090 to Home Assistant Bridge

**tar1090 / readsb stats to Home Assistant via MQTT with auto-discovery.**

This tool polls your tar1090 `stats.json`, `outline.json`, and `receiver.json`, and publishes a small set of sensors to
an MQTT broker using [Home Assistant MQTT discovery](https://www.home-assistant.io/integrations/mqtt/).

The layout matches [powerwall-ha-bridge](https://github.com/Deishelon/powerwall-ha-bridge): one Home Assistant device,
one MQTT discovery payload, and a catalog of sensors you can extend.

## Features

- **Aircraft now**: total, with position, without position, ADS-B, and every other type summed together.
- **Recent window**: messages, tracks, and max distance from the readsb 1 minute and 15 minute buckets.
- **Since readsb start**: messages, positions, tracks, max distance, uptime, dropped samples.
- **24 h outline**: farthest contact and highest outline altitude from `outline.json`, which readsb keeps on the
  receiver.
- **Receiver health**: signal, noise, SNR, gain, frequency error, strong signals.
- **HA auto-discovery**: entities appear under one MQTT device.

`stats.json` has `last1min`, `last5min`, `last15min`, and `total`. `total` covers the time since the readsb process
started. The rolling 24 hour figure in this bridge comes from `outline.json` (`actualRange.last24h`), which readsb
maintains. Restarting the bridge does not clear it.

`tracks.all` counts tracks. A track ends about 5 minutes after the last message, and the same aircraft can open another
track later. None of the tar1090 JSON files publish a unique aircraft total for 24 hours, so this bridge does not count
hexes itself.

## Sensors

| Sensor                            | Source                                                 |
|-----------------------------------|--------------------------------------------------------|
| Aircraft Now                      | `aircraft_with_pos` + `aircraft_without_pos`           |
| Aircraft With Position            | `aircraft_with_pos`                                    |
| Aircraft Without Position         | `aircraft_without_pos`                                 |
| Aircraft ADS-B                    | `aircraft_count_by_type.adsb_icao`                     |
| Aircraft Other Types              | every other `aircraft_count_by_type` entry             |
| Closest Aircraft                  | nearest `aircraft.json` position, ground distance in km |
| Closest Aircraft Bearing         | bearing from the receiver to that aircraft, degrees     |
| Max Distance (24 h)               | farthest `outline.json` point from the receiver, in km |
| Outline Max Altitude (24 h)       | highest altitude on those outline points, in m         |
| Aircraft Tracks (15 min)          | `last15min.tracks.all`                                 |
| Messages (1 min) / (15 min)       | `last1min.messages`, `last15min.messages`              |
| Messages per Second               | `last1min.messages` divided by that window's length    |
| Max Distance (15 min)             | `last15min.max_distance`, published in km              |
| Aircraft Tracks Since Start       | `total.tracks.all`                                     |
| Messages Since Start              | `total.messages`                                       |
| Positions Since Start             | `total.position_count_total`                           |
| Max Distance Since Start          | `total.max_distance`, published in km                  |
| Receiver Uptime                   | `total.end - total.start`, seconds                     |
| Single Message Tracks Since Start | `total.tracks.single_message`                          |
| Signal / Noise / SNR (1 min)      | `last1min.local.signal` and `noise`                    |
| Tuner Gain                        | `gain_db`                                              |
| Frequency Error                   | `estimated_ppm`                                        |
| Strong Signals (1 min)            | `last1min.local.strong_signals`                        |
| Samples Dropped Since Start       | `total.local.samples_dropped`                          |

Signal, noise, gain, and the other receiver counters are Home Assistant diagnostic entities.

## Usage

### Run locally (no systemd)

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
cp .env.example .env
```

Edit `.env` and set `MQTT_BROKER` to a broker you can reach. The copied example uses `localhost`. The default `TAR1090_BASE_URL` is `https://plane.home.deishelon.com/map/data`.

```bash
python src/main.py
python src/main.py /path/to/other.env
```

With no argument, the script loads `.env` from the repo root when that file exists. A path argument is the env file to load, absolute or relative to the working directory, and values in that file replace variables already set in the process. The log line `Loaded env file ...` is the file that was used. The next line is the MQTT host it will connect to.

In PyCharm, open the `src/main.py` run configuration and put the env file in **Script parameters**:

```text
/home/deishelon/PycharmProjects/tar1090-ha-bridge/.env
```

Logs go to the terminal. Stop the process with Ctrl-C. Each poll logs how many entities it published. The process only talks to the tar1090 URLs and the MQTT broker. It does not configure Home Assistant.

Run the tests with:

```bash
python -m unittest discover -s tests -v
```

### Run as systemd service (Linux)

```bash
./install.sh
nano .env
sudo systemctl start tar1090-ha-bridge
```

`install.sh` writes a systemd unit whose start command is:

```text
python src/main.py /path/to/this/repo/.env
```

That is the same env-file argument as a local run. The unit does not use systemd `EnvironmentFile`, so the file is parsed only by the script. `install.sh` creates `venv`, installs Python dependencies, writes `.env` from `.env.example` when `.env` is missing, and installs the unit. It does not start the service.

If the unit was installed before this change, run `./install.sh` again, then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart tar1090-ha-bridge
```

Logs:

```bash
journalctl -u tar1090-ha-bridge -f
```

After `git pull`, restart the service:

```bash
sudo systemctl restart tar1090-ha-bridge
```

## Configuration

| Variable              | Description                                                      | Default                                     |
|-----------------------|------------------------------------------------------------------|-----------------------------|
| `TAR1090_BASE_URL`    | Directory with `stats.json`, `outline.json`, `receiver.json`, and `aircraft.json` | `https://plane.home.deishelon.com/map/data` |
| `TAR1090_LAT`         | Receiver latitude, used only when `receiver.json` has no position                   |                                                 |
| `TAR1090_LON`         | Receiver longitude, used only when `receiver.json` has no position                  |                                                 |
| `TAR1090_TIMEOUT_SEC` | HTTP timeout                                                     | `10`                                        |
| `POLL_INTERVAL_SEC`   | Seconds between polls                                            | `20`                                        |
| `MQTT_BROKER`          | MQTT broker host                             | `localhost`                                            |
| `MQTT_PORT`            | MQTT port                                    | `1883`                                                 |
| `MQTT_USERNAME`        | MQTT username                                |                                                        |
| `MQTT_PASSWORD`        | MQTT password                                |                                                        |
| `MQTT_CLIENT_ID`       | MQTT client ID                               | `tar1090-ha-bridge`                                    |
| `MQTT_HA_PREFIX`       | HA discovery prefix                          | `homeassistant`                                        |
| `HA_DEVICE_ID_PREFIX`  | Prefix for the device id                     | `tar1090`                                              |
| `HA_DEVICE_NAME`       | Device name in Home Assistant                | `tar1090`                                              |

The receiver position comes from `receiver.json` `lat` and `lon`. `TAR1090_LAT` and `TAR1090_LON` are used only when that file has no position. Closest Aircraft uses readsb's `r_dst` when an aircraft has one, converted from nautical miles to kilometres. Otherwise it is the great-circle distance from the receiver position to the aircraft `lat`/`lon`. Closest Aircraft Bearing uses `r_dir` for that same aircraft: degrees clockwise from true north, where 0 is north and 90 is east. With no positioned aircraft, both sensors are cleared.

Max Distance (24 h) is the great-circle distance from `receiver.json` lat/lon to the farthest point in `outline.json`.
Outline Max Altitude (24 h) is the highest altitude stored on those points, converted from feet to metres. readsb writes that file for the map outline,
using a 24 hour window by default.

## Home Assistant Setup

1. Add the [MQTT](https://www.home-assistant.io/integrations/mqtt/) integration to your Home Assistant instance.
2. Run this script.
3. Entities auto-discover under the MQTT integration as one device.

## Adding a stat

Sensors live in `src/stats_catalog.py` as `CATALOG`. A direct field is a path. A derived value is a function that takes
`PollContext`.

```python
SensorDef(
    component_id="messages_5min",
    name="Messages (5 min)",
    extract=number_at("last5min.messages"),
    icon="mdi:message-text",
),
```

```python
def positions_per_message(ctx: PollContext):
    messages = as_number(dig(ctx.stats, "last15min.messages"))
    positions = as_number(dig(ctx.stats, "last15min.position_count_total"))
    if not messages:
        return None
    return float(positions or 0) / float(messages)
```

Restart the bridge after editing the catalog. The next discovery payload replaces the device's component list.

Set `state_class` to `StateClass.total_increasing` for a counter that grows and may reset when readsb restarts. Use
`StateClass.measurement` for a live value. Use `entity_category="diagnostic"` for receiver health that should stay off
the main device page.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Acknowledgments

- [tar1090](https://github.com/wiedehopf/tar1090) and [readsb](https://github.com/wiedehopf/readsb) provide
  `stats.json`, `outline.json`, and `receiver.json`.
- The MQTT discovery shape follows [powerwall-ha-bridge](https://github.com/Deishelon/powerwall-ha-bridge).
