import "./style.css";

// Wails injects these globals once the runtime is ready.
const Go = () => window.go.main.App;
const RT = () => window.runtime;

const BROADCAST = "255.255.255.255";
const DEFAULT_SHUTDOWN =
  'powershell -Command "Stop-Computer -ComputerName {ip} -Force"';
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

let devices = [];
let selected = null;
let version = "2.0.0";

const app = document.getElementById("app");

// ---- small helpers ------------------------------------------------------

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

const boltSvg = (size) =>
  `<svg class="logo" width="${size}" height="${size}" viewBox="0 0 34 34" fill="none">
     <rect x="1" y="1" width="32" height="32" rx="9" fill="#8b7cf7"/>
     <path d="M18.6 6.5 L10.4 20.2 H15.4 L12.8 30.5 L22.2 15.6 H16.6 Z" fill="#f6f5ff"/>
   </svg>`;

const clockSvg = () =>
  `<svg class="clock" width="13" height="13" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round">
     <circle cx="12" cy="12" r="9"/><path d="M12 12V7"/><path d="M12 12l4 2"/>
   </svg>`;

function scheduleActive(d) {
  const s = d.schedule;
  if (!s) return false;
  if (s.mode === "repeating") return (s.days || []).length > 0;
  if (s.mode === "onetime") return !s.fired;
  return false;
}

// ---- shell --------------------------------------------------------------

function buildShell() {
  app.innerHTML = `
    <div class="shell">
      <div class="header">
        ${boltSvg(34)}
        <div class="titles">
          <span class="name">WoLmk</span>
          <span class="eyebrow">WAKE ON LAN</span>
        </div>
        <div class="spacer"></div>
        <button class="btn" id="myDeviceBtn">My Device</button>
        <button class="btn" id="scanBtn">Scan network</button>
        <button class="btn" id="wakeAll">Wake all</button>
        <button class="btn primary" id="addBtn">+ Add device</button>
      </div>
      <div class="list-wrap"><div class="list" id="list"></div></div>
      <div class="footer">
        <div class="dot" id="statusDot"></div>
        <span class="status" id="statusText">Ready</span>
        <div class="spacer"></div>
        <button class="btn small" id="historyBtn">History</button>
        <button class="btn small" id="dataBtn">Data</button>
        <span class="ver">v${esc(version)}</span>
      </div>
    </div>`;

  document.getElementById("addBtn").onclick = () => openDeviceDialog(null, -1);
  document.getElementById("myDeviceBtn").onclick = openMyDevice;
  document.getElementById("scanBtn").onclick = openScanModal;
  document.getElementById("wakeAll").onclick = () => Go().WakeAll();
  document.getElementById("historyBtn").onclick = openHistory;
  document.getElementById("dataBtn").onclick = (e) => openDataMenu(e.currentTarget);
}

// ---- device list --------------------------------------------------------

function renderDevices() {
  const list = document.getElementById("list");
  list.innerHTML = "";
  if (!devices.length) {
    list.appendChild(
      el(`<div class="empty">
            <div class="mark">${boltSvg(28)}</div>
            <div class="t">No devices yet</div>
            <div>Add a device and wake it from here.</div>
          </div>`)
    );
    return;
  }
  devices.forEach((d, i) => list.appendChild(renderCard(d, i)));
}

function renderCard(d, i) {
  const target = d.host === BROADCAST ? "LAN broadcast" : `${esc(d.host)} WAN`;
  const meta = `${esc(d.mac)}   ${target}   :${esc(d.port)}`;
  const card = el(`
    <div class="card${selected === i ? " selected" : ""}" data-mac="${esc(d.mac)}" data-i="${i}">
      <div class="led"></div>
      <div class="card-body">
        <div class="card-name">
          <span class="nm">${esc(d.name)}</span>
          ${scheduleActive(d) ? clockSvg() : ""}
        </div>
        <div class="card-meta">${meta}</div>
        <div class="card-status muted"></div>
      </div>
      <div class="card-actions">
        <button class="btn small" data-act="check">Check</button>
        <button class="btn small" data-act="power">Power</button>
        <button class="btn small" data-act="schedule">Schedule</button>
        <button class="btn primary small" data-act="wake">Wake</button>
        <button class="btn icon small" data-act="more">&#8943;</button>
      </div>
    </div>`);

  card.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    selected = selected === i ? null : i;
    renderDevices();
  });
  card.querySelectorAll("button[data-act]").forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      handleAction(b.dataset.act, i, b);
    };
  });
  return card;
}

