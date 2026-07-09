# ⚡ WoLmk

A tiny, standalone Wake-on-LAN desktop app for Windows. Add your devices once, then wake them with a single click — over your LAN or across the internet.

![screenshot placeholder](docs/screenshot.png)
*(screenshot coming soon)*

## Features

- 🖥️ **Device manager** — save name, MAC address, host and port; persists between launches
- 📡 **LAN wake** — broadcast magic packets on your local network (default `255.255.255.255:9`)
- 🌍 **WAN wake** — target a public IP/DNS name and forwarded port to wake machines over the internet
- ✅ **Status feedback** — see immediately whether the packet was sent
- 📦 **Zero-install** — a single portable `.exe`, no runtime required
- 🔌 **CLI mode** — `wolmk.exe --send AA:BB:CC:DD:EE:FF [host] [port]` for scripts

## Download & Run

Grab the latest `WoLmk.exe` from [Releases](../../releases) and double-click it. That's it.

Device configs are stored in `%APPDATA%\WoLmk\devices.json`.

## Run from source

```bash
python wolmk.py
```

Requires Python 3.9+. No dependencies for core functionality — `customtkinter` is used automatically if installed (optional, for a more modern look).

## Build the .exe yourself

```bash
build.bat
```

This installs PyInstaller if needed and produces `dist\WoLmk.exe` as a single file.

## How Wake-on-LAN works

Wake-on-LAN wakes a sleeping/powered-off machine by sending a **magic packet**: a UDP datagram containing 6 bytes of `0xFF` followed by the target's MAC address repeated 16 times (102 bytes total). The network card, which stays powered in low-power states, watches for this pattern and signals the motherboard to boot.

For it to work, the target machine needs:

1. **BIOS/UEFI**: enable *Wake on LAN* / *Power On by PCI-E*
2. **Windows**: Device Manager → network adapter → Power Management → *Allow this device to wake the computer* (and disable *Fast Startup* for wake-from-shutdown)
3. **Wired connection** — WOL over Wi-Fi (WoWLAN) is rare and unreliable

### Waking over the internet (WAN)

Magic packets are broadcast-based and don't route across the internet by themselves. To wake a machine remotely:

1. On your router, forward an external UDP port (e.g. `9`) to your LAN's broadcast address (e.g. `192.168.1.255`) — or to the target's static IP with a static ARP entry
2. In WoLmk, set the device's **host** to your public IP or DDNS hostname and **port** to the forwarded port
3. Click Wake from anywhere

## License

[MIT](LICENSE)
