package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// App holds the application state and exposes bound methods to the frontend.
type App struct {
	ctx      context.Context
	mu       sync.Mutex
	devices  []Device
	settings Settings
	watchers map[string]context.CancelFunc // keyed by MAC
	fired    map[string]bool               // repeating schedule dedupe keys
	quitting bool
	trayReady bool
}

// Response is a simple result for actions that can fail validation.
type Response struct {
	OK    bool   `json:"ok"`
	Error string `json:"error"`
}

// ImportResult carries devices parsed from an import file.
type ImportResult struct {
	OK      bool     `json:"ok"`
	Error   string   `json:"error"`
	Devices []Device `json:"devices"`
}

// NewApp creates a new App.
func NewApp() *App {
	return &App{
		devices:  loadDevices(),
		settings: loadSettings(),
		watchers: map[string]context.CancelFunc{},
		fired:    map[string]bool{},
	}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	go a.schedulerLoop()
	a.setupTray()
}

// OnReady is called by the frontend once it has registered event listeners.
// Autowake fires here so the UI can display the resulting status.
func (a *App) OnReady() {
	a.mu.Lock()
	devices := append([]Device(nil), a.devices...)
	a.mu.Unlock()
	for _, d := range devices {
		if d.AutoWake {
			a.wakeDevice(d, false)
		}
	}
}

// ---- getters ------------------------------------------------------------

func (a *App) GetDevices() []Device {
	a.mu.Lock()
	defer a.mu.Unlock()
	return append([]Device(nil), a.devices...)
}

func (a *App) GetSettings() Settings {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.settings
}

func (a *App) GetHistory() []HistoryEntry {
	h := loadHistory()
	if len(h) > historyShown {
		h = h[len(h)-historyShown:]
	}
	// newest first
	for i, j := 0, len(h)-1; i < j; i, j = i+1, j-1 {
		h[i], h[j] = h[j], h[i]
	}
	return h
}

func (a *App) Version() string { return appVersion }

// ---- device CRUD --------------------------------------------------------

func sanitizeDevice(d Device) (Device, error) {
	d.Name = strings.TrimSpace(d.Name)
	if d.Name == "" {
		return d, fmt.Errorf("Name is required.")
	}
	mac, err := normalizeMAC(d.MAC)
	if err != nil {
		return d, fmt.Errorf("Invalid MAC address. Use format AA:BB:CC:DD:EE:FF.")
	}
	d.MAC = mac
	d.Host = strings.TrimSpace(d.Host)
	if d.Host == "" {
		d.Host = defaultBroadcast
	}
	if d.Port == 0 {
		d.Port = defaultPort
	}
	if d.Port < 1 || d.Port > 65535 {
		return d, fmt.Errorf("Port must be 1-65535.")
	}
	if sp := strings.TrimSpace(d.ServicePort); sp != "" {
		n, err := strconv.Atoi(sp)
		if err != nil || n < 1 || n > 65535 {
			return d, fmt.Errorf("Service port must be 1-65535.")
		}
		d.ServicePort = sp
	}
	so, err := normalizeSecureOn(d.SecureOn)
	if err != nil {
		return d, fmt.Errorf("Invalid SecureOn password. Use 6 hex bytes like AA:BB:CC:DD:EE:FF.")
	}
	d.SecureOn = so
	d.IP = strings.TrimSpace(d.IP)
	d.AgentToken = strings.TrimSpace(d.AgentToken)
	if d.AgentPort < 0 || d.AgentPort > 65535 {
		return d, fmt.Errorf("Agent port must be 1-65535.")
	}
	return d, nil
}

func (a *App) AddDevice(d Device) Response {
	clean, err := sanitizeDevice(d)
	if err != nil {
		return Response{false, err.Error()}
	}
	a.mu.Lock()
	a.devices = append(a.devices, clean)
	err = saveDevices(a.devices)
	a.mu.Unlock()
	return respFrom(err)
}

