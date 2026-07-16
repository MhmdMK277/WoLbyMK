// Package netinfo enumerates the machine's network adapters for the
// desktop app's My Device view and the agent's startup report.
package netinfo

import (
	"net"
	"strings"
)

// Adapter describes one network interface.
type Adapter struct {
	Name    string `json:"name"`
	MAC     string `json:"mac"`
	IPv4    string `json:"ipv4"`
	Up      bool   `json:"up"`
	Gateway bool   `json:"gateway"` // carries the default route
}

// DefaultRouteIP returns the local IPv4 address the OS routes outbound
// traffic through, or "" when there is no default route. Dialing UDP only
// selects a source address; no packet is sent.
func DefaultRouteIP() string {
	conn, err := net.Dial("udp4", "8.8.8.8:53")
	if err != nil {
		return ""
	}
	defer conn.Close()
	if addr, ok := conn.LocalAddr().(*net.UDPAddr); ok {
		return addr.IP.String()
	}
	return ""
}

// ipv4Of returns the interface's first IPv4 that is neither loopback nor
// link-local, or "".
func ipv4Of(iface net.Interface) string {
	addrs, err := iface.Addrs()
	if err != nil {
		return ""
	}
	for _, a := range addrs {
		ipnet, ok := a.(*net.IPNet)
		if !ok {
			continue
		}
		ip := ipnet.IP.To4()
		if ip == nil || ip.IsLoopback() || ip.IsLinkLocalUnicast() {
			continue
		}
		return ip.String()
	}
	return ""
}

// Adapters lists the machine's network interfaces, skipping loopback and
// pseudo interfaces that have neither a MAC nor a usable IPv4 address.
func Adapters() []Adapter {
	gw := DefaultRouteIP()
	ifaces, err := net.Interfaces()
	if err != nil {
		return nil
	}
	out := make([]Adapter, 0, len(ifaces))
	for _, iface := range ifaces {
		if iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		mac := iface.HardwareAddr.String()
		ip := ipv4Of(iface)
		if mac == "" && ip == "" {
			continue
		}
		out = append(out, Adapter{
			Name:    iface.Name,
			MAC:     strings.ToUpper(mac),
			IPv4:    ip,
			Up:      iface.Flags&net.FlagUp != 0 && iface.Flags&net.FlagRunning != 0,
			Gateway: gw != "" && ip == gw,
		})
	}
	return out
}

// Primary picks the adapter to prefer: the one holding the default gateway,
// falling back to the first connected adapter with an IPv4 address. The
// second return value states why it was chosen.
func Primary(adapters []Adapter) (Adapter, string, bool) {
	for _, a := range adapters {
		if a.Gateway {
			return a, "has the default gateway", true
		}
	}
	for _, a := range adapters {
		if a.Up && a.IPv4 != "" {
			return a, "first connected adapter with an IPv4 address", true
		}
	}
	return Adapter{}, "", false
}
