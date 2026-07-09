#!/usr/bin/env python3
"""WoLmk, a tiny Wake-on-LAN desktop app.

Sends WOL magic packets over UDP to wake machines on your LAN,
or over the internet via a router/relay host (WAN wake). Also does
live status checks, scheduled wakes, and optional remote power
commands (shutdown/sleep) to managed Windows targets.

Magic packet format: 6 bytes of 0xFF followed by the target MAC
address repeated 16 times, sent as a UDP datagram (default port 9).
An optional SecureOn password (6 hex bytes) is appended after that.
"""

import ctypes
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import filedialog, messagebox

APP_NAME = "WoLmk"
APP_VERSION = "1.3.0"
DEFAULT_PORT = 9
DEFAULT_BROADCAST = "255.255.255.255"
HISTORY_LIMIT = 200
HISTORY_SHOWN = 50
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DEFAULT_SHUTDOWN = 'powershell -Command "Stop-Computer -ComputerName {ip} -Force"'
DEFAULT_SLEEP = ('powershell -Command "Invoke-Command -ComputerName {ip} '
                 '-ScriptBlock { rundll32.exe powrprof.dll,SetSuspendState 0,1,0 }"')

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ---------------------------------------------------------------- storage

def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


CONFIG_FILE = os.path.join(config_dir(), "devices.json")
HISTORY_FILE = os.path.join(config_dir(), "history.json")
SETTINGS_FILE = os.path.join(config_dir(), "settings.json")


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def load_devices() -> list:
    return _load_json(CONFIG_FILE, [])


def save_devices(devices: list) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2)


def load_settings() -> dict:
    settings = {"watch_timeout": 60, "watch_interval": 2,
                "send_count": 3, "send_interval": 500, "stagger": 2}
    settings.update(_load_json(SETTINGS_FILE, {}))
    return settings


def load_history() -> list:
    return _load_json(HISTORY_FILE, [])


def append_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-HISTORY_LIMIT:], f, indent=2)


def update_history(entry_id: float, ping_ok: bool) -> None:
    history = load_history()
    for entry in reversed(history):
        if entry.get("id") == entry_id:
            entry["ping"] = ping_ok
            break
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

# ---------------------------------------------------------------- WOL core

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-\. ]?){5}[0-9A-Fa-f]{2}$")
HEX6_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-\. ]?){5}[0-9A-Fa-f]{2}$")


def normalize_mac(mac: str) -> str:
    """Validate a MAC address and return it as AA:BB:CC:DD:EE:FF."""
    mac = mac.strip()
    if not MAC_RE.match(mac):
        raise ValueError(f"Invalid MAC address: {mac!r}")
    digits = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def normalize_secureon(pw: str) -> str:
    """Validate a SecureOn password (6 hex bytes) or return '' if empty."""
    pw = (pw or "").strip()
    if not pw:
        return ""
    if not HEX6_RE.match(pw):
        raise ValueError(f"Invalid SecureOn password: {pw!r}")
    digits = re.sub(r"[^0-9A-Fa-f]", "", pw).upper()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def build_magic_packet(mac: str, secureon: str = "") -> bytes:
    digits = normalize_mac(mac).replace(":", "")
    packet = b"\xff" * 6 + bytes.fromhex(digits) * 16
    if secureon:
        packet += bytes.fromhex(normalize_secureon(secureon).replace(":", ""))
    return packet


def send_magic_packet(mac: str, host: str = DEFAULT_BROADCAST,
                      port: int = DEFAULT_PORT, count: int = 1,
                      interval_ms: int = 0, secureon: str = "") -> None:
    """Send the magic packet, optionally repeated. Raises on failure."""
    packet = build_magic_packet(mac, secureon)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for i in range(max(1, count)):
            sock.sendto(packet, (host, port))
            if i < count - 1 and interval_ms > 0:
                time.sleep(interval_ms / 1000)