function handleAction(act, i, btn) {
  switch (act) {
    case "wake": Go().Wake(i); break;
    case "check": Go().Check(i); break;
    case "power": openPowerMenu(btn, i); break;
    case "schedule": openScheduleDialog(i); break;
    case "more": openCardMenu(btn, i); break;
  }
}

function openPowerMenu(anchor, i) {
  showMenu(anchor, [
    { label: "Shutdown", fn: () => doPower(i, "shutdown") },
    { label: "Reboot", fn: () => doPower(i, "reboot") },
    { label: "Sleep", fn: () => doPower(i, "sleep") },
    { label: "Lock", fn: () => doPower(i, "lock") },
  ]);
}

function doPower(i, action) {
  if ((action === "shutdown" || action === "reboot") &&
      !confirm(`Send ${action} to ${devices[i].name}?`)) return;
  Go().Remote(i, action);
}

function openCardMenu(anchor, i) {
  showMenu(anchor, [
    { label: "Edit device", fn: () => openDeviceDialog(devices[i], i) },
    { label: "Remove device", fn: () => removeDevice(i) },
  ]);
}

async function removeDevice(i) {
  if (!confirm(`Remove ${devices[i].name}?`)) return;
  await Go().DeleteDevice(i);
  selected = null;
  await refresh();
}

// ---- floating menu ------------------------------------------------------

function showMenu(anchor, items) {
  closeMenu();
  const rect = anchor.getBoundingClientRect();
  const menu = el(`<div class="menu"></div>`);
  items.forEach((it) => {
    if (it.sep) { menu.appendChild(el(`<div class="sep"></div>`)); return; }
    const b = el(`<button>${esc(it.label)}</button>`);
    b.onclick = () => { closeMenu(); it.fn(); };
    menu.appendChild(b);
  });
  document.body.appendChild(menu);
  const mw = menu.offsetWidth;
  menu.style.left = Math.max(8, Math.min(rect.right - mw, window.innerWidth - mw - 8)) + "px";
  menu.style.top = rect.bottom + 6 + "px";
  setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
}
function closeMenu() {
  document.querySelectorAll(".menu").forEach((m) => m.remove());
}

function openDataMenu(anchor) {
  showMenu(anchor, [
    { label: "Export devices...", fn: exportDevices },
    { label: "Import devices...", fn: importDevices },
  ]);
}

async function exportDevices() {
  await Go().ExportDevices();
}

async function importDevices() {
  const res = await Go().ImportDevices();
  if (!res.ok) {
    if (res.error) setStatus(res.error, "err");
    return;
  }
  const merge = confirm(
    `Import ${res.devices.length} device(s).\n\nOK = merge with your current list\nCancel = replace your current list`
  );
  const list = merge ? devices.concat(res.devices) : res.devices;
  await Go().SaveDeviceList(list);
  selected = null;
  await refresh();
  setStatus(
    `Imported ${res.devices.length} device(s) (${merge ? "merged" : "replaced"})`,
    "ok"
  );
}

// ---- device dialog ------------------------------------------------------

function field(label, key, value, hint, mono, full) {
  return `
    <div class="field${full ? " full" : ""}">
      <label>${label}</label>
      <input type="text" data-k="${key}" class="${mono ? "" : "ui"}"
             value="${esc(value)}" spellcheck="false"/>
      <span class="hint">${esc(hint)}</span>
    </div>`;
}

