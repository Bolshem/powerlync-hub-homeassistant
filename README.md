# Powerlync Hub — Home Assistant Integration

[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A custom Home Assistant integration that exposes real-time energy monitoring data from the **BC Hydro Powerlync Hub** (by Powerley) as sensors in Home Assistant — with no cloud dependency and no reverse-engineering of proprietary protocols.

---

## Background

The BC Hydro Powerlync Hub is a smart energy monitor that reads your electricity meter via Zigbee (Smart Energy Profile) and reports real-time consumption data to the Powerley cloud. It retails for ~$75 and is available to BC Hydro customers.

While the device communicates upstream to AWS IoT Core using mutual TLS (making cloud traffic interception impractical), it also advertises itself as an **Apple HomeKit accessory** over mDNS on your local network. This integration leverages that HomeKit interface to extract energy data locally, without any cloud dependency.

---

## Architecture

```
 Zigbee (Smart Energy Profile)
 ┌─────────────┐                    ┌──────────────────┐
 │ BC Hydro    │ ─────────────────► │ Powerlync Hub    │
 │ Smart Meter │                    │ (Powerley device)│
 └─────────────┘                    └────────┬─────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                   │
                    HomeKit HAP        MQTTS/TLS           mDNS
                    (port 80)     AWS IoT Core          _hap._tcp
                          │          (cloud)                 │
                          ▼                                   │
               ┌──────────────────┐                          │
               │  Home Assistant  │ ◄────────────────────────┘
               │                  │  pairs via HomeKit Controller
               │  homekit_        │  integration
               │  controller      │
               │                  │
               │  powerlync_      │  reads characteristics
               │  energy          │  every 10 seconds
               │  (this addon)    │
               └──────────────────┘
```

### How it works

1. **HomeKit pairing**: The Powerlync hub speaks the HomeKit Accessory Protocol (HAP) over HTTP on port 80. You pair it with HA's built-in `homekit_controller` integration using the 8-digit code printed on the device label.

2. **Custom HAP service**: In addition to a standard HomeKit smart plug service, the hub exposes a custom Powerley service (UUID `DBDE3C5B-D7EA-434B-8684-356FAFAFD1A6`) containing energy monitoring characteristics not defined in the official HomeKit spec. These are the characteristics this integration reads.

3. **Polling**: The `homekit_controller` integration ignores unknown custom UUIDs and does not expose them as entities. This custom integration calls `pairing.get_characteristics()` directly every 10 seconds to read the energy data and expose it as standard HA sensor entities.

### Custom HAP Characteristics

| IID | Name | Format | Example |
|-----|------|--------|---------|
| 21 | Instantaneous Demand | string | `"000000.859 kW"` |
| 22 | Current Summation Delivered | string | `"064732.4 kWh"` |
| 23 | Current Summation Received | string | `"000000.1 kWh"` |
| 24 | Local Instantaneous Demand | float | `859.0` (watts) |
| 25 | Local Summation Delivered | float | `64732.4` (kWh) |
| 27 | Meter Time (UTC) | int | Unix timestamp |

All characteristics have `"perms": ["pr", "ev"]` — they support both read and push notifications, though this integration uses polling for simplicity and reliability.

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations → ⋮ → Custom repositories**
3. Add URL: `https://github.com/Bolshem/powerlync-hub-homeassistant`
4. Category: **Integration**
5. Click **Add**, then search for **Powerlync** and install

### Manual

Copy the `custom_components/powerlync_energy` folder into your HA
`config/custom_components/` directory and restart Home Assistant.

---

## Prerequisites

- Home Assistant 2024.1 or newer
- The `homekit_controller` integration (built into HA — no installation needed)
- The Powerlync Hub physically installed and connected to your local network
- The **8-digit HomeKit setup code** printed on the label on your device

---

## Step 1 — Pair the Powerlync Hub with Home Assistant

The Powerlync Hub is a HomeKit accessory. Before this custom integration can work, you must pair the device with HA's built-in HomeKit Controller integration.

> **Note:** If you have previously paired the hub with the Apple Home app or the HydroHome/Powerley app, you may need to **factory reset** the device first to clear the existing pairing. HomeKit devices can only be paired with one controller at a time.

### 1.1 — Connect the hub to your network

Ensure the Powerlync Hub is powered on and connected to your Wi-Fi or LAN. The HydroHome app can be used for initial network setup if needed (iOS or Android).

### 1.2 — Add via Home Assistant

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **HomeKit Controller** and select it
4. HA will scan for HomeKit devices on your network. You should see **Powerlync-001-XXXXXX** appear in the list
5. If it does not appear automatically, click **Enter device pairing code manually**
6. Enter the **8-digit code** from the label on your Powerlync Hub (no dashes)
7. Click **Submit**

### 1.3 — Verify pairing

After pairing, HA will create two entities automatically:

- `button.powerlync_001_xxxxxx_identify` — flashes the device LED
- `switch.powerlync_001_xxxxxx_powerlync_plug` — controls the built-in smart plug outlet

If you see these, the HomeKit pairing was successful and you can proceed to install the custom integration.

---

## Step 2 — Install the Custom Integration

### 2.1 — Copy the integration files

Copy the `powerlync_energy` folder from this repository into your Home Assistant `custom_components` directory:

```
config/
└── custom_components/
    └── powerlync_energy/
        ├── __init__.py
        ├── config_flow.py
        ├── manifest.json
        ├── sensor.py
        └── strings.json
```

If you're using the HA file editor, Samba share, or SSH, the path is typically `/config/custom_components/`.

### 2.2 — Enable the integration

Add the following line to your `configuration.yaml`:

```yaml
powerlync_energy:
```

### 2.3 — Restart Home Assistant

Go to **Settings → System → Restart** and restart Home Assistant.

### 2.4 — Confirm the integration loaded

Go to **Settings → Devices & Services**. You should see **Powerlync Energy Monitor** listed. It will have created 6 new sensor entities (see below).

---

## Sensor Entities

After installation, the following entities will appear in Home Assistant:

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.powerlync_energy_monitor_instantaneous_demand` | Real-time power draw from the grid | W |
| `sensor.powerlync_energy_monitor_total_energy_consumed` | Lifetime cumulative energy consumed | kWh |
| `sensor.powerlync_energy_monitor_total_energy_received_solar` | Lifetime solar / feed-in energy | kWh |
| `sensor.powerlync_energy_monitor_local_instantaneous_demand` | Local real-time power (float) | W |
| `sensor.powerlync_energy_monitor_local_energy_delivered` | Local cumulative energy | kWh |
| `sensor.powerlync_energy_monitor_meter_last_updated` | Last time meter data was synced | timestamp |

All sensors are updated every **10 seconds**.

> **Note:** Entity names may vary slightly depending on how HA names the device. If you cannot find them, go to **Developer Tools → States** and search for `powerlync`.

---

## Step 3 — Add to the Energy Dashboard (optional)

1. Go to **Settings → Energy**
2. Under **Electricity Grid**, click **Add consumption** and select `sensor.powerlync_energy_monitor_total_energy_consumed`
3. If you have solar panels, under **Solar Panels** add `sensor.powerlync_energy_monitor_total_energy_received_solar`
4. Click **Save**

The Energy Dashboard will start accumulating statistics. Historical comparison charts will become available after sufficient data has been collected.

---

## Troubleshooting

### The integration does not appear after restart

Check **Settings → System → Logs** and filter for `powerlync`. Confirm that `custom_components/powerlync_energy/` is in the correct location and that `powerlync_energy:` is in `configuration.yaml`.

### Sensors show `unavailable` or `unknown`

The integration finds the paired Powerlync device by looking for any `HKDevice` object in `hass.data["homekit_controller-devices"]`. If the HomeKit Controller integration hasn't finished loading yet, the poll will be retried automatically on the next interval.

Check that the homekit pairing is working correctly by verifying the `switch.powerlync_*_plug` entity has a valid state.

### The device was already paired with another app

HomeKit devices support only one controller pairing at a time. Reset the device:

1. In the HydroHome app, go to device settings and select **Remove Device**
2. Or perform a factory reset by holding the reset button on the hub for 10 seconds until the LED flashes
3. Re-pair using Step 1 above

### Poll interval

The default poll interval is 10 seconds. The Zigbee smart meter typically updates every 30 seconds, so polling faster than that won't yield new readings. To adjust, edit `sensor.py`:

```python
SCAN_INTERVAL = timedelta(seconds=30)
```

---

## Reloading without a full restart

After updating integration files, you don't need to restart all of Home Assistant. Go to:

**Settings → Devices & Services → Powerlync Energy Monitor → ⋮ → Reload**

---

## Known Limitations

- **Single pairing**: If you unpair the hub from HA (e.g. to use the HydroHome app), this integration will stop working until you re-pair and reconfigure.
- **No push updates**: The hub supports HomeKit event notifications (`ev` permission), but HA's homekit_controller does not subscribe to unknown custom service characteristics. This integration works around that by polling on a fixed interval.
- **Powerlync Hub only**: This was developed and tested on the **$75 Powerlync Hub**. The **$179 Energy Bridge** has a different architecture (local MQTT on port 2883) and does not need this integration.
- **Long-term statistics**: The `Total Energy Consumed` sensor has `state_class: total_increasing`. HA will accumulate long-term statistics automatically, but comparison charts in the Energy Dashboard require several days of history to be meaningful.

---

## How this was discovered

This integration was developed by reverse engineering the HomeKit mDNS advertisements and HAP characteristic map of the Powerlync Hub. Key findings:

- The hub advertises `_hap._tcp.local` on the network (visible via mDNS/Bonjour)
- HAP communication runs over HTTP on port 80 (not the usual port 8080)
- A custom Powerley service UUID exposes energy characteristics not in the HomeKit spec
- The cloud connection uses mutual TLS to AWS IoT Core — not practical to intercept
- The built-in `/identify` HTTP endpoint (POST) triggers the LED identification mode

---

## Known Possible Issues

All previously identified issues have been resolved:

- **`iot_class` corrected**: `manifest.json` now declares `"iot_class": "local_polling"`, accurately reflecting the fixed-interval polling behaviour.

- **HomeKit device lookup hardened**: `sensor.py` now resolves the Powerlync device by matching `homekit_entry_id` from the config entry against each paired `HKDevice`, ensuring the correct device is selected even when multiple HomeKit accessories are paired. A warning-logged fallback to the first device is retained for resilience against HA version differences.

- **IID 26 (`Local Time`) now polled**: IID 26 is included in the `CHARACTERISTICS` poll list and exposed as a `sensor.powerlync_energy_monitor_local_time` timestamp entity.

- **Fallback to last known value**: Sensors retain their last known good value when a poll returns `None` or a parse failure. Cumulative energy sensors (`retain_on_zero=True`) additionally retain their last value when the parsed result is `0`, preventing spurious zero-readings from causing spikes in the Energy Dashboard.

---

## Contributing

Pull requests are welcome. If you have a Powerlync Hub and find additional characteristics or behaviours, please open an issue.

---

## License

MIT
