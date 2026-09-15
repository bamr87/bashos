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
