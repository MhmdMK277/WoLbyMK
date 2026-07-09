//go:build !windows

package main

// attachConsole is a no-op on platforms that already have a usable stdout.
func attachConsole() {}
