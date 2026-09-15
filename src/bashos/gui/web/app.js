/* bashOS desktop — one page over the kernel.
 *
 * No framework and no build step: the whole front end is this file, app.css,
 * and index.html. Scenes render into a single container; the console keeps its
 * own DOM so a run in flight survives navigation. Everything the page knows it
 * learned from /api — there is no client-side model of the machine.
 */

import * as shell from "/shell.js";

const TOKEN_KEY = "bashos.token." + location.port;
const THEME_KEY = "bashos.theme";
const PREFS_KEY = "bashos.prefs";
const CODE_MARK = "@@bashos-code-";

const SCENES = [
  { id: "overview", label: "Overview", icon: "i-grid", group: "Workspace" },
  { id: "console", label: "Console", icon: "i-terminal", group: "Workspace" },
  { id: "commands", label: "Commands", icon: "i-slash", group: "Workspace" },
  { id: "runs", label: "Runs", icon: "i-activity", group: "Workspace" },
  { id: "health", label: "Health", icon: "i-gauge", group: "System" },
  { id: "engine", label: "Engine", icon: "i-chip", group: "System" },
  { id: "settings", label: "Settings", icon: "i-sliders", group: "System" },
];

const EXPERIENCES = [
  { id: "single", label: "Single", hint: "one scene, full width" },
  { id: "tiling", label: "Side by side", hint: "two scenes, focus follows click" },
  { id: "plain", label: "Plain", hint: "one scene, no chrome" },
];

const store = {
  token: "",
  state: null,
  commands: [],
  policy: null,
  doctor: null,
  runs: [],
  scene: "overview",
  prefs: { dryRun: false, model: "", experience: "single" },
  history: [],
  historyAt: -1,
  shell: shell.initialState(),
};

/* ───────────────────────────────────────────────────────────── plumbing */

const $ = (sel, root = document) => root.querySelector(sel);
const bind = (name, root = document) => root.querySelector(`[data-bind="${name}"]`);

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** Tty, the bashOS prompt — a shell with a face. Lives in web/mascot.svg. */
function mascot(cls = "mascot") {
  return el("img", { class: cls, src: "/mascot.svg", alt: "", width: 220, height: 200 });
}

function icon(name, cls = "ic") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", cls);
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#" + name);
  svg.append(use);
  return svg;
}

function readToken() {
  const url = new URL(location.href);
  const fromUrl = url.searchParams.get("k");
  if (fromUrl) {
    try { sessionStorage.setItem(TOKEN_KEY, fromUrl); } catch (_) {}
    url.searchParams.delete("k");
    history.replaceState(null, "", url.pathname + url.hash);
    return fromUrl;
  }
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch (_) { return ""; }
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "x-bashos-token": store.token };
  if (body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`);
  return payload;
}

function streamRun(runId, onEvent) {
  const source = new EventSource(
    `/api/runs/${encodeURIComponent(runId)}/events?k=${encodeURIComponent(store.token)}`
  );
  for (const kind of ["status", "node", "trace", "tool", "output", "error"]) {
    source.addEventListener(kind, (event) => onEvent(kind, JSON.parse(event.data)));
  }
  source.addEventListener("done", (event) => {
    source.close();
    onEvent("done", JSON.parse(event.data));
  });
  source.onerror = () => {
    source.close();
    onEvent("closed", null);
  };
  return source;
}

const fmt = {
  duration(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  },
  clock(epoch) {
    if (!epoch) return "—";
    return new Date(epoch * 1000).toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  },
};

function toast(message) {
  const node = bind("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { node.hidden = true; }, 2200);
}

/* ─────────────────────────────────────────────────────────── markdown */

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_, label, href) => `<a href="${href}" target="_blank" rel="noreferrer noopener">${label}</a>`
    );
}

function codeBlockHtml(block) {
  return (
    `<div class="code"><div class="code-head"><span>${escapeHtml(block.lang)}</span>` +
    `<span class="spacer"></span>` +
    `<button class="btn btn--ghost btn--sm" data-action="copy">copy</button></div>` +
    `<pre><code>${escapeHtml(block.code)}</code></pre></div>`
  );
}

/** A small, strict markdown subset: escape first, then structure. */
function renderMarkdown(source) {
  const blocks = [];
  let text = String(source).replace(/\r\n/g, "\n");
  text = text.replace(/```([\w+#.-]*)[ \t]*\n([\s\S]*?)```/g, (_, lang, code) => {
    blocks.push({ lang: lang || "text", code: code.replace(/\n$/, "") });
    return `${CODE_MARK}${blocks.length - 1}@@`;
  });
  text = escapeHtml(text);

  const lines = text.split("\n");
  const out = [];
  let paragraph = [];

  const flush = () => {
    if (paragraph.length) out.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const codeRef = line.trim().match(/^@@bashos-code-(\d+)@@$/);
    if (codeRef && blocks[Number(codeRef[1])]) {
      flush();
      out.push(codeBlockHtml(blocks[Number(codeRef[1])]));
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    if (/^(---+|\*\*\*+|___+)\s*$/.test(line.trim())) { flush(); out.push("<hr>"); continue; }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flush();
      const level = Math.min(heading[1].length, 4);
      out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    if (/^\s*&gt;\s?/.test(line)) {
      flush();
      const quoted = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*&gt;\s?/, ""));
        i++;
      }
      i--;
      out.push(`<blockquote>${inlineMarkdown(quoted.join(" "))}</blockquote>`);
      continue;
    }

    const bullet = /^\s*[-*+]\s+(.*)$/;
    const numbered = /^\s*\d+[.)]\s+(.*)$/;
    if (bullet.test(line) || numbered.test(line)) {
      flush();
      const ordered = numbered.test(line);
      const pattern = ordered ? numbered : bullet;
      const items = [];
      while (i < lines.length && pattern.test(lines[i])) {
        items.push(`<li>${inlineMarkdown(lines[i].match(pattern)[1])}</li>`);
        i++;
      }
      i--;
      out.push(`<${ordered ? "ol" : "ul"}>${items.join("")}</${ordered ? "ol" : "ul"}>`);
      continue;
    }

    const next = lines[i + 1] || "";
    if (line.trim().startsWith("|") && /^\s*\|[\s:|-]+\|\s*$/.test(next)) {
      flush();
      const cells = (row) =>
        row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line).map((c) => `<th>${inlineMarkdown(c)}</th>`).join("");
      const body = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        body.push(`<tr>${cells(lines[i]).map((c) => `<td>${inlineMarkdown(c)}</td>`).join("")}</tr>`);
        i++;
      }
      i--;
      out.push(`<table><thead><tr>${head}</tr></thead><tbody>${body.join("")}</tbody></table>`);
      continue;
    }

    paragraph.push(line.trim());
  }
  flush();
  return out.join("\n");
}