def ping_host(host: str, timeout_ms: int = 1000):
    """One ICMP echo via the system ping tool. Returns (online, rtt_ms).

    Uses OS-specific flags so the app works on Windows, Linux and macOS.
    """
    secs = max(1, round(timeout_ms / 1000))
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    elif sys.platform == "darwin":
        cmd = ["ping", "-c", "1", "-t", str(secs), host]
    else:  # linux and other unix
        cmd = ["ping", "-c", "1", "-W", str(secs), host]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_ms / 1000 + 3,
                              creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    out = proc.stdout or ""
    # On Windows, exit code 0 can still mean "unreachable"; TTL= marks a reply.
    online = proc.returncode == 0 and (
        "TTL=" in out.upper() or sys.platform != "win32")
    if not online:
        return False, None
    match = re.search(r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms", out, re.IGNORECASE)
    return True, (float(match.group(1)) if match else None)


def check_port(host: str, port: int, timeout: float = 1.0):
    """TCP connect check. Returns (online, rtt_ms)."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.monotonic() - start) * 1000
    except OSError:
        return False, None


def ping_target(device: dict):
    """The address used for status checks and remote commands."""
    ip = device.get("ip", "").strip()
    if ip:
        return ip
    if device["host"] != DEFAULT_BROADCAST:
        return device["host"]
    return None


def probe_device(device):
    """Check reachability. Returns (online, rtt_ms, label) or None if no target."""
    target = ping_target(device)
    if not target:
        return None
    sp = str(device.get("service_port", "")).strip()
    if sp:
        ok, rtt = check_port(target, int(sp))
        return ok, rtt, f"port {sp}"
    ok, rtt = ping_host(target)
    return ok, rtt, ""


def status_text(online, rtt, label, stamp):
    if not online:
        tag = f" ({label})" if label else ""
        return f"Offline{tag}, {stamp}"
    tag = f" ({label})" if label else ""
    rtt_txt = f", {rtt:.0f} ms" if rtt is not None else ""
    return f"Online{tag}{rtt_txt}, {stamp}"


def run_remote_command(device: dict, kind: str):
    """Run the per-device shutdown/sleep command. Returns (ok, message)."""
    template = device.get(f"cmd_{kind}", "").strip() or (
        DEFAULT_SHUTDOWN if kind == "shutdown" else DEFAULT_SLEEP)
    target = device.get("ip", "").strip() or (
        device["host"] if device["host"] != DEFAULT_BROADCAST else "")
    if not target and "{ip}" in template:
        return False, "No device IP or host set for remote commands"
    cmd = template.replace("{ip}", target).replace(
        "{user}", device.get("username", ""))
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=30, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, "ok"
    err = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
    return False, err[:160] or f"exit code {proc.returncode}"

# ------------------------------------------------------------ schedule model

def schedule_active(device: dict) -> bool:
    sch = device.get("schedule")
    if not sch:
        return False
    if sch.get("mode") == "repeating":
        return bool(sch.get("days"))
    if sch.get("mode") == "onetime":
        return not sch.get("fired")
    return False


def schedule_summary(sch: dict) -> str:
    if not sch:
        return "No schedule set"
    if sch.get("mode") == "repeating" and sch.get("days"):
        days = ", ".join(WEEKDAYS[d] for d in sorted(sch["days"]))
        return f"Every {days} at {sch.get('time', '')}"
    if sch.get("mode") == "onetime":
        state = " (fired)" if sch.get("fired") else ""
        return f"Once on {sch.get('date', '')} at {sch.get('time', '')}{state}"
    return "No schedule set"

# ---------------------------------------------------------------- theme

C = {
    "base":     "#0e1015",
    "surface":  "#161a22",
    "raise":    "#1c212b",
    "line":     "#262c38",
    "line_hi":  "#333b4b",
    "accent":   "#8b7cf7",
    "accent_hi": "#9d90fa",
    "accent_lo": "#7568e0",
    "on_accent": "#f6f5ff",
    "text":     "#eceef4",
    "muted":    "#9aa3b5",
    "faint":    "#5d6575",
    "ok":       "#45d18c",
    "warn":     "#e8c35a",
    "err":      "#f0645c",
    "err_bg":   "#2a1c1e",
}
STATE_COLORS = {"ok": C["ok"], "warn": C["warn"], "err": C["err"],
                "muted": C["faint"]}


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def dark_titlebar(window) -> None:
    """Ask DWM for a dark native title bar (Windows 10 1809+)."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (and pre-20H1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), 4) == 0:
                break
    except Exception:
        pass


def pick_family(root, candidates, fallback):
    families = set(tkfont.families(root))
    for name in candidates:
        if name in families:
            return name
    return fallback


class Fonts:
    def __init__(self, root):
        ui = pick_family(root, ["Segoe UI Variable Text", "Segoe UI"], "TkDefaultFont")
        display = pick_family(root, ["Segoe UI Variable Display", ui], ui)
        mono = pick_family(root, ["Cascadia Mono", "Consolas"], "Courier New")
        self.display = (display, 15, "bold")
        self.body = (ui, 10)
        self.strong = (ui, 10, "bold")
        self.small = (ui, 9)
        self.tiny = (ui, 8)
        self.eyebrow = (ui, 8, "bold")
        self.mono = (mono, 9)
        self.mono_small = (mono, 8)


def rounded_points(x1, y1, x2, y2, r):
    """Point list for a smoothed polygon approximating a rounded rect."""
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def draw_round_rect(canvas, x1, y1, x2, y2, r, **kw):
    return canvas.create_polygon(rounded_points(x1, y1, x2, y2, r),
                                 smooth=True, **kw)


def draw_bolt(canvas, cx, cy, scale, fill):
    """Lightning bolt mark, same geometry as the app icon."""
    pts = [(20, -46), (-42, 58), (-4, 58), (-24, 138), (48, 26), (6, 26)]
    coords = [(cx + x * scale, cy + (y - 46) * scale) for x, y in pts]
    return canvas.create_polygon(*[c for xy in coords for c in xy], fill=fill)


def draw_clock(canvas, cx, cy, r, color):
    """Small clock glyph marking an active schedule."""
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=1.4)
    canvas.create_line(cx, cy, cx, cy - r * 0.55, fill=color, width=1.2)
    canvas.create_line(cx, cy, cx + r * 0.45, cy, fill=color, width=1.2)

# ---------------------------------------------------------------- widgets

class Pill(tk.Canvas):
    """Rounded flat button with hover and press states."""

    STYLES = {
        "primary": dict(fill=C["accent"], hover=C["accent_hi"], press=C["accent_lo"],
                        text=C["on_accent"], text_hover=C["on_accent"],
                        line="", line_hover=""),
        "ghost": dict(fill=C["surface"], hover=C["raise"], press=C["base"],
                      text=C["muted"], text_hover=C["text"],
                      line=C["line"], line_hover=C["line_hi"]),
        "danger": dict(fill=C["surface"], hover=C["err_bg"], press=C["base"],
                       text=C["muted"], text_hover=C["err"],
                       line=C["line"], line_hover="#4a2c2e"),
    }

    def __init__(self, parent, text, command, kind="ghost", font=None,
                 padx=14, height=30, bg=None):
        self.style = self.STYLES[kind]
        self.command = command
        font = font or ("Segoe UI", 9, "bold")
        width = tkfont.Font(font=font).measure(text) + padx * 2
        super().__init__(parent, width=width, height=height,
                         bg=bg or parent["bg"], highlightthickness=0, bd=0,
                         cursor="hand2")
        self.rect = draw_round_rect(self, 1, 1, width - 1, height - 1, 12,
                                    fill=self.style["fill"],
                                    outline=self.style["line"] or self.style["fill"])
        self.label = self.create_text(width // 2, height // 2, text=text,
                                      font=font, fill=self.style["text"])
        self.bind("<Enter>", lambda e: self._paint("hover"))
        self.bind("<Leave>", lambda e: self._paint("rest"))
        self.bind("<ButtonPress-1>", lambda e: self._paint("press"))
        self.bind("<ButtonRelease-1>", self._release)

    def _paint(self, state):
        s = self.style
        fill = {"rest": s["fill"], "hover": s["hover"], "press": s["press"]}[state]
        line = s["line_hover"] if state != "rest" else s["line"]
        text = s["text_hover"] if state != "rest" else s["text"]
        self.itemconfigure(self.rect, fill=fill, outline=line or fill)
        self.itemconfigure(self.label, fill=text)

    def _release(self, event):
        self._paint("hover")
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.command()


