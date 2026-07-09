package main

import "testing"

func TestMagicPacket(t *testing.T) {
	p, err := buildMagicPacket("AA:BB:CC:DD:EE:FF", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(p) != 102 {
		t.Fatalf("want 102 bytes, got %d", len(p))
	}
	for i := 0; i < 6; i++ {
		if p[i] != 0xFF {
			t.Fatalf("byte %d not 0xFF", i)
		}
	}
	p2, err := buildMagicPacket("aa-bb-cc-dd-ee-ff", "DE:AD:BE:EF:12:34")
	if err != nil {
		t.Fatal(err)
	}
	if len(p2) != 108 {
		t.Fatalf("want 108 with SecureOn, got %d", len(p2))
	}
	if p2[102] != 0xDE || p2[107] != 0x34 {
		t.Fatalf("SecureOn tail wrong: %x", p2[102:])
	}
}

func TestNormalize(t *testing.T) {
	got, err := normalizeMAC("aabbccddeeff")
	if err != nil || got != "AA:BB:CC:DD:EE:FF" {
		t.Fatalf("normalizeMAC got %q err %v", got, err)
	}
	if _, err := normalizeMAC("zz:zz"); err == nil {
		t.Fatal("expected error for bad MAC")
	}
	if s, _ := normalizeSecureOn(""); s != "" {
		t.Fatal("empty SecureOn should stay empty")
	}
}

func TestStatusText(t *testing.T) {
	if s := statusText(true, 3, "port 9100", "13:00:00"); s != "Online (port 9100), 3 ms, 13:00:00" {
		t.Fatalf("got %q", s)
	}
	if s := statusText(true, -1, "", "13:00:00"); s != "Online, 13:00:00" {
		t.Fatalf("got %q", s)
	}
	if s := statusText(false, -1, "port 22", "13:00:00"); s != "Offline (port 22), 13:00:00" {
		t.Fatalf("got %q", s)
	}
}
