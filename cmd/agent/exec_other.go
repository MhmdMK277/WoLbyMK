//go:build !windows

package main

import (
	"os/exec"
	"runtime"
)

// actionCommand returns the local command that performs the given action on
// Linux or macOS, or nil for an unknown action.
func actionCommand(action string) *exec.Cmd {
	if runtime.GOOS == "darwin" {
		switch action {
		case "shutdown":
			return exec.Command("osascript", "-e", `tell app "System Events" to shut down`)
		case "reboot":
			return exec.Command("osascript", "-e", `tell app "System Events" to restart`)
		case "sleep":
			return exec.Command("pmset", "sleepnow")
		case "lock":
			return exec.Command("pmset", "displaysleepnow")
		}
		return nil
	}
	switch action { // linux and other unix
	case "shutdown":
		return exec.Command("systemctl", "poweroff")
	case "reboot":
		return exec.Command("systemctl", "reboot")
	case "sleep":
		return exec.Command("systemctl", "suspend")
	case "lock":
		return exec.Command("loginctl", "lock-session")
	}
	return nil
}