def themed_menu(parent, fonts):
    return tk.Menu(parent, tearoff=0, bg=C["raise"], fg=C["text"],
                   activebackground=C["accent"], activeforeground=C["on_accent"],
                   relief="flat", bd=0, font=fonts.small)


class DeviceCard(tk.Canvas):
    """One device row: LED, name, technical meta, live status, actions."""

    HEIGHT = 84

    def __init__(self, parent, app, index, device):
        super().__init__(parent, height=self.HEIGHT, bg=C["base"],
                         highlightthickness=0, bd=0)
        self.app, self.index, self.device = app, index, device
        self.state_kind, self.state_text = "muted", ""
        self.buttons = [
            Pill(self, "Wake", lambda: app.wake(self), kind="primary",
                 font=app.fonts.strong, bg=C["surface"], padx=12),
            Pill(self, "Sleep", lambda: app.remote(self, "sleep"),
                 font=app.fonts.small, bg=C["surface"], padx=9),
            Pill(self, "Shutdown", lambda: app.remote(self, "shutdown"),
                 font=app.fonts.small, bg=C["surface"], padx=9),
            Pill(self, "Check", lambda: app.check(self),
                 font=app.fonts.small, bg=C["surface"], padx=9),
            Pill(self, "Schedule", lambda: app.schedule_device(self.index),
                 font=app.fonts.small, bg=C["surface"], padx=9),
            Pill(self, "⋯", self._menu, font=app.fonts.strong,
                 bg=C["surface"], padx=8),
        ]
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", self._maybe_unhover)
        self.bind("<Button-1>", lambda e: app.select(self.index))

    @property
    def selected(self):
        return self.app.selected == self.index

    def _menu(self):
        menu = themed_menu(self, self.app.fonts)
        menu.add_command(label="Edit device",
                         command=lambda: self.app.edit_device(self.index))
        menu.add_command(label="Remove device",
                         command=lambda: self.app.delete_device(self.index))
        x = self.winfo_rootx() + self.winfo_width() - 30
        y = self.winfo_rooty() + self.HEIGHT // 2
        menu.tk_popup(x, y)

    def _hover(self, on):
        self.hovered = on
        self._paint_frame()
        fill = C["raise"] if on else C["surface"]
        for b in self.buttons:
            b.configure(bg=fill)

    def _paint_frame(self):
        on = getattr(self, "hovered", False)
        fill = C["raise"] if on else C["surface"]
        line = C["accent"] if self.selected else (C["line_hi"] if on else C["line"])
        self.itemconfigure(self.bg, fill=fill, outline=line)

    def _maybe_unhover(self, event):
        if not (0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()):
            self._hover(False)

    @staticmethod
    def _fit(text, font, avail):
        """Trim text with an ellipsis so it fits in avail pixels."""
        measure = tkfont.Font(font=font).measure
        if measure(text) <= avail:
            return text
        while text and measure(text + "...") > avail:
            text = text[:-1]
        return text + "..."

    def _buttons_width(self):
        return sum(int(b["width"]) + 8 for b in self.buttons) + 14

    def _draw(self):
        self.delete("all")
        w, h, dev, f = self.winfo_width(), self.HEIGHT, self.device, self.app.fonts
        self.bg = draw_round_rect(self, 1, 2, w - 2, h - 3, 14,
                                  fill=C["surface"], outline=C["line"])
        self.led = self.create_oval(22, 21, 30, 29,
                                    fill=STATE_COLORS[self.state_kind], outline="")
        avail = max(60, w - 46 - self._buttons_width() - 10)
        name_x = 46
        self.create_text(name_x, 25, text=self._fit(dev["name"], f.strong, avail),
                         font=f.strong, fill=C["text"], anchor="w")
        if schedule_active(dev):
            nx = name_x + tkfont.Font(font=f.strong).measure(
                self._fit(dev["name"], f.strong, avail)) + 12
            draw_clock(self, nx, 25, 6, C["accent"])
        wan = dev["host"] != DEFAULT_BROADCAST
        target = f"{dev['host']}  WAN" if wan else "LAN broadcast"
        meta = f"{dev['mac']}   {target}   :{dev['port']}"
        self.create_text(46, 46, text=self._fit(meta, f.mono, avail),
                         font=f.mono, fill=C["muted"], anchor="w")
        self.status_item = self.create_text(
            46, 65, text=self._fit(self.state_text, f.tiny, avail), font=f.tiny,
            fill=STATE_COLORS[self.state_kind], anchor="w")
        x = w - 14
        for b in self.buttons:
            self.create_window(x, h // 2, window=b, anchor="e")
            x -= int(b["width"]) + 8
        self._paint_frame()

    def set_state(self, kind, text):
        """Update the LED and status line. Safe to call for a dead card."""
        if not self.winfo_exists():
            return
        self.state_kind, self.state_text = kind, text
        avail = max(60, self.winfo_width() - 46 - self._buttons_width() - 10)
        self.itemconfigure(self.led, fill=STATE_COLORS[kind])
        self.itemconfigure(self.status_item, fill=STATE_COLORS[kind],
                           text=self._fit(text, self.app.fonts.tiny, avail))

    def pulse(self, color):
        """Expanding ring from the LED: the packet leaving the app."""
        cx, cy = 26, 25
        ring = self.create_oval(cx, cy, cx, cy, outline=color, width=2)

        def step(i=0):
            if not self.winfo_exists():
                return
            if i > 10:
                self.delete(ring)
                return
            r = 4 + i * 2.2
            self.coords(ring, cx - r, cy - r, cx + r, cy + r)
            self.itemconfigure(ring, width=max(1, 2 - i * 0.15))
            self.after(28, lambda: step(i + 1))

        step()

# ---------------------------------------------------------------- dialogs

def styled_entry(parent, font, value=""):
    entry = tk.Entry(parent, font=font, bg=C["surface"], fg=C["text"],
                     insertbackground=C["accent"], relief="flat",
                     highlightthickness=1, highlightbackground=C["line"],
                     highlightcolor=C["accent"])
    entry.insert(0, value)
    return entry


class DeviceDialog(tk.Toplevel):
    """Add/edit device modal. Result in self.result (dict) or None."""

    def __init__(self, parent, device=None):
        super().__init__(parent)
        self.result = None
        self.app = parent
        self.title("Edit device" if device else "Add device")
        self.configure(bg=C["base"])
        self.resizable(False, False)
        self.transient(parent)
        dark_titlebar(self)
        self.grab_set()
        f = parent.fonts
        device = device or {}

        # Scrollable form so the taller v1.3 dialog stays usable on small screens.
        outer = tk.Frame(self, bg=C["base"])
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=C["base"], highlightthickness=0, bd=0,
                           width=360, height=560)
        self.form_canvas = canvas
        scroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview,
                              width=6, relief="flat", bd=0, elementborderwidth=0,
                              bg=C["line_hi"], troughcolor=C["base"],
                              activebackground=C["accent"])
        body = tk.Frame(canvas, bg=C["base"], padx=26, pady=20)
        self.form_body = body
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.bind("<MouseWheel>",
                  lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        self.entries = {}
        # (label, value, hint, font, span) laid out in two columns.
        fields = [
            ("NAME", device.get("name", ""), "How the device appears in the list", f.body, 2),
            ("MAC ADDRESS", device.get("mac", ""), "AA:BB:CC:DD:EE:FF, any separator works", f.mono, 2),
            ("HOST", device.get("host", DEFAULT_BROADCAST),
             "255.255.255.255 for LAN, or IP/DNS for WAN", f.mono, 1),
            ("PORT", str(device.get("port", DEFAULT_PORT)),
             "9 is standard", f.mono, 1),
            ("DEVICE IP", device.get("ip", ""),
             "Optional; pinged for status and remote commands", f.mono, 1),
            ("SERVICE PORT", str(device.get("service_port", "")),
             "Optional; check this TCP port instead of ping", f.mono, 1),
            ("SECUREON PASSWORD", device.get("secureon", ""),
             "Optional 6 hex bytes appended to the packet", f.mono, 1),
            ("USERNAME", device.get("username", ""),
             "Optional; the {user} placeholder for commands", f.mono, 1),
            ("CREDENTIAL HINT", device.get("cred_hint", ""),
             "Optional note only; passwords are never stored", f.body, 2),
        ]
        row = col = 0
        for label, value, hint, font, span in fields:
            if span == 2 and col == 1:
                row += 1
                col = 0
            self._field(body, label, value, hint, font, row, col, span)
            col += span
            if col >= 2:
                row += 1
                col = 0
        if col == 1:
            row += 1

        self.autowake = tk.BooleanVar(value=bool(device.get("autowake")))
        tk.Checkbutton(
            body, text="Wake on app start", variable=self.autowake,
            font=f.small, bg=C["base"], fg=C["muted"], activebackground=C["base"],
            activeforeground=C["text"], selectcolor=C["surface"],
            highlightthickness=0, bd=0, anchor="w", cursor="hand2").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(14, 0))
        row += 1

        # Collapsible Advanced section for custom remote commands.
        self.adv_open = tk.BooleanVar(value=bool(
            device.get("cmd_shutdown") or device.get("cmd_sleep")))
        self.adv_header = tk.Label(
            body, text="", font=f.eyebrow, bg=C["base"], fg=C["accent"],
            anchor="w", cursor="hand2")
        self.adv_header.grid(row=row, column=0, columnspan=2, sticky="w",
                             pady=(16, 0))
        self.adv_header.bind("<Button-1>", lambda e: self._toggle_advanced())
        row += 1
        self.adv_frame = tk.Frame(body, bg=C["base"])
        self.adv_frame.grid(row=row, column=0, columnspan=2, sticky="ew")
        self.adv_frame.columnconfigure(0, weight=1)
        self._field(self.adv_frame, "SHUTDOWN COMMAND",
                    device.get("cmd_shutdown", ""),
                    "Blank uses the default. Placeholders: {ip}, {user}",
                    f.mono_small, 0, 0, 1)
        self._field(self.adv_frame, "SLEEP COMMAND",
                    device.get("cmd_sleep", ""),
                    "Blank uses the default. Power users can set SSH here",
                    f.mono_small, 1, 0, 1)
        tk.Label(self.adv_frame,
                 text=f"Default shutdown: {DEFAULT_SHUTDOWN}",
                 font=(f.small[0], 7), bg=C["base"], fg=C["faint"],
                 anchor="w", wraplength=300, justify="left").grid(
            row=2, column=0, sticky="w", pady=(2, 0))
        row += 1
        self._render_advanced()

        btns = tk.Frame(body, bg=C["base"])
        btns.grid(row=row, column=0, columnspan=2, sticky="e", pady=(20, 0))
        Pill(btns, "Cancel", self.destroy, font=f.small,
             bg=C["base"]).pack(side="left", padx=(0, 8))
        Pill(btns, "Save device", self._save, kind="primary",
             font=f.strong, bg=C["base"]).pack(side="left")

        self._device = device
        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.entries["NAME"].focus_set()
        self.after(10, self._resize_canvas)

    def _resize_canvas(self):
        """Fit the form to its content, capped to the screen so it never
        runs off the bottom; only very tall forms then need to scroll."""
        self.update_idletasks()
        needed = self.form_body.winfo_reqheight()
        cap = self.winfo_screenheight() - 160
        self.form_canvas.configure(height=min(needed, cap))

    def _field(self, parent, label, value, hint, font, row, col, span):
        f = self.app.fonts
        padx = (0, 10) if (span == 1 and col == 0) else (0, 0)
        cell = tk.Frame(parent, bg=C["base"])
        cell.grid(row=row, column=col, columnspan=span, sticky="ew", padx=padx)
        tk.Label(cell, text=label, font=f.eyebrow, bg=C["base"], fg=C["faint"],
                 anchor="w").pack(anchor="w", pady=(12, 4))
        entry = styled_entry(cell, font, value)
        entry.pack(fill="x", ipady=6, ipadx=8)
        tk.Label(cell, text=hint, font=(f.small[0], 8), bg=C["base"],
                 fg=C["faint"], anchor="w").pack(anchor="w", pady=(3, 0))
        self.entries[label] = entry

    def _toggle_advanced(self):
        self.adv_open.set(not self.adv_open.get())
        self._render_advanced()
        self._resize_canvas()

    def _render_advanced(self):
        if self.adv_open.get():
            self.adv_header.configure(text="▾  ADVANCED (REMOTE COMMANDS)")
            self.adv_frame.grid()
        else:
            self.adv_header.configure(text="▸  ADVANCED (REMOTE COMMANDS)")
            self.adv_frame.grid_remove()

    def _save(self):
        get = lambda k: self.entries[k].get().strip()
        name = get("NAME")
        if not name:
            messagebox.showerror(APP_NAME, "Name is required.", parent=self)
            return
        try:
            mac = normalize_mac(get("MAC ADDRESS"))
        except ValueError:
            messagebox.showerror(
                APP_NAME, "Invalid MAC address.\nUse format AA:BB:CC:DD:EE:FF.",
                parent=self)
            return
        try:
            port = int(get("PORT") or DEFAULT_PORT)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, "Port must be 1-65535.", parent=self)
            return
        service_port = get("SERVICE PORT")
        if service_port:
            try:
                sp = int(service_port)
                if not 1 <= sp <= 65535:
                    raise ValueError
            except ValueError:
                messagebox.showerror(APP_NAME, "Service port must be 1-65535.",
                                     parent=self)
                return
        try:
            secureon = normalize_secureon(get("SECUREON PASSWORD"))
        except ValueError:
            messagebox.showerror(
                APP_NAME, "Invalid SecureOn password.\nUse 6 hex bytes like "
                "AA:BB:CC:DD:EE:FF.", parent=self)
            return
        self.result = {
            "name": name, "mac": mac, "host": get("HOST") or DEFAULT_BROADCAST,
            "port": port, "ip": get("DEVICE IP"), "service_port": service_port,
            "secureon": secureon, "username": get("USERNAME"),
            "cred_hint": get("CREDENTIAL HINT"),
            "cmd_shutdown": self.entries["SHUTDOWN COMMAND"].get().strip(),
            "cmd_sleep": self.entries["SLEEP COMMAND"].get().strip(),
            "autowake": self.autowake.get(),
            "schedule": self._device.get("schedule"),
        }
        self.destroy()


