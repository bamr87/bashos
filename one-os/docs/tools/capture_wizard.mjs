#!/usr/bin/env node
// Capture documentation screenshots of the flash wizard (make docs-screenshots).
//
// Starts a real wizard server and headless Chrome, drives the page over the DevTools
// protocol (Node's built-in WebSocket, no packages), and writes docs/images/wizard-*.png.
// Progress / finished / boot-test views use sample job data injected into the page,
// because a docs run must never write a disk. Needs a removable disk inserted for the
// device-selection shots (it picks the first one whose name contains $DOCS_DISK_MATCH,
// default "SDXC"); without one it shows a sample SD-card entry.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "../..");
const OUT = join(ROOT, "docs/images");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const MATCH = process.env.DOCS_DISK_MATCH || "SDXC";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- wizard server -----------------------------------------------------------------
const server = spawn("python3", [join(ROOT, "ui/server.py"), "--port", "8790", "--no-open"], { cwd: ROOT });
const url = await new Promise((res, rej) => {
  server.stdout.on("data", (d) => { const m = String(d).match(/(http:\/\/127\.0\.0\.1:\d+\/\?t=\S+)/); if (m) res(m[1]); });
  server.on("exit", (c) => rej(new Error("wizard server exited " + c)));
});

// --- chrome + CDP --------------------------------------------------------------------
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9333", "--hide-scrollbars",
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "oneos-docs-"))}`, "about:blank"], { stdio: "ignore" });
let target;
for (let i = 0; i < 50 && !target; i++) {
  try { target = (await (await fetch("http://127.0.0.1:9333/json/list")).json()).find((t) => t.type === "page"); }
  catch { await sleep(200); }
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0; const pending = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const cdp = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq; pending.set(id, (m) => (m.error ? rej(new Error(method + ": " + m.error.message)) : res(m.result)));
  ws.send(JSON.stringify({ id, method, params }));
});
const js = async (expr) => (await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

async function page(scheme) {
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] });
  await cdp("Emulation.setDeviceMetricsOverride", { width: 920, height: 900, deviceScaleFactor: 2, mobile: false });
  await cdp("Page.navigate", { url });
  await sleep(3500); // first /api/state + /api/devices round trips
}
async function shot(name) {
  const h = await js("document.documentElement.scrollHeight");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 920, height: Math.min(h, 2400), deviceScaleFactor: 2, mobile: false });
  await sleep(300);
  const { data } = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  writeFileSync(join(OUT, name), Buffer.from(data, "base64"));
  console.log("docs/images/" + name);
}
const freeze = "for (let i = 1; i < 9999; i++) clearInterval(i);"; // stop polling so injected state stays

try {
  await page("light");
  await shot("wizard-overview.png");

  // choose the card, then type the confirmation
  const picked = await js(`(() => { const d = [...document.querySelectorAll('[data-dev]')].find(e => e.textContent.includes(${JSON.stringify(MATCH)}));
    if (!d) return false; d.click(); return true; })()`);
  if (!picked) {
    // No such disk plugged in: show a sample SD card (sized like the current card image).
    console.log(`(no disk matching "${MATCH}"; using a sample SD card entry)`);
    await js(`${freeze}
      S.devices.unshift({ disk: "disk5", media: "Built In SDXC Reader", bus: "Secure Digital", size: 128177930240,
        partitions: [{ name: "Ventoy", type: "Microsoft Basic Data", size: "128.1 GB" }, { name: "VTOYEFI", type: "Microsoft Basic Data", size: "34 MB" }],
        is_oneos: true, card_image_fits: true });
      S.selKey = S.devices[0].media + "|" + S.devices[0].size; render();`);
  }
  await sleep(600);
  await js(`(() => { const c = document.getElementById('confirm'); if (!c) return;
    c.value = selected().media; c.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await sleep(300);
  await shot("wizard-flash-confirm.png");

  // sample: flash in progress
  await js(`${freeze}
    S.state.job = { id: "doc1", step: "flash", title: "Flash " + selected().media + " (" + selected().disk + ")", state: "running",
      started: Date.now()/1000 - 96, elapsed: 96, progress: { phase: "write", done: 3.42, total: 5.57, rate: "38.9" },
      log: "write-image: 10 extents, 5.57 GB of data in a 128.2 GB image\\n  wrote   3.42 / 5.57 GB  ( 38.9 MB/s)", result: {} };
    render();`);
  await sleep(500);
  await shot("wizard-flash-progress.png");

  // sample: finished + history
  await js(`${freeze}
    S.state.job = { id: "doc2", step: "flash", title: "Flash " + selected().media + " (" + selected().disk + ")", state: "ok",
      elapsed: 214, progress: { phase: "verify", done: 10, total: 10 }, log: "write-image: verified OK", result: { state: "ok" } };
    S.state.history = [{ time: "2026-11-08 09:12:44", disk: selected().disk, media: selected().media, size: selected().size, result: "verified" }];
    render();`);
  await sleep(500);
  await shot("wizard-flash-done.png");

  // sample: boot-test results (uses the real last test screenshot if there is one)
  await js(`${freeze}
    S.state.job = { id: "doc3", step: "test", title: "Boot the flashed image and check it", state: "ok", elapsed: 430, ended: 1,
      progress: null, log: "", result: { screenshot: true, checks: [
        "PASS: live account 'user' exists", "PASS: password 'live' works",
        "PASS: Xfce desktop logged in automatically (panel + desktop up)", "PASS: persistence mounted",
        "PASS: guest agent running", "PASS: build v1" ] } };
    S.open.add("test"); render();`);
  await sleep(1500);
  await shot("wizard-boot-test.png");

  await page("dark");
  await shot("wizard-overview-dark.png");
} finally {
  ws.close(); chrome.kill(); server.kill();
}
