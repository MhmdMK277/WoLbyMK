package main

import (
	"fmt"
	"net"
	"os/exec"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"
)

var rttRE = regexp.MustCompile(`(?i)time[=<]\s*(\d+(?:\.\d+)?)\s*ms`)

// pingHost runs one ICMP echo using the system ping tool, with OS-specific
// flags so it works on Windows, Linux and macOS. Returns online and the
// round-trip time in milliseconds (-1 when unknown).
func pingHost(host string, timeoutMs int) (bool, float64) {
	secs := (timeoutMs + 999) / 1000
	if secs < 1 {
		secs = 1
	}
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("ping", "-n", "1", "-w", strconv.Itoa(timeoutMs), host)
	case "darwin":
		cmd = exec.Command("ping", "-c", "1", "-t", strconv.Itoa(secs), host)
	default:
		cmd = exec.Command("ping", "-c", "1", "-W", strconv.Itoa(secs), host)
	}
	configureCmd(cmd)
	out, err := cmd.CombinedOutput()
	text := string(out)
	// On Windows exit code 0 can still mean "unreachable"; a TTL marks a reply.
	online := err == nil
	if runtime.GOOS == "windows" {
		online = online && strings.Contains(strings.ToUpper(text), "TTL=")
	}
	if !online {
		return false, -1
	}
	if m := rttRE.FindStringSubmatch(text); m != nil {
		if v, e := strconv.ParseFloat(m[1], 64); e == nil {
			return true, v
		}
	}
	return true, -1
}

// checkPort does a TCP connect check. Returns online and the connect time
// in milliseconds (-1 when it failed).
func checkPort(host string, port, timeoutMs int) (bool, float64) {
	start := time.Now()
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("%s:%d", host, port),
		time.Duration(timeoutMs)*time.Millisecond)
	if err != nil {
		return false, -1
	}
	_ = conn.Close()
	return true, float64(time.Since(start).Microseconds()) / 1000.0
}

// resolveHost turns a DNS name into its first IPv4 address. Broadcast
// addresses and literal IPs are returned unchanged.
func resolveHost(host string) string {
	if host == "" || host == defaultBroadcast || net.ParseIP(host) != nil {
		return host
	}
	if ips, err := net.LookupIP(host); err == nil {
		for _, ip := range ips {
			if v4 := ip.To4(); v4 != nil {
				return v4.String()
			}
		}
	}
	return host
}

// pingTarget is the address used for status checks and remote commands:
// the explicit device IP, else a non-broadcast host, else empty.
func pingTarget(d Device) string {
	if ip := strings.TrimSpace(d.IP); ip != "" {
		return ip
	}
	if d.Host != defaultBroadcast {
		return d.Host
	}
	return ""
}

// probeDevice checks reachability using a TCP service port when set,
// otherwise ICMP. Returns whether a target existed, online, rtt and a label.
func probeDevice(d Device) (hasTarget, online bool, rtt float64, label string) {
	target := pingTarget(d)
	if target == "" {
		return false, false, -1, ""
	}
	if sp := strings.TrimSpace(d.ServicePort); sp != "" {
		port, err := strconv.Atoi(sp)
		if err == nil {
			ok, ms := checkPort(target, port, 1000)
			return true, ok, ms, "port " + sp
		}
	}
	ok, ms := pingHost(target, 1000)
	return true, ok, ms, ""
}

// statusText formats a status line for a probe result.
func statusText(online bool, rtt float64, label, stamp string) string {
	tag := ""
	if label != "" {
		tag = " (" + label + ")"
	}
	if !online {
		return fmt.Sprintf("Offline%s, %s", tag, stamp)
	}
	rttTxt := ""
	if rtt >= 0 {
		rttTxt = fmt.Sprintf(", %.0f ms", rtt)
	}
	return fmt.Sprintf("Online%s%s, %s", tag, rttTxt, stamp)
}