class ScheduleDialog(tk.Toplevel):
    """Set a repeating or one-time wake schedule. Result in self.result."""

    SENTINEL = object()

    def __init__(self, parent, device):
        super().__init__(parent)
        self.result = self.SENTINEL  # unchanged unless saved or cleared
        self.title(f"Schedule: {device['name']}")
        self.configure(bg=C["base"], padx=26, pady=22)
        self.resizable(False, False)
        self.transient(parent)
        dark_titlebar(self)
        self.grab_set()
        f = parent.fonts
        sch = device.get("schedule") or {}

        self.mode = tk.StringVar(value=sch.get("mode") or "repeating")
        modes = tk.Frame(self, bg=C["base"])
        modes.pack(anchor="w")
        for text, val in (("Repeating", "repeating"), ("One time", "onetime")):
            tk.Radiobutton(
                modes, text=text, value=val, variable=self.mode,
                command=self._render, font=f.small, bg=C["base"], fg=C["muted"],
                activebackground=C["base"], activeforeground=C["text"],
                selectcolor=C["surface"], highlightthickness=0, bd=0,
                cursor="hand2").pack(side="left", padx=(0, 12))

        # Repeating section
        self.rep = tk.Frame(self, bg=C["base"])
        tk.Label(self.rep, text="DAYS", font=f.eyebrow, bg=C["base"],
                 fg=C["faint"], anchor="w").pack(anchor="w", pady=(14, 6))
        days_row = tk.Frame(self.rep, bg=C["base"])
        days_row.pack(anchor="w")
        self.day_vars = []
        active_days = set(sch.get("days", []))
        for i, name in enumerate(WEEKDAYS):
            var = tk.BooleanVar(value=i in active_days)
            self.day_vars.append(var)
            tk.Checkbutton(
                days_row, text=name, variable=var, font=f.tiny, bg=C["base"],
                fg=C["muted"], activebackground=C["base"],
                activeforeground=C["text"], selectcolor=C["surface"],
                highlightthickness=0, bd=0, cursor="hand2",
                indicatoron=False, width=4, relief="flat",
                offrelief="flat").pack(side="left", padx=2)
        tk.Label(self.rep, text="TIME (HH:MM)", font=f.eyebrow, bg=C["base"],
                 fg=C["faint"], anchor="w").pack(anchor="w", pady=(14, 4))
        self.rep_time = styled_entry(self.rep, f.mono, sch.get("time", "08:00")
                                     if sch.get("mode") != "onetime" else "08:00")
        self.rep_time.pack(fill="x", ipady=6, ipadx=8)

        # One-time section
        self.once = tk.Frame(self, bg=C["base"])
        tk.Label(self.once, text="DATE (YYYY-MM-DD)", font=f.eyebrow, bg=C["base"],
                 fg=C["faint"], anchor="w").pack(anchor="w", pady=(14, 4))
        self.once_date = styled_entry(self.once, f.mono, sch.get("date", "")
                                      if sch.get("mode") == "onetime" else "")
        self.once_date.pack(fill="x", ipady=6, ipadx=8)
        tk.Label(self.once, text="TIME (HH:MM)", font=f.eyebrow, bg=C["base"],
                 fg=C["faint"], anchor="w").pack(anchor="w", pady=(12, 4))
        self.once_time = styled_entry(self.once, f.mono, sch.get("time", "08:00")
                                      if sch.get("mode") == "onetime" else "08:00")
        self.once_time.pack(fill="x", ipady=6, ipadx=8)

        btns = tk.Frame(self, bg=C["base"])
        btns.pack(anchor="e", pady=(22, 0))
        Pill(btns, "Clear schedule", self._clear, kind="danger", font=f.small,
             bg=C["base"]).pack(side="left", padx=(0, 8))
        Pill(btns, "Save", self._save, kind="primary", font=f.strong,
             bg=C["base"]).pack(side="left")

        self._render()
        self.bind("<Escape>", lambda e: self.destroy())

    def _render(self):
        if self.mode.get() == "repeating":
            self.once.pack_forget()
            self.rep.pack(fill="x", anchor="w")
        else:
            self.rep.pack_forget()
            self.once.pack(fill="x", anchor="w")

    @staticmethod
    def _valid_time(text):
        try:
            datetime.strptime(text, "%H:%M")
            return True
        except ValueError:
            return False

    def _clear(self):
        self.result = None
        self.destroy()

    def _save(self):
        if self.mode.get() == "repeating":
            days = [i for i, v in enumerate(self.day_vars) if v.get()]
            t = self.rep_time.get().strip()
            if not days:
                messagebox.showerror(APP_NAME, "Pick at least one day.", parent=self)
                return
            if not self._valid_time(t):
                messagebox.showerror(APP_NAME, "Time must be HH:MM (24 hour).",
                                     parent=self)
                return
            self.result = {"mode": "repeating", "days": days, "time": t}
        else:
            d = self.once_date.get().strip()
            t = self.once_time.get().strip()
            try:
                datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showerror(
                    APP_NAME, "Enter a valid date (YYYY-MM-DD) and time (HH:MM).",
                    parent=self)
                return
            self.result = {"mode": "onetime", "date": d, "time": t, "fired": False}
        self.destroy()


