//go:build windows

package main

import (
	"fmt"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

const serviceName = "WoLmkAgent"

// isService reports whether the process was started by the service manager.
func isService() bool {
	ok, err := svc.IsWindowsService()
	return err == nil && ok
}

type agentService struct{ cfg Config }

func (s *agentService) Execute(args []string, r <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	status <- svc.Status{State: svc.StartPending}
	ln, err := listen(s.cfg)
	if err != nil {
		return true, 1
	}
	go serve(ln, s.cfg)
	status <- svc.Status{State: svc.Running, Accepts: svc.AcceptStop | svc.AcceptShutdown}
	for c := range r {
		switch c.Cmd {
		case svc.Interrogate:
			status <- c.CurrentStatus
		case svc.Stop, svc.Shutdown:
			status <- svc.Status{State: svc.StopPending}
			_ = ln.Close()
			return false, 0
		}
	}
	return false, 0
}

func runService(cfg Config) {
	_ = svc.Run(serviceName, &agentService{cfg: cfg})
}

func installService() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	exe, _ = filepath.Abs(exe)
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()
	if s, err := m.OpenService(serviceName); err == nil {
		s.Close()
		return fmt.Errorf("service %q is already installed", serviceName)
	}
	s, err := m.CreateService(serviceName, exe, mgr.Config{
		DisplayName: "WoLmk Agent",
		Description: "Executes WoLmk power commands on this machine.",
		StartType:   mgr.StartAutomatic,
	})
	if err != nil {
		return err
	}
	defer s.Close()
	return s.Start()
}

func removeService() error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()
	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service is not installed")
	}
	defer s.Close()
	_, _ = s.Control(svc.Stop)
	return s.Delete()
}
