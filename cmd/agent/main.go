// Command WoLmk-Agent is a lightweight companion service that runs on a
// target machine and executes power commands (shutdown, reboot, sleep, lock)
// on request from the WoLmk desktop or web app. Requests are authenticated
// with a token generated on first run.
package main

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strconv"

	_ "embed"

	"github.com/energye/systray"
	"WoLmk/internal/agentproto"
	"WoLmk/internal/netinfo"
)

//go:embed icon.ico
var iconICO []byte

// Config is the agent's persisted settings.
type Config struct {
	Token string `json:"token"`
	Port  int    `json:"port"`
}

func configDirAgent() string {
	var dir string
	switch runtime.GOOS {
	case "windows":
		base := os.Getenv("APPDATA")
		if base == "" {
			base, _ = os.UserConfigDir()
		}
		dir = filepath.Join(base, "WoLmk-Agent")
	case "darwin":
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, "Library", "Application Support", "wolmk-agent")
	default:
		if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
			dir = filepath.Join(xdg, "wolmk-agent")
		} else {
			home, _ := os.UserHomeDir()
			dir = filepath.Join(home, ".config", "wolmk-agent")
		}
	}
	_ = os.MkdirAll(dir, 0o755)
	return dir
}

func configPath() string { return filepath.Join(configDirAgent(), "agent.json") }

func newToken() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// loadConfig reads the config, creating it with a fresh token on first run.
func loadConfig() Config {
	cfg := Config{Port: agentproto.DefaultPort}
	if data, err := os.ReadFile(configPath()); err == nil {
		_ = json.Unmarshal(data, &cfg)
	}
	changed := false
	if cfg.Token == "" {
		cfg.Token = newToken()
		changed = true
	}
	if cfg.Port == 0 {
		cfg.Port = agentproto.DefaultPort
		changed = true
	}
	if changed {
		data, _ := json.MarshalIndent(cfg, "", "  ")
		_ = os.WriteFile(configPath(), data, 0o600)
	}
	return cfg
}

func printInfo(cfg Config) {
	host, _ := os.Hostname()
	adapters := netinfo.Adapters()
	sel, reason, found := netinfo.Primary(adapters)
	fmt.Println("WoLmk Agent")
	fmt.Println("===========")
	fmt.Printf("Hostname   : %s\n", host)
	fmt.Printf("IP address : %s\n", sel.IPv4)
	fmt.Printf("MAC address: %s\n", sel.MAC)
	fmt.Printf("Agent port : %d\n", cfg.Port)
	fmt.Printf("Auth token : %s\n", cfg.Token)
	fmt.Println()
	fmt.Println("Network adapters:")
	for _, ad := range adapters {
		marker := "   "
		if found && ad.Name == sel.Name {
			marker = " * "
		}
		status := "disconnected"
		if ad.Up {
			status = "connected"
		}
		ip := ad.IPv4
		if ip == "" {
			ip = "-"
		}
		mac := ad.MAC
		if mac == "" {
			mac = "-"
		}
		fmt.Printf("%s%-24s MAC %-17s IP %-15s %s\n", marker, ad.Name, mac, ip, status)
	}
	if found {
		fmt.Printf("Selected %q because it %s.\n", sel.Name, reason)
	} else {
		fmt.Println("No usable network adapter found.")
	}
	fmt.Println()
	fmt.Println("Enter the IP, agent port and auth token in the WoLmk device dialog.")
	fmt.Println("This window can stay open, or install as a service with --install.")
}

// listen opens the TCP listener for the agent.
func listen(cfg Config) (net.Listener, error) {
	return net.Listen("tcp", fmt.Sprintf(":%d", cfg.Port))
}

// serve accepts and handles connections until the listener is closed.
func serve(ln net.Listener, cfg Config) {
	for {
		conn, err := ln.Accept()
		if err != nil {
			return // listener closed
		}
		go handle(conn, cfg)
	}
}

func handle(conn net.Conn, cfg Config) {
	defer conn.Close()
	var cmd agentproto.Command
	if err := json.NewDecoder(conn).Decode(&cmd); err != nil {
		writeResp(conn, agentproto.Response{Status: "error", Message: "bad request"})
		return
	}
	if subtle.ConstantTimeCompare([]byte(cmd.Token), []byte(cfg.Token)) != 1 {
		writeResp(conn, agentproto.Response{Status: "error", Message: "unauthorized"})
		return
	}
	if cmd.Action == agentproto.ActionPing {
		host, _ := os.Hostname()
		writeResp(conn, agentproto.Response{Status: "ok", Host: host})
		return
	}
	if !agentproto.ValidAction(cmd.Action) {
		writeResp(conn, agentproto.Response{Status: "error", Message: "unknown action"})
		return
	}
	c := actionCommand(cmd.Action)
	if c == nil {
		writeResp(conn, agentproto.Response{Status: "error", Message: "action not supported on this OS"})
		return
	}
	// Start the command and reply before the OS potentially terminates us.
	if err := c.Start(); err != nil {
		writeResp(conn, agentproto.Response{Status: "error", Message: err.Error()})
		return
	}
	go func() { _ = c.Wait() }()
	writeResp(conn, agentproto.Response{Status: "ok"})
}

func writeResp(conn net.Conn, resp agentproto.Response) {
	_ = json.NewEncoder(conn).Encode(resp)
}

func runTray() {
	start, _ := systray.RunWithExternalLoop(func() {
		defer func() { _ = recover() }()
		systray.SetIcon(iconICO)
		systray.SetTitle("WoLmk Agent")
		systray.SetTooltip("WoLmk Agent")
		quit := systray.AddMenuItem("Quit", "Stop the agent")
		quit.Click(func() { os.Exit(0) })
	}, nil)
	start()
}

func main() {
	// Windows service context: run without a tray or console output.
	if isService() {
		runService(loadConfig())
		return
	}

	args := os.Args[1:]
	if len(args) > 0 {
		switch args[0] {
		case "--install":
			if err := installService(); err != nil {
				fmt.Println("Install failed:", err)
				os.Exit(1)
			}
			fmt.Println("WoLmk Agent installed and started as a Windows service.")
			return
		case "--uninstall":
			if err := removeService(); err != nil {
				fmt.Println("Uninstall failed:", err)
				os.Exit(1)
			}
			fmt.Println("WoLmk Agent service removed.")
			return
		case "--help", "-h":
			fmt.Println("Usage: WoLmk-Agent [--install | --uninstall | --port N]")
			return
		case "--port":
			// handled below via parsePort
		}
	}

	cfg := loadConfig()
	if p := parsePort(args); p > 0 {
		cfg.Port = p
	}

	ln, err := listen(cfg)
	if err != nil {
		fmt.Println("Could not start listener:", err)
		os.Exit(1)
	}
	printInfo(cfg)
	go serve(ln, cfg)
	runTray() // blocks; Quit calls os.Exit
	select {}
}

// parsePort reads an optional --port N argument.
func parsePort(args []string) int {
	for i, a := range args {
		if a == "--port" && i+1 < len(args) {
			if p, err := strconv.Atoi(args[i+1]); err == nil {
				return p
			}
		}
	}
	return 0
}
