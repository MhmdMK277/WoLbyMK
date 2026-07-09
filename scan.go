package main

import (
	"net"
	"os/exec"
	"regexp"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// ScanResult is one host discovered on the local network.
type ScanResult struct {
	IP   string `json:"ip"`
	MAC  string `json:"mac"`
	Host string `json:"host"`
}

var (
	ipRE  = regexp.MustCompile(`(\d{1,3}(?:\.\d{1,3}){3})`)
	macRE2 = regexp.MustCompile(`([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})`)
)

// localHosts returns the list of host IPs to scan on the primary interface,
// bounded to a /24 so large subnets do not explode the scan.
func localHosts() (hosts []string, self string) {
	ifaces, _ := net.Interfaces()
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, _ := iface.Addrs()
		for _, a := range addrs {
			ipnet, ok := a.(*net.IPNet)
			if !ok || ipnet.IP.To4() == nil {
				continue
			}
			ip4 := ipnet.IP.To4()
			// Bound to a /24 around the interface address.
			base := net.IPv4(ip4[0], ip4[1], ip4[2], 0).To4()
			for i := 1; i < 255; i++ {
				host := net.IPv4(base[0], base[1], base[2], byte(i)).String()
				if host == ip4.String() {
					continue
				}
				hosts = append(hosts, host)
			}
			return hosts, ip4.String()
		}
	}
	return nil, ""
}

// arpTable reads the OS ARP cache into an IP to MAC map.
func arpTable() map[string]string {
	table := map[string]string{}
	var cmd *exec.Cmd
	if runtime.GOOS == "linux" {
		cmd = exec.Command("ip", "neigh")
	} else {
		cmd = exec.Command("arp", "-a")
	}
	configureCmd(cmd)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return table
	}
	for _, line := range strings.Split(string(out), "\n") {
		ip := ipRE.FindString(line)
		mac := macRE2.FindString(line)
		if ip != "" && mac != "" {
			table[ip] = normalizeScanMAC(mac)
		}
	}
	return table
}

func normalizeScanMAC(mac string) string {
	mac = strings.ToUpper(strings.ReplaceAll(mac, "-", ":"))
	return mac
}

// ScanNetwork sweeps the local /24, then enriches responders with their MAC
// (from the ARP cache) and reverse DNS hostname. Progress and the final result
// are delivered through "scan:progress" and "scan:done" events.
func (a *App) ScanNetwork() {
	go func() {
		hosts, _ := localHosts()
		total := len(hosts)
		if total == 0 {
			a.emitScanDone(nil)
			return
		}
		var done int32
		var mu sync.Mutex
		var wg sync.WaitGroup
		found := map[string]bool{}
		sem := make(chan struct{}, 64)

		for _, ip := range hosts {
			wg.Add(1)
			sem <- struct{}{}
			go func(ip string) {
				defer wg.Done()
				defer func() { <-sem }()
				online, _ := pingHost(ip, 600)
				n := atomic.AddInt32(&done, 1)
				if n%8 == 0 || int(n) == total {
					a.emitScanProgress(int(n), total)
				}
				if online {
					mu.Lock()
					found[ip] = true
					mu.Unlock()
				}
			}(ip)
		}
		wg.Wait()

		arp := arpTable()
		results := make([]ScanResult, 0, len(found))
		for ip := range found {
			r := ScanResult{IP: ip, MAC: arp[ip]}
			ctx := make(chan string, 1)
			go func() {
				names, _ := net.LookupAddr(ip)
				if len(names) > 0 {
					ctx <- strings.TrimSuffix(names[0], ".")
					return
				}
				ctx <- ""
			}()
			select {
			case r.Host = <-ctx:
			case <-time.After(800 * time.Millisecond):
			}
			results = append(results, r)
		}
		sort.Slice(results, func(i, j int) bool {
			return ipLess(results[i].IP, results[j].IP)
		})
		a.emitScanDone(results)
	}()
}

func ipLess(a, b string) bool {
	ia, ib := net.ParseIP(a).To4(), net.ParseIP(b).To4()
	if ia == nil || ib == nil {
		return a < b
	}
	for i := 0; i < 4; i++ {
		if ia[i] != ib[i] {
			return ia[i] < ib[i]
		}
	}
	return false
}

func (a *App) emitScanProgress(done, total int) {
	if a.ctx != nil {
		wruntime.EventsEmit(a.ctx, "scan:progress", map[string]int{"done": done, "total": total})
	}
}

func (a *App) emitScanDone(results []ScanResult) {
	if results == nil {
		results = []ScanResult{}
	}
	if a.ctx != nil {
		wruntime.EventsEmit(a.ctx, "scan:done", results)
	}
}
