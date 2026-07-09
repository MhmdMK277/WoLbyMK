package main

import (
	"embed"
	"fmt"
	"os"
	"strconv"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/windows"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	// CLI mode: WoLmk.exe --send AA:BB:CC:DD:EE:FF [host] [port]
	if len(os.Args) > 2 && os.Args[1] == "--send" {
		runCLI(os.Args[2:])
		return
	}

	// Web server mode: WoLmk.exe --serve [port]
	if len(os.Args) > 1 && os.Args[1] == "--serve" {
		attachConsole()
		port := 8080
		if len(os.Args) > 2 {
			if p, e := strconv.Atoi(os.Args[2]); e == nil {
				port = p
			}
		}
		if err := startWebServer(port); err != nil {
			fmt.Println("Web server error:", err.Error())
			os.Exit(1)
		}
		return
	}

	app := NewApp()
	err := wails.Run(&options.App{
		Title:            "WoLmk",
		Width:            860,
		Height:           660,
		MinWidth:         680,
		MinHeight:        480,
		BackgroundColour: &options.RGBA{R: 14, G: 16, B: 21, A: 1},
		AssetServer:      &assetserver.Options{Assets: assets},
		OnStartup:        app.startup,
		OnBeforeClose:    app.beforeClose,
		Bind:             []interface{}{app},
		Windows:          &windows.Options{Theme: windows.Dark},
	})
	if err != nil {
		println("Error:", err.Error())
	}
}

func runCLI(args []string) {
	attachConsole()
	mac := args[0]
	host := defaultBroadcast
	port := defaultPort
	if len(args) > 1 {
		host = args[1]
	}
	if len(args) > 2 {
		if p, e := strconv.Atoi(args[2]); e == nil {
			port = p
		}
	}
	if err := sendMagicPacket(mac, host, port, 1, 0, ""); err != nil {
		fmt.Println("Error:", err.Error())
		os.Exit(1)
	}
	norm, _ := normalizeMAC(mac)
	fmt.Printf("Magic packet sent to %s via %s:%d\n", norm, host, port)
	os.Exit(0)
}
