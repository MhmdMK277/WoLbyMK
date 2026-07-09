//go:build !windows

package main

import "fmt"

func isService() bool     { return false }
func runService(_ Config) {}

func installService() error {
	return fmt.Errorf("service install is only supported on Windows")
}

func removeService() error {
	return fmt.Errorf("service uninstall is only supported on Windows")
}