/** Kernel reports ([dry-run], usage:) are literal text — the CLI agrees. */
function outputNode(text) {
  if (/^(\[dry-run\]|usage:)/.test(String(text).trim())) {
    return el("pre", { class: "plain", text });
  }
  return el("div", { class: "md", html: renderMarkdown(text) });
}

/* ───────────────────────────────────────────────────────────── console */

const consoleView = {
  root: null,
  log: null,
  textarea: null,
  suggest: null,
  matches: [],
  active: -1,
};

function buildConsole() {
  const log = el("div", { class: "console-log" }, [
    el("div", { class: "console-inner" }, [consoleHero()]),
  ]);
  const textarea = el("textarea", {
    rows: 1,
    placeholder: "/sh find files over 100MB modified this week   ·   or just ask in plain english",
    spellcheck: "false",
    autocomplete: "off",
  });
  const suggest = el("div", { class: "suggest", hidden: true });
  const composer = el("div", { class: "composer-wrap" }, [
    el("div", { class: "composer-inner" }, [
      suggest,
      el("div", { class: "composer" }, [
        el("span", { class: "composer-caret", text: "▸" }),
        textarea,
        el("button", { class: "btn btn--primary", dataset: { action: "submit" } }, [
          icon("i-play", "ic ic--fill"), "Run",
        ]),
      ]),
      el("div", { class: "composer-hint" }, [
        el("span", { text: "⏎ run · ⇧⏎ newline · / commands · ↑ history" }),
        el("span", { class: "spacer" }),
        el("span", { class: "mono", dataset: { bind: "composer-model" } }),
      ]),
    ]),
  ]);

  textarea.addEventListener("input", onComposerInput);
  textarea.addEventListener("keydown", onComposerKey);

  consoleView.log = log;
  consoleView.textarea = textarea;
  consoleView.suggest = suggest;
  consoleView.root = el("div", { class: "console" }, [log, composer]);
  return consoleView.root;
}

function consoleHero() {
  const picks = ["/sh", "/script", "/sys", "/explain", "/pipe", "/audit"];
  return el("div", { class: "hero" }, [
    el("div", { class: "hero-text" }, [
      el("h2", { text: "One line reaches everything" }),
      el("p", {
        text:
          "Slash commands route straight to their loop. Plain english goes through the " +
          "kernel's classifier first. The react loop touches the real machine — read-only, " +
          "gated by the engine's policy, with every tool call shown here as it happens.",
      }),
      el(
        "div",
        { class: "hero-chips" },
        picks.map((name) =>
          el("button", {
            class: "chip",
            dataset: { action: "prefill", value: name + " " },
            text: name,
          })
        )
      ),
    ]),
    mascot("mascot mascot--xs"),
  ]);
}

function onComposerInput() {
  const textarea = consoleView.textarea;
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 180) + "px";
  updateSuggestions();
}

function updateSuggestions() {
  const match = consoleView.textarea.value.match(/^\/(\w*)$/);
  if (!match) return hideSuggestions();
  const query = match[1].toLowerCase();
  const matches = store.commands.filter((command) => command.name.startsWith(query));
  if (!matches.length) return hideSuggestions();
  consoleView.matches = matches;
  consoleView.active = 0;
  renderSuggestions();
}

function renderSuggestions() {
  consoleView.suggest.replaceChildren(
    ...consoleView.matches.map((command, index) =>
      el(
        "div",
        {
          class: "suggest-item",
          dataset: {
            active: String(index === consoleView.active),
            action: "suggest",
            value: command.name,
          },
        },
        [
          el("span", { class: "suggest-name", text: "/" + command.name }),
          el("span", { class: "pill pill--" + command.loop, text: command.loop }),
          el("span", { class: "suggest-desc", text: command.description }),
          el("span", { class: "spacer" }),
          el("span", { class: "suggest-desc mono", text: command.argument_hint }),
        ]
      )
    )
  );
  consoleView.suggest.hidden = false;
}

function hideSuggestions() {
  consoleView.suggest.hidden = true;
  consoleView.matches = [];
  consoleView.active = -1;
}

function acceptSuggestion(name) {
  consoleView.textarea.value = `/${name} `;
  hideSuggestions();
  consoleView.textarea.focus();
}

function onComposerKey(event) {
  const open = !consoleView.suggest.hidden && consoleView.matches.length > 0;
  if (open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    consoleView.active =
      (consoleView.active + step + consoleView.matches.length) % consoleView.matches.length;
    renderSuggestions();
    return;
  }
  if (open && (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey))) {
    event.preventDefault();
    acceptSuggestion(consoleView.matches[consoleView.active].name);
    return;
  }
  if (event.key === "Escape") return hideSuggestions();
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    void submitLine();
    return;
  }
  if (event.key === "ArrowUp" && !consoleView.textarea.value.trim() && store.history.length) {
    event.preventDefault();
    store.historyAt = Math.min(store.historyAt + 1, store.history.length - 1);
    consoleView.textarea.value = store.history[store.historyAt];
    onComposerInput();
  }
}

function prefill(value) {
  navigate("console", null, "focus");
  consoleView.textarea.value = value;
  onComposerInput();
  consoleView.textarea.focus();
}

async function submitLine() {
  const line = consoleView.textarea.value.trim();
  if (!line) return;
  consoleView.textarea.value = "";
  onComposerInput();
  hideSuggestions();
  store.history.unshift(line);
  store.historyAt = -1;
  await startRun(line);
}

async function startRun(line) {
  if (!consoleView.root) buildConsole();
  const hero = $(".hero", consoleView.log);
  if (hero) hero.remove();
  const card = runCard(line);
  $(".console-inner", consoleView.log).append(card.node);
  scrollLog();
  let summary;
  try {
    summary = await api("/api/runs", {
      method: "POST",
      body: { input: line, dry_run: store.prefs.dryRun, model: store.prefs.model || undefined },
    });
  } catch (error) {
    card.fail(String(error.message || error));
    return;
  }
  card.node.dataset.run = summary.id;
  streamRun(summary.id, (kind, payload) => card.handle(kind, payload));
}