function openDeviceDialog(device, index) {
  const d = device || { host: BROADCAST, port: 9 };
  const isEdit = index >= 0;
  const body = `
    <div class="form-grid">
      ${field("NAME", "name", d.name || "", "How the device appears in the list", false, true)}
      ${field("MAC ADDRESS", "mac", d.mac || "", "AA:BB:CC:DD:EE:FF, any separator works", true, true)}
      ${field("HOST", "host", d.host || BROADCAST, "255.255.255.255 for LAN, or IP/DNS for WAN", true)}
      ${field("PORT", "port", d.port || 9, "9 is standard", true)}
      ${field("DEVICE IP", "ip", d.ip || "", "Optional; pinged for status and remote commands", true)}
      ${field("SERVICE PORT", "servicePort", d.servicePort || "", "Optional; check this TCP port instead of ping", true)}
      ${field("SECUREON PASSWORD", "secureon", d.secureon || "", "Optional 6 hex bytes appended to the packet", true)}
      ${field("USERNAME", "username", d.username || "", "Optional; the {user} placeholder for commands", true)}
      ${field("AGENT PORT", "agentPort", d.agentPort || "", "Optional; WoLmk-Agent port (default 9477)", true)}
      ${field("AGENT TOKEN", "agentToken", d.agentToken || "", "Optional; token the agent prints on first run", true)}
      ${field("CREDENTIAL HINT", "credHint", d.credHint || "", "Optional note only; passwords are never stored", false, true)}
    </div>
    <label class="check"><input type="checkbox" data-k="autowake" ${d.autowake ? "checked" : ""}/> Wake on app start</label>
    <div class="advanced-toggle" id="advToggle">&#9656; ADVANCED (REMOTE COMMANDS)</div>
    <div class="advanced" id="advBox">
      ${field("SHUTDOWN COMMAND", "cmdShutdown", d.cmdShutdown || "", "Blank uses the default. Placeholders: {ip}, {user}", true, true)}
      ${field("SLEEP COMMAND", "cmdSleep", d.cmdSleep || "", "Blank uses the default. Power users can set SSH here", true, true)}
      <div class="default-cmd">Default shutdown: ${esc(DEFAULT_SHUTDOWN)}</div>
    </div>`;

  const modal = openModal(isEdit ? "Edit device" : "Add device", body, [
    { label: "Cancel", cls: "btn", fn: closeModal },
    { label: "Save device", cls: "btn primary", fn: () => saveDevice(index, d) },
  ], "wide");

  const advOpen = !!(d.cmdShutdown || d.cmdSleep);
  const advBox = modal.querySelector("#advBox");
  const advToggle = modal.querySelector("#advToggle");
  const setAdv = (open) => {
    advBox.classList.toggle("open", open);
    advToggle.innerHTML =
      (open ? "&#9662;" : "&#9656;") + " ADVANCED (REMOTE COMMANDS)";
  };
  setAdv(advOpen);
  advToggle.onclick = () => setAdv(!advBox.classList.contains("open"));

  const first = modal.querySelector('input[data-k="name"]');
  if (first) first.focus();
}

async function saveDevice(index, base) {
  const modal = document.querySelector(".modal");
  const dev = Object.assign({}, base);
  modal.querySelectorAll("input[data-k]").forEach((inp) => {
    const k = inp.dataset.k;
    if (inp.type === "checkbox") dev[k] = inp.checked;
    else if (k === "port") dev[k] = parseInt(inp.value || "9", 10) || 9;
    else if (k === "agentPort") dev[k] = parseInt(inp.value || "0", 10) || 0;
    else dev[k] = inp.value.trim();
  });
  const res = index >= 0 ? await Go().UpdateDevice(index, dev) : await Go().AddDevice(dev);
  if (!res.ok) {
    setStatus(res.error || "Could not save device", "err");
    return;
  }
  closeModal();
  await refresh();
  setStatus(`${index >= 0 ? "Updated" : "Added"} ${dev.name}`, "ok");
}

// ---- schedule dialog ----------------------------------------------------

