//go:build windows

package main

import (
	"os/exec"
	"syscall"
)

// actionCommand returns the local command that performs the given action on
// Windows, or nil for an unknown action.
func actionCommand(action string) *exec.Cmd {
	var cmd *exec.Cmd
	switch action {
	case "shutdown":
		cmd = exec.Command("shutdown", "/s", "/t", "0")
	case "reboot":
		cmd = exec.Command("shutdown", "/r", "/t", "0")
	case "sleep":
		cmd = exec.Command("rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0")
	case "lock":
		cmd = exec.Command("rundll32.exe", "user32.dll,LockWorkStation")
	}
	if cmd != nil {
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	}
	return cmd
}
