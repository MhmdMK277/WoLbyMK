#!/usr/bin/env python3
"""WoLmk, a tiny Wake-on-LAN desktop app.

Sends WOL magic packets over UDP to wake machines on your LAN,
or over the internet via a router/relay host (WAN wake).

Magic packet format: 6 bytes of 0xFF followed by the target MAC
address repeated 16 times, sent as a UDP datagram (default port 9).
"""

import ctypes
import json
import os
import re
import socket
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

APP_NAME = "WoLmk"
APP_VERSION = "1.1.0"
DEFAULT_PORT = 9
DEFAULT_BROADCAST = "255.255.255.255"

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
    "err":      "#f0645c",
    "err_bg":   "#2a1c1e",
}


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


class DeviceCard(tk.Canvas):
    """One device row: LED, name, technical meta line, actions."""

    HEIGHT = 66

    def __init__(self, parent, app, index, device):
        super().__init__(parent, height=self.HEIGHT, bg=C["base"],
                         highlightthickness=0, bd=0)
        self.app, self.index, self.device = app, index, device
        self.hovered = False
        self.buttons = [
            Pill(self, "Wake", lambda: app.wake(self), kind="primary",
                 font=app.fonts.strong, bg=C["surface"]),
            Pill(self, "Edit", lambda: app.edit_device(index),
                 font=app.fonts.small, bg=C["surface"]),
            Pill(self, "Remove", lambda: app.delete_device(index), kind="danger",
                 font=app.fonts.small, bg=C["surface"]),
        ]
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", self._maybe_unhover)

    def _hover(self, on):
        self.hovered = on
        fill = C["raise"] if on else C["surface"]
        line = C["line_hi"] if on else C["line"]
        self.itemconfigure(self.bg, fill=fill, outline=line)
        for b in self.buttons:
            b.configure(bg=fill)

    def _maybe_unhover(self, event):
        if not (0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()):
            self._hover(False)

    def _draw(self):
        self.delete("all")
        w, h, dev, f = self.winfo_width(), self.HEIGHT, self.device, self.app.fonts
        self.bg = draw_round_rect(self, 1, 2, w - 2, h - 3, 14,
                                  fill=C["surface"], outline=C["line"])
        self.led = self.create_oval(22, h // 2 - 4, 30, h // 2 + 4,
                                    fill=C["faint"], outline="")
        self.create_text(46, 22, text=dev["name"], font=f.strong,
                         fill=C["text"], anchor="w")
        wan = dev["host"] != DEFAULT_BROADCAST
        target = f"{dev['host']}  WAN" if wan else "LAN broadcast"
        meta = f"{dev['mac']}   {target}   :{dev['port']}"
        self.create_text(46, 44, text=meta, font=f.mono, fill=C["muted"],
                         anchor="w")
        x = w - 14
        for b in self.buttons:
            self.create_window(x, h // 2, window=b, anchor="e")
            x -= int(b["width"]) + 8

    def pulse(self, color):
        """Expanding ring from the LED: the packet leaving the app."""
        self.itemconfigure(self.led, fill=color)
        cx, cy = 26, self.HEIGHT // 2
        ring = self.create_oval(cx, cy, cx, cy, outline=color, width=2)

        def step(i=0):
            if i > 10:
                self.delete(ring)
                self.after(2500, lambda: self.itemconfigure(self.led, fill=C["faint"]))
                return
            r = 4 + i * 2.2
            self.coords(ring, cx - r, cy - r, cx + r, cy + r)
            self.itemconfigure(ring, width=max(1, 2 - i * 0.15))
            self.after(28, lambda: step(i + 1))

        step()

# ---------------------------------------------------------------- dialog

class DeviceDialog(tk.Toplevel):
    """Add/edit device modal. Result in self.result (dict) or None."""

    def __init__(self, parent, device=None):
        super().__init__(parent)
        self.result = None
        self.title("Edit device" if device else "Add device")
        self.configure(bg=C["base"], padx=26, pady=20)
        self.resizable(False, False)
        self.transient(parent)
        dark_titlebar(self)
        self.grab_set()
        f = parent.fonts

        device = device or {}
        fields = [
            ("NAME", device.get("name", ""), "How the device appears in the list", f.body),
            ("MAC ADDRESS", device.get("mac", ""), "AA:BB:CC:DD:EE:FF, any separator works", f.mono),
            ("HOST", device.get("host", DEFAULT_BROADCAST),
             "255.255.255.255 for LAN, public IP or DNS name for WAN", f.mono),
            ("PORT", str(device.get("port", DEFAULT_PORT)),
             "9 is standard; use your forwarded port for WAN", f.mono),
        ]
        self.entries = {}
        for row, (label, value, hint, font) in enumerate(fields):
            tk.Label(self, text=label, font=f.eyebrow, bg=C["base"],
                     fg=C["faint"], anchor="w").grid(
                row=row * 3, column=0, sticky="w", pady=(14 if row else 0, 4))
            entry = tk.Entry(self, font=font, width=36, bg=C["surface"],
                             fg=C["text"], insertbackground=C["accent"],
                             relief="flat", highlightthickness=1,
                             highlightbackground=C["line"],
                             highlightcolor=C["accent"])
            entry.insert(0, value)
            entry.grid(row=row * 3 + 1, column=0, sticky="ew", ipady=6, ipadx=8)
            tk.Label(self, text=hint, font=(f.small[0], 8), bg=C["base"],
                     fg=C["faint"], anchor="w").grid(
                row=row * 3 + 2, column=0, sticky="w", pady=(3, 0))
            self.entries[label] = entry

        btns = tk.Frame(self, bg=C["base"])
        btns.grid(row=12, column=0, sticky="e", pady=(22, 0))
        Pill(btns, "Cancel", self.destroy, font=f.small,
             bg=C["base"]).pack(side="left", padx=(0, 8))
        Pill(btns, "Save device", self._save, kind="primary",
             font=f.strong, bg=C["base"]).pack(side="left")

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.entries["NAME"].focus_set()

    def _save(self):
        name = self.entries["NAME"].get().strip()
        mac = self.entries["MAC ADDRESS"].get().strip()
        host = self.entries["HOST"].get().strip() or DEFAULT_BROADCAST
        port_s = self.entries["PORT"].get().strip() or str(DEFAULT_PORT)
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
        self.title(APP_NAME)
        self.configure(bg=C["base"])
        self.geometry("640x520")
        self.minsize(560, 420)
        self.fonts = Fonts(self)
        dark_titlebar(self)
        try:
            # default=... also applies the icon to child dialogs
            self.iconbitmap(default=resource_path(os.path.join("assets", "wolmk.ico")))
        except tk.TclError:
            pass
        self.devices = load_devices()
        self.cards = []
        self._build_ui()
        self.render()

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
        inner.pack(fill="x", padx=24, pady=7)
        self.status_dot = tk.Canvas(inner, width=8, height=8, bg=C["surface"],
                                    highlightthickness=0, bd=0)
        self._dot = self.status_dot.create_oval(1, 1, 7, 7, fill=C["faint"],
                                                outline="")
        self.status_dot.pack(side="left")
        self.status = tk.Label(inner, text="Ready", font=f.small,
                               bg=C["surface"], fg=C["muted"], anchor="w")
        self.status.pack(side="left", padx=(8, 0))
        tk.Label(inner, text=f"v{APP_VERSION}", font=f.mono_small,
                 bg=C["surface"], fg=C["faint"]).pack(side="right")

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

    # ----------------------------------------------------------- actions

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
            self.render()
            self.set_status(f"Removed {dev['name']}")

    def wake(self, card):
        dev = card.device
        try:
            send_magic_packet(dev["mac"], dev["host"], dev["port"])
        except Exception as exc:
            card.pulse(C["err"])
            self.set_status(f"Failed to wake {dev['name']}: {exc}", "err")
            return
        card.pulse(C["ok"])
        self.set_status(
            f"Magic packet sent to {dev['name']} ({dev['host']}:{dev['port']})", "ok")

    def set_status(self, text, kind="muted"):
        color = {"ok": C["ok"], "err": C["err"], "muted": C["muted"]}[kind]
        self.status.configure(text=text, fg=color)
        self.status_dot.itemconfigure(
            self._dot, fill=color if kind != "muted" else C["faint"])


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
