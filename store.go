package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
)

// configDir returns the OS-appropriate application data directory,
// creating it if needed.
func configDir() string {
	var dir string
	switch runtime.GOOS {
	case "windows":
		base := os.Getenv("APPDATA")
		if base == "" {
			base, _ = os.UserConfigDir()
		}
		dir = filepath.Join(base, appName)
	case "darwin":
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, "Library", "Application Support", "wolmk")
	default: // linux and other unix
		if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
			dir = filepath.Join(xdg, "wolmk")
		} else {
			home, _ := os.UserHomeDir()
			dir = filepath.Join(home, ".config", "wolmk")
		}
	}
	_ = os.MkdirAll(dir, 0o755)
	return dir
}

func devicesPath() string  { return filepath.Join(configDir(), "devices.json") }
func settingsPath() string { return filepath.Join(configDir(), "settings.json") }
func historyPath() string  { return filepath.Join(configDir(), "history.json") }

func loadDevices() []Device {
	var devices []Device
	readJSON(devicesPath(), &devices)
	if devices == nil {
		devices = []Device{}
	}
	return devices
}

func saveDevices(devices []Device) error {
	return writeJSON(devicesPath(), devices)
}

func loadSettings() Settings {
	s := defaultSettings()
	readJSON(settingsPath(), &s)
	if s.WatchInterval < 1 {
		s.WatchInterval = 1
	}
	if s.SendCount < 1 {
		s.SendCount = 1
	}
	return s
}

func loadHistory() []HistoryEntry {
	var h []HistoryEntry
	readJSON(historyPath(), &h)
	if h == nil {
		h = []HistoryEntry{}
	}
	return h
}

func appendHistory(entry HistoryEntry) {
	h := loadHistory()
	h = append(h, entry)
	if len(h) > historyLimit {
		h = h[len(h)-historyLimit:]
	}
	_ = writeJSON(historyPath(), h)
}

func updateHistoryPing(id int64, ok bool) {
	h := loadHistory()
	for i := len(h) - 1; i >= 0; i-- {
		if h[i].ID == id {
			h[i].Ping = &ok
			break
		}
	}
	_ = writeJSON(historyPath(), h)
}

func readJSON(path string, out interface{}) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	// Tolerate a UTF-8 BOM from hand-edited files.
	data = bytes.TrimPrefix(data, []byte{0xEF, 0xBB, 0xBF})
	_ = json.Unmarshal(data, out)
}

func writeJSON(path string, v interface{}) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}
