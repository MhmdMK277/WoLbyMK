<p align="center">
  <img src="assets/logo.svg" alt="WoLmk" width="320"/>
</p>

<p align="center">
  <a href="https://github.com/MhmdMK277/WoLbyMK/releases"><img src="https://img.shields.io/github/v/release/MhmdMK277/WoLbyMK?color=8b7cf7" alt="Release"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"/></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-8b7cf7" alt="Platform"/>
  <img src="https://img.shields.io/badge/Go-1.26-00ADD8?logo=go&logoColor=white" alt="Go"/>
  <img src="https://img.shields.io/badge/built%20with-Wails-df0000" alt="Wails"/>
</p>

<p align="center">
  A fast, single binary Wake-on-LAN desktop app. Add your devices once, then wake them, watch them come online, schedule wakes, and send remote power commands, all from a clean dark interface.
</p>

---

## Features

- Device manager: name, MAC, broadcast host, port, optional device IP, service port, SecureOn password, username and credential hint. Configs persist between launches.
- LAN wake over UDP broadcast, and WAN wake to a public IP or DNS name and forwarded port.
- Repeat wake: each wake sends a configurable number of magic packets a short interval apart.
- Live status checks: after a wake, WoLmk pings the device and shows the result on the card (waiting, online with round-trip time, or unreachable). A Check button runs a single probe on demand.
- Custom TCP port checks: set a service port and status checks use a TCP connect to that port instead of ICMP.
- SecureOn password: optional 6 hex byte password appended to the magic packet.
- Scheduled wake: repeating (weekdays and time) or one-time (date and time). A background loop runs every 30 seconds, schedules survive restarts, and a clock icon marks scheduled devices.
- Remote power: per-device Shutdown and Sleep buttons with editable command templates ({ip} and {user} placeholders). Defaults use Windows PowerShell remoting; power users can set SSH or any command.
- Wake all with a staggered delay between devices and live progress.
- Auto-wake on launch: per-device toggle.
- Wake history: the last 50 attempts are logged and viewable in an overlay.
- Import and export device configs through native file dialogs.
- System tray: closing the window minimizes to the tray, with a Show, Wake all and Exit menu.
- Keyboard shortcuts: Ctrl+N add, Ctrl+W wake selected, Ctrl+A wake all, Escape close dialogs.
- CLI mode for scripts and schedulers.
- Cross-platform: Windows, macOS and Linux, with per-OS ping flag detection.

## Screenshots

![Main window](docs/screenshot.png)

*The devices, MAC addresses, IPs and hostnames shown are fictional sample data, not real values.*

![Add or edit device](docs/screenshot-device.png)

*Example placeholder values; enter your own device details here.*

![Schedule a wake](docs/screenshot-schedule.png)

*Fictional sample schedule.*

![Wake history](docs/screenshot-history.png)

*History entries shown are fictional sample data.*

## Download

Grab the latest `WoLmk.exe` for Windows from the [Releases](https://github.com/MhmdMK277/WoLbyMK/releases) page and run it. No installer or runtime is required. macOS and Linux users can build from source (see below).

Configuration lives in the OS application data directory:

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\WoLmk\` |
| macOS | `~/Library/Application Support/wolmk/` |
| Linux | `~/.config/wolmk/` |

It holds `devices.json` (devices and schedules), `history.json` (wake log) and optionally `settings.json`.

## Getting started

1. Launch WoLmk and click **+ Add device**.
2. Enter a name and the target's MAC address. Leave the host as `255.255.255.255` for a normal LAN wake.
3. Optionally set a **Device IP** so WoLmk can ping the machine and report when it comes online, or a **Service port** to check a TCP port instead.
4. Click **Wake**. The status line and LED update as the device responds.

For the target to wake, enable Wake-on-LAN in its BIOS/UEFI and network adapter power settings, and use a wired connection where possible.

### settings.json

All keys are optional; defaults shown:

```json
{
  "watchTimeout": 60,
  "watchInterval": 2,
  "sendCount": 3,
  "sendInterval": 500,
  "stagger": 2
}
```

- `watchTimeout`, `watchInterval`: how long (seconds) and how often to ping after a wake.
- `sendCount`, `sendInterval`: packets per wake and the gap between them (milliseconds).
- `stagger`: seconds between devices when using Wake all.

## Building from source

WoLmk is a [Wails](https://wails.io) app: a Go backend with an HTML, CSS and JavaScript frontend.

Prerequisites:

- Go 1.24 or newer
- Node.js and npm (for the frontend build)
- The Wails CLI

```bash
# install the Wails CLI
go install github.com/wailsapp/wails/v2/cmd/wails@latest

# from the repository root
wails build
```

The binary is written to `build/bin/WoLmk.exe` (or the platform equivalent). For live development use `wails dev`.

## CLI usage

WoLmk can send a magic packet without opening the window, which is handy for Task Scheduler, cron or scripts:

```bash
WoLmk.exe --send AA:BB:CC:DD:EE:FF [host] [port]
```

- `host` defaults to `255.255.255.255`
- `port` defaults to `9`

The command exits with code 0 on success and 1 on error.

## History

WoLmk started as a Python and Tkinter app. Version 2.0.0 is a full rewrite in Go and Wails with the same feature set and a native web frontend. The original Python edition is preserved in the repository history.

## License

[MIT](LICENSE)
