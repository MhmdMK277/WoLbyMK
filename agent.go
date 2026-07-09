package main

import (
	"encoding/json"
	"fmt"
	"net"
	"strconv"
	"time"

	"WoLmk/internal/agentproto"
)

// agentSend opens a TCP connection to a WoLmk-Agent, sends one authenticated
// command, and returns an error if the agent reports failure or is unreachable.
func agentSend(host string, port int, token, action string) error {
	if host == "" {
		return fmt.Errorf("no host to reach the agent")
	}
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(host, strconv.Itoa(port)), 4*time.Second)
	if err != nil {
		return fmt.Errorf("agent unreachable: %w", err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(6 * time.Second))

	if err := json.NewEncoder(conn).Encode(agentproto.Command{Action: action, Token: token}); err != nil {
		return err
	}
	var resp agentproto.Response
	if err := json.NewDecoder(conn).Decode(&resp); err != nil {
		return fmt.Errorf("no response from agent: %w", err)
	}
	if resp.Status != "ok" {
		if resp.Message != "" {
			return fmt.Errorf("%s", resp.Message)
		}
		return fmt.Errorf("agent returned an error")
	}
	return nil
}

// deviceUsesAgent reports whether a device has agent credentials configured.
func deviceUsesAgent(d Device) bool {
	return d.AgentPort > 0 && d.AgentToken != ""
}

// performRemote runs a power action against a device. It prefers the companion
// agent, and falls back to the custom or default command template for shutdown
// and sleep. Shared by the desktop app and the web server.
func performRemote(d Device, action string) error {
	if deviceUsesAgent(d) {
		host := pingTarget(d)
		if host == "" {
			host = d.Host
		}
		return agentSend(host, d.AgentPort, d.AgentToken, action)
	}
	if action == "shutdown" || action == "sleep" {
		return runRemoteCommand(d, action)
	}
	return fmt.Errorf("set an agent port and token to use %s", action)
}