function openScheduleDialog(index) {
  const d = devices[index];
  const s = d.schedule || {};
  const mode = s.mode || "repeating";
  const activeDays = new Set(s.days || []);
  const days = WEEKDAYS.map(
    (name, i) =>
      `<div class="day${activeDays.has(i) ? " on" : ""}" data-day="${i}">${name}</div>`
  ).join("");
  const body = `
    <div class="mode-row">
      <label><input type="radio" name="smode" value="repeating" ${mode === "repeating" ? "checked" : ""}/> Repeating</label>
      <label><input type="radio" name="smode" value="onetime" ${mode === "onetime" ? "checked" : ""}/> One time</label>
    </div>
    <div id="repBox">
      <div class="field"><label>DAYS</label><div class="days">${days}</div></div>
      <div class="field"><label>TIME (HH:MM)</label>
        <input type="text" id="repTime" value="${esc(mode !== "onetime" ? s.time || "08:00" : "08:00")}"/></div>
    </div>
    <div id="onceBox">
      <div class="field"><label>DATE (YYYY-MM-DD)</label>
        <input type="text" id="onceDate" value="${esc(mode === "onetime" ? s.date || "" : "")}"/></div>
      <div class="field"><label>TIME (HH:MM)</label>
        <input type="text" id="onceTime" value="${esc(mode === "onetime" ? s.time || "08:00" : "08:00")}"/></div>
    </div>`;

  const modal = openModal(`Schedule: ${d.name}`, body, [
    { label: "Clear schedule", cls: "btn danger", fn: () => saveSchedule(index, null) },
    { label: "Save", cls: "btn primary", fn: () => saveScheduleFromForm(index) },
  ]);

  const repBox = modal.querySelector("#repBox");
  const onceBox = modal.querySelector("#onceBox");
  const applyMode = () => {
    const m = modal.querySelector('input[name="smode"]:checked').value;
    repBox.style.display = m === "repeating" ? "block" : "none";
    onceBox.style.display = m === "onetime" ? "block" : "none";
  };
  modal.querySelectorAll('input[name="smode"]').forEach((r) => (r.onchange = applyMode));
  applyMode();
  modal.querySelectorAll(".day").forEach(
    (dayEl) => (dayEl.onclick = () => dayEl.classList.toggle("on"))
  );
}

function validTime(t) { return /^([01]?\d|2[0-3]):[0-5]\d$/.test(t); }
function validDate(d) { return /^\d{4}-\d{2}-\d{2}$/.test(d) && !isNaN(Date.parse(d)); }

async function saveScheduleFromForm(index) {
  const modal = document.querySelector(".modal");
  const m = modal.querySelector('input[name="smode"]:checked').value;
  let sched;
  if (m === "repeating") {
    const days = [...modal.querySelectorAll(".day.on")].map((x) => parseInt(x.dataset.day, 10));
    const time = modal.querySelector("#repTime").value.trim();
    if (!days.length) return setStatus("Pick at least one day.", "err");
    if (!validTime(time)) return setStatus("Time must be HH:MM (24 hour).", "err");
    sched = { mode: "repeating", days, time, date: "", fired: false };
  } else {
    const date = modal.querySelector("#onceDate").value.trim();
    const time = modal.querySelector("#onceTime").value.trim();
    if (!validDate(date) || !validTime(time))
      return setStatus("Enter a valid date (YYYY-MM-DD) and time (HH:MM).", "err");
    sched = { mode: "onetime", days: [], time, date, fired: false };
  }
  await saveSchedule(index, sched);
}

async function saveSchedule(index, sched) {
  await Go().SetSchedule(index, sched);
  closeModal();
  await refresh();
  setStatus(sched ? "Schedule saved" : "Schedule cleared", "ok");
}

// ---- history ------------------------------------------------------------

async function openHistory() {
  const entries = (await Go().GetHistory()) || [];
  let rows = "";
  if (!entries.length) {
    rows = `<tr><td class="history-empty" colspan="5">No wake attempts recorded yet.</td></tr>`;
  } else {
    rows = entries
      .map((e) => {
        const ping =
          e.ping === true
            ? `<td class="on">came online</td>`
            : e.ping === false
            ? `<td class="off">no reply</td>`
            : `<td></td>`;
        return `<tr>
          <td>${esc(e.ts)}</td>
          <td>${esc(e.device)}</td>
          <td class="${esc(e.result)}">${esc(e.result)}</td>
          <td>${esc(e.target)}</td>
          ${ping}
        </tr>`;
      })
      .join("");
  }
  openModal(
    "Wake history",
    `<table class="history-table">${rows}</table>`,
    [{ label: "Close", cls: "btn", fn: closeModal }],
    "wide"
  );
}

