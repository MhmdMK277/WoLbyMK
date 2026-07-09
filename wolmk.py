#!/usr/bin/env python3
"""WoLmk — a tiny Wake-on-LAN desktop app.

Sends WOL magic packets over UDP to wake machines on your LAN,
or over the internet via a router/relay host (WAN wake).

Magic packet format: 6 bytes of 0xFF followed by the target MAC
address repeated 16 times, sent as a UDP datagram (default port 9).
"""

import json
import os
import re
import socket
import sys
import tkinter as tk
from tkinter import messagebox

APP_NAME = "WoLmk"
APP_VERSION = "1.0.0"
DEFAULT_PORT = 9
DEFAULT_BROADCAST = "255.255.255.255"

# Optional modern UI — falls back to plain tkinter if not installed.
try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

# ---------------------------------------------------------------- storage

def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


CONFIG_FILE = os.path.join(config_dir(), "devices.json")


def load_devices() -> list:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_devices(devices: list) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2)

# ---------------------------------------------------------------- WOL core

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-\. ]?){5}[0-9A-Fa-f]{2}$")


def normalize_mac(mac: str) -> str:
    """Validate a MAC address and return it as AA:BB:CC:DD:EE:FF."""
    mac = mac.strip()
    if not MAC_RE.match(mac):
        raise ValueError(f"Invalid MAC address: {mac!r}")
    digits = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def build_magic_packet(mac: str) -> bytes:
    digits = normalize_mac(mac).replace(":", "")
    mac_bytes = bytes.fromhex(digits)
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(mac: str, host: str = DEFAULT_BROADCAST,
                      port: int = DEFAULT_PORT) -> None:
    """Send the magic packet. Raises on failure."""
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (host, port))

# ---------------------------------------------------------------- theming

COLORS = {
    "bg": "#1e1e2e",
    "panel": "#27273a",
    "panel_hi": "#313147",
    "accent": "#7c6cf0",
    "accent_hi": "#9385f5",
    "text": "#e6e6f0",
    "muted": "#8f8fa8",
    "ok": "#4cc38a",
    "err": "#e5534b",
    "danger": "#a83a3a",
}
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")


def flat_button(parent, text, command, bg=None, fg=None, **kw):
    bg = bg or COLORS["accent"]
    btn = tk.Button(parent, text=text, command=command, font=FONT_BOLD,
                    bg=bg, fg=fg or COLORS["text"], activebackground=COLORS["accent_hi"],
                    activeforeground=COLORS["text"], relief="flat", bd=0,
                    padx=14, pady=6, cursor="hand2", **kw)
    return btn

# ---------------------------------------------------------------- dialogs

class DeviceDialog(tk.Toplevel):
    """Add/edit device modal. Result in self.result (dict) or None."""

    def __init__(self, parent, device=None):
        super().__init__(parent)
        self.result = None
        self.title("Edit device" if device else "Add device")
        self.configure(bg=COLORS["bg"], padx=20, pady=16)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        device = device or {}
        fields = [
            ("Name", device.get("name", ""), "e.g. Gaming PC"),
            ("MAC address", device.get("mac", ""), "AA:BB:CC:DD:EE:FF"),
            ("Host / broadcast IP", device.get("host", DEFAULT_BROADCAST),
             "255.255.255.255 for LAN, public IP/DNS for WAN"),
            ("Port", str(device.get("port", DEFAULT_PORT)), "9 (or your router's forwarded port)"),
        ]
        self.entries = {}
        for row, (label, value, hint) in enumerate(fields):
            tk.Label(self, text=label, font=FONT_BOLD, bg=COLORS["bg"],
                     fg=COLORS["text"], anchor="w").grid(row=row * 2, column=0,
                                                         sticky="w", pady=(8, 1))
            entry = tk.Entry(self, font=FONT, width=38, bg=COLORS["panel"],
                             fg=COLORS["text"], insertbackground=COLORS["text"],
                             relief="flat", highlightthickness=1,
                             highlightbackground=COLORS["panel_hi"],
                             highlightcolor=COLORS["accent"])
            entry.insert(0, value)
            entry.grid(row=row * 2, column=1, sticky="ew", pady=(8, 1), ipady=4)
            tk.Label(self, text=hint, font=("Segoe UI", 8), bg=COLORS["bg"],
                     fg=COLORS["muted"], anchor="w").grid(row=row * 2 + 1,
                                                          column=1, sticky="w")
            self.entries[label] = entry

        btns = tk.Frame(self, bg=COLORS["bg"])
        btns.grid(row=9, column=0, columnspan=2, sticky="e", pady=(16, 0))
        flat_button(btns, "Cancel", self.destroy,
                    bg=COLORS["panel_hi"]).pack(side="left", padx=(0, 8))
        flat_button(btns, "Save", self._save).pack(side="left")

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.entries["Name"].focus_set()

    def _save(self):
        name = self.entries["Name"].get().strip()
        mac = self.entries["MAC address"].get().strip()
        host = self.entries["Host / broadcast IP"].get().strip() or DEFAULT_BROADCAST
        port_s = self.entries["Port"].get().strip() or str(DEFAULT_PORT)
        if not name:
            messagebox.showerror(APP_NAME, "Name is required.", parent=self)
            return
        try:
            mac = normalize_mac(mac)
        except ValueError:
            messagebox.showerror(
                APP_NAME, "Invalid MAC address.\nUse format AA:BB:CC:DD:EE:FF.",
                parent=self)
            return
        try:
            port = int(port_s)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, "Port must be 1-65535.", parent=self)
            return
        self.result = {"name": name, "mac": mac, "host": host, "port": port}
        self.destroy()

