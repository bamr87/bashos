/* The shell reducer's contract — docs/frontend/SPEC-os-shell.md §4.
 *
 * "Documented intent ⇒ tested consumer" is the rule those docs exist to
 * enforce, so every intent is asserted here. Run through pytest
 * (tests/test_shell.py) or directly:  node --test tests/shell.test.mjs
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import * as shell from "../src/bashos/gui/web/shell.js";

const start = () => shell.initialState("overview");

const nav = (state, sceneId, intent = "replace", resourceId = null) =>
  shell.reduce(state, { type: "navigate", sceneId, resourceId, intent });

test("initial state is one focused window in single mode", () => {
  const state = start();
  assert.equal(state.experience, "single");
  assert.equal(state.windows.length, 1);
  assert.equal(shell.focused(state).sceneId, "overview");
});

test("replace mutates the focused window and never adds a pane", () => {
  const state = nav(start(), "health");
  assert.equal(state.windows.length, 1);
  assert.equal(shell.focused(state).sceneId, "health");
  assert.equal(state.experience, "single");
});

test("reduce does not mutate the state it is given", () => {
  const before = start();
  const snapshot = JSON.stringify(before);
  nav(before, "engine", "sideBySide");
  assert.equal(JSON.stringify(before), snapshot);
});

test("sideBySide from single opens a second pane and turns tiling on", () => {
  const state = nav(start(), "runs", "sideBySide");
  assert.equal(state.experience, "tiling");
  assert.equal(state.windows.length, 2);
  assert.equal(shell.focused(state).sceneId, "runs");
  assert.equal(state.windows[0].sceneId, "overview");
});

test("new appends a pane, like sideBySide below the cap", () => {
  const state = nav(start(), "engine", "new");
  assert.equal(state.windows.length, 2);
  assert.equal(shell.focused(state).sceneId, "engine");
});

test("at the pane cap a split replaces the pane you are not watching", () => {
  let state = nav(start(), "runs", "sideBySide"); // overview | runs(focus)
  assert.equal(state.windows.length, shell.MAX_PANES);
  state = nav(state, "health", "sideBySide");
  assert.equal(state.windows.length, shell.MAX_PANES, "never grows past the cap");
  assert.equal(shell.focused(state).sceneId, "health");
  const scenes = state.windows.map((w) => w.sceneId).sort();
  assert.deepEqual(scenes, ["health", "runs"], "the focused pane survived");
});

test("focus reuses an open target instead of duplicating it", () => {
  let state = nav(start(), "runs", "sideBySide");
  state = shell.reduce(state, { type: "focus", id: state.windows[0].id });
  assert.equal(shell.focused(state).sceneId, "overview");

  const focused = nav(state, "runs", "focus");
  assert.equal(focused.windows.length, 2, "no third pane");
  assert.equal(shell.focused(focused).sceneId, "runs");
});

test("focus on a target that is not open falls back to replace", () => {
  const state = nav(start(), "commands", "focus");
  assert.equal(state.windows.length, 1);
  assert.equal(shell.focused(state).sceneId, "commands");
});

test("the console is a singleton — a split never mounts it twice", () => {
  let state = nav(start(), "console", "sideBySide");
  assert.equal(state.windows.length, 2);
  state = shell.reduce(state, { type: "focus", id: state.windows[0].id });
  state = nav(state, "console", "new");
  const consoles = state.windows.filter((w) => w.sceneId === "console");
  assert.equal(consoles.length, 1, "one Console, one event stream");
  assert.equal(shell.focused(state).sceneId, "console");
});

test("run details are separate windows, keyed by resource", () => {
  let state = nav(start(), "runs", "sideBySide", "run_a");
  assert.equal(shell.focused(state).resourceId, "run_a");
  state = nav(state, "runs", "focus", "run_b");
  assert.equal(shell.focused(state).resourceId, "run_b", "a different run is a different target");
});

test("plain refuses to split: the mode has a real consumer", () => {
  let state = shell.reduce(start(), { type: "experience", experience: "plain" });
  state = nav(state, "runs", "sideBySide");
  assert.equal(state.windows.length, 1);
  assert.equal(state.experience, "plain");
  assert.equal(shell.focused(state).sceneId, "runs");
});

test("switching to single or plain keeps the focused window only", () => {
  const split = nav(start(), "health", "sideBySide");
  const single = shell.reduce(split, { type: "experience", experience: "single" });
  assert.equal(single.windows.length, 1);
  assert.equal(shell.focused(single).sceneId, "health");
});

test("close never leaves zero panes and moves focus off the closed one", () => {
  const split = nav(start(), "runs", "sideBySide");
  const closed = shell.reduce(split, { type: "close", id: split.focusId });
  assert.equal(closed.windows.length, 1);
  assert.equal(shell.focused(closed).sceneId, "overview");

  const again = shell.reduce(closed, { type: "close", id: closed.focusId });
  assert.equal(again, closed, "closing the last pane is a no-op");
});

test("expand maximizes exactly one pane", () => {
  const split = nav(start(), "runs", "sideBySide");
  const expanded = shell.reduce(split, { type: "expand", id: split.windows[0].id });
  assert.deepEqual(
    expanded.windows.map((w) => w.expanded),
    [true, false]
  );
  const restored = shell.reduce(expanded, {
    type: "expand",
    id: split.windows[0].id,
    expanded: false,
  });
  assert.ok(restored.windows.every((w) => !w.expanded));
});

test("closing a pane clears any maximize", () => {
  const split = nav(start(), "runs", "sideBySide");
  const expanded = shell.reduce(split, { type: "expand", id: split.focusId });
  const closed = shell.reduce(expanded, { type: "close", id: split.windows[0].id });
  assert.ok(closed.windows.every((w) => !w.expanded));
});

test("cycle moves focus and wraps", () => {
  const split = nav(start(), "runs", "sideBySide");
  const once = shell.reduce(split, { type: "cycle" });
  assert.notEqual(once.focusId, split.focusId);
  const twice = shell.reduce(once, { type: "cycle" });
  assert.equal(twice.focusId, split.focusId);
  assert.equal(shell.reduce(start(), { type: "cycle" }).windows.length, 1);
});

test("a narrow viewport is single whatever the setting says", () => {
  const split = nav(start(), "runs", "sideBySide");
  assert.equal(shell.effectiveExperience(split, 1400), "tiling");
  assert.equal(shell.effectiveExperience(split, shell.NARROW_WIDTH - 1), "single");
  assert.equal(shell.isMultiPane(split, shell.NARROW_WIDTH - 1), false);
});

test("hashes match the routes the desktop already published", () => {
  assert.equal(shell.hashFor({ sceneId: "console", resourceId: null }), "#/console");
  assert.equal(shell.hashFor({ sceneId: "runs", resourceId: "abc123" }), "#/runs/abc123");
});

test("an unknown action leaves the state untouched", () => {
  const state = start();
  assert.equal(shell.reduce(state, { type: "nope" }), state);
});

/* ───────────────────────────────── desktop mode (os) and workspace layouts */

