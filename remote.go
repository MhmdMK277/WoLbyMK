package main

import (
	"fmt"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

const (
	defaultShutdown = `powershell -Command "Stop-Computer -ComputerName {ip} -Force"`
	defaultSleep    = `powershell -Command "Invoke-Command -ComputerName {ip} -ScriptBlock { rundll32.exe powrprof.dll,SetSuspendState 0,1,0 }"`
)

// runRemoteCommand runs the per-device shutdown or sleep command, filling the
// {ip} and {user} placeholders. Returns an error message on failure.
func runRemoteCommand(d Device, kind string) error {
	template := strings.TrimSpace(d.CmdShutdown)
	if kind == "sleep" {
		template = strings.TrimSpace(d.CmdSleep)
	}
	if template == "" {
		if kind == "sleep" {
			template = defaultSleep
		} else {
			template = defaultShutdown
		}
	}
	target := strings.TrimSpace(d.IP)
	if target == "" && d.Host != defaultBroadcast {
		target = d.Host
	}
	if target == "" && strings.Contains(template, "{ip}") {
		return fmt.Errorf("no device IP or host set for remote commands")
	}
	command := strings.ReplaceAll(template, "{ip}", target)
	command = strings.ReplaceAll(command, "{user}", d.Username)

	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.Command("cmd", "/C", command)
	} else {
		cmd = exec.Command("sh", "-c", command)
	}
	configureCmd(cmd)
	done := make(chan error, 1)
	var out []byte
	go func() {
		var e error
		out, e = cmd.CombinedOutput()
		done <- e
	}()
	select {
	case err := <-done:
		if err == nil {
			return nil
		}
		msg := strings.TrimSpace(string(out))
		msg = strings.ReplaceAll(msg, "\n", " ")
		if msg == "" {
			msg = err.Error()
		}
		if len(msg) > 200 {
			msg = msg[:200]
		}
		return fmt.Errorf("%s", msg)
	case <-time.After(30 * time.Second):
		_ = cmd.Process.Kill()
		return fmt.Errorf("command timed out")
	}
}