# ---------------------------------------------------------------- main app

class WolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Wake-on-LAN")
        self.configure(bg=COLORS["bg"])
        self.geometry("560x480")
        self.minsize(480, 360)
        self.devices = load_devices()
        self.rows = []
        self._build_ui()
        self._render_devices()

    def _build_ui(self):
        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(header, text="⚡ WoLmk", font=FONT_TITLE, bg=COLORS["bg"],
                 fg=COLORS["text"]).pack(side="left")
        flat_button(header, "+ Add device", self._add_device).pack(side="right")

        tk.Label(self, text="Wake your machines with a magic packet.",
                 font=FONT, bg=COLORS["bg"], fg=COLORS["muted"],
                 anchor="w").pack(fill="x", padx=22)

        # Scrollable device list
        wrap = tk.Frame(self, bg=COLORS["bg"])
        wrap.pack(fill="both", expand=True, padx=20, pady=12)
        self.canvas = tk.Canvas(wrap, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg=COLORS["bg"])
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._list_window = self.canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._list_window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.status = tk.Label(self, text="Ready", font=FONT, bg=COLORS["panel"],
                               fg=COLORS["muted"], anchor="w", padx=12, pady=6)
        self.status.pack(fill="x", side="bottom")

    def _render_devices(self):
        for row in self.rows:
            row.destroy()
        self.rows = []
        if not self.devices:
            empty = tk.Label(self.list_frame,
                             text="No devices yet.\nClick “+ Add device” to get started.",
                             font=FONT, bg=COLORS["bg"], fg=COLORS["muted"],
                             pady=40, justify="center")
            empty.pack(fill="x")
            self.rows.append(empty)
            return
        for i, dev in enumerate(self.devices):
            self.rows.append(self._device_row(i, dev))

    def _device_row(self, index, dev):
        card = tk.Frame(self.list_frame, bg=COLORS["panel"], padx=14, pady=10)
        card.pack(fill="x", pady=4)

        info = tk.Frame(card, bg=COLORS["panel"])
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=dev["name"], font=FONT_BOLD, bg=COLORS["panel"],
                 fg=COLORS["text"], anchor="w").pack(fill="x")
        target = "LAN broadcast" if dev["host"] == DEFAULT_BROADCAST \
            else f"{dev['host']} (WAN)"
        tk.Label(info, text=f"{dev['mac']}  ·  {target}  ·  port {dev['port']}",
                 font=("Segoe UI", 9), bg=COLORS["panel"], fg=COLORS["muted"],
                 anchor="w").pack(fill="x")

        flat_button(card, "Wake", lambda: self._wake(dev)).pack(side="right", padx=(8, 0))
        flat_button(card, "Edit", lambda: self._edit_device(index),
                    bg=COLORS["panel_hi"]).pack(side="right", padx=(8, 0))
        flat_button(card, "✕", lambda: self._delete_device(index),
                    bg=COLORS["danger"]).pack(side="right")
        return card

    # ----------------------------------------------------------- actions

    def _add_device(self):
        dialog = DeviceDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.devices.append(dialog.result)
            save_devices(self.devices)
            self._render_devices()
            self._set_status(f"Added “{dialog.result['name']}”", ok=True)

    def _edit_device(self, index):
        dialog = DeviceDialog(self, self.devices[index])
        self.wait_window(dialog)
        if dialog.result:
            self.devices[index] = dialog.result
            save_devices(self.devices)
            self._render_devices()
            self._set_status(f"Updated “{dialog.result['name']}”", ok=True)

    def _delete_device(self, index):
        dev = self.devices[index]
        if messagebox.askyesno(APP_NAME, f"Delete “{dev['name']}”?", parent=self):
            del self.devices[index]
            save_devices(self.devices)
            self._render_devices()
            self._set_status(f"Deleted “{dev['name']}”")

    def _wake(self, dev):
        try:
            send_magic_packet(dev["mac"], dev["host"], dev["port"])
        except Exception as exc:
            self._set_status(f"✗ Failed to wake “{dev['name']}”: {exc}", err=True)
            return
        self._set_status(
            f"✓ Magic packet sent to “{dev['name']}” "
            f"({dev['host']}:{dev['port']})", ok=True)

    def _set_status(self, text, ok=False, err=False):
        color = COLORS["ok"] if ok else COLORS["err"] if err else COLORS["muted"]
        self.status.configure(text=text, fg=color)


def main():
    if HAS_CTK:
        ctk.set_appearance_mode("dark")
    app = WolApp()
    app.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--send":
        # Headless mode: wolmk.py --send <MAC> [host] [port]
        mac = sys.argv[2]
        host = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_BROADCAST
        port = int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_PORT
        send_magic_packet(mac, host, port)
        print(f"Magic packet sent to {normalize_mac(mac)} via {host}:{port}")
    else:
        main()
