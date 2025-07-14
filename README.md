# Bosch Indego Integration for Home Assistant

![GitHub release (latest by date)](https://img.shields.io/github/v/release/WhyLev/indegohomeassistant)
![GitHub contributors](https://img.shields.io/github/contributors/WhyLev/indegohomeassistant)
[![Discord](https://img.shields.io/discord/983383013830864927)](https://discord.gg/aD33GsP)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

A modern, fully-featured Home Assistant integration for Bosch Indego robotic lawn mowers.

## 🌟 Features

- Modern OAuth2 authentication via Bosch SingleKey ID
- Real-time state monitoring and control
- Rich sensor data including:
  - Battery status and temperature
  - Mowing progress and statistics
  - Runtime analytics
  - Garden coverage tracking
- Interactive map visualization with:
  - Static base map
  - Dynamic progress overlay
  - Configurable appearance
- Smart automation capabilities:
  - Mowing schedule management
  - Weather-aware planning
  - Alerts and notifications
- Comprehensive command support:
  - Start/Stop mowing
  - Return to dock
  - SmartMowing control
  - Alert management

## 📦 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the "+" button
4. Search for "Bosch Indego Mower"
5. Click "Download"
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/indego` directory to your Home Assistant configuration directory
2. Restart Home Assistant

## 🔐 Authentication

This integration uses Bosch's modern OAuth2 authentication system. Due to CORS restrictions, you'll need to use the provided Chrome extension for the initial setup:

1. Download and unzip `chrome-extension.zip`
2. Open Chrome Extensions page (chrome://extensions/)
3. Enable Developer Mode
4. Click "Load unpacked" and select the unzipped folder
5. In Home Assistant, add the integration and follow the prompts
6. After successful authentication, you can remove the extension

Alternatively, you can use the `auth_proxy.py` script included in this repository.

## 🎛 Configuration

All configuration is handled through the UI. Available options include:

- Update intervals for position and state
- Map appearance customization
- Alert filtering preferences
- Smart mowing settings

## 🤖 Entities

The integration provides the following entities:

| Entity | ID Pattern | Description |
|--------|------------|-------------|
| Mower State | `sensor.indego_mower_state` | Current operational state |
| Battery | `sensor.indego_battery_percentage` | Battery level and charging status |
| Mowing Progress | `sensor.indego_lawn_mowed` | Percentage of lawn covered |
| Runtime Stats | `sensor.indego_runtime_total` | Total operation time |
| Alerts | `binary_sensor.indego_alert` | Active alerts indicator |
| Map | `camera.indego` | Static garden map |
| Progress Map | `camera.indego_progress` | Dynamic mowing progress |

## 🛠 Services

Available services include:

| Service | Description |
|---------|-------------|
| `indego.command` | Send mower commands (mow/pause/dock) |
| `indego.smartmowing` | Toggle SmartMowing feature |
| `indego.read_alert` | Mark alerts as read |
| `indego.delete_alert` | Remove alerts |
| `indego.download_map` | Save current map as SVG |

## 📊 Dashboard

A modern Mushroom-based dashboard is included in the `dashboard/` directory. Features:

- Clean, modern UI
- Responsive design
- Status overview
- Command shortcuts
- Weather integration

Required HACS Frontend dependencies:
- Mushroom
- Card Mod
- ApexCharts Card
- Vertical Stack in Card

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md).

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 💬 Support

- Join our [Discord community](https://discord.gg/aD33GsP)
- Report issues on [GitHub](https://github.com/WhyLev/indegohomeassistant/issues)
- Check the [Wiki](https://github.com/WhyLev/indegohomeassistant/wiki) for detailed documentation

## 🙏 Credits

- Original OAuth implementation by [sander1988](https://github.com/sander1988)
- Camera system by [kimzeuner](https://github.com/kimzeuner)
- Based on work from [iMarkus/Indego](https://github.com/iMarkus/Indego)