function runCard(input) {
  const activity = el("div", { class: "activity" });
  const body = el("div", { class: "run-body" }, [
    el("div", { class: "thinking" }, [
      el("span", { class: "dots" }, [el("i"), el("i"), el("i")]),
      el("span", { text: "routing through the kernel…" }),
    ]),
  ]);
  const status = el("span", { class: "pill pill--running", text: "running" });
  const meta = el("span", { class: "run-meta" });
  const node = el("div", { class: "run" }, [
    el("div", { class: "run-head" }, [
      el("span", { class: "run-input" }, [el("span", { class: "caret", text: "▸" }), input]),
      el("span", { class: "spacer" }),
      meta,
      status,
    ]),
    activity,
    body,
  ]);

  const push = (kind, text) =>
    activity.append(
      el("div", { class: "event", dataset: { kind } }, [
        el("span", { class: "event-dot" }),
        el("span", { class: "event-text", text }),
        el("span", { class: "event-at", text: fmt.clock(Date.now() / 1000) }),
      ])
    );

  const card = {
    node,
    handle(kind, payload) {
      if (kind === "node" || kind === "trace" || kind === "tool") {
        push(kind, payload.text);
      } else if (kind === "output") {
        body.replaceChildren(outputNode(payload.text));
      } else if (kind === "error") {
        card.fail(payload.text);
      } else if (kind === "done") {
        status.className = "pill pill--" + (payload.status === "ok" ? "ok" : "error");
        status.textContent = payload.status;
        const bits = [
          payload.command ? "/" + payload.command : payload.route,
          payload.loop,
          fmt.duration(payload.duration),
          payload.dry_run ? "dry run" : null,
        ].filter(Boolean);
        meta.textContent = bits.join(" · ");
        void refreshRuns();
      } else if (kind === "closed" && status.textContent === "running") {
        card.fail("the event stream closed before the run finished");
      }
      scrollLog();
    },
    fail(message) {
      status.className = "pill pill--error";
      status.textContent = "error";
      body.replaceChildren(el("div", { class: "run-body--error", text: message }));
    },
  };
  return card;
}

function scrollLog() {
  if (!consoleView.log) return;
  const slack =
    consoleView.log.scrollHeight - consoleView.log.scrollTop - consoleView.log.clientHeight;
  if (slack < 240) consoleView.log.scrollTop = consoleView.log.scrollHeight;
}

/* ───────────────────────────────────────────────────────────── scenes */

function statTile(label, value, note) {
  return el("div", { class: "stat" }, [
    el("div", { class: "stat-label", text: label }),
    el("div", { class: "stat-value", text: String(value) }),
    el("div", { class: "stat-note", text: note }),
  ]);
}

function dlRows(pairs) {
  const nodes = [];
  for (const [label, value] of pairs) {
    nodes.push(el("dt", { text: label }), el("dd", { text: value }));
  }
  return nodes;
}

function masthead(state) {
  return el("div", { class: "masthead" }, [
    el("div", {}, [
      el("h1", {}, [
        "Every capability, ",
        el("span", { class: "mark", text: "one line" }),
        " away.",
      ]),
      el("p", {
        text:
          "Slash commands route through a LangGraph kernel onto the OpenCode engine, on your " +
          "Claude Code login. This window is a view of that runtime: your terminal runs the " +
          "same kernel, and nothing here widens what it can touch.",
      }),
      el("div", { class: "masthead-actions" }, [
        el("button", { class: "btn btn--primary", dataset: { action: "scene:console" } }, [
          icon("i-play", "ic ic--fill"), "Open console",
        ]),
        el("button", { class: "btn", dataset: { action: "scene:commands" } }, ["Browse commands"]),
        el("span", { class: "pill", text: state.backend || "…" }),
        el("span", { class: "pill", text: store.prefs.model || state.model || "" }),
      ]),
    ]),
    mascot(),
  ]);
}

function sceneOverview() {
  const state = store.state || {};
  const runs = state.runs || {};
  const wrap = el("div", { class: "wrap" });
  wrap.append(
    masthead(state),
    el("div", { class: "grid grid--stats" }, [
      statTile("Commands", (state.commands || []).length, "userland in .claude/commands"),
      statTile("Runs this session", runs.total || 0, `${runs.ok || 0} ok · ${runs.failed || 0} failed`),
      statTile("Tool calls", runs.tool_calls || 0, "engine-gated, read-only"),
      statTile("Avg duration", fmt.duration(runs.avg_duration || 0), "per completed run"),
    ]),
    el("div", { class: "section-head" }, [
      el("h2", { text: "Start a line" }),
      el("span", { class: "spacer" }),
      el("button", { class: "btn btn--sm", dataset: { action: "scene:console" } }, ["Open console"]),
    ]),
    el(
      "div",
      { class: "hero-chips" },
      (state.commands || []).slice(0, 10).map((command) =>
        el("button", {
          class: "chip",
          dataset: { action: "prefill", value: "/" + command.name + " " },
          text: "/" + command.name,
        })
      )
    ),
    el("div", { class: "section-head" }, [
      el("h2", { text: "Recent runs" }),
      el("span", { class: "spacer" }),
      el("button", { class: "btn btn--sm", dataset: { action: "scene:runs" } }, ["All runs"]),
    ]),
    runsTable(store.runs.slice(0, 6)),
    el("div", { class: "section-head" }, [el("h2", { text: "How a line travels" })]),
    flowCard(state)
  );
  return wrap;
}

function flowCard(state) {
  const rows = [
    ["terminal", "one line in — the REPL, `bashos run`, or the console in this window"],
    ["kernel", "parse → classify → dispatch, as a LangGraph state machine"],
    ["loop", "prompt · refine (draft → shellcheck → repair) · react (agent loop)"],
    ["policy", "deny-by-default tool rules, compiled into the engine's config"],
    ["engine", `opencode — agent loop, tool broker, permission gate (${state.backend || "…"})`],
  ];
  const body = el("div", { class: "flow" });
  rows.forEach(([name, description], index) => {
    body.append(
      el("div", { class: "flow-row" }, [el("b", { text: name }), el("span", { text: description })])
    );
    if (index < rows.length - 1) body.append(el("div", { class: "flow-arrow", text: "▼" }));
  });
  return el("div", { class: "card" }, [el("div", { class: "card-body" }, [body])]);
}

function runsTable(runs) {
  if (!runs.length) {
    return el("div", { class: "empty" }, [
      mascot("mascot mascot--sm"),
      el("strong", { text: "No runs yet" }),
      "Every line this window sends through the kernel is recorded here with its trace.",
    ]);
  }
  const rows = runs.map((run) =>
    el("tr", { dataset: { action: "run:" + run.id } }, [
      el("td", { class: "mono nowrap", text: fmt.clock(run.started_at) }),
      el("td", { class: "truncate mono", text: run.input }),
      el("td", {}, [run.command ? el("span", { class: "pill", text: "/" + run.command }) : "—"]),
      el("td", {}, [run.loop ? el("span", { class: "pill pill--" + run.loop, text: run.loop }) : "—"]),
      el("td", { class: "num", text: String(run.tool_calls || 0) }),
      el("td", { class: "num", text: fmt.duration(run.duration) }),
      el("td", {}, [el("span", { class: "pill pill--" + run.status, text: run.status })]),
    ])
  );
  return el("div", { class: "card" }, [
    el("table", { class: "table" }, [
      el("thead", {}, [
        el(
          "tr",
          {},
          ["time", "input", "command", "loop", "tools", "took", "status"].map((head) =>
            el("th", { text: head })
          )
        ),
      ]),
      el("tbody", {}, rows),
    ]),
  ]);
}