class HistoryOverlay(tk.Frame):
    """Scrollable overlay listing recent wake attempts."""

    def __init__(self, app):
        super().__init__(app, bg=C["base"])
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        f = app.fonts
        panel = tk.Frame(self, bg=C["surface"], highlightthickness=1,
                         highlightbackground=C["line_hi"])
        panel.place(relx=0.5, rely=0.5, anchor="center",
                    relwidth=0.88, relheight=0.82)
        head = tk.Frame(panel, bg=C["surface"])
        head.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(head, text="Wake history", font=f.strong, bg=C["surface"],
                 fg=C["text"]).pack(side="left")
        Pill(head, "Close", self.destroy, font=f.small,
             bg=C["surface"]).pack(side="right")

        text = tk.Text(panel, bg=C["surface"], fg=C["muted"], font=f.mono,
                       relief="flat", bd=0, highlightthickness=0, wrap="none",
                       cursor="arrow", padx=18, pady=4, spacing3=6)
        scroll = tk.Scrollbar(panel, orient="vertical", command=text.yview,
                              width=6, relief="flat", bd=0,
                              elementborderwidth=0, bg=C["line_hi"],
                              troughcolor=C["surface"],
                              activebackground=C["accent"])
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", pady=(0, 14))
        text.pack(fill="both", expand=True, pady=(0, 14))
        for tag, color in (("sent", C["ok"]), ("failed", C["err"]),
                           ("ok", C["ok"]), ("timeout", C["err"]),
                           ("dim", C["faint"])):
            text.tag_configure(tag, foreground=color)

        entries = load_history()[-HISTORY_SHOWN:]
        if not entries:
            text.insert("end", "No wake attempts recorded yet.", "dim")
        for e in reversed(entries):
            ping = e.get("ping")
            ping_txt, ping_tag = (
                ("came online", "ok") if ping is True else
                ("no reply", "timeout") if ping is False else ("", "dim"))
            text.insert("end", f"{e.get('ts', '')}  ", "dim")
            text.insert("end", f"{e.get('device', ''):<16.16}  ")
            text.insert("end", f"{e.get('result', ''):<6}", e.get("result", "dim"))
            text.insert("end", f"  {e.get('target', ''):<20.20}  ", "dim")
            text.insert("end", f"{ping_txt}\n", ping_tag)
        text.configure(state="disabled")

