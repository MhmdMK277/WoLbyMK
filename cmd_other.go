//go:build !windows

package main

import "os/exec"

// configureCmd is a no-op on platforms without a console window to hide.
func configureCmd(cmd *exec.Cmd) {}