function sceneCommands() {
  const wrap = el("div", { class: "wrap" });
  const grid = el("div", { class: "grid grid--cards" });
  const draw = (query) => {
    const needle = query.trim().toLowerCase();
    const found = store.commands.filter(
      (command) =>
        !needle ||
        command.name.includes(needle) ||
        command.description.toLowerCase().includes(needle)
    );
    grid.replaceChildren(...found.map(commandCard));
  };
  const search = el("input", {
    class: "btn input",
    placeholder: "filter commands…",
    oninput: (event) => draw(event.target.value),
  });
  wrap.append(
    el("h1", { class: "title", text: "Commands" }),
    el("p", {
      class: "subtitle",
      text:
        "Userland is a directory of markdown. Each file is a Claude Code slash command, a " +
        "bashOS kernel program, and — once compiled — an OpenCode command. Add one by dropping " +
        "a file into .claude/commands; it appears here, with no registration and no code.",
    }),
    el("div", { class: "section-head" }, [
      el("h2", { text: `${store.commands.length} in userland` }),
      el("span", { class: "spacer" }),
      search,
    ]),
    grid
  );
  draw("");
  return wrap;
}

function commandCard(command) {
  return el("div", { class: "cmd" }, [
    el("div", { class: "cmd-top" }, [
      el("span", { class: "cmd-name", text: "/" + command.name }),
      el("span", { class: "spacer" }),
      el("span", { class: "pill pill--" + command.loop, text: command.loop }),
    ]),
    el("div", { class: "cmd-desc", text: command.description }),
    el("div", { class: "cmd-hint", text: command.argument_hint || "(no arguments)" }),
    el("div", { class: "cmd-foot" }, [
      el("span", { class: "pill", text: command.agent }),
      el("span", { class: "spacer" }),
      el(
        "button",
        {
          class: "btn btn--primary btn--sm",
          dataset: { action: "prefill", value: "/" + command.name + " " },
        },
        ["Run"]
      ),
    ]),
    el("details", {}, [
      el("summary", { text: "prompt spec" }),
      el("div", { class: "cmd-body", text: command.body || "" }),
    ]),
  ]);
}

function sceneRuns() {
  const wrap = el("div", { class: "wrap" });
  wrap.append(
    el("h1", { class: "title", text: "Runs" }),
    el("p", {
      class: "subtitle",
      text:
        "Every line this window sent through the kernel: the route it took, each node as it " +
        "completed, and every tool call the engine made. In memory, this process only — " +
        "bashOS keeps no history file.",
    }),
    runsTable(store.runs)
  );
  return wrap;
}

async function sceneRunDetail(runId) {
  const wrap = el("div", { class: "wrap" });
  let run;
  try {
    run = await api("/api/runs/" + encodeURIComponent(runId));
  } catch (error) {
    wrap.append(el("div", { class: "empty" }, [String(error.message || error)]));
    return wrap;
  }
  const events = el(
    "div",
    { class: "activity" },
    (run.events || [])
      .filter((event) => event.kind !== "output")
      .map((event) =>
        el("div", { class: "event", dataset: { kind: event.kind } }, [
          el("span", { class: "event-dot" }),
          el("span", { class: "event-text", text: event.text }),
          el("span", { class: "event-at", text: fmt.clock(event.at) }),
        ])
      )
  );
  wrap.append(
    el("div", { class: "section-head" }, [
      el("button", { class: "btn btn--sm", dataset: { action: "scene:runs" } }, ["← Runs"]),
      el("span", { class: "spacer" }),
      el("span", { class: "pill pill--" + run.status, text: run.status }),
    ]),
    el("h1", { class: "title mono", text: run.input }),
    el("div", { class: "card" }, [
      el("div", { class: "card-body" }, [
        el(
          "dl",
          { class: "dl" },
          dlRows([
            ["run id", run.id],
            ["route", run.route || "—"],
            ["command", run.command ? "/" + run.command : "—"],
            ["loop", run.loop || "—"],
            ["model", run.model],
            ["dry run", String(run.dry_run)],
            ["started", fmt.clock(run.started_at)],
            ["duration", fmt.duration(run.duration)],
            ["tool calls", String(run.tool_calls)],
          ])
        ),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [el("h2", { text: "Kernel activity" })]),
      events,
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [el("h2", { text: run.error ? "Error" : "Output" })]),
      el("div", { class: "card-body" }, [
        run.error ? el("pre", { class: "plain", text: run.error }) : outputNode(run.output || ""),
      ]),
    ])
  );
  return wrap;
}

function sceneHealth() {
  const state = store.state || {};
  const host = state.host || {};
  const wrap = el("div", { class: "wrap" });
  wrap.append(
    el("h1", { class: "title", text: "Health" }),
    el("p", {
      class: "subtitle",
      text:
        "The react loop answers questions about this machine from live probes. It runs under " +
        "the engine's deny-by-default policy: reads, searches, and an allowlist of diagnostic " +
        "commands — nothing that writes, connects out, or spawns an unbound agent.",
    }),
    el("div", { class: "grid grid--stats" }, [
      statTile("OS", host.system || "—", `${host.release || ""} ${host.machine || ""}`.trim()),
      statTile("Python", host.python || "—", "kernel runtime"),
      statTile("Shell", host.shell || "—", "host shell"),
      statTile("Backend", state.backend || "—", state.model || ""),
    ]),
    el("div", { class: "section-head" }, [el("h2", { text: "Sweeps" })]),
    el("div", { class: "grid grid--2" }, [
      sweepCard("health", "Verdict-style machine health check — a deterministic floor, then investigation."),
      sweepCard("sys", "Ask anything about this machine; answered from live read-only probes."),
      sweepCard("debug", "Diagnose a failing command or script from its error output."),
      sweepCard("dash", "Generate a labelled, self-healing tmux monitoring dashboard."),
    ]),
    el("div", { class: "section-head" }, [el("h2", { text: "What a sweep may run" })]),
    el("div", { class: "card" }, [
      el("div", { class: "card-body" }, [
        el(
          "div",
          { class: "rules" },
          (store.policy?.probes || []).map((probe) =>
            el("span", { class: "rule rule--allow", text: probe })
          )
        ),
        el("p", {
          class: "card-sub mt",
          text: "Anything else that would execute is refused by the engine before it runs.",
        }),
      ]),
    ])
  );
  return wrap;
}

function sweepCard(name, description) {
  const spec = store.commands.find((command) => command.name === name);
  if (!spec) return el("div", { class: "empty" }, [`/${name} is not in this userland`]);
  return el("div", { class: "cmd" }, [
    el("div", { class: "cmd-top" }, [
      el("span", { class: "cmd-name", text: "/" + name }),
      el("span", { class: "spacer" }),
      el("span", { class: "pill pill--" + spec.loop, text: spec.loop }),
    ]),
    el("div", { class: "cmd-desc", text: description }),
    el("div", { class: "cmd-foot" }, [
      el("span", { class: "pill", text: spec.agent }),
      el("span", { class: "spacer" }),
      el(
        "button",
        {
          class: "btn btn--primary btn--sm",
          dataset: {
            action: spec.requires_args ? "prefill" : "run",
            value: "/" + name + (spec.requires_args ? " " : ""),
          },
        },
        [spec.requires_args ? "Compose" : "Run sweep"]
      ),
    ]),
  ]);
}