// ---- my device ----------------------------------------------------------

async function openMyDevice() {
  const adapters = (await Go().GetNetworkAdapters()) || [];
  let body;
  if (!adapters.length) {
    body = `<div class="history-empty">No network adapters found.</div>`;
  } else {
    body =
      `<div class="scan-note">Network adapters on this machine. The primary adapter carries the default gateway.</div>` +
      `<table class="adapter-table">` +
      adapters
        .map(
          (a, i) => `<tr>
            <td>
              <div class="ad-name">${esc(a.name)}${a.gateway ? ` <span class="badge">primary</span>` : ""}</div>
              <div class="mono">MAC ${esc(a.mac || "-")} &nbsp; IP ${esc(a.ipv4 || "-")}</div>
            </td>
            <td class="${a.up ? "on" : "off"}">${a.up ? "connected" : "disconnected"}</td>
            <td style="text-align:right">
              <button class="btn small" data-i="${i}">Copy</button>
            </td>
          </tr>`
        )
        .join("") +
      `</table>`;
  }
  const modal = openModal("My Device", body, [
    { label: "Close", cls: "btn", fn: closeModal },
  ], "wide");
  modal.querySelectorAll("button[data-i]").forEach((b) => {
    b.onclick = async () => {
      const a = adapters[parseInt(b.dataset.i, 10)];
      const text = `Name: ${a.name}, MAC: ${a.mac || "-"}, IP: ${a.ipv4 || "-"}`;
      try {
        if (RT().ClipboardSetText) await RT().ClipboardSetText(text);
        else await navigator.clipboard.writeText(text);
        b.textContent = "Copied";
        setTimeout(() => (b.textContent = "Copy"), 1200);
      } catch {
        setStatus("Could not copy to clipboard", "err");
      }
    };
  });
}

// ---- network scan -------------------------------------------------------

function openScanModal() {
  const body = `
    <div class="scan-bar-track"><div class="scan-bar" id="scanBar"></div></div>
    <div class="scan-note" id="scanNote">Detecting your network...</div>
    <div id="scanResults"></div>`;
  openModal("Scan network", body, [
    { label: "Close", cls: "btn", fn: closeScan },
  ], "wide");
  RT().EventsOn("scan:progress", (e) => {
    const pct = e.total ? Math.round((e.done / e.total) * 100) : 0;
    const bar = document.getElementById("scanBar");
    const note = document.getElementById("scanNote");
    if (bar) bar.style.width = pct + "%";
    if (note) note.textContent = `Scanning your subnet... ${e.done}/${e.total}`;
  });
  RT().EventsOn("scan:done", (results) => {
    RT().EventsOff("scan:progress");
    const bar = document.getElementById("scanBar");
    const note = document.getElementById("scanNote");
    if (bar) bar.style.width = "100%";
    if (note) note.textContent = `Found ${results.length} device(s) on your network.`;
    renderScanResults(results || []);
  });
  Go().ScanNetwork();
}

function closeScan() {
  RT().EventsOff("scan:progress");
  RT().EventsOff("scan:done");
  closeModal();
}

function renderScanResults(results) {
  const box = document.getElementById("scanResults");
  if (!box) return;
  if (!results.length) {
    box.innerHTML = `<div class="history-empty">No devices responded to the sweep.</div>`;
    return;
  }
  box.innerHTML =
    `<table class="scan-table">` +
    results
      .map(
        (r) => `<tr>
          <td class="mono">${esc(r.ip)}</td>
          <td class="mono">${esc(r.mac || "-")}</td>
          <td>${esc(r.host || "")}</td>
          <td style="text-align:right">
            <button class="btn small primary" data-ip="${esc(r.ip)}"
                    data-mac="${esc(r.mac || "")}" data-host="${esc(r.host || "")}">Add</button>
          </td>
        </tr>`
      )
      .join("") +
    `</table>`;
  box.querySelectorAll("button[data-ip]").forEach((b) => {
    b.onclick = () => {
      closeScan();
      openDeviceDialog(
        {
          name: b.dataset.host || b.dataset.ip,
          mac: b.dataset.mac,
          ip: b.dataset.ip,
          host: BROADCAST,
          port: 9,
        },
        -1
      );
    };
  });
}

