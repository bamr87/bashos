"""Capture the bashOS desktop: the stills and GIFs in docs/DESKTOP-TOUR.md.

    pip install playwright pillow && playwright install chromium
    python tools/capture_desktop.py                 # writes docs/media/

Starts `bashos gui` on a private port, drives every scene with a real browser,
and writes PNG stills plus animated GIFs. Every run it records goes through the
dry-run path, so the capture needs no credentials, no network and no engine —
the same property the test suite relies on.

Not part of the package and not run by CI: it is how the documentation stays
honest, regenerated when the front end changes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parents[1]
URL_RE = re.compile(r"http://127\.0\.0\.1:\d+/\?k=[A-Za-z0-9_-]+")

VIEWPORT = {"width": 1440, "height": 900}
# GIFs are captured at their own, narrower viewport and written at native size:
# no resampling, so the terminal text in them stays sharp.
MOTION_VIEWPORT = {"width": 1200, "height": 780}
STILL_SCALE = 2  # retina stills — the reference images in the docs
MOTION_SCALE = 1

SEED_LINES = [
    "/script rotate logs in /var/log, keep 7 days",
    "count unique IPs in access.log",
    "/explain rsync -avz --delete src/ host:/dst",
]


# --------------------------------------------------------------------- server


def start_server(port: int) -> tuple[subprocess.Popen[str], str]:
    """Run `bashos gui` headless and return the URL it printed."""
    env = {**os.environ, "COLUMNS": "200", "BASHOS_BACKEND": "opencode"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "bashos", "gui", "--browser", "--no-open", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if match := URL_RE.search(line):
            return proc, match.group(0)
        if proc.poll() is not None:
            break
    proc.kill()
    raise SystemExit("bashos gui did not print a URL — is the venv installed?")


# ---------------------------------------------------------------------- gifs


class Reel:
    """Frames on disk, each with a hold, assembled into one GIF.

    A pause is a longer duration on one frame, never a repeated frame — GIF
    encoders drop consecutive duplicates, which silently eats every pause.
    """

    def __init__(self, page: Page, name: str, out: Path, tmp: Path) -> None:
        self.page = page
        self.name = name
        self.out = out
        self.dir = tmp / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shots: list[tuple[Path, int]] = []

    async def snap(self, hold: int = 1) -> None:
        path = self.dir / f"{len(self.shots):04d}.png"
        await self.page.screenshot(path=str(path))
        self.shots.append((path, hold))

    async def type_into(self, selector: str, text: str, every: int = 2) -> None:
        for index, char in enumerate(text):
            await self.page.type(selector, char, delay=14)
            if index % every == 0:
                await self.snap()
        await self.snap(3)

    async def watch(self, seconds: float, step: float = 0.25) -> None:
        for _ in range(int(seconds / step)):
            await self.page.wait_for_timeout(int(step * 1000))
            await self.snap()

    def write(self, *, frame_ms: int = 150, width: int | None = None, colors: int = 96) -> Path:
        images, durations = [], []
        for path, hold in self.shots:
            image = Image.open(path).convert("RGB")
            if width and width != image.width:
                scale = width / image.width
                image = image.resize((width, round(image.height * scale)), Image.LANCZOS)
            images.append(image.quantize(colors=colors, method=Image.MEDIANCUT))
            durations.append(frame_ms * hold)
        target = self.out / f"{self.name}.gif"
        images[0].save(
            target,
            save_all=True,
            append_images=images[1:],
            duration=durations,
            loop=0,
            optimize=True,
            disposal=2,
        )
        return target


# -------------------------------------------------------------------- driving


async def still(page: Page, out: Path, name: str) -> Path:
    path = out / f"{name}.png"
    await page.screenshot(path=str(path))
    return path


async def goto_scene(page: Page, scene: str, settle: int = 500) -> None:
    await page.click(f'[data-action="scene:{scene}"]')
    await page.wait_for_timeout(settle)


async def seed_runs(page: Page) -> None:
    """Fill the history with real dry-run kernel runs."""
    await goto_scene(page, "console")
    for line in SEED_LINES:
        await page.fill("textarea", line)
        await page.click('[data-action="submit"]')
        await page.wait_for_timeout(1500)


async def open_desktop(page) -> None:
    """Switch the window into desktop mode through the palette."""
    await page.keyboard.press("Control+k")
    await page.wait_for_timeout(250)
    await page.fill('[data-bind="palette-query"]', "Experience: Desktop")
    await page.wait_for_timeout(250)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(700)


async def check_desktop(page) -> list[str]:
    """Assert the desktop's windows really behave (SPEC §4, ROADMAP phase 3)."""
    failures: list[str] = []

    def expect(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    await open_desktop(page)
    expect("desktop renders", await page.locator(".desktop-surface").count() == 1)
    expect("an icon per scene", await page.locator(".icon").count() == 7)
    expect("taskbar renders", await page.locator(".taskbar").count() == 1)

    await page.dblclick('[data-action="icon"][data-value="health"]')
    await page.wait_for_timeout(600)
    expect("an icon opens a window", await page.locator(".window").count() == 2)

    surface = await page.locator(".desktop-surface").bounding_box()
    head = await page.locator('.window[data-focus="true"] .win-head').bounding_box()
    await page.mouse.move(head["x"] + 60, head["y"] + 12)
    await page.mouse.down()
    await page.mouse.move(head["x"] + 260, head["y"] + 150, steps=10)
    await page.mouse.up()
    await page.wait_for_timeout(400)
    moved = await page.locator('.window[data-focus="true"]').bounding_box()
    expect("a window drags", moved["x"] > head["x"] + 120)

    head = await page.locator('.window[data-focus="true"] .win-head').bounding_box()
    await page.mouse.move(head["x"] + 60, head["y"] + 12)
    await page.mouse.down()
    await page.mouse.move(surface["x"] + 6, surface["y"] + 140, steps=12)
    expect("a snap preview appears", await page.locator(".snap-preview").is_visible())
    await page.mouse.up()
    await page.wait_for_timeout(400)
    snapped = await page.locator('.window[data-focus="true"]').bounding_box()
    expect("snapping halves the desktop", abs(snapped["width"] - surface["width"] / 2) < 14)

    await page.click('.window[data-focus="true"] [data-action="win-min"]')
    await page.wait_for_timeout(400)
    expect("minimize hides the window", await page.locator(".window:visible").count() == 1)
    expect("the taskbar keeps it", await page.locator('.task[data-minimized="true"]').count() == 1)
    await page.click('.task[data-minimized="true"]')
    await page.wait_for_timeout(400)
    expect("the taskbar restores it", await page.locator(".window:visible").count() == 2)

    await page.click('[data-action="arrange"][data-value="tile"]')
    await page.wait_for_timeout(400)
    boxes = [await w.bounding_box() for w in await page.locator(".window:visible").all()]
    expect("tiling gives each window a cell", len({round(b["x"]) for b in boxes}) == len(boxes))

    await page.click('.window[data-focus="true"] [data-action="win-close"]')
    await page.wait_for_timeout(400)
    expect("closing removes it", await page.locator(".window").count() == 1)
    return failures


async def capture(url: str, out: Path, tmp: Path) -> list[Path]:
    written: list[Path] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=os.environ.get("BASHOS_CHROMIUM") or None
        )
        errors: list[str] = []

        # ---- motion pass: a smaller, non-retina context keeps GIFs light
        motion = await browser.new_context(
            viewport=MOTION_VIEWPORT, device_scale_factor=MOTION_SCALE
        )
        page = await motion.new_page()
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None,
        )
        await page.goto(url, wait_until="networkidle")
        await page.click('[data-bind="dry-run"] + .switch-track')  # no model needed
        await page.wait_for_timeout(300)

        shell_failures = await check_shell(page)
        shell_failures += await check_desktop(page)
        if shell_failures:
            errors.extend(f"shell check failed: {name}" for name in shell_failures)
        else:
            print("shell intents and desktop windows verified against the DOM")
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(200)
        await page.fill('[data-bind="palette-query"]', "Experience: Single")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)

        # 1. a line through the kernel, from keystroke to answer
        reel = Reel(page, "console-run", out, tmp)
        await goto_scene(page, "console")
        await reel.snap(8)
        await reel.type_into("textarea", "/scr", every=1)
        await reel.snap(10)  # the completion list, held so it can be read
        await page.keyboard.press("Tab")
        await reel.snap(6)
        await reel.type_into("textarea", "rotate logs in /var/log, keep 7 days", every=4)
        await page.click('[data-action="submit"]')
        await reel.watch(2.4, step=0.2)
        await reel.snap(16)
        written.append(reel.write())

        # 2. the command palette
        reel = Reel(page, "command-palette", out, tmp)
        await goto_scene(page, "overview")
        await reel.snap(3)
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(250)
        await reel.snap(3)
        await reel.type_into('[data-bind="palette-query"]', "reg", every=1)
        await reel.snap(8)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)
        await reel.snap(14)
        written.append(reel.write())

        # 3. the whole product, scene by scene
        await seed_runs(page)
        reel = Reel(page, "scene-tour", out, tmp)
        for scene in ("overview", "console", "commands", "runs", "health", "engine", "settings"):
            await goto_scene(page, scene, settle=650)
            await reel.snap(7)
        written.append(reel.write(frame_ms=170))

        # 4. light ↔ dark
        reel = Reel(page, "theme-toggle", out, tmp)
        await goto_scene(page, "overview")
        await reel.snap(9)
        await page.click('[data-action="theme"]')
        await page.wait_for_timeout(260)
        await reel.snap(11)
        await page.click('[data-action="theme"]')
        await page.wait_for_timeout(260)
        await reel.snap(8)
        written.append(reel.write(frame_ms=150))

        # 5. userland: filter, then read a command's prompt spec
        reel = Reel(page, "commands-browse", out, tmp)
        await goto_scene(page, "commands")
        await reel.snap(8)
        await reel.type_into(".input", "scr", every=1)
        await reel.snap(11)
        await page.fill(".input", "")
        await page.wait_for_timeout(300)
        await reel.snap(6)
        await page.click("details summary")
        await page.wait_for_timeout(450)
        await reel.snap(14)
        written.append(reel.write(frame_ms=150))

        # 6. the OS shell: two scenes side by side, chrome, and back to one
        reel = Reel(page, "side-by-side", out, tmp)
        await goto_scene(page, "console")
        await reel.snap(8)
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(250)
        await page.fill('[data-bind="palette-query"]', "Side by side: Health")
        await page.wait_for_timeout(250)
        await reel.snap(10)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(700)
        await reel.snap(14)
        await page.click('[data-action="scene:runs"]', button="right")
        await page.wait_for_timeout(350)
        await reel.snap(12)
        await page.keyboard.press("Escape")
        await page.click('.pane[data-focus="true"] [data-action="pane-expand"]')
        await page.wait_for_timeout(400)
        await reel.snap(10)
        await page.click('.pane[data-focus="true"] [data-action="pane-expand"]')
        await page.wait_for_timeout(400)
        await reel.snap(6)
        await page.click('.pane[data-focus="true"] [data-action="pane-close"]')
        await page.wait_for_timeout(500)
        await reel.snap(12)
        written.append(reel.write(frame_ms=150))

        # 7. the desktop: icons, floating windows, snapping, the taskbar
        reel = Reel(page, "desktop", out, tmp)
        await open_desktop(page)
        await reel.snap(10)
        await page.dblclick('[data-action="icon"][data-value="health"]')
        await page.wait_for_timeout(600)
        await reel.snap(10)
        surface = await page.locator(".desktop-surface").bounding_box()
        head = await page.locator('.window[data-focus="true"] .win-head').bounding_box()
        await page.mouse.move(head["x"] + 60, head["y"] + 12)
        await page.mouse.down()
        for step in range(1, 5):
            await page.mouse.move(head["x"] + 60 + step * 70, head["y"] + 12 + step * 34, steps=4)
            await reel.snap(2)
        await page.mouse.up()
        await reel.snap(8)
        head = await page.locator('.window[data-focus="true"] .win-head').bounding_box()
        await page.mouse.move(head["x"] + 60, head["y"] + 12)
        await page.mouse.down()
        await page.mouse.move(surface["x"] + 120, surface["y"] + 160, steps=4)
        await reel.snap(2)
        await page.mouse.move(surface["x"] + 6, surface["y"] + 150, steps=6)
        await reel.snap(8)  # the snap preview
        await page.mouse.up()
        await reel.snap(10)
        await page.click('.window[data-focus="true"] [data-action="win-min"]')
        await page.wait_for_timeout(400)
        await reel.snap(10)
        await page.click('.task[data-minimized="true"]')
        await page.wait_for_timeout(400)
        await reel.snap(8)
        await page.click('[data-action="arrange"][data-value="tile"]')
        await page.wait_for_timeout(450)
        await reel.snap(14)
        written.append(reel.write(frame_ms=150))

        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(200)
        await page.fill('[data-bind="palette-query"]', "Experience: Single")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)

        # 8. a run, from the table to its full trace
        reel = Reel(page, "run-detail", out, tmp)
        await goto_scene(page, "runs")
        await reel.snap(10)
        await page.click(".table tbody tr")
        await page.wait_for_timeout(700)
        await reel.snap(11)
        await page.mouse.wheel(0, 420)
        await page.wait_for_timeout(350)
        await reel.snap(8)
        await page.mouse.wheel(0, 420)
        await page.wait_for_timeout(350)
        await reel.snap(13)
        written.append(reel.write(frame_ms=150))
        await motion.close()

        # ---- stills pass: retina, with history already recorded
        shots = await browser.new_context(viewport=VIEWPORT, device_scale_factor=STILL_SCALE)
        page = await shots.new_page()
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None,
        )
        await page.goto(url, wait_until="networkidle")
        await page.click('[data-bind="dry-run"] + .switch-track')
        await seed_runs(page)

        for scene, name in (
            ("overview", "overview"),
            ("console", "console"),
            ("commands", "commands"),
            ("runs", "runs"),
            ("health", "health"),
            ("engine", "engine"),
            ("settings", "settings"),
        ):
            await goto_scene(page, scene, settle=700)
            written.append(await still(page, out, name))

        await goto_scene(page, "runs")
        await page.click(".table tbody tr")
        await page.wait_for_timeout(800)
        written.append(await still(page, out, "run-detail"))

        await goto_scene(page, "overview")
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(350)
        written.append(await still(page, out, "palette"))
        await page.keyboard.press("Escape")

        # the desktop: three windows, icons and the taskbar
        await open_desktop(page)
        await page.dblclick('[data-action="icon"][data-value="health"]')
        await page.wait_for_timeout(500)
        await page.dblclick('[data-action="icon"][data-value="runs"]')
        await page.wait_for_timeout(500)
        await page.click('[data-action="arrange"][data-value="cascade"]')
        await page.wait_for_timeout(600)
        written.append(await still(page, out, "desktop"))
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(200)
        await page.fill('[data-bind="palette-query"]', "Experience: Single")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)

        # the shell: Console beside Health, with a run in the left pane
        await goto_scene(page, "console")
        await page.fill("textarea", "/sh find files over 100MB modified this week")
        await page.click('[data-action="submit"]')
        await page.wait_for_timeout(1400)
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(250)
        await page.fill('[data-bind="palette-query"]', "Side by side: Health")
        await page.wait_for_timeout(250)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(900)
        written.append(await still(page, out, "side-by-side"))
        await page.click('.pane[data-focus="true"] [data-action="pane-close"]')
        await page.wait_for_timeout(500)

        await page.click('[data-action="theme"]')
        await page.wait_for_timeout(350)
        written.append(await still(page, out, "overview-dark"))
        await goto_scene(page, "console")
        written.append(await still(page, out, "console-dark"))

        await shots.close()
        await browser.close()

    if errors:
        print("\n!! browser errors:", *errors, sep="\n   ")
    else:
        print("\nno browser console errors")
    return written