function sceneEngine() {
  const wrap = el("div", { class: "wrap" });
  wrap.append(
    el("h1", { class: "title", text: "Engine" }),
    el("p", {
      class: "subtitle",
      text:
        "bashOS implements no reasoning loop. OpenCode owns the agent loop, the tool broker, " +
        "sessions and the permission gate; bashOS owns userland, routing, policy and the terminal.",
    }),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Diagnostics" }),
        el("span", { class: "spacer" }),
        el("span", { class: "card-sub", text: "bashos doctor — offline by design" }),
        el("button", { class: "btn btn--sm", dataset: { action: "doctor" } }, [
          icon("i-refresh"), "Re-check",
        ]),
      ]),
      el("div", { dataset: { bind: "doctor" } }, [doctorTable(store.doctor)]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Live engine" }),
        el("span", { class: "spacer" }),
        el("span", { class: "card-sub", text: "bashos opencode status" }),
      ]),
      el("div", { class: "card-body" }, [
        el("p", {
          class: "card-sub",
          text:
            "Booting starts (or attaches to) a local opencode server and installs your Claude " +
            "Code credential into its environment — never onto disk.",
        }),
        el(
          "button",
          { class: "btn btn--primary mt", dataset: { action: "engine-status" } },
          [icon("i-bolt", "ic ic--fill"), "Boot engine & report"]
        ),
        el("div", { class: "mt", dataset: { bind: "engine-rows" } }),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Tool policy" }),
        el("span", { class: "spacer" }),
        el("span", { class: "card-sub", text: "src/bashos/opencode/policy.py" }),
      ]),
      el("div", { class: "card-body" }, [
        el(
          "div",
          { class: "rules" },
          (store.policy?.rules || []).map((rule) =>
            el("span", {
              class: "rule rule--" + (rule.action === "allow" ? "allow" : "deny"),
              text: `${rule.key}=${rule.action}`,
            })
          )
        ),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: store.policy?.config_file || "opencode.jsonc" }),
        el("span", { class: "spacer" }),
        el("span", {
          class: "pill pill--" + (store.policy?.in_sync ? "ok" : "running"),
          text: store.policy?.in_sync ? "in sync" : "stale — regenerated on next run",
        }),
      ]),
      el("div", { class: "card-body" }, [
        el("details", {}, [
          el("summary", { text: "generated engine config" }),
          el("pre", { class: "plain plain--tall", text: store.policy?.config_text || "" }),
        ]),
      ]),
    ])
  );
  return wrap;
}

function doctorTable(checks) {
  if (!checks) {
    return el("div", { class: "card-body" }, [el("span", { class: "card-sub", text: "checking…" })]);
  }
  return el("table", { class: "table" }, [
    el(
      "tbody",
      {},
      checks.map((check) =>
        el("tr", {}, [
          el("td", { class: "col-mark" }, [
            el("span", {
              class: "pill pill--" + (check.ok ? "ok" : "running"),
              text: check.ok ? "ok" : "check",
            }),
          ]),
          el("td", { class: "col-label", text: check.label }),
          el("td", { class: "mono", text: check.detail }),
        ])
      )
    ),
  ]);
}

function sceneSettings() {
  const state = store.state || {};
  const wrap = el("div", { class: "wrap" });
  const modelInput = el("input", {
    class: "btn input",
    value: store.prefs.model || state.model || "",
    oninput: (event) => {
      store.prefs.model = event.target.value.trim();
      savePrefs();
      paintChrome();
    },
  });
  wrap.append(
    el("h1", { class: "title", text: "Settings" }),
    el("p", {
      class: "subtitle",
      text:
        "Preferences for this window. The defaults come from the environment the way the CLI " +
        "reads them — BASHOS_MODEL, BASHOS_BACKEND, .env.",
    }),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [el("h2", { text: "Runs" })]),
      el("div", { class: "card-body" }, [
        el("dl", { class: "dl" }, [
          el("dt", { text: "model" }),
          el("dd", {}, [modelInput]),
          el("dt", { text: "dry run" }),
          el("dd", {}, [
            el("label", { class: "switch" }, [
              el("input", {
                type: "checkbox",
                checked: store.prefs.dryRun,
                onchange: (event) => {
                  store.prefs.dryRun = event.target.checked;
                  savePrefs();
                  paintChrome();
                },
              }),
              el("span", { class: "switch-track" }, [el("span", { class: "switch-thumb" })]),
              el("span", {
                class: "switch-label",
                text: "route and render the prompt; never call a model",
              }),
            ]),
          ]),
        ]),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Workspace" }),
        el("span", { class: "spacer" }),
        el("span", { class: "card-sub", text: "docs/frontend/SPEC-os-shell.md" }),
      ]),
      el("div", { class: "card-body" }, [
        el("div", { class: "seg" }, EXPERIENCES.map((mode) =>
          el("button", {
            class: "seg-btn",
            dataset: { action: "experience", value: mode.id, active: String(store.shell.experience === mode.id) },
          }, [el("strong", { text: mode.label }), el("small", { text: mode.hint })])
        )),
        el("p", {
          class: "card-sub mt",
          text:
            "Side by side opens a second pane of any other scene; the Console keeps its " +
            "own DOM and its event stream, so it is never mounted twice. Narrow windows " +
            "fall back to a single scene whatever is set here.",
        }),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [el("h2", { text: "About this runtime" })]),
      el("div", { class: "card-body" }, [
        el(
          "dl",
          { class: "dl" },
          dlRows([
            ["version", state.version || "—"],
            ["root", state.root || "—"],
            ["backend", state.backend || "—"],
            ["default model", state.model || "—"],
            ["max output tokens", String(state.config?.max_output_tokens ?? "—")],
            ["react max turns", String(state.config?.react_max_turns ?? "—")],
            ["refine max iters", String(state.config?.refine_max_iters ?? "—")],
            ["window uptime", fmt.duration(state.uptime || 0)],
          ])
        ),
      ]),
    ]),
    el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [el("h2", { text: "The terminal is still the core" })]),
      el("div", { class: "card-body" }, [
        el("p", {
          class: "card-sub",
          text:
            "This window runs kernel lines and nothing else. Shell passthrough (!) stays in " +
            "your terminal, where it is your own shell by your own keystroke.",
        }),
        el("div", { class: "code mt" }, [
          el("div", { class: "code-head" }, [
            el("span", { text: "shell" }),
            el("span", { class: "spacer" }),
            el("button", { class: "btn btn--ghost btn--sm", dataset: { action: "copy" } }, ["copy"]),
          ]),
          el("pre", {}, [
            el("code", {
              text:
                "bashos            # the REPL\n" +
                "bashos run /sh …  # one-shot\n" +
                "bashos gui        # this window\n" +
                "bashos doctor     # auth + environment",
            }),
          ]),
        ]),
      ]),
    ])
  );
  return wrap;
}

