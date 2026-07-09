# WoLmk

A standalone Wake-on-LAN desktop app for Windows. Add your devices once, then wake them with a single click, either on your local network or over the internet.

![Main window](docs/screenshot.png)

*The devices, MAC addresses and hostnames shown are fictional sample data, not real values.*

## Features

- Device manager: save name, MAC address, host and port. Configs persist between launches.
- LAN wake: broadcast magic packets on your local network (default `255.255.255.255:9`).
- WAN wake: target a public IP or DNS name and forwarded port to wake machines remotely.
- Status feedback: shows whether the packet was sent or failed.
- Single portable `.exe`, no runtime required.
- CLI mode: `wolmk.exe --send AA:BB:CC:DD:EE:FF [host] [port]` for use in scripts.

![Add device dialog](docs/screenshot-add-device.png)

*Example placeholder values; enter your own device details here.*

## Download and run

Download the latest `WoLmk.exe` from [Releases](../../releases) and run it.

Device configs are stored in `%APPDATA%\WoLmk\devices.json`.

## Run from source

```bash
python wolmk.py
```

Requires Python 3.9 or newer. Core functionality has no dependencies. If `customtkinter` is installed, the app uses it automatically for a more modern look; this is optional.

## Build the .exe yourself

```bash
build.bat
```

This installs PyInstaller if needed and produces `dist\WoLmk.exe` as a single file.

## How Wake-on-LAN works

Wake-on-LAN wakes a sleeping or powered-off machine by sending a magic packet: a UDP datagram containing 6 bytes of `0xFF` followed by the target's MAC address repeated 16 times (102 bytes total). The network card stays powered in low-power states, watches for this pattern, and signals the motherboard to boot.

For it to work, the target machine needs:

1. BIOS/UEFI: enable Wake on LAN (sometimes called "Power On by PCI-E").
2. Windows: Device Manager, network adapter, Power Management tab, enable "Allow this device to wake the computer". Disable Fast Startup if you want wake-from-shutdown.
3. A wired connection. WOL over Wi-Fi (WoWLAN) is rarely supported and unreliable.

### Waking over the internet (WAN)

Magic packets are broadcast-based and do not route across the internet by themselves. To wake a machine remotely:

1. On your router, forward an external UDP port (for example `9`) to your LAN's broadcast address (for example `192.168.1.255`), or to the target's static IP with a static ARP entry.
2. In WoLmk, set the device's host to your public IP or DDNS hostname and the port to the forwarded port.
3. Click Wake.

## License

[MIT](LICENSE)