async def check_shell(page) -> list[str]:
    """Assert the nav intents against the real DOM (SPEC §4 consumers).

    The reducer has unit tests (tests/shell.test.mjs); this is the other half —
    that what it decides is what the page actually mounts.
    """
    failures: list[str] = []

    def expect(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    await goto_scene(page, "console")
    expect("starts single", await page.locator(".pane").count() == 0)

    await page.keyboard.press("Control+k")
    await page.wait_for_timeout(250)
    await page.fill('[data-bind="palette-query"]', "Side by side: Health")
    await page.wait_for_timeout(250)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(700)
    scenes = await page.locator(".pane").evaluate_all("els => els.map(e => e.dataset.scene)")
    expect("sideBySide opens two panes", sorted(scenes) == ["console", "health"])

    await page.click('[data-action="scene:console"]', button="right")
    await page.wait_for_timeout(300)
    await page.click('.menu-item:has-text("Open side by side")')
    await page.wait_for_timeout(600)
    scenes = await page.locator(".pane").evaluate_all("els => els.map(e => e.dataset.scene)")
    expect("the console is a singleton", scenes.count("console") == 1)
    expect("console composer survives", await page.locator(".pane[data-scene=console] textarea").count() == 1)

    await page.click('.pane[data-focus="true"] [data-action="pane-expand"]')
    await page.wait_for_timeout(350)
    expect("maximize hides the other pane", await page.locator(".pane:visible").count() == 1)
    await page.click('.pane[data-focus="true"] [data-action="pane-expand"]')
    await page.wait_for_timeout(350)

    await page.click('.pane[data-focus="true"] [data-action="pane-close"]')
    await page.wait_for_timeout(500)
    expect("closing returns to one scene", await page.locator(".pane").count() <= 1)
    return failures


# ----------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "docs" / "media"), help="output directory")
    parser.add_argument("--port", type=int, default=8931, help="port for the captured server")
    parser.add_argument("--url", help="drive an already-running desktop instead of starting one")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="bashos-capture-"))

    proc = None
    try:
        if args.url:
            url = args.url
        else:
            proc, url = start_server(args.port)
            print(f"desktop up on {url.split('/?')[0]}")
        written = asyncio.run(capture(url, out, tmp))
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(written)} files in {out}")
    for path in sorted(written):
        print(f"  {path.name:<24} {path.stat().st_size / 1024:>8.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
