{% if prerelease %}

### ⚠️ NB: This is a Beta version!

{% endif %}

# Bosch Indego Mower – Lovelace Enhanced Edition

![Screenshot](https://raw.githubusercontent.com/WhyLev/indegohomeassistant/main/doc/0-Sensors_3.png)

This is a custom fork of the original [Indego integration](https://github.com/sander1988/Indego) for Home Assistant – enhanced with:

* 🔑 Modern OAuth login
* 🧱 Live map camera (as a `generic camera` entity) (based on [kimzeuner](https://github.com/kimzeuner)'s contributions)
* 🎨 Beautiful Lovelace Dashboard example (Mushroom Cards)
* 🌦️ Weather, UV & Rain forecast support
* ✅ Full YAML compatibility
* 🛠️ Optimized UX and simplified setup

---

### 🧹 Installation

> Don’t forget to install the Chrome extension (see [README](https://github.com/WhyLev/indegohomeassistant/blob/main/README.md)) to finish the login process.
> Alternatively, run `auth_proxy.py` to handle the OAuth callback without Chrome.

---

### 🔧 Setup

Add the integration via Home Assistant:

* Go to **Settings** → **Devices & Services** → **Add Integration**
* Search for **Bosch Indego Mower**

Follow the instructions in the UI. YAML configuration is no longer supported.

---

### 💬 Community

* [GitHub Repository](https://github.com/WhyLev/indegohomeassistant)
* [Discord Support](https://discord.gg/aD33GsP)