# ---------------------------------------------------------------- main app

class WolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=C["base"])
        self.geometry("760x560")
        self.minsize(680, 460)
        self.fonts = Fonts(self)
        dark_titlebar(self)
        try:
            self.iconbitmap(default=resource_path(os.path.join("assets", "wolmk.ico")))
        except tk.TclError:
            pass
        self.alive = True
        self.selected = None
        self.devices = load_devices()
        self.settings = load_settings()
        self.cards = []
        self.overlay = None
        self.tray = None
        self._fired = set()
        self._build_ui()
        self.render()
        self._bind_shortcuts()
        self._setup_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(600, self._autowake)
        threading.Thread(target=self._scheduler_loop, daemon=True).start()

    # ------------------------------------------------------------ layout

    def _build_ui(self):
        f = self.fonts
        header = tk.Frame(self, bg=C["base"])
        header.pack(fill="x", padx=24, pady=(20, 4))
        logo = tk.Canvas(header, width=30, height=30, bg=C["base"],
                         highlightthickness=0, bd=0)
        draw_round_rect(logo, 1, 1, 29, 29, 9, fill=C["accent"], outline="")
        draw_bolt(logo, 15, 15, 0.145, C["on_accent"])
        logo.pack(side="left")
        titles = tk.Frame(header, bg=C["base"])
        titles.pack(side="left", padx=(12, 0))
        tk.Label(titles, text=APP_NAME, font=f.display, bg=C["base"],
                 fg=C["text"], anchor="w").pack(fill="x")
        tk.Label(titles, text="WAKE ON LAN", font=f.eyebrow, bg=C["base"],
                 fg=C["faint"], anchor="w").pack(fill="x")
        Pill(header, "+  Add device", self.add_device, kind="primary",
             font=f.strong, bg=C["base"], height=32).pack(side="right")
        Pill(header, "Wake all", self.wake_all, font=f.small,
             bg=C["base"], height=32).pack(side="right", padx=(0, 8))

        body = tk.Frame(self, bg=C["base"])
        body.pack(fill="both", expand=True, padx=24, pady=(14, 10))
        self.canvas = tk.Canvas(body, bg=C["base"], highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(
            body, orient="vertical", command=self.canvas.yview, width=6,
            relief="flat", bd=0, elementborderwidth=0,
            bg=C["line_hi"], troughcolor=C["base"], activebackground=C["accent"])
        self.list_frame = tk.Frame(self.canvas, bg=C["base"])
        self._list_window = self.canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", self._sync_scroll)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._list_window, width=e.width))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        footer = tk.Frame(self, bg=C["surface"])
        footer.pack(fill="x", side="bottom")
        tk.Frame(footer, bg=C["line"], height=1).pack(fill="x")
        inner = tk.Frame(footer, bg=C["surface"])
        inner.pack(fill="x", padx=24, pady=6)
        self.status_dot = tk.Canvas(inner, width=8, height=8, bg=C["surface"],
                                    highlightthickness=0, bd=0)
        self._dot = self.status_dot.create_oval(1, 1, 7, 7, fill=C["faint"],
                                                outline="")
        self.status_dot.pack(side="left")
        self.status = tk.Label(inner, text="Ready", font=f.small,
                               bg=C["surface"], fg=C["muted"], anchor="w")
        self.status.pack(side="left", padx=(8, 0))
        tk.Label(inner, text=f"v{APP_VERSION}", font=f.mono_small,
                 bg=C["surface"], fg=C["faint"]).pack(side="right", padx=(12, 0))
        Pill(inner, "⚙  Data", self._data_menu, font=f.small,
             bg=C["surface"], height=24, padx=10).pack(side="right", padx=(8, 0))
        Pill(inner, "History", self.show_history, font=f.small,
             bg=C["surface"], height=24, padx=10).pack(side="right")

    def _data_menu(self):
        menu = themed_menu(self, self.fonts)
        menu.add_command(label="Export devices...", command=self.export_devices)
        menu.add_command(label="Import devices...", command=self.import_devices)
        px = self.winfo_pointerx()
        py = self.winfo_pointery()
        menu.tk_popup(px, py)

    def _sync_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.list_frame.winfo_reqheight() > self.canvas.winfo_height()
        if need and not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y", padx=(6, 0))
        elif not need and self.scrollbar.winfo_ismapped():
            self.scrollbar.pack_forget()

    def render(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.cards = []
        if not self.devices:
            self._empty_state()
            return
        for i, dev in enumerate(self.devices):
            card = DeviceCard(self.list_frame, self, i, dev)
            card.pack(fill="x", pady=3)
            self.cards.append(card)

    def _empty_state(self):
        box = tk.Frame(self.list_frame, bg=C["base"])
        box.pack(expand=True, pady=70)
        mark = tk.Canvas(box, width=56, height=56, bg=C["base"],
                         highlightthickness=0, bd=0)
        draw_round_rect(mark, 1, 1, 55, 55, 16, fill=C["surface"],
                        outline=C["line"])
        draw_bolt(mark, 28, 28, 0.24, C["faint"])
        mark.pack()
        tk.Label(box, text="No devices yet", font=self.fonts.strong,
                 bg=C["base"], fg=C["text"]).pack(pady=(14, 2))
        tk.Label(box, text="Add a device and wake it from here.",
                 font=self.fonts.small, bg=C["base"], fg=C["muted"]).pack()

    # ------------------------------------------------------- interaction

    def _bind_shortcuts(self):
        self.bind("<Control-n>", lambda e: self.add_device())
        self.bind("<Control-w>", lambda e: self._wake_selected())
        self.bind("<Return>", lambda e: self._wake_selected())
        self.bind("<Control-a>", lambda e: self.wake_all())
        self.bind("<Escape>", lambda e: self._dismiss_overlay())

    def select(self, index):
        self.selected = None if self.selected == index else index
        for card in self.cards:
            card._paint_frame()

    def _wake_selected(self):
        if self.selected is not None and self.selected < len(self.cards):
            self.wake(self.cards[self.selected])

    def _dismiss_overlay(self):
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.destroy()
        self.overlay = None

    def show_history(self):
        self._dismiss_overlay()
        self.overlay = HistoryOverlay(self)

    def ui(self, fn):
        """Run fn on the Tk thread; ignore if the app is shutting down."""
        if self.alive:
            try:
                self.after(0, fn)
            except tk.TclError:
                pass

    # ----------------------------------------------------------- devices

    def add_device(self):
        dialog = DeviceDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.devices.append(dialog.result)
            save_devices(self.devices)
            self.render()
            self.set_status(f"Added {dialog.result['name']}", "ok")

    def edit_device(self, index):
        dialog = DeviceDialog(self, self.devices[index])
        self.wait_window(dialog)
        if dialog.result:
            self.devices[index] = dialog.result
            save_devices(self.devices)
            self.render()
            self.set_status(f"Updated {dialog.result['name']}", "ok")

    def delete_device(self, index):
        dev = self.devices[index]
        if messagebox.askyesno(APP_NAME, f"Remove {dev['name']}?", parent=self):
            del self.devices[index]
            save_devices(self.devices)
            self.selected = None
            self.render()
            self.set_status(f"Removed {dev['name']}")

    def schedule_device(self, index):
        dialog = ScheduleDialog(self, self.devices[index])
        self.wait_window(dialog)
        if dialog.result is ScheduleDialog.SENTINEL:
            return
        self.devices[index]["schedule"] = dialog.result
        save_devices(self.devices)
        self.render()
        sch = self.devices[index].get("schedule")
        self.set_status(schedule_summary(sch) if sch else "Schedule cleared", "ok")

    def export_devices(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Export devices", defaultextension=".json",
            initialfile="wolmk-devices.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.devices, f, indent=2)
        except OSError as exc:
            self.set_status(f"Export failed: {exc}", "err")
            return
        self.set_status(f"Exported {len(self.devices)} device(s)", "ok")

    def import_devices(self):
        path = filedialog.askopenfilename(
            parent=self, title="Import devices",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        data = _load_json(path, [])
        if not isinstance(data, list) or not all(
                isinstance(d, dict) and "mac" in d for d in data):
            self.set_status("Import failed: not a valid devices file", "err")
            return
        merge = messagebox.askyesnocancel(
            APP_NAME,
            f"Import {len(data)} device(s).\n\n"
            "Yes = merge with your current list\n"
            "No = replace your current list", parent=self)
        if merge is None:
            return
        self.devices = (self.devices + data) if merge else data
        save_devices(self.devices)
        self.selected = None
        self.render()
        self.set_status(
            f"Imported {len(data)} device(s) ({'merged' if merge else 'replaced'})",
            "ok")

    # ------------------------------------------------------------- wake

    def wake(self, card, announce=True):
        dev = card.device
        count = max(1, int(self.settings.get("send_count", 3)))
        interval = max(0, int(self.settings.get("send_interval", 500)))
        entry = {"id": time.time(),
                 "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "device": dev["name"], "mac": dev["mac"],
                 "target": f"{dev['host']}:{dev['port']}",
                 "result": "sent", "ping": None}

        def send():
            try:
                send_magic_packet(dev["mac"], dev["host"], dev["port"], count,
                                  interval, dev.get("secureon", ""))
            except Exception as exc:
                entry["result"] = "failed"
                append_history(entry)
                self.ui(lambda: card.pulse(C["err"]))
                self.ui(lambda: card.set_state("err", f"Send failed: {exc}"))
                if announce:
                    self.ui(lambda: self.set_status(
                        f"Failed to wake {dev['name']}: {exc}", "err"))
                return
            append_history(entry)
            self.ui(lambda: card.pulse(C["ok"]))
            if announce:
                self.ui(lambda: self.set_status(
                    f"{count} packet(s) sent to {dev['mac']}", "ok"))
            target = ping_target(dev)
            if target:
                self.ui(lambda: card.set_state(
                    "warn", "Packet sent, waiting for reply..."))
                self._watch(card, dev, entry["id"])
            else:
                self.ui(lambda: card.set_state(
                    "muted", "Sent; set a device IP to track status"))

        threading.Thread(target=send, daemon=True).start()

    def _watch(self, card, dev, entry_id):
        """Ping the device until it answers or the watch times out."""
        interval = max(1, int(self.settings.get("watch_interval", 2)))
        timeout = max(interval, int(self.settings.get("watch_timeout", 60)))
        deadline = time.monotonic() + timeout
        while self.alive and time.monotonic() < deadline:
            result = probe_device(dev)
            if result and result[0]:
                _, rtt, label = result
                stamp = datetime.now().strftime("%H:%M:%S")
                self.ui(lambda: card.set_state(
                    "ok", status_text(True, rtt, label, stamp)))
                update_history(entry_id, True)
                return
            time.sleep(interval)
        if self.alive:
            self.ui(lambda: card.set_state("err", f"Unreachable after {timeout} s"))
            update_history(entry_id, False)

    def check(self, card):
        """Manual one-shot status check."""
        dev = card.device
        target = ping_target(dev)
        if not target:
            card.set_state("err", "No device IP set; edit the device to add one")
            return
        label = f"port {dev['service_port']}" if str(
            dev.get("service_port", "")).strip() else target
        card.set_state("warn", f"Checking {label}...")

        def run():
            result = probe_device(dev)
            stamp = datetime.now().strftime("%H:%M:%S")
            online, rtt, lbl = result if result else (False, None, "")
            self.ui(lambda: card.set_state(
                "ok" if online else "err",
                status_text(online, rtt, lbl, stamp)))

        threading.Thread(target=run, daemon=True).start()

    def remote(self, card, kind):
        """Run a remote shutdown or sleep command."""
        dev = card.device
        if kind == "shutdown" and not messagebox.askyesno(
                APP_NAME, f"Send shutdown to {dev['name']}?", parent=self):
            return
        self.set_status(f"Sending {kind} to {dev['name']}...", "muted")

        def run():
            ok, msg = run_remote_command(dev, kind)
            if ok:
                self.ui(lambda: self.set_status(
                    f"{kind.capitalize()} command sent to {dev['name']}", "ok"))
            else:
                self.ui(lambda: self.set_status(
                    f"{kind.capitalize()} failed for {dev['name']}: {msg}", "err"))

        threading.Thread(target=run, daemon=True).start()

    def wake_all(self):
        if not self.cards:
            return
        stagger = max(0, float(self.settings.get("stagger", 2)))
        total = len(self.cards)

        def run():
            for i, card in enumerate(self.cards, 1):
                if not self.alive:
                    return
                self.ui(lambda i=i: self.set_status(
                    f"Waking {i}/{total}...", "warn"))
                self.ui(lambda c=card: self.wake(c, announce=False))
                if i < total:
                    time.sleep(stagger)
            self.ui(lambda: self.set_status(f"Woke {total} device(s)", "ok"))

        threading.Thread(target=run, daemon=True).start()

    def _autowake(self):
        for card in self.cards:
            if card.device.get("autowake"):
                self.wake(card, announce=False)

    def set_status(self, text, kind="muted"):
        color = {"ok": C["ok"], "err": C["err"], "warn": C["warn"],
                 "muted": C["muted"]}[kind]
        self.status.configure(text=text, fg=color)
        self.status_dot.itemconfigure(
            self._dot, fill=color if kind != "muted" else C["faint"])

    # -------------------------------------------------------- scheduler

    def _scheduler_loop(self):
        while self.alive:
            try:
                self._check_schedules()
            except Exception:
                pass
            for _ in range(30):
                if not self.alive:
                    return
                time.sleep(1)

    def _check_schedules(self):
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        today = now.weekday()
        datestr = now.strftime("%Y-%m-%d")
        for idx, dev in enumerate(self.devices):
            sch = dev.get("schedule")
            if not sch:
                continue
            if sch.get("mode") == "repeating":
                if today in sch.get("days", []) and sch.get("time") == hhmm:
                    key = f"{dev.get('mac')}:{datestr}:{hhmm}"
                    if key not in self._fired:
                        self._fired.add(key)
                        self.ui(lambda i=idx: self._fire_schedule(i))
            elif sch.get("mode") == "onetime" and not sch.get("fired"):
                try:
                    dt = datetime.strptime(
                        f"{sch.get('date')} {sch.get('time')}", "%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    continue
                if now >= dt:
                    sch["fired"] = True
                    save_devices(self.devices)
                    self.ui(lambda i=idx: self._fire_schedule(i))

    def _fire_schedule(self, idx):
        if idx < len(self.cards):
            self.set_status(
                f"Scheduled wake for {self.devices[idx]['name']}", "ok")
            self.wake(self.cards[idx], announce=False)
            if self.devices[idx].get("schedule", {}).get("mode") == "onetime":
                self.render()  # refresh the clock icon now that it fired

    # -------------------------------------------------------------- tray

    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return
        try:
            image = Image.open(resource_path(os.path.join("assets", "wolmk.png")))
        except OSError:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda *a: self.ui(self._show_window),
                             default=True),
            pystray.MenuItem("Wake all", lambda *a: self.ui(self.wake_all)),
            pystray.MenuItem("Exit", lambda *a: self.ui(self.quit_app)))
        self.tray = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self):
        if self.tray:
            self.withdraw()
            self.set_status("Running in the system tray")
        else:
            self.quit_app()

    def quit_app(self):
        self.alive = False
        if self.tray:
            self.tray.stop()
        self.destroy()


def main():
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