/* ─────────────────────────────────────────────────────────────── chrome */

function paintNav() {
  const nav = bind("nav");
  nav.replaceChildren();
  let group = null;
  for (const scene of SCENES) {
    if (scene.group !== group) {
      group = scene.group;
      nav.append(el("div", { class: "nav-label", text: group }));
    }
    const open = store.shell.windows.filter((w) => w.sceneId === scene.id);
    const isFocused = shell.focused(store.shell).sceneId === scene.id;
    const item = el(
      "button",
      {
        class: "nav-item",
        dataset: { action: "scene:" + scene.id, open: String(open.length > 0) },
        "aria-current": String(isFocused),
        title: open.length ? "open — right-click for pane actions" : scene.label,
      },
      [icon(scene.icon), el("span", { text: scene.label })]
    );
    if (scene.id === "commands" && store.commands.length) {
      item.append(el("span", { class: "nav-count", text: String(store.commands.length) }));
    }
    if (scene.id === "runs" && store.runs.length) {
      item.append(el("span", { class: "nav-count", text: String(store.runs.length) }));
    }
    nav.append(item);
  }
}

function paintChrome() {
  const state = store.state || {};
  bind("backend").textContent = state.backend || "…";
  bind("model").textContent = store.prefs.model || state.model || "";
  const root = bind("root");
  root.textContent = state.root || "";
  root.title = state.root || "";
  bind("dry-run").checked = store.prefs.dryRun;
  bind("engine-dot").dataset.state = state.backend === "opencode" ? "ok" : "warn";
  const composerModel = bind("composer-model");
  if (composerModel) {
    composerModel.textContent =
      (store.prefs.model || state.model || "") + (store.prefs.dryRun ? " · dry run" : "");
  }
  const version = bind("brand-version");
  if (version) version.textContent = state.version ? "v" + state.version : "";
  const mac = (navigator.platform || "").toLowerCase().includes("mac");
  bind("palette-key").textContent = mac ? "⌘K" : "^K";
}

/* The shell — experience modes over the same scene builders.
 * docs/frontend/SPEC-os-shell.md: `replace` is what #20 always did; `new`,
 * `focus` and `sideBySide` are the intents this adds, each with a consumer. */

let hashLock = false;

function viewportWidth() {
  return window.innerWidth || document.documentElement.clientWidth || 1200;
}

function sceneLabel(win) {
  const scene = SCENES.find((entry) => entry.id === win.sceneId);
  if (win.resourceId) return "Run";
  return scene ? scene.label : "Overview";
}

/** Build the DOM for one window. Console hands back its persistent node. */
function buildSceneNode(win) {
  if (win.sceneId === "console") return consoleView.root || buildConsole();
  if (win.resourceId) {
    const host = el("div", { class: "wrap" }, [
      el("div", { class: "empty", text: "loading run…" }),
    ]);
    sceneRunDetail(win.resourceId).then((node) => host.replaceChildren(...node.childNodes));
    return host;
  }
  const builders = {
    overview: sceneOverview,
    commands: sceneCommands,
    runs: sceneRuns,
    health: sceneHealth,
    engine: sceneEngine,
    settings: sceneSettings,
  };
  return (builders[win.sceneId] || sceneOverview)();
}

function paneActions(win, state) {
  const many = state.windows.length > 1;
  const actions = [
    el("button", {
      class: "pane-btn",
      title: "Open a scene beside this one",
      dataset: { action: "pane-split", win: win.id },
    }, [icon("i-columns", "ic ic--sm")]),
  ];
  if (many) {
    actions.push(
      el("button", {
        class: "pane-btn",
        title: win.expanded ? "Restore" : "Maximize",
        dataset: { action: "pane-expand", win: win.id },
      }, [icon(win.expanded ? "i-restore" : "i-maximize", "ic ic--sm")]),
      el("button", {
        class: "pane-btn",
        title: "Close pane",
        dataset: { action: "pane-close", win: win.id },
      }, [icon("i-x", "ic ic--sm")])
    );
  }
  return actions;
}

function paneNode(win, state) {
  const body = el("div", { class: "pane-body" }, [buildSceneNode(win)]);
  if (win.sceneId === "console" && !win.resourceId) body.classList.add("pane-body--flush");
  return el(
    "section",
    {
      class: "pane",
      dataset: {
        pane: win.id,
        scene: win.sceneId,
        focus: String(win.id === state.focusId),
        expanded: String(Boolean(win.expanded)),
      },
    },
    [
      el("header", { class: "pane-head", dataset: { action: "pane-focus", win: win.id } }, [
        icon(SCENES.find((s) => s.id === win.sceneId)?.icon || "i-grid", "ic ic--sm"),
        el("span", { class: "pane-title", text: sceneLabel(win) }),
        win.resourceId ? el("span", { class: "pane-resource mono", text: win.resourceId }) : null,
        el("span", { class: "spacer" }),
        ...paneActions(win, state),
      ]),
      body,
    ]
  );
}

function render() {
  const state = store.shell;
  const mode = shell.effectiveExperience(state, viewportWidth());
  const win = shell.focused(state);
  const container = bind("scene");

  document.documentElement.dataset.experience = mode;
  store.scene = win.resourceId ? "run" : win.sceneId;
  bind("crumb").textContent = sceneLabel(win);
  paintNav();

  const tiling = mode === "tiling" && state.windows.length > 1;
  container.classList.toggle("scene--panes", tiling);
  if (tiling) {
    container.classList.remove("scene--flush");
    const grid = el("div", { class: "panes" }, state.windows.map((w) => paneNode(w, state)));
    grid.dataset.expanded = String(state.windows.some((w) => w.expanded));
    container.replaceChildren(grid);
  } else {
    container.classList.toggle("scene--flush", win.sceneId === "console" && !win.resourceId);
    container.replaceChildren(buildSceneNode(win));
    container.scrollTop = 0;
    if (win.sceneId === "console") setTimeout(() => consoleView.textarea.focus(), 0);
  }
  if (state.windows.some((w) => w.sceneId === "engine") && !store.doctor) void loadDoctor();
}

function dispatch(action) {
  const next = shell.reduce(store.shell, action);
  if (next === store.shell) return;
  store.shell = next;
  if (next.experience !== store.prefs.experience) {
    store.prefs.experience = next.experience;
    savePrefs();
  }
  render();
  syncHash();
}

function syncHash() {
  const hash = shell.hashFor(shell.focused(store.shell));
  if (location.hash !== hash) {
    hashLock = true;
    location.hash = hash;
  }
}

