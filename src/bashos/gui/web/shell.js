/* The shell: layout state for the desktop's experience modes.
 *
 * docs/frontend/SPEC-os-shell.md §2–§4. Pure functions over a plain object —
 * no DOM, no fetch, no globals — so the reducer can be reasoned about (and
 * asserted against from a real browser) independently of what app.js draws.
 *
 * Phase 0 scope: `single` (one scene, today's behaviour), `tiling` (two scenes
 * side by side) and `plain` (one scene, chrome unmounted). Floating windows
 * are Phase 3 and deliberately absent — an experience with no consumer is the
 * drift these docs exist to avoid.
 */

export const EXPERIENCES = ["single", "tiling", "plain"];
export const INTENTS = ["replace", "new", "focus", "sideBySide"];

/** Phase 0 is side-by-side, not a tiling tree. */
export const MAX_PANES = 2;

/** Scenes that own persistent DOM and a live event stream: one instance only.
 *  (ROADMAP kill-signal: "Console singleton pattern; second pane for other
 *  scenes" — a second Console would fork its SSE and its composer.) */
export const SINGLETON_SCENES = ["console"];

/** Below this width multi-pane is forced off, whatever the setting says. */
export const NARROW_WIDTH = 900;

let counter = 0;

export function windowId() {
  counter += 1;
  return `win_${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function makeWindow(sceneId, resourceId = null) {
  return {
    id: windowId(),
    sceneId,
    resourceId: resourceId || null,
    expanded: false,
    createdAt: new Date().toISOString(),
  };
}

export function initialState(sceneId = "overview", resourceId = null) {
  const first = makeWindow(sceneId, resourceId);
  return { experience: "single", windows: [first], focusId: first.id };
}

export function focused(state) {
  return state.windows.find((w) => w.id === state.focusId) || state.windows[0];
}

export function sameTarget(win, sceneId, resourceId = null) {
  return win.sceneId === sceneId && (win.resourceId || null) === (resourceId || null);
}

export function hashFor(win) {
  if (!win) return "#/overview";
  return win.resourceId ? `#/runs/${win.resourceId}` : `#/${win.sceneId}`;
}

/** What the viewport actually gets — a narrow window is always single. */
export function effectiveExperience(state, width) {
  if (state.experience === "plain") return "plain";
  if (state.experience === "tiling" && width >= NARROW_WIDTH) return "tiling";
  return "single";
}

export function isMultiPane(state, width) {
  return effectiveExperience(state, width) === "tiling" && state.windows.length > 1;
}

function replaceFocused(state, sceneId, resourceId) {
  const windows = state.windows.map((w) =>
    w.id === state.focusId ? { ...w, sceneId, resourceId: resourceId || null } : w
  );
  return { ...state, windows };
}

function withFocus(state, id) {
  return state.windows.some((w) => w.id === id) ? { ...state, focusId: id } : state;
}

/** Fold every action into a new state. Never mutates its argument. */
export function reduce(state, action) {
  switch (action.type) {
    case "navigate":
      return navigateReducer(state, action);

    case "focus":
      return withFocus(state, action.id);

    case "close": {
      // never zero panes: closing the last one is a no-op
      if (state.windows.length <= 1) return state;
      const windows = state.windows
        .filter((w) => w.id !== action.id)
        .map((w) => ({ ...w, expanded: false }));
      const focusId = action.id === state.focusId ? windows[0].id : state.focusId;
      return { ...state, windows, focusId };
    }

    case "expand": {
      const expand = action.expanded !== undefined ? action.expanded : true;
      const windows = state.windows.map((w) => ({
        ...w,
        expanded: w.id === action.id ? expand : false,
      }));
      return { ...withFocus({ ...state, windows }, action.id) };
    }

    case "cycle": {
      if (state.windows.length < 2) return state;
      const index = state.windows.findIndex((w) => w.id === state.focusId);
      const next = state.windows[(index + 1) % state.windows.length];
      return { ...state, focusId: next.id };
    }

    case "experience": {
      const experience = EXPERIENCES.includes(action.experience)
        ? action.experience
        : state.experience;
      if (experience === "tiling") return { ...state, experience };
      // single and plain show one scene: keep the focused one, drop the rest
      const keep = focused(state);
      return {
        ...state,
        experience,
        windows: [{ ...keep, expanded: false }],
        focusId: keep.id,
      };
    }

    default:
      return state;
  }
}

function navigateReducer(state, action) {
  const { sceneId, intent = "replace" } = action;
  const resourceId = action.resourceId || null;
  const existing = state.windows.find((w) => sameTarget(w, sceneId, resourceId));

  // A singleton scene is never opened twice — focus the instance that exists.
  if (existing && (intent === "focus" || SINGLETON_SCENES.includes(sceneId))) {
    return withFocus(state, existing.id);
  }

  const splitting = intent === "new" || intent === "sideBySide";
  if (!splitting) return replaceFocused(state, sceneId, resourceId);

  // `plain` is a deliberate single-scene mode: a split intent degrades to
  // replace rather than silently re-mounting the chrome it just unmounted.
  if (state.experience === "plain") return replaceFocused(state, sceneId, resourceId);

  // Asking for a split is the consumer of `tiling`: turn it on.
  const base = state.experience === "tiling" ? state : { ...state, experience: "tiling" };

  if (base.windows.length >= MAX_PANES) {
    // At the cap, the pane you are not watching is the one that changes.
    const other = base.windows.find((w) => w.id !== base.focusId) || base.windows[0];
    const windows = base.windows.map((w) =>
      w.id === other.id ? { ...w, sceneId, resourceId, expanded: false } : { ...w, expanded: false }
    );
    return { ...base, windows, focusId: other.id };
  }

  const win = makeWindow(sceneId, resourceId);
  return {
    ...base,
    windows: [...base.windows.map((w) => ({ ...w, expanded: false })), win],
    focusId: win.id,
  };
}