func (a *App) UpdateDevice(index int, d Device) Response {
	clean, err := sanitizeDevice(d)
	if err != nil {
		return Response{false, err.Error()}
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if index < 0 || index >= len(a.devices) {
		return Response{false, "Device not found."}
	}
	// Preserve an existing schedule unless the caller supplied one.
	if clean.Schedule == nil {
		clean.Schedule = a.devices[index].Schedule
	}
	a.devices[index] = clean
	return respFrom(saveDevices(a.devices))
}

func (a *App) DeleteDevice(index int) Response {
	a.mu.Lock()
	defer a.mu.Unlock()
	if index < 0 || index >= len(a.devices) {
		return Response{false, "Device not found."}
	}
	a.devices = append(a.devices[:index], a.devices[index+1:]...)
	return respFrom(saveDevices(a.devices))
}

func (a *App) SetSchedule(index int, s *Schedule) Response {
	a.mu.Lock()
	defer a.mu.Unlock()
	if index < 0 || index >= len(a.devices) {
		return Response{false, "Device not found."}
	}
	a.devices[index].Schedule = s
	return respFrom(saveDevices(a.devices))
}

// SaveDeviceList replaces the whole list (used by import merge/replace).
func (a *App) SaveDeviceList(devices []Device) Response {
	cleaned := make([]Device, 0, len(devices))
	for _, d := range devices {
		c, err := sanitizeDevice(d)
		if err != nil {
			continue // skip invalid rows rather than failing the whole import
		}
		c.Schedule = d.Schedule
		cleaned = append(cleaned, c)
	}
	a.mu.Lock()
	a.devices = cleaned
	err := saveDevices(a.devices)
	a.mu.Unlock()
	return respFrom(err)
}

// ---- wake / status ------------------------------------------------------

func (a *App) deviceAt(index int) (Device, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if index < 0 || index >= len(a.devices) {
		return Device{}, false
	}
	return a.devices[index], true
}

func (a *App) Wake(index int) {
	if d, ok := a.deviceAt(index); ok {
		a.wakeDevice(d, true)
	}
}

func (a *App) wakeDevice(d Device, announce bool) {
	a.mu.Lock()
	s := a.settings
	a.mu.Unlock()
	entry := HistoryEntry{
		ID:     time.Now().UnixNano(),
		TS:     time.Now().Format("2006-01-02 15:04:05"),
		Device: d.Name, MAC: d.MAC,
		Target: fmt.Sprintf("%s:%d", d.Host, d.Port),
		Result: "sent",
	}
	go func() {
		err := sendMagicPacket(d.MAC, d.Host, d.Port, s.SendCount, s.SendInterval, d.SecureOn)
		if err != nil {
			entry.Result = "failed"
			appendHistory(entry)
			a.emitPulse(d.MAC, "err")
			a.emitStatus(d.MAC, "err", "Send failed: "+err.Error())
			if announce {
				a.emitBar(fmt.Sprintf("Failed to wake %s: %s", d.Name, err.Error()), "err")
			}
			return
		}
		appendHistory(entry)
		a.emitPulse(d.MAC, "ok")
		if announce {
			msg := fmt.Sprintf("%d packet(s) sent to %s", s.SendCount, d.MAC)
			if resolved := resolveHost(d.Host); resolved != d.Host && resolved != "" {
				msg += " via " + resolved
			}
			a.emitBar(msg, "ok")
		}
		if pingTarget(d) != "" {
			a.emitStatus(d.MAC, "warn", "Packet sent, waiting for reply...")
			a.watch(d, entry.ID)
		} else {
			a.emitStatus(d.MAC, "muted", "Sent; set a device IP to track status")
		}
	}()
}

func (a *App) watch(d Device, id int64) {
	a.cancelWatch(d.MAC)
	ctx, cancel := context.WithCancel(context.Background())
	a.mu.Lock()
	a.watchers[d.MAC] = cancel
	interval := a.settings.WatchInterval
	timeout := a.settings.WatchTimeout
	a.mu.Unlock()
	if interval < 1 {
		interval = 1
	}
	if timeout < interval {
		timeout = interval
	}
	deadline := time.Now().Add(time.Duration(timeout) * time.Second)
	for time.Now().Before(deadline) {
		select {
		case <-ctx.Done():
			return
		default:
		}
		has, online, rtt, label := probeDevice(d)
		if has && online {
			a.emitStatus(d.MAC, "ok", statusText(true, rtt, label, time.Now().Format("15:04:05")))
			updateHistoryPing(id, true)
			a.clearWatch(d.MAC)
			return
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Duration(interval) * time.Second):
		}
	}
	a.emitStatus(d.MAC, "err", fmt.Sprintf("Unreachable after %d s", timeout))
	updateHistoryPing(id, false)
	a.clearWatch(d.MAC)
}