/** Legacy shape kept: navigate("run", id) still means the run detail. */
function navigate(id, param, intent = "replace") {
  const sceneId = id === "run" ? "runs" : id;
  const resourceId = id === "run" ? param : param || null;
  dispatch({ type: "navigate", sceneId, resourceId, intent });
}

function showScene(id, param) {
  navigate(id, param);
}

function fromHash() {
  if (hashLock) {
    hashLock = false;
    return;
  }
  const raw = location.hash.replace(/^#\/?/, "");
  const [head, tail] = raw.split("/");
  if (head === "runs" && tail) return navigate("run", tail);
  const scene = SCENES.find((entry) => entry.id === head);
  navigate(scene ? scene.id : "overview");
}

/* ─────────────────────────────────────────────────────── context menus */

function closeMenu() {
  const layer = bind("menu-layer");
  layer.replaceChildren();
  layer.hidden = true;
}

function openMenu(x, y, items) {
  const layer = bind("menu-layer");
  const menu = el(
    "div",
    { class: "menu", role: "menu" },
    items.map((item) =>
      el("button", {
        class: "menu-item",
        role: "menuitem",
        text: item.label,
        onclick: () => {
          closeMenu();
          item.run();
        },
      })
    )
  );
  layer.replaceChildren(menu);
  layer.hidden = false;
  // CSSOM, not a style attribute: the CSP forbids the latter
  const width = 232;
  menu.style.left = Math.min(x, viewportWidth() - width - 8) + "px";
  menu.style.top = Math.min(y, window.innerHeight - 8 - items.length * 34) + "px";
}

function targetUrl(sceneId, resourceId, { token = false } = {}) {
  const hash = shell.hashFor({ sceneId, resourceId });
  const base = location.origin + location.pathname;
  return token ? `${base}?k=${encodeURIComponent(store.token)}${hash}` : base + hash;
}

/** The actions PostHog offers on a window, on our scenes. */
function targetMenu(sceneId, resourceId = null) {
  return [
    { label: "Open", run: () => navigate(sceneId, resourceId) },
    {
      label: "Open side by side",
      run: () => navigate(sceneId, resourceId, "sideBySide"),
    },
    {
      label: "Open in new browser tab",
      // the token is per process, and a new tab has no sessionStorage of ours
      run: () => window.open(targetUrl(sceneId, resourceId, { token: true }), "_blank"),
    },
    {
      label: "Copy link",
      run: () =>
        navigator.clipboard.writeText(targetUrl(sceneId, resourceId)).then(
          () => toast("link copied — without the token"),
          () => toast("copy blocked by the browser")
        ),
    },
  ];
}

function splitMenu(winId) {
  const state = store.shell;
  const open = new Set(state.windows.map((w) => w.sceneId));
  return SCENES.filter((scene) => !open.has(scene.id)).map((scene) => ({
    label: `Side by side: ${scene.label}`,
    run: () => {
      dispatch({ type: "focus", id: winId });
      navigate(scene.id, null, "sideBySide");
    },
  }));
}

/* ─────────────────────────────────────────────────────────────  palette */

const palette = { open: false, items: [], filtered: [], active: 0 };

function paletteItems() {
  const items = SCENES.map((scene) => ({
    label: scene.label,
    hint: "scene",
    run: () => navigate(scene.id),
  }));
  for (const command of store.commands) {
    items.push({
      label: "/" + command.name,
      hint: command.description,
      badge: command.loop,
      run: () => prefill("/" + command.name + " "),
    });
  }
  for (const scene of SCENES) {
    items.push({
      label: `Side by side: ${scene.label}`,
      hint: "open beside the focused scene",
      run: () => navigate(scene.id, null, "sideBySide"),
    });
  }
  if (store.shell.windows.length > 1) {
    items.push({
      label: "Close focused pane",
      hint: "workspace",
      run: () => dispatch({ type: "close", id: store.shell.focusId }),
    });
    items.push({ label: "Cycle panes", hint: "workspace", run: () => dispatch({ type: "cycle" }) });
  }
  for (const mode of EXPERIENCES) {
    items.push({
      label: `Experience: ${mode.label}`,
      hint: mode.hint,
      run: () => dispatch({ type: "experience", experience: mode.id }),
    });
  }
  items.push({ label: "Toggle theme", hint: "appearance", run: toggleTheme });
  items.push({
    label: "Toggle dry run",
    hint: "runs",
    run: () => {
      store.prefs.dryRun = !store.prefs.dryRun;
      savePrefs();
      paintChrome();
      toast(`dry run ${store.prefs.dryRun ? "on" : "off"}`);
    },
  });
  return items;
}

function openPalette() {
  palette.open = true;
  palette.items = paletteItems();
  palette.active = 0;
  bind("palette-overlay").hidden = false;
  const input = bind("palette-query");
  input.value = "";
  renderPalette("");
  input.focus();
}

function closePalette() {
  palette.open = false;
  bind("palette-overlay").hidden = true;
}

function renderPalette(query) {
  const needle = query.trim().toLowerCase();
  const found = palette.items.filter(
    (item) =>
      !needle ||
      item.label.toLowerCase().includes(needle) ||
      (item.hint || "").toLowerCase().includes(needle)
  );
  palette.filtered = found;
  palette.active = Math.min(palette.active, Math.max(found.length - 1, 0));
  bind("palette-list").replaceChildren(
    ...found.slice(0, 40).map((item, index) =>
      el(
        "div",
        {
          class: "palette-item",
          dataset: { active: String(index === palette.active), palette: String(index) },
        },
        [
          el("span", { class: "mono", text: item.label }),
          item.badge ? el("span", { class: "pill pill--" + item.badge, text: item.badge }) : null,
          el("span", { class: "spacer" }),
          el("small", { text: item.hint || "" }),
        ]
      )
    )
  );
}

/* ───────────────────────────────────────────────────────── preferences */

function loadPrefs() {
  try {
    Object.assign(store.prefs, JSON.parse(localStorage.getItem(PREFS_KEY) || "{}"));
  } catch (_) {}
}

function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(store.prefs));
  } catch (_) {}
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch (_) {}
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

/* ──────────────────────────────────────────────────────────── loading */

async function refreshState() {
  store.state = await api("/api/state");
  store.commands = store.state.commands || [];
  paintChrome();
  paintNav();
}

async function refreshRuns() {
  try {
    store.runs = await api("/api/runs?limit=100");
    const state = await api("/api/state");
    if (store.state) store.state.runs = state.runs;
  } catch (_) {
    return;
  }
  paintNav();
  const showsRuns = store.shell.windows.some(
    (w) => !w.resourceId && (w.sceneId === "runs" || w.sceneId === "overview")
  );
  if (showsRuns) render();
}

async function loadDoctor() {
  try {
    store.doctor = await api("/api/doctor");
  } catch (error) {
    store.doctor = [{ label: "doctor", ok: false, detail: String(error.message || error) }];
  }
  const slot = bind("doctor");
  if (slot) slot.replaceChildren(doctorTable(store.doctor));
}

