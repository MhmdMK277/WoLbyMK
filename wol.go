package main

import (
	"encoding/hex"
	"fmt"
	"net"
	"regexp"
	"strings"
	"time"
)

var (
	macRE  = regexp.MustCompile(`^([0-9A-Fa-f]{2}[:\-\. ]?){5}[0-9A-Fa-f]{2}$`)
	hex6RE = macRE // SecureOn password has the same shape as a MAC
)

// normalizeMAC validates a MAC address and returns it as AA:BB:CC:DD:EE:FF.
func normalizeMAC(mac string) (string, error) {
	mac = strings.TrimSpace(mac)
	if !macRE.MatchString(mac) {
		return "", fmt.Errorf("invalid MAC address: %q", mac)
	}
	return groupHex(mac), nil
}

// normalizeSecureOn validates a SecureOn password (6 hex bytes) or returns
// an empty string when none is set.
func normalizeSecureOn(pw string) (string, error) {
	pw = strings.TrimSpace(pw)
	if pw == "" {
		return "", nil
	}
	if !hex6RE.MatchString(pw) {
		return "", fmt.Errorf("invalid SecureOn password: %q", pw)
	}
	return groupHex(pw), nil
}

// groupHex strips separators and regroups 12 hex digits as AA:BB:...:FF.
func groupHex(s string) string {
	var digits strings.Builder
	for _, r := range s {
		if (r >= '0' && r <= '9') || (r >= 'a' && r <= 'f') || (r >= 'A' && r <= 'F') {
			digits.WriteRune(r)
		}
	}
	up := strings.ToUpper(digits.String())
	parts := make([]string, 0, 6)
	for i := 0; i < 12; i += 2 {
		parts = append(parts, up[i:i+2])
	}
	return strings.Join(parts, ":")
}

// buildMagicPacket returns 6 bytes of 0xFF, the MAC 16 times, and an
// optional 6 byte SecureOn password appended at the end.
func buildMagicPacket(mac, secureon string) ([]byte, error) {
	norm, err := normalizeMAC(mac)
	if err != nil {
		return nil, err
	}
	macBytes, _ := hex.DecodeString(strings.ReplaceAll(norm, ":", ""))
	packet := make([]byte, 0, 102+6)
	for i := 0; i < 6; i++ {
		packet = append(packet, 0xFF)
	}
	for i := 0; i < 16; i++ {
		packet = append(packet, macBytes...)
	}
	so, err := normalizeSecureOn(secureon)
	if err != nil {
		return nil, err
	}
	if so != "" {
		soBytes, _ := hex.DecodeString(strings.ReplaceAll(so, ":", ""))
		packet = append(packet, soBytes...)
	}
	return packet, nil
}

// sendMagicPacket sends the packet over UDP, optionally repeated count times
// with intervalMs between sends.
func sendMagicPacket(mac, host string, port, count, intervalMs int, secureon string) error {
	packet, err := buildMagicPacket(mac, secureon)
	if err != nil {
		return err
	}
	if host == "" {
		host = defaultBroadcast
	}
	if port == 0 {
		port = defaultPort
	}
	addr := &net.UDPAddr{IP: net.ParseIP(host), Port: port}
	if addr.IP == nil {
		// Resolve DNS names for WAN targets.
		resolved, rerr := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%d", host, port))
		if rerr != nil {
			return fmt.Errorf("cannot resolve host %q: %w", host, rerr)
		}
		addr = resolved
	}
	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		return err
	}
	defer conn.Close()
	if count < 1 {
		count = 1
	}
	for i := 0; i < count; i++ {
		if _, err := conn.Write(packet); err != nil {
			return err
		}
		if i < count-1 && intervalMs > 0 {
			time.Sleep(time.Duration(intervalMs) * time.Millisecond)
		}
	}
	return nil
}