func (a *App) cancelWatch(mac string) {
	a.mu.Lock()
	if cancel, ok := a.watchers[mac]; ok {
		cancel()
		delete(a.watchers, mac)
	}
	a.mu.Unlock()
}

func (a *App) clearWatch(mac string) {
	a.mu.Lock()
	delete(a.watchers, mac)
	a.mu.Unlock()
}

func (a *App) Check(index int) {
	d, ok := a.deviceAt(index)
	if !ok {
		return
	}
	target := pingTarget(d)
	if target == "" {
		a.emitStatus(d.MAC, "err", "No device IP set; edit the device to add one")
		return
	}
	label := target
	if sp := strings.TrimSpace(d.ServicePort); sp != "" {
		label = "port " + sp
	}
	a.emitStatus(d.MAC, "warn", "Checking "+label+"...")
	go func() {
		_, online, rtt, lbl := probeDevice(d)
		kind := "err"
		if online {
			kind = "ok"
		}
		a.emitStatus(d.MAC, kind, statusText(online, rtt, lbl, time.Now().Format("15:04:05")))
	}()
}

func (a *App) WakeAll() {
	a.mu.Lock()
	devices := append([]Device(nil), a.devices...)
	stagger := a.settings.Stagger
	a.mu.Unlock()
	if len(devices) == 0 {
		return
	}
	go func() {
		total := len(devices)
		for i, d := range devices {
			a.emitBar(fmt.Sprintf("Waking %d/%d...", i+1, total), "warn")
			a.wakeDevice(d, false)
			if i < total-1 && stagger > 0 {
				time.Sleep(time.Duration(stagger) * time.Second)
			}
		}
		a.emitBar(fmt.Sprintf("Woke %d device(s)", total), "ok")
	}()
}

// ---- remote power -------------------------------------------------------

// Remote runs a power action (shutdown, sleep, reboot, lock). It uses the
// companion agent when the device has agent credentials, otherwise falls back
// to the custom or default command template for shutdown and sleep.
func (a *App) Remote(index int, action string) {
	d, ok := a.deviceAt(index)
	if !ok {
		return
	}
	a.emitBar(fmt.Sprintf("Sending %s to %s...", action, d.Name), "muted")
	go func() {
		err := performRemote(d, action)
		if err != nil {
			a.emitBar(fmt.Sprintf("%s failed for %s: %s", title(action), d.Name, err.Error()), "err")
			return
		}
		a.emitBar(fmt.Sprintf("%s command sent to %s", title(action), d.Name), "ok")
	}()
}

// ---- import / export ----------------------------------------------------

func (a *App) ExportDevices() Response {
	path, err := wruntime.SaveFileDialog(a.ctx, wruntime.SaveDialogOptions{
		DefaultFilename: "wolmk-devices.json",
		Title:           "Export devices",
		Filters:         []wruntime.FileFilter{{DisplayName: "JSON", Pattern: "*.json"}},
	})
	if err != nil || path == "" {
		return Response{OK: false}
	}
	a.mu.Lock()
	data, _ := json.MarshalIndent(a.devices, "", "  ")
	count := len(a.devices)
	a.mu.Unlock()
	if err := os.WriteFile(path, data, 0o644); err != nil {
		return Response{false, err.Error()}
	}
	a.emitBar(fmt.Sprintf("Exported %d device(s)", count), "ok")
	return Response{OK: true}
}