const desktop = () => shell.reduce(start(), { type: "experience", experience: "os" });

test("the desktop holds more than two windows, up to a cap", () => {
  let state = desktop();
  for (const scene of ["runs", "health", "engine", "commands", "settings"]) {
    state = nav(state, scene, "new");
  }
  assert.equal(state.windows.length, 6);
  assert.ok(state.windows.length <= shell.MAX_WINDOWS);
});

test("a full desktop reuses a window instead of growing forever", () => {
  let state = desktop();
  const scenes = ["runs", "health", "engine", "commands", "settings", "console", "overview"];
  for (let i = 0; i < 12; i++) state = nav(state, scenes[i % scenes.length], "new", `r${i}`);
  assert.equal(state.windows.length, shell.MAX_WINDOWS);
});

test("new desktop windows cascade instead of stacking exactly", () => {
  const state = nav(desktop(), "runs", "new");
  const [first, second] = state.windows;
  assert.notDeepEqual(first.position, second.position);
});

test("focus raises a window above the others", () => {
  let state = nav(desktop(), "runs", "new");
  const [first, second] = state.windows;
  assert.ok(second.zIndex > first.zIndex, "the new window is on top");
  state = shell.reduce(state, { type: "focus", id: first.id });
  const raised = state.windows.find((w) => w.id === first.id);
  assert.ok(raised.zIndex > second.zIndex, "focusing raises");
});

test("move and resize are clamped to the desktop", () => {
  let state = desktop();
  const id = state.focusId;
  state = shell.reduce(state, { type: "move", id, xPct: 999, yPct: -50 });
  const moved = shell.focused(state);
  assert.equal(moved.position.xPct, 98);
  assert.equal(moved.position.yPct, 0);

  state = shell.reduce(state, { type: "resize", id, wPct: 5, hPct: 400 });
  const sized = shell.focused(state);
  assert.equal(sized.size.wPct, 18, "a window never shrinks to nothing");
  assert.equal(sized.size.hPct, 100);
});

test("snapping sets an edge, and dragging clears it", () => {
  let state = desktop();
  const id = state.focusId;
  state = shell.reduce(state, { type: "snap", id, edge: "left" });
  assert.equal(shell.focused(state).snapped, "left");
  assert.deepEqual(shell.focused(state).size, { wPct: 50, hPct: 100 });

  state = shell.reduce(state, { type: "move", id, xPct: 20, yPct: 20 });
  assert.equal(shell.focused(state).snapped, null, "moving a snapped window unsnaps it");
});

test("minimize hides a window but the taskbar still lists it", () => {
  let state = nav(desktop(), "runs", "new");
  const runs = shell.focused(state);
  state = shell.reduce(state, { type: "minimize", id: runs.id });
  assert.equal(shell.visibleWindows(state).length, 1);
  assert.equal(shell.taskbarWindows(state).length, 2, "minimized is not closed");
  assert.notEqual(state.focusId, runs.id, "focus moved off the minimized window");

  state = shell.reduce(state, { type: "restore", id: runs.id });
  assert.equal(shell.visibleWindows(state).length, 2);
  assert.equal(state.focusId, runs.id);
});

