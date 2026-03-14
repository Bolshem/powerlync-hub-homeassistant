# Powerlync Plug/Hub — Home Assistant Integration

[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Bolshem&repository=powerlync-hub-homeassistant&category=integration)

A custom Home Assistant integration that exposes real-time energy monitoring data from the **BC Hydro Powerlync Plug/Hub** (by Powerley) as sensors in Home Assistant — with no cloud dependency and no reverse-engineering of proprietary protocols.

---

## Background

The BC Hydro Powerlync Plug/Hub is a smart energy monitor that reads your electricity meter via Zigbee (Smart Energy Profile) and reports real-time consumption data to the Powerley cloud. It retails for ~$75 and is available to BC Hydro customers.

While the device communicates upstream to AWS IoT Core using mutual TLS (making cloud traffic interception impractical), it also advertises itself as an **Apple HomeKit accessory** over mDNS on your local network. This integration leverages that HomeKit interface to extract energy data locally, without any cloud dependency.

---

## Architecture

```
 Zigbee (Smart Energy Profile)
 ┌─────────────┐                    ┌──────────────────┐
 │ BC Hydro    │ ─────────────────► │ Powerlync Plug/  │
 │ Smart Meter │                    │ Hub (Powerley)   │
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
| 26 | Local Time (UTC) | int | Unix timestamp |
| 27 | Meter Time (UTC) | int | Unix timestamp |

All characteristics have `"perms": ["pr", "ev"]` — they support both read and push notifications, though this integration uses polling for simplicity and reliability.

---

## Prerequisites

- Home Assistant 2024.1 or newer
- The `homekit_controller` integration (built into HA — no installation needed)
- The Powerlync Plug/Hub physically installed and connected to your local network
- The **8-digit HomeKit setup code** from your device label or QR code (see note below if your device has no printed code)

---

## Step 1 — Pair the Powerlync Plug/Hub with Home Assistant

The Powerlync Plug/Hub is a HomeKit accessory. Before this custom integration can work, you must pair the device with HA's built-in HomeKit Controller integration.

> **Note:** If you have previously paired the hub with the Apple Home app or the HydroHome/Powerley app, you may need to **factory reset** the device first to clear the existing pairing. HomeKit devices can only be paired with one controller at a time.

> **No printed pairing code?** Some units (e.g. Powerlync 002) have a QR code on the label but no printed 8-digit code. Scan the QR code — it produces a string like `X-HM://00XXXXXXX`. You can decode the HomeKit pairing code from that string using the tool at **[dekyon.com](https://dekyon.com)**, or manually with the JavaScript snippet in the [troubleshooting section](#no-printed-pairing-code--qr-code-only) below.

### 1.1 — Connect the hub to your network

Ensure the Powerlync Plug/Hub is powered on and connected to your Wi-Fi or LAN. The HydroHome app can be used for initial network setup if needed (iOS or Android).

### 1.2 — Add via Home Assistant

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **HomeKit Controller** and select it
4. HA will scan for HomeKit devices on your network. You should see **Powerlync-001-XXXXXX** appear in the list
5. If it does not appear automatically, click **Enter device pairing code manually**
6. Enter the **8-digit code** from the label on your Powerlync Plug/Hub (no dashes)
7. Click **Submit**

### 1.3 — Verify pairing

After pairing, HA will create two entities automatically:

- `button.powerlync_001_xxxxxx_identify` — flashes the device LED
- `switch.powerlync_001_xxxxxx_powerlync_plug` — controls the built-in smart plug outlet

If you see these, the HomeKit pairing was successful and you can proceed to install the custom integration.

---

## Step 2 — Install via HACS (recommended)

### 2.1 — Add to HACS

**One-click** (if HACS is already installed): click the button at the top of this page, then skip to step 2.3.

Or add manually:

1. Open **HACS** in the Home Assistant sidebar
2. Click **Integrations**
3. Click the **⋮** menu (top right) → **Custom repositories**
4. Paste `https://github.com/Bolshem/powerlync-hub-homeassistant` and set Category to **Integration**
5. Click **Add**, then search for **Powerlync** and click **Download**

### 2.2 — Restart Home Assistant

Go to **Settings → System → Restart** after the download completes.

### 2.3 — Add the integration

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **Powerlync** and select **Powerlync Energy Monitor**
4. The integration will automatically find your paired Powerlync device and create the sensors

> **Important:** HACS only downloads the files. You must complete step 2.3 to actually set up the integration — it will not appear under installed integrations until you do this step.

---

## Step 2 (alternative) — Manual install

Copy the `custom_components/powerlync_energy` folder from this repository into your HA `config/custom_components/` directory:

```
config/
└── custom_components/
    └── powerlync_energy/
        ├── __init__.py
        ├── config_flow.py
        ├── manifest.json
        ├── sensor.py
        ├── strings.json
        └── translations/
            └── en.json
```

Restart Home Assistant, then go to **Settings → Devices & Services → + Add Integration** and search for **Powerlync**.

> **Note:** No `configuration.yaml` changes are required.

---

## Sensor Entities