func (a *App) ImportDevices() ImportResult {
	path, err := wruntime.OpenFileDialog(a.ctx, wruntime.OpenDialogOptions{
		Title:   "Import devices",
		Filters: []wruntime.FileFilter{{DisplayName: "JSON", Pattern: "*.json"}},
	})
	if err != nil || path == "" {
		return ImportResult{OK: false}
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return ImportResult{Error: "Could not read the file."}
	}
	var devices []Device
	if err := json.Unmarshal(data, &devices); err != nil {
		return ImportResult{Error: "Not a valid devices file."}
	}
	for _, d := range devices {
		if strings.TrimSpace(d.MAC) == "" {
			return ImportResult{Error: "Not a valid devices file."}
		}
	}
	return ImportResult{OK: true, Devices: devices}
}

// ---- scheduler ----------------------------------------------------------

func (a *App) schedulerLoop() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		if a.quitting {
			return
		}
		a.checkSchedules()
	}
}

func (a *App) checkSchedules() {
	now := time.Now()
	hhmm := now.Format("15:04")
	today := int(now.Weekday()+6) % 7 // Go: Sunday=0; convert to Monday=0
	dateStr := now.Format("2006-01-02")

	a.mu.Lock()
	devices := append([]Device(nil), a.devices...)
	a.mu.Unlock()

	for i := range devices {
		d := devices[i]
		if d.Schedule == nil {
			continue
		}
		sch := d.Schedule
		switch sch.Mode {
		case "repeating":
			if sch.Time == hhmm && containsInt(sch.Days, today) {
				key := d.MAC + ":" + dateStr + ":" + hhmm
				a.mu.Lock()
				already := a.fired[key]
				a.fired[key] = true
				a.mu.Unlock()
				if !already {
					a.fireSchedule(d)
				}
			}
		case "onetime":
			if sch.Fired {
				continue
			}
			when, err := time.ParseInLocation("2006-01-02 15:04", sch.Date+" "+sch.Time, time.Local)
			if err != nil {
				continue
			}
			if !now.Before(when) {
				a.mu.Lock()
				if i < len(a.devices) && a.devices[i].Schedule != nil {
					a.devices[i].Schedule.Fired = true
					_ = saveDevices(a.devices)
				}
				a.mu.Unlock()
				a.fireSchedule(d)
				a.emitDevicesChanged()
			}
		}
	}
}

func (a *App) fireSchedule(d Device) {
	a.emitBar("Scheduled wake for "+d.Name, "ok")
	a.wakeDevice(d, false)
}

// ---- event helpers ------------------------------------------------------

func (a *App) emitStatus(mac, kind, text string) {
	if a.ctx != nil {
		wruntime.EventsEmit(a.ctx, "status", StatusEvent{MAC: mac, Kind: kind, Text: text})
	}
}

func (a *App) emitPulse(mac, kind string) {
	if a.ctx != nil {
		wruntime.EventsEmit(a.ctx, "pulse", map[string]string{"mac": mac, "kind": kind})
	}
}

func (a *App) emitBar(text, kind string) {
	if a.ctx != nil {
		wruntime.EventsEmit(a.ctx, "statusbar", map[string]string{"text": text, "kind": kind})
	}
}

func (a *App) emitDevicesChanged() {
	if a.ctx != nil {
		wruntime.EventsEmit(a.ctx, "devices:changed")
	}
}

// ---- window / lifecycle -------------------------------------------------

func (a *App) beforeClose(ctx context.Context) bool {
	if a.quitting || !a.trayReady {
		return false // allow the app to close
	}
	wruntime.WindowHide(ctx)
	a.emitBar("Running in the system tray", "muted")
	return true // keep running in the tray
}

func (a *App) showWindow() {
	if a.ctx != nil {
		wruntime.WindowShow(a.ctx)
	}
}

func (a *App) quitApp() {
	a.quitting = true
	if a.ctx != nil {
		wruntime.Quit(a.ctx)
	}
}

// ---- small helpers ------------------------------------------------------

func respFrom(err error) Response {
	if err != nil {
		return Response{false, err.Error()}
	}
	return Response{OK: true}
}

func containsInt(s []int, v int) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}

func title(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
