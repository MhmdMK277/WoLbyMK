package main

// Data model shared with the frontend over the Wails bindings.
// JSON tags use lowerCamelCase so the JS side reads natural field names.

const (
	appName          = "WoLmk"
	appVersion       = "2.0.0"
	defaultPort      = 9
	defaultBroadcast = "255.255.255.255"
	historyLimit     = 200
	historyShown     = 50
)

// Schedule is an optional per-device wake schedule.
type Schedule struct {
	Mode  string `json:"mode"`  // "repeating" or "onetime"
	Days  []int  `json:"days"`  // repeating: 0=Mon .. 6=Sun
	Time  string `json:"time"`  // HH:MM (24 hour)
	Date  string `json:"date"`  // onetime: YYYY-MM-DD
	Fired bool   `json:"fired"` // onetime: set true once it runs
}

// Device is a single wake target and all of its optional settings.
type Device struct {
	Name        string    `json:"name"`
	MAC         string    `json:"mac"`
	Host        string    `json:"host"` // broadcast or WAN address
	Port        int       `json:"port"`
	IP          string    `json:"ip"`          // optional; used for ping and commands
	ServicePort string    `json:"servicePort"` // optional; TCP port to check
	SecureOn    string    `json:"secureon"`    // optional 6 hex bytes
	Username    string    `json:"username"`    // optional; {user} placeholder
	CredHint    string    `json:"credHint"`    // optional note, never a password
	CmdShutdown string    `json:"cmdShutdown"` // optional custom command
	CmdSleep    string    `json:"cmdSleep"`    // optional custom command
	AutoWake    bool      `json:"autowake"`
	Schedule    *Schedule `json:"schedule"`
}

// Settings controls wake and watch behavior. All values have defaults.
type Settings struct {
	WatchTimeout  int `json:"watchTimeout"`  // seconds to keep pinging after a wake
	WatchInterval int `json:"watchInterval"` // seconds between pings
	SendCount     int `json:"sendCount"`     // packets per wake
	SendInterval  int `json:"sendInterval"`  // milliseconds between packets
	Stagger       int `json:"stagger"`       // seconds between devices on Wake all
}

func defaultSettings() Settings {
	return Settings{WatchTimeout: 60, WatchInterval: 2, SendCount: 3,
		SendInterval: 500, Stagger: 2}
}

// HistoryEntry is one recorded wake attempt.
type HistoryEntry struct {
	ID     int64  `json:"id"`
	TS     string `json:"ts"`
	Device string `json:"device"`
	MAC    string `json:"mac"`
	Target string `json:"target"`
	Result string `json:"result"` // "sent" or "failed"
	Ping   *bool  `json:"ping"`   // null unknown, true online, false no reply
}

// StatusEvent is emitted to the frontend to drive a card's live LED.
type StatusEvent struct {
	MAC  string `json:"mac"`
	Kind string `json:"kind"` // ok, warn, err, muted
	Text string `json:"text"`
}