async function loadPolicy() {
  try {
    store.policy = await api("/api/policy");
  } catch (_) {}
}

async function bootEngine(button) {
  const slot = bind("engine-rows");
  button.disabled = true;
  const label = button.textContent;
  button.textContent = "booting…";
  try {
    const result = await api("/api/engine/status", { method: "POST" });
    slot.replaceChildren(
      result.ok
        ? el("dl", { class: "dl" }, dlRows(result.rows.map(([key, value]) => [key, value])))
        : el("pre", { class: "plain", text: result.error })
    );
  } catch (error) {
    slot.replaceChildren(el("pre", { class: "plain", text: String(error.message || error) }));
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

/* ───────────────────────────────────────────────────────────── events */

document.addEventListener("click", (event) => {
  const paletteRow = event.target.closest("[data-palette]");
  if (paletteRow) {
    const item = palette.filtered[Number(paletteRow.dataset.palette)];
    closePalette();
    if (item) item.run();
    return;
  }
  if (palette.open && !event.target.closest(".palette")) closePalette();
  if (!event.target.closest(".menu")) closeMenu();

  const node = event.target.closest("[data-action]");
  if (!node) {
    // clicking into a pane focuses it — but never steal a click from a control
    const pane = event.target.closest(".pane");
    if (pane && pane.dataset.pane !== store.shell.focusId) {
      dispatch({ type: "focus", id: pane.dataset.pane });
    }
    return;
  }
  const action = node.dataset.action;

  if (action === "pane-focus") return dispatch({ type: "focus", id: node.dataset.win });
  if (action === "pane-close") return dispatch({ type: "close", id: node.dataset.win });
  if (action === "pane-expand") {
    const win = store.shell.windows.find((w) => w.id === node.dataset.win);
    return dispatch({ type: "expand", id: node.dataset.win, expanded: !win?.expanded });
  }
  if (action === "pane-split") {
    const box = node.getBoundingClientRect();
    return openMenu(box.left, box.bottom + 6, splitMenu(node.dataset.win));
  }
  if (action === "experience") {
    return dispatch({ type: "experience", experience: node.dataset.value });
  }

  if (action === "theme") return toggleTheme();
  if (action === "palette") return openPalette();
  if (action === "submit") return void submitLine();
  if (action === "doctor") {
    store.doctor = null;
    return void loadDoctor();
  }
  if (action === "engine-status") return void bootEngine(node);
  if (action === "prefill") return prefill(node.dataset.value);
  if (action === "suggest") return acceptSuggestion(node.dataset.value);
  if (action === "run") {
    navigate("console", null, "focus");
    return void startRun(node.dataset.value.trim());
  }
  if (action === "copy") {
    const code = node.closest(".code")?.querySelector("code");
    if (code) {
      navigator.clipboard.writeText(code.textContent).then(
        () => toast("copied"),
        () => toast("copy blocked by the browser")
      );
    }
    return;
  }
  if (action.startsWith("scene:")) return navigate(action.slice(6));
  if (action.startsWith("run:")) return navigate("run", action.slice(4));
});

document.addEventListener("keydown", (event) => {
  const mod = event.metaKey || event.ctrlKey;
  if (mod && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (palette.open) closePalette();
    else openPalette();
    return;
  }
  if (mod && event.key === "\\") {
    event.preventDefault();
    return dispatch({ type: "cycle" });
  }
  if (mod && event.key.toLowerCase() === "w" && store.shell.windows.length > 1) {
    // browsers reserve ⌘W for the tab; it lands in the native window
    event.preventDefault();
    return dispatch({ type: "close", id: store.shell.focusId });
  }
  if (event.key === "Escape" && !bind("menu-layer").hidden) return closeMenu();
  if (!palette.open) return;
  if (event.key === "Escape") return closePalette();
  const found = palette.filtered;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    palette.active = (palette.active + step + found.length) % Math.max(found.length, 1);
    renderPalette(bind("palette-query").value);
  } else if (event.key === "Enter") {
    event.preventDefault();
    const item = found[palette.active];
    closePalette();
    if (item) item.run();
  }
});

document.addEventListener("input", (event) => {
  if (event.target === bind("palette-query")) renderPalette(event.target.value);
  if (event.target === bind("dry-run")) {
    store.prefs.dryRun = event.target.checked;
    savePrefs();
    paintChrome();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const project = event.target.closest(".project");
  if (project) {
    event.preventDefault();
    navigate("engine");
  }
});

document.addEventListener("contextmenu", (event) => {
  const hit = event.target.closest("[data-action]");
  if (!hit) return;
  const action = hit.dataset.action || "";
  let target = null;
  if (action.startsWith("scene:")) target = { sceneId: action.slice(6), resourceId: null };
  else if (action.startsWith("run:")) target = { sceneId: "runs", resourceId: action.slice(4) };
  else if (action === "pane-focus") {
    const win = store.shell.windows.find((w) => w.id === hit.dataset.win);
    if (win) target = { sceneId: win.sceneId, resourceId: win.resourceId };
  } else if (action === "prefill" && hit.dataset.value) {
    target = { sceneId: "console", resourceId: null };
  }
  if (!target) return;
  event.preventDefault();
  openMenu(event.clientX, event.clientY, targetMenu(target.sceneId, target.resourceId));
});

window.addEventListener("hashchange", fromHash);

let narrow = viewportWidth() < shell.NARROW_WIDTH;
window.addEventListener("resize", () => {
  const isNarrow = viewportWidth() < shell.NARROW_WIDTH;
  if (isNarrow !== narrow) {
    narrow = isNarrow;
    render();
  }
});

/* ──────────────────────────────────────────────────────────────── boot */

function lockedScreen(message) {
  document.body.replaceChildren(
    el("div", { class: "locked" }, [
      el("div", { class: "card" }, [
        el("h1", { class: "title", text: "bashOS desktop is locked" }),
        el("p", { class: "subtitle", text: message }),
        el("pre", { class: "plain", text: "bashos gui" }),
      ]),
    ])
  );
}

async function boot() {
  try {
    applyTheme(localStorage.getItem(THEME_KEY) || "light");
  } catch (_) {
    applyTheme("light");
  }
  loadPrefs();
  store.token = readToken();
  if (!store.token) {
    return lockedScreen(
      "This page needs the one-time token bashOS printed when it started. Open the URL from " +
        "your terminal, or start the desktop again."
    );
  }
  try {
    await refreshState();
  } catch (error) {
    return lockedScreen(String(error.message || error));
  }
  buildConsole();
  await Promise.all([loadPolicy(), refreshRuns()]);
  paintChrome();
  if (store.prefs.experience && store.prefs.experience !== store.shell.experience) {
    store.shell = shell.reduce(store.shell, {
      type: "experience",
      experience: store.prefs.experience,
    });
  }
  fromHash();
  render();
}

boot();