test("cycle skips minimized windows", () => {
  let state = nav(desktop(), "runs", "new");
  const runs = shell.focused(state);
  state = shell.reduce(state, { type: "minimize", id: runs.id });
  const cycled = shell.reduce(state, { type: "cycle" });
  assert.equal(cycled.focusId, state.focusId, "nothing else to cycle to");
});

test("arrange tiles every visible window without overlap", () => {
  let state = desktop();
  for (const scene of ["runs", "health"]) state = nav(state, scene, "new");
  const tiled = shell.reduce(state, { type: "arrange", mode: "tile" });
  const boxes = tiled.windows.map((w) => `${w.position.xPct},${w.position.yPct}`);
  assert.equal(new Set(boxes).size, boxes.length, "each window got its own cell");
  assert.ok(tiled.windows.every((w) => w.size.wPct <= 50));
});

test("arrange cascade puts them back on a diagonal", () => {
  let state = desktop();
  state = nav(state, "runs", "new");
  const tiled = shell.reduce(state, { type: "arrange", mode: "tile" });
  const cascaded = shell.reduce(tiled, { type: "arrange", mode: "cascade" });
  const [first, second] = cascaded.windows;
  assert.ok(second.position.xPct > first.position.xPct);
  assert.ok(second.position.yPct > first.position.yPct);
});

test("switching os → tiling keeps two windows, → single keeps one", () => {
  let state = desktop();
  for (const scene of ["runs", "health"]) state = nav(state, scene, "new");
  const tiling = shell.reduce(state, { type: "experience", experience: "tiling" });
  assert.equal(tiling.windows.length, shell.MAX_PANES);
  const single = shell.reduce(state, { type: "experience", experience: "single" });
  assert.equal(single.windows.length, 1);
});

test("a narrow viewport is single, desktop or not", () => {
  const state = nav(desktop(), "runs", "new");
  assert.equal(shell.effectiveExperience(state, 1400), "os");
  assert.equal(shell.effectiveExperience(state, shell.NARROW_WIDTH - 1), "single");
  assert.equal(shell.isDesktop(state, shell.NARROW_WIDTH - 1), false);
});

test("a layout round-trips through encode and decode", () => {
  let state = desktop();
  state = nav(state, "runs", "new", "run_abc");
  state = shell.reduce(state, { type: "snap", id: state.focusId, edge: "right" });

  const restored = shell.decodeLayout(shell.encodeLayout(state));
  assert.equal(restored.experience, "os");
  assert.equal(restored.windows.length, state.windows.length);
  assert.deepEqual(
    restored.windows.map((w) => [w.sceneId, w.resourceId, w.snapped]),
    state.windows.map((w) => [w.sceneId, w.resourceId, w.snapped])
  );
  assert.equal(shell.focused(restored).sceneId, shell.focused(state).sceneId);
});

test("an encoded layout carries no credential and no run output", () => {
  const encoded = JSON.stringify(shell.encodeLayout(nav(desktop(), "runs", "new", "run_abc")));
  for (const forbidden of ["token", "k=", "secret", "output", "trace"]) {
    assert.ok(!encoded.includes(forbidden), `layout leaked ${forbidden}`);
  }
});

test("a hostile layout cannot invent scenes or fork the console", () => {
  const hostile = {
    v: 1,
    e: "os",
    f: 0,
    w: [
      { s: "console", x: 0, y: 0, cx: 50, cy: 50 },
      { s: "console", x: 10, y: 10, cx: 50, cy: 50 },
      { s: "../../etc/passwd", x: 0, y: 0, cx: 50, cy: 50 },
      { s: "runs", x: 0, y: 0, cx: 50, cy: 50 },
    ],
  };
  const restored = shell.decodeLayout(hostile, ["overview", "console", "runs"]);
  const scenes = restored.windows.map((w) => w.sceneId);
  assert.deepEqual(scenes, ["console", "runs"], "unknown scene dropped, console deduped");
});

test("decodeLayout refuses junk rather than half-restoring it", () => {
  assert.equal(shell.decodeLayout(null), null);
  assert.equal(shell.decodeLayout({ v: 99, w: [{ s: "runs" }] }), null);
  assert.equal(shell.decodeLayout({ v: 1, w: [] }), null);
  assert.equal(shell.decodeLayout({ v: 1, w: [{ nope: true }] }), null);
});

test("hydrate replaces the state, but not with nothing", () => {
  const state = start();
  const layout = shell.decodeLayout(shell.encodeLayout(desktop()));
  assert.equal(shell.reduce(state, { type: "hydrate", state: layout }).experience, "os");
  assert.equal(shell.reduce(state, { type: "hydrate", state: null }), state);
});