After installation, the following entities will appear in Home Assistant. Entity IDs include the device serial number (e.g. `000528`) to support multiple hubs:

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.powerlync_energy_monitor_XXXXXX_instantaneous_demand` | Real-time power draw from the grid | W |
| `sensor.powerlync_energy_monitor_XXXXXX_total_energy_consumed` | Lifetime cumulative energy consumed | kWh |
| `sensor.powerlync_energy_monitor_XXXXXX_total_energy_received` | Lifetime solar / feed-in energy | kWh |
| `sensor.powerlync_energy_monitor_XXXXXX_local_instantaneous_demand` | Local real-time power (float) | W |
| `sensor.powerlync_energy_monitor_XXXXXX_local_energy_delivered` | Local cumulative energy | kWh |
| `sensor.powerlync_energy_monitor_XXXXXX_local_time` | Local device time | timestamp |
| `sensor.powerlync_energy_monitor_XXXXXX_meter_last_updated` | Last time meter data was synced | timestamp |

Where `XXXXXX` is the last segment of your device serial number (e.g. `000528` from `Powerlync-001-000528`).

All sensors are updated every **10 seconds**.

> **Tip:** If you cannot find your entities, go to **Developer Tools → States** and search for `powerlync`.

---

## Step 3 — Add to the Energy Dashboard (optional)

1. Go to **Settings → Energy**
2. Under **Electricity Grid**, click **Add consumption** and select your `total_energy_consumed` sensor
3. If you have solar panels, add your `total_energy_received` sensor under **Solar Panels**
4. Click **Save**

The Energy Dashboard will start accumulating statistics. Historical comparison charts will become available after a few days of data.

> **Note:** The first time the sensor is registered, HA may record a large one-time spike equal to your lifetime meter reading. This is normal HA behaviour with `total_increasing` sensors and self-corrects from the next reading onward. If it persists, go to **Developer Tools → Statistics**, find the sensor, and use **Fix issue** to clear the outlier.

---

## Multiple Hubs

The integration supports multiple Powerlync hubs on the same HA instance. When you run **Add Integration** a second time, it will detect the second paired device and create a separate set of entities scoped to that hub's serial number. Each hub appears as a distinct device in **Settings → Devices & Services**.

---

## Troubleshooting

### No printed pairing code — QR code only

Some units (notably the **Powerlync 002**) ship with a QR code sticker but no printed 8-digit HomeKit setup code.

1. Scan the QR code with any QR scanner app — you will get a string like `X-HM://00XXXXXXX`
2. Use the online decoder at **[dekyon.com](https://dekyon.com/powerlync.html)** to convert it to the 8-digit code, **or** run this in your browser console:

```js
function decodeHomekitQR(qrString) {
  const encoded = qrString.split('://')[1];
  const decimal = parseInt(encoded, 36);
  const code = (decimal & 0x7FFFFFF).toString().padStart(8, '0');
  return `${code.slice(0,3)}-${code.slice(3,5)}-${code.slice(5)}`;
}
// Example: decodeHomekitQR("X-HM://00QR4AAEX")
```

3. Use the resulting `XXX-XX-XXX` formatted code when prompted by HA during pairing

---

### "No Powerlync device found" when adding the integration

The integration requires the hub to be paired via **HomeKit Controller** first (Step 1). If HomeKit Controller doesn't show the hub, make sure the device is on the same network as Home Assistant and try pairing manually using the 8-digit code on the label.

### Sensors show `unavailable` or `unknown`

Check that the HomeKit Controller pairing is healthy by verifying the `switch.powerlync_*_plug` entity has a valid state. If it shows unavailable, the hub may have lost its network connection or the HomeKit pairing may need to be re-established.

### Energy Dashboard spikes every few days

This happens when the HomeKit connection drops and reconnects, causing HA to re-register the lifetime meter value as a new reading. The integration retains the last known value when a poll returns zero or fails, which mitigates most cases. For persistent spikes, go to **Developer Tools → Statistics → Fix issues**.

### The device was already paired with another app

HomeKit devices support only one controller pairing at a time. Reset the device:

1. In the HydroHome app, go to device settings and select **Remove Device**
2. Or perform a factory reset by holding the reset button on the hub for 10 seconds until the LED flashes
3. Re-pair using Step 1 above

### Changing the poll interval

The default poll interval is 10 seconds. The Zigbee smart meter typically updates every 30 seconds, so polling faster than that won't yield new readings. To adjust, edit `sensor.py`:

```python
SCAN_INTERVAL = timedelta(seconds=30)
```

### Reloading without a full restart

After updating integration files, reload without restarting HA:

**Settings → Devices & Services → Powerlync Energy Monitor → ⋮ → Reload**

---

## Known Limitations

- **Single pairing**: If you unpair the hub from HA (e.g. to use the HydroHome app), this integration will stop working until you re-pair and reconfigure.
- **No push updates**: The hub supports HomeKit event notifications (`ev` permission), but HA's homekit_controller does not subscribe to unknown custom service characteristics. This integration works around that by polling on a fixed interval.
- **Powerlync Plug/Hub only**: This was developed and tested on the **$75 Powerlync Plug/Hub**. The **$179 Energy Bridge** has a different architecture (local MQTT on port 2883) and does not need this integration.
- **Long-term statistics**: Comparison charts in the Energy Dashboard require several days of history to be meaningful.

---

## How this was discovered

This integration was developed by reverse engineering the HomeKit mDNS advertisements and HAP characteristic map of the Powerlync Plug/Hub. Key findings:

- The hub advertises `_hap._tcp.local` on the network (visible via mDNS/Bonjour)
- HAP communication runs over HTTP on port 80 (not the usual port 8080)
- A custom Powerley service UUID exposes energy characteristics not in the HomeKit spec
- The cloud connection uses mutual TLS to AWS IoT Core — not practical to intercept
- The built-in `/identify` HTTP endpoint (POST) triggers the LED identification mode

---

## Contributing

Pull requests are welcome. If you have a Powerlync Plug/Hub and find additional characteristics or behaviours, please open an issue.

---

## License

MIT
