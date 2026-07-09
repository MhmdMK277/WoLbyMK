//go:build windows

package main

import (
	"os"
	"syscall"
)

// attachConsole attaches to the parent terminal (when launched from one) so
// CLI output from --send is visible on Windows GUI builds.
func attachConsole() {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	attach := kernel32.NewProc("AttachConsole")
	const attachParentProcess = ^uintptr(0) // (DWORD)-1
	if r, _, _ := attach.Call(attachParentProcess); r == 0 {
		return
	}
	if h, err := syscall.Open("CONOUT$", syscall.O_RDWR, 0); err == nil {
		os.Stdout = os.NewFile(uintptr(h), "CONOUT$")
		os.Stderr = os.NewFile(uintptr(h), "CONOUT$")
	}
}
