package main

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"
)

//go:embed web/index.html
var webIndex []byte

// localIP returns the first non-loopback IPv4 address, or "localhost".
func localIP() string {
	ifaces, _ := net.Interfaces()
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, _ := iface.Addrs()
		for _, a := range addrs {
			if ipnet, ok := a.(*net.IPNet); ok && ipnet.IP.To4() != nil {
				return ipnet.IP.String()
			}
		}
	}
	return "localhost"
}

// startWebServer runs the HTTP server that mirrors the desktop app. It shares
// the same devices.json. Blocks until the server exits.
func startWebServer(port int) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/", serveIndex)
	mux.HandleFunc("/api/devices", apiDevices)
	mux.HandleFunc("/api/wake/", apiAction("wake"))
	mux.HandleFunc("/api/shutdown/", apiAction("shutdown"))
	mux.HandleFunc("/api/reboot/", apiAction("reboot"))
	mux.HandleFunc("/api/sleep/", apiAction("sleep"))
	mux.HandleFunc("/api/lock/", apiAction("lock"))
	mux.HandleFunc("/api/status/", apiStatus)

	addr := fmt.Sprintf(":%d", port)
	ip := localIP()
	fmt.Printf("%s web UI running.\n", appName)
	fmt.Printf("  Local:   http://localhost:%d\n", port)
	fmt.Printf("  Network: http://%s:%d\n", ip, port)
	fmt.Println("Press Ctrl+C to stop.")
	srv := &http.Server{Addr: addr, Handler: mux, ReadTimeout: 15 * time.Second}
	return srv.ListenAndServe()
}

func serveIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write(webIndex)
}

func writeJSONResp(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func deviceByID(idStr string) (Device, int, bool) {
	id, err := strconv.Atoi(idStr)
	if err != nil {
		return Device{}, -1, false
	}
	devices := loadDevices()
	if id < 0 || id >= len(devices) {
		return Device{}, -1, false
	}
	return devices[id], id, true
}

func apiDevices(w http.ResponseWriter, r *http.Request) {
	writeJSONResp(w,http.StatusOK, loadDevices())
}

func apiAction(kind string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResp(w,http.StatusMethodNotAllowed, map[string]string{"error": "use POST"})
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/api/"+kind+"/")
		d, _, ok := deviceByID(id)
		if !ok {
			writeJSONResp(w,http.StatusNotFound, map[string]string{"error": "device not found"})
			return
		}
		var err error
		if kind == "wake" {
			s := loadSettings()
			err = sendMagicPacket(d.MAC, d.Host, d.Port, s.SendCount, s.SendInterval, d.SecureOn)
		} else {
			err = performRemote(d, kind)
		}
		if err != nil {
			writeJSONResp(w,http.StatusBadGateway, map[string]string{"error": err.Error()})
			return
		}
		writeJSONResp(w,http.StatusOK, map[string]string{"status": "ok"})
	}
}

func apiStatus(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/api/status/")
	d, _, ok := deviceByID(id)
	if !ok {
		writeJSONResp(w,http.StatusNotFound, map[string]string{"error": "device not found"})
		return
	}
	hasTarget, online, rtt, label := probeDevice(d)
	writeJSONResp(w,http.StatusOK, map[string]interface{}{
		"hasTarget": hasTarget, "online": online, "rtt": rtt, "label": label,
	})
}
