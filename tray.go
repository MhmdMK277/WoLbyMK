package main

import (
	_ "embed"
	"runtime"

	"github.com/energye/systray"
)

//go:embed build/windows/icon.ico
var iconICO []byte

//go:embed build/appicon.png
var iconPNG []byte

// setupTray starts a system tray icon with a Show, Wake all and Exit menu.
// It is best effort: any failure leaves the app running without a tray, and
// closing the window then quits normally.
func (a *App) setupTray() {
	defer func() { _ = recover() }()
	start, _ := systray.RunWithExternalLoop(a.onTrayReady, nil)
	start()
}

func (a *App) onTrayReady() {
	defer func() { _ = recover() }()
	if runtime.GOOS == "windows" {
		systray.SetIcon(iconICO)
	} else {
		systray.SetIcon(iconPNG)
	}
	systray.SetTitle(appName)
	systray.SetTooltip(appName)

	mShow := systray.AddMenuItem("Show", "Show the window")
	mWake := systray.AddMenuItem("Wake all", "Wake every device")
	systray.AddSeparator()
	mExit := systray.AddMenuItem("Exit", "Quit WoLmk")

	mShow.Click(func() { a.showWindow() })
	mWake.Click(func() { a.WakeAll() })
	mExit.Click(func() { a.quitApp() })

	a.trayReady = true
}
