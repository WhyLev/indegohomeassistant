# Indego Home Assistant Integration


Join the [Discord community](https://discord.gg/aD33GsP) to ask questions, share feedback, and help shape future development!

Read the [Wiki](https://github.com/WhyLev/indegohomeassistant/wiki/Indego-Home-Assistant-Integration) for help
---

## 🌱 Overview

**Indego Home Assistant** is a custom component for Bosch Indego robotic lawn mowers. It offers real-time mower data, control commands, map rendering, and a beautiful Lovelace dashboard using Mushroom, ApexCharts, and Card Mod.

This fork combines the solid Bosch Indego integration developed by [sander1988](https://github.com/sander1988) with the camera and feature enhancements introduced by [kimzeuner](https://github.com/kimzeuner), while the new UI/UX design and dashboard were created by myself.

---

## ⚙️ Features

* OAuth2 login via Bosch SingleKey ID
* Real-time state, mowing progress, battery status
* Static map camera plus animated progress camera (resets after 24h or on completion)
* Progress path line width set by `MAP_PROGRESS_LINE_WIDTH` (default 6px)
* Alert and error handling with delete/read actions
* Service commands: mow, pause, return to dock
* SmartMowing toggling
* Map position updates every 10 seconds by default (configurable)
* State update timeout configurable via `state_update_timeout` option (default 10s)
* Map file is automatically downloaded on Home Assistant restart if missing
* Forecast sensor with rain probability & mow suggestion
* Mushroom-based Lovelace dashboard with

  * Status grid
  * Battery widget
  * Command buttons
  * Alert deletion
  * Weather chips (OpenWeatherMap + OpenUV)

---

## 🔧 Installation

### Option 1: Manual

1. Copy `custom_components/indego` into your Home Assistant config directory
2. Restart Home Assistant

---

## 🌐 Authentication Setup

Bosch requires login via **SingleKey ID** with OAuth2. Due to CORS restrictions, authentication requires **Google Chrome** and a **temporary extension**.

### Chrome Extension Setup

1. Download [chrome-extension.zip](/chrome-extension.zip)
2. Unzip it
3. Open `chrome://extensions/`
4. Enable *Developer mode* (top right)
5. Click *Load unpacked*, select unzipped folder
6. Authenticate via Home Assistant: *Settings > Devices & Services > Add Integration > Bosch Indego Mower*

After linking, you can disable/remove the extension.

> Note: You can add multiple Indego devices individually.

### Alternative OAuth Helper

If you prefer not to use Chrome, run `auth_proxy.py` from this repository. It
starts a small web server that forwards the OAuth callback to Home Assistant.
Open the printed URL, complete the login and the token will be sent to HA.

---

## 🪡 Entities & Sensors

All entities are auto-discovered and appear under *unused entities* after integration.

| Function           | Entity                                           |
| ------------------ | ------------------------------------------------ |
| Mower state        | `sensor.indego_mower_state`             |
| Mower state detail | `sensor.indego_mower_state_detail`      |
| Lawn mowed %       | `sensor.indego_lawn_mowed`              |
| Total runtime      | `sensor.indego_runtime_total`           |
| Total mowing time  | `sensor.indego_total_mowing_time`       |
| Total charging time| `sensor.indego_total_charging_time`     |
| Total operation time| `sensor.indego_total_operation_time`   |
| Battery percentage | `sensor.indego_battery_percentage`      |
| Ambient temperature | `sensor.indego_ambient_temperature`    |
| Battery temperature | `sensor.indego_battery_temperature`    |
| Battery cycles      | `sensor.indego_battery_cycles`         |
| Average mow time    | `sensor.indego_average_mow_time`       |
| Weekly mowed area   | `sensor.indego_weekly_area`            |
| Alerts present     | `binary_sensor.indego_alert`            |
| Last completed     | `sensor.indego_last_completed`          |
| Next scheduled mow | `sensor.indego_next_mow`                |
| Forecast           | `sensor.indego_forecast`                |
| Mowing mode        | `sensor.indego_mowing_mode`             |
| Garden size        | `sensor.indego_garden_size`             |
| Online state       | `binary_sensor.indego_online`           |
| Update available   | `binary_sensor.indego_update_available` |
| Firmware version   | `sensor.indego_firmware_version`        |
| Serial number      | `sensor.indego_serial_number`           |
| Camera map         | `camera.indego` (static)                |
| Progress camera    | `camera.indego_progress`                |

### Automation Examples

Use these sensors to build automations. Examples:

```yaml
- alias: Notify when mower battery cycles high
  trigger:
    - platform: numeric_state
      entity_id: sensor.indego_battery_cycles
      above: 500
  action:
    - service: notify.mobile_app_phone
      data:
        message: "Indego battery has reached 500 cycles."
```

```yaml
- alias: Log weekly mowed area
  trigger:
    - platform: time
      at: "23:59:00"
  action:
    - service: system_log.write
      data:
        message: "Mowed area this week: {{ states('sensor.indego_weekly_area') }} m²"
```


---

## 🚜 Services

You can call the following services:

| Service                   | Purpose                                |
| ------------------------- | -------------------------------------- |
| `indego.command`          | Send `mow`, `pause`, or `returnToDock` |
| `indego.smartmowing`      | Toggle SmartMowing on/off              |
| `indego.read_alert`       | Mark one alert as read                 |
| `indego.read_alert_all`   | Mark all alerts as read                |
| `indego.delete_alert`     | Delete one alert                       |
| `indego.delete_alert_all` | Delete all alerts                      |

---

## 📊 Dashboard

A complete Mushroom-based dashboard is included in `/dashboard/lovelace.yaml`. Highlights:

* Picture-entity with camera map
* Battery widget (colored icon)
* Status grid (state, lawn mowed, last/next mow, alerts, updates)
* Weather chips (OpenWeather, OpenUV)
* Command buttons (Start, Pause, Dock)

Required HACS Frontend Cards:

* [Mushroom](https://github.com/piitaya/lovelace-mushroom)
* [Card Mod](https://github.com/thomasloven/lovelace-card-mod)
* [ApexCharts Card](https://github.com/RomRider/apexcharts-card)
* [Vertical Stack in Card](https://github.com/ofekashery/vertical-stack-in-card)
* [OpenUV](https://www.home-assistant.io/integrations/openuv/)

---

## 🌿 Supported Mower Models

All Indego models are supported. See [the GitHub repository](https://github.com/WhyLev/indegohomeassistant) for details.

---

## ❤️ Credits

* Special thanks to [**kimzeuner**](https://github.com/kimzeuner) for the Camera-System
* Gratitude to [**sander1988**](https://github.com/sander1988) for the OAuth-based Indego integration
* Based on [iMarkus/Indego](https://github.com/iMarkus/Indego) and ideas from [grauonline.de](http://grauonline.de/wordpress/?page_id=219)

---

## 🙋 Support

For issues, open a [GitHub Issue](https://github.com/WhyLev/indegohomeassistant/issues) or join the [Discord](https://discord.gg/aD33GsP).

> Pull Requests welcome! Help improve features, translations, or dashboards.

---