// ---- modal plumbing -----------------------------------------------------

function openModal(title, bodyHtml, actions, extraClass) {
  closeModal();
  const overlay = el(`
    <div class="overlay">
      <div class="modal ${extraClass || ""}">
        <div class="modal-head"><span class="t">${esc(title)}</span></div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-foot"></div>
      </div>
    </div>`);
  const foot = overlay.querySelector(".modal-foot");
  actions.forEach((a) => {
    const b = el(`<button class="${a.cls}">${esc(a.label)}</button>`);
    b.onclick = a.fn;
    foot.appendChild(b);
  });
  overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) closeModal();
  });
  document.body.appendChild(overlay);
  return overlay.querySelector(".modal");
}

function closeModal() {
  document.querySelectorAll(".overlay").forEach((o) => o.remove());
  // Defensively drop scan listeners if a scan modal was open.
  if (window.runtime) {
    RT().EventsOff("scan:progress");
    RT().EventsOff("scan:done");
  }
}

// ---- status + live events ----------------------------------------------

function setStatus(text, kind) {
  const t = document.getElementById("statusText");
  const dot = document.getElementById("statusDot");
  if (!t) return;
  t.textContent = text;
  t.style.color =
    kind === "ok" ? "var(--ok)" : kind === "err" ? "var(--err)" :
    kind === "warn" ? "var(--warn)" : "var(--muted)";
  dot.className = "dot" + (kind && kind !== "muted" ? " " + kind : "");
}

function cardByMac(mac) {
  return document.querySelector(`.card[data-mac="${CSS.escape(mac)}"]`);
}

function applyStatus(ev) {
  const card = cardByMac(ev.mac);
  if (!card) return;
  const led = card.querySelector(".led");
  const st = card.querySelector(".card-status");
  led.className = "led" + (ev.kind && ev.kind !== "muted" ? " " + ev.kind : "");
  st.className = "card-status " + ev.kind;
  st.textContent = ev.text;
}

function pulse(ev) {
  const card = cardByMac(ev.mac);
  if (!card) return;
  const led = card.querySelector(".led");
  const ring = document.createElement("span");
  ring.className = "ring" + (ev.kind === "err" ? " err" : "");
  led.appendChild(ring);
  setTimeout(() => ring.remove(), 720);
}

// ---- data + init --------------------------------------------------------

async function refresh() {
  devices = (await Go().GetDevices()) || [];
  if (selected != null && selected >= devices.length) selected = null;
  renderDevices();
}

function bindShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (document.querySelector(".overlay")) closeModal();
      closeMenu();
      return;
    }
    const inField = ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
    if (e.ctrlKey && e.key.toLowerCase() === "n") {
      e.preventDefault(); openDeviceDialog(null, -1);
    } else if (e.ctrlKey && e.key.toLowerCase() === "a" && !inField) {
      e.preventDefault(); Go().WakeAll();
    } else if (e.ctrlKey && e.key.toLowerCase() === "w") {
      e.preventDefault();
      if (selected != null) Go().Wake(selected);
    }
  });
}

function subscribe() {
  RT().EventsOn("status", applyStatus);
  RT().EventsOn("pulse", pulse);
  RT().EventsOn("statusbar", (e) => setStatus(e.text, e.kind));
  RT().EventsOn("devices:changed", refresh);
}

function start() {
  if (!window.go || !window.go.main || !window.runtime) {
    return setTimeout(start, 30);
  }
  Go().Version().then((v) => {
    version = v;
    buildShell();
    subscribe();
    bindShortcuts();
    refresh().then(() => Go().OnReady());
  });
}

start();
