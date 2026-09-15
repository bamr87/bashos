# PostHog.com OS-Style Desktop Frontend — Research Brief

**Repo:** https://github.com/PostHog/posthog.com (master, read via `gh` API + raw URLs; **not cloned**)  
**Primary sources:** `contents/handbook/engineering/posthog-com/technical-architecture.md`, `contents/blog/why-os.mdx`, `contents/handbook/engineering/posthog-com/how-posthog-website-works.mdx`, `agents/{apps,windows,techstack,components,styling}.md`, and key `src/` files listed below.  
**Audience:** Cloud agent drafting a PRD/spec/roadmap for **bashOS** L6 OS-style frontend.  
**Date researched:** 2026-09-15

---

## 1. Product intent (why an OS UI)

From Cory Watilo’s post [*Why our website looks like an operating system*](https://posthog.com/blog/why-os) (`contents/blog/why-os.mdx`, 2025-09-10):

| Problem with typical marketing/docs sites | OS-UI answer |
|---|---|
| Tab explosion (`CMD`+click → many identical-favicon tabs) as product surface grows | Multi-window desktop: keep several pages open, arrange, snap |
| Long-scroll landing pages, oversized footers, wasteful whitespace | Information-dense “apps” (Notion/research-paper density, not landing-page fluff) |
| Content hard to multitask across | Window snapping, keyboard shortcuts, bookmark app, shareable desktop layouts |
| Brand blandness | Nostalgic OS metaphors (explorer, PPT-like decks, Outlook forums, QuickTime, screensaver, wallpapers) |

**Positioning quotes (paraphrased):** the site should feel jarring at first, then indispensable; prototype in production TypeScript/Tailwind rather than mockups-first; treat the visual layer as separable from content (JSON-driven product data).

**Brand fit:** PostHog’s handbook/brand voice favors distinctive, nostalgic, non-corporate UX. The OS shell is a brand system *and* an information architecture, not a gimmick alone.

**Implication for bashOS:** An OS shell for an agent runtime should solve a real multitasking / context problem (many agents, terminals, docs, tools) — not decorate a single linear page. Nostalgia is optional; **windowed multitasking + dense apps + keyboard-first** are the transferable product bets.

---

## 2. Architecture map

### 2.1 High-level stack

| Layer | Choice |
|---|---|
| Framework | **Gatsby 4** (static site + `wrapPageElement` / `wrapRootElement`) |
| UI | **React 18**, **Tailwind CSS 3**, custom **OS-*** + **RadixUI** wrappers |
| Motion / window chrome | **Framer Motion** (`framer-motion` ^10) — drag controls, `AnimatePresence`, snap indicators |
| State | React Context in `src/context/App.tsx` (split contexts for perf) + Kea for some app logic |
| Content | MDX under `contents/`, product JSON hooks (`src/hooks/productData/*`, `useProduct`, `useCustomers`), Strapi for community/changelog |
| Search | Algolia → Spotlight overlay (`Cmd/Ctrl+K`, `/`) |
| Hosting | Vercel; SEO via static HTML generation |

### 2.2 Boot / wrap chain

```
gatsby-browser.tsx / gatsby-ssr.js
  wrapRootElement → ToastProvider → UserProvider → kea wrapElement
  wrapPageElement → App Provider (element, location) → Wrapper | KoreanWrapper
```

`Provider` converts the Gatsby page `element` + `location` into **windows**. `Wrapper` paints the desktop shell.

### 2.3 Shell component tree

```
AppContainer (#app-container; data-window-expanded / snapped-*)
├── TaskBarMenu          # macOS-style top menu bar (#taskbar)
├── DesktopViewport (constraintsRef)   # drag bounds
│   ├── Desktop          # wallpapers, icons, screensaver, hedgehog, confetti, notifications
│   └── WindowList       # maps windows → AppWindow (isolated subscription)
├── SearchOverlay        # Spotlight
├── ChatOverlay          # Ask Max (global overlay, not a managed window)
└── CookieBannerToast
```

**Key paths**

| Role | Path |
|---|---|
| App Provider / site + window state | `src/context/App.tsx` |
| Per-window context | `src/context/Window.tsx` |
| Desktop layout shell | `src/components/Wrapper/index.tsx` |
| Window chrome + drag/resize/snap | `src/components/AppWindow/index.tsx` |
| Desktop icons + wallpapers host | `src/components/Desktop/index.tsx` |
| Wallpaper scenes | `src/components/Desktop/Wallpapers.tsx` |
| Desktop icon cell | `src/components/Desktop/DesktopIcon.tsx` |
| Taskbar / menu bar | `src/components/TaskBarMenu/index.tsx`, `menuData.tsx`, `README.md` |
| App chrome (back/search/filters) | `src/components/OSChrome/HeaderBar.tsx`, `AddressBar.tsx` |
| Active windows panel | `src/components/ActiveWindowsPanel/index.tsx` |
| Display options “Control Panel” | `src/pages/display-options.tsx` |
| Agent-oriented docs | `agents/windows.md`, `agents/apps.md`, `agents/techstack.md` |
| Handbook architecture | `contents/handbook/engineering/posthog-com/technical-architecture.md` |
| How the site works | `contents/handbook/engineering/posthog-com/how-posthog-website-works.mdx` |

### 2.4 Context split (performance pattern)

`App.tsx` intentionally splits contexts so consumers don’t re-render on every window move:

| Context | Hook | Contents |
|---|---|---|
| Full (legacy) | `useApp()` | Everything |
| Actions (stable identity) | `useAppActions()` | open/close/snap/update setters + refs |
| Settings (rare) | `useAppSettings()` | `siteSettings`, `compact`, `isMobile`, `menu`, `posthogInstance` |
| UI flags | `useAppUIState()` | search/chat/panels/screensaver/confetti |
| Windows list | `useAppWindows()` | `windows` only |

`Wrapper` uses this: `WindowList` only subscribes to windows; Desktop uses settings/UI state.

### 2.5 Experience modes: `posthog` vs `boring`

**Documented** (technical-architecture.md):

- `siteSettings.experience = 'posthog'` → full desktop OS  
- `siteSettings.experience = 'boring'` → traditional website (mobile / explicit toggle / debug)

**Observed in master source (2026-09-15):**

- `SiteSettings` interface in `App.tsx` **does not include `experience`**.
- Only write site found: Spotlight action `boring-mode` sets `updateSiteSettings({ ...siteSettings, experience: 'boring' })` (`src/components/SpotlightSearch/actions.tsx`), with comment that boring mode “unmounts the desktop” and exit is via a “boring-mode header.”
- Full-tree scan of `src/**/*.{ts,tsx,js,jsx}` found **no reader** of `siteSettings.experience` / `'boring'` gate besides that Spotlight writer.
- Practical fallbacks that *do* exist: `isMobile` (`innerWidth < 768`), `compact` (iframe/`window !== window.parent` for embedded docs), TaskBar mobile menu truncation (`TaskBarMenu/README.md`).

**PRD note:** Treat handbook “experience modes” as **intent / incomplete or drifted**; confirm live UI. For bashOS, still recommend an explicit `experience: 'shell' | 'plain'` with a real consumer (shell unmount).

---

## 3. Window system — types, lifecycle, routing

### 3.1 `AppWindow` shape (`src/context/Window.tsx`)

```ts
interface AppWindow {
  element: React.ReactNode
  key: string
  zIndex: number
  meta?: { title: string }
  coordinates?: { x: number; y: number }
  minimized: boolean
  path: string
  fromHistory?: boolean
  props: any
  ref?: React.RefObject<HTMLDivElement>
  sizeConstraints: { min: { width; height }; max: { width; height } }
  size: { width; height }
  previousSize: { width; height }
  position: { x; y }
  previousPosition: { x; y }
  fixedSize: boolean
  fromOrigin?: { x; y }          // open animation origin (last click)
  minimal: boolean
  appSettings?: AppSetting
  location?: Location
  modal?: { type: 'standard' | 'side' | 'floating' }
  expanded: boolean              // maximized / full desktop area
  snapped: 'left' | 'right' | false
  windowed?: boolean             // centered ~85% chrome mode vs expanded
}
```

Per-window `Window` provider also exposes in-window nav: `goBack` / `goForward` / history, `menu`, `view: 'marketing' | 'developer'`, `dragControls`, `animating`.

### 3.2 `AppSetting` / `appSettings` (`App.tsx`)

```ts
interface AppSetting {
  experiment?: { variant: 'control' | 'test'; flag: string }
  size?: {
    min: { width: number; height: number }
    max: { width: number; height: number }
    fixed?: boolean
    autoHeight?: boolean
  }
  position?: {
    center?: boolean
    topCenter?: boolean
    getPositionDefaults?: (size, windows, getDesktopCenterPosition) => { x; y }
  }
  modal?: { type: 'standard' | 'side' | 'floating' }
  closeOnEscape?: boolean
  toolbar?: boolean
  hideTitle?: boolean
}
```

`appSettings` is a large route-keyed map (examples): `/`, `/products`, `/paint`, `/demo`, `/merch`, `/display-options`, `ask-max`, `search`, `community-auth-*`, pricing modal keys, `/fm`, etc. Unlisted routes fall back to ~90% viewport defaults.

### 3.3 `SiteSettings`

```ts
interface SiteSettings {
  colorMode: 'light' | 'dark' | 'system'
  theme: 'light' | 'dark'
  skinMode: 'modern' | 'classic'   // classic forced off in getInitialSiteSettings
  cursor: 'default' | 'xl' | 'james'
  wallpaper: 'keyboard-garden' | 'hogzilla' | 'startup-monopoly' | 'office-party'
  screensaverDisabled?: boolean
  reduceTransparency?: boolean
  clickBehavior?: 'single' | 'double'   // stored; AppIcon wiring not confirmed in scan
  performanceBoost?: boolean            // reduces wallpaper motion
  scrollbars?: 'system' | 'show' | 'auto'
}
```

Persisted to `localStorage.siteSettings`. Body attrs: `data-skin`, `data-wallpaper`, `data-reduce-transparency`.

### 3.4 Lifecycle

1. **SSR / first paint:** `windows = [createNewWindow(element, ...)]`  
2. **Hydrate:** `getInitialSiteSettings()`, detect `compact` / `isMobile`  
3. **Route change:** `useEffect([element])` → `updatePages(element)` unless `skipPageUpdate` or `?windows=` restore in progress  
4. **Mount chrome:** `AppWindow` wraps content in `WindowProvider` + chrome; entrance animation; optional `fromOrigin`  
5. **Interact:** drag (Framer `useDragControls`), resize handles, snap left/right, expand/windowed, minimize, focus (`bringToFront` / zIndex reshuffle)  
6. **Close:** set `closing` → exit animation → `closeWindow` filters path; navigate to next highest non-minimized or `/` with `skipPageUpdate`  
7. **Close all:** `animateClosingAllWindows` → `closeAllWindows`  

**AppWindow internal Router** (important): path can override rendered app shell:

- `/questions*` → `<Inbox />`  
- handbook/docs/manual (with post data) → `<Handbook />`  
- posts → `<BlogPost />`  
- legal paths → `<Legal />`  
- else children, optionally inside `PageModal` / `FloatingModal` if `appSettings.modal`

So “apps” are both **page templates** and **path-based routers inside the window chrome**.

### 3.5 Routing: new / focus / replace (handbook vs code)

**Handbook claims three behaviors:**

1. **New window** if `location.state.newWindow === true` or no window for path  
2. **Focus** if same path already open  
3. **Replace** focused window content on normal navigation  

**`updatePages` in current `App.tsx` (observed):**

```
existingWindow(same path)? → bringToFront (+ optional size/mode sync)
else if sideBySide?        → snap focused sibling + append new window
else if appSettings.size.fixed? → append (replacing other fixed windows)
else                       → replaceFocusedWindow(newWindow)
```

There is **no explicit `location.state.newWindow` branch** in `updatePages` on master. Yet:

- Desktop `AppLink` always passes `state: { newWindow: true }`  
- Link context menu: “Open in new PostHog window” / “side by side”  
- Agents docs instruct `navigate(path, { state: { newWindow: true } })` to avoid losing the previous window  
- `replaceFocusedWindow` **preserves non-focused windows** (only mutates highest z-index slot) — so multitasking works once multiple windows exist (side-by-side, fixed modals, `?windows=` restore, contact dual-open, etc.)

**Open question for live UI:** Does “Open in new PostHog window” currently append a second content window, or only replace the focused slot while leaving others? PRD should specify bashOS behavior explicitly (recommend: **append** when `newWindow`, **replace** when not, **focus** when path match).

**Other navigation state flags:**

| Flag | Effect |
|---|---|
| `newWindow` | Documented append; also sets `preventScroll` in `Link` |
| `sideBySide: 'left' \| 'right'` | Split focused + new |
| `skipPageUpdate` | Don’t run `updatePages` (focus/URL sync only) |
| `expanded` / `windowed` / `snapped` / `size` / `position` | Seed window geometry |
| `savedWindows` / `?windows=` | Shareable desktop layout (positions as % of viewport) |

### 3.6 Focus, snap, expand

- **Focus:** highest `zIndex`; click titlebar / taskbar entry / `Shift+>` cycle  
- **Snap:** drag near edge (`snapThreshold`) or `Shift+←/→` / `handleSnapToSide`; visual `SnapIndicator`  
- **Expand:** fills desktop under taskbar; `Shift+↑` toggles expand ↔ windowed  
- **Minimize:** `Shift+↓`; restored via taskbar / active windows  
- **windowsInView:** coverage heuristic (<80% occluded) for shareable desktop / inactivity  

### 3.7 Keyboard shortcuts (from `App.tsx` handler)

| Shortcut | Action |
|---|---|
| `/` | Open Spotlight search |
| `Cmd/Ctrl+K` | Open search |
| `?` or `Shift+/` | Open Ask Max chat |
| `,` | Open `/display-options` (newWindow) |
| `m` | Cycle color mode system → light → dark |
| `\` | Cycle wallpaper |
| `Shift+← / →` | Snap left / right |
| `Shift+↑` | Expand / unexpand to windowed |
| `Shift+↓` | Minimize focused |
| `Shift+W` | Close focused (dispatches `windowClose` event) |
| `Shift+X` | Close all (animated) |
| `Shift+Z` | Screensaver preview |
| `Shift+<` | Active windows panel |
| `Shift+>` | Cycle next window |
| `Shift+C` | Copy shareable desktop URL |

Ignored when focus is in `INPUT` / `TEXTAREA` / shadow DOM / `.mdxeditor`.

Handbook also mentions `.` for shortcuts help and `|` for wallpapers — **not found** in the current handler (drift: `\` cycles wallpaper; `m` cycles theme). Confirm live.

---

## 4. Feature inventory

### 4.1 Shell features

| Feature | Implementation notes |
|---|---|
| Taskbar / menu bar | `TaskBarMenu` + Radix MenuBar; mobile consolidates into logo menu; `menuData.tsx` |
| Desktop icons | Left product links + right “apps” (About, Changelog, Handbook, Store, Careers, Trash); glass glyphs; wallpaper-tinted glow |
| Wallpapers | Four scenes: `keyboard-garden` (default), `hogzilla`, `startup-monopoly`, `office-party`; CSS `body[data-wallpaper]` + Tailwind variant classes; `performanceBoost` reduces motion |
| Screensaver | DVD-logo-style bouncing Lottie; inactivity hook; `Shift+Z`; dismissible with toast → disable |
| Hedgehog Mode | `@posthog/hedgehog-mode`; localStorage; walks/sits on windows |
| Confetti | `react-confetti` overlay via `setConfetti` |
| Custom cursors | `default` / oversized SVG `xl` / James face PNGs |
| Spotlight search | Algolia + command actions (theme, wallpaper, boring mode, screensaver, copy desktop link, …) |
| Chat overlay | Ask Max — params in app state, not window list |
| Notifications panel | Desktop-mounted |
| Active windows panel | List + close all |
| Shareable desktop | `?windows=[{path,position%,size%,zIndex}]` |
| Display options | Theme, scrollbars, cursor, wallpaper, screensaver, hedgehog, reduce transparency, performance |
| Bookmarks | `/bookmarks` page + `BookmarkButton`; user bookmarks; Explorer chrome |
| Context menus | Desktop + Link (“new PostHog window”, side-by-side, browser tab) |

### 4.2 App templates (canonical — `agents/apps.md`)

| App | Metaphor | Example routes | Source |
|---|---|---|---|
| **Editor** | Editable document / dense page | `/about`, `/careers`, Changelog template, many marketing pages | `src/components/Editor/index.tsx` |
| **ReaderView** | 1–3 column reader (nav / main / on-page) | Docs, handbook, blog, pricing, product reader pages | `src/components/ReaderView/` |
| **Presentation** | Slide deck | `/for/[...path]` sales/persona decks; slide JSON under `src/presentations/` | `src/components/Presentation/` |
| **Explorer** | Windows File Explorer (grid/list, sidebars) | `/paint`, `/videos`, `/bookmarks`, product-analytics-explorer, merch Collection (`data-app="Explorer"`) | `src/components/Explorer/` |
| **Inbox** | Outlook Express / mail panes | `/questions*` (via AppWindow Router) | `src/components/Inbox/index.tsx` |
| **Wizard** | Stepped slides | `/vibe-check` | pages under vibe-check |
| **MediaPlayer** | QuickTime clone | `/demo`, `/videos/play`, `/spicy.mov`, changelog video | `src/components/MediaPlayer/index.tsx` |

**Shared chrome:** `HeaderBar`, `AddressBar`, `OSTable`, `OSTabs`, `OSButton`, `MDXEditor`, `OSFieldset`.

### 4.3 Blog nostalgic inventory → current source mapping

From `why-os.mdx` claims vs master (note evolution):

| Blog claim | Route(s) | Current source reality |
|---|---|---|
| Windows File Explorer + merch UI | `/products`, `/merch` | **Merch** `Collection.tsx` is Explorer-like (HeaderBar/AddressBar, `data-app="Explorer"`). **`/products`** currently renders `ProductsTest` inside **Editor**, not Explorer — explorer metaphor still used on `product-analytics-explorer` and other explorer pages |
| PowerPoint product pages | e.g. `/ai-observability` | Many product URLs now use **`ProductReaderView`**; **Presentation** / `SlidesTemplate` still used for `/for/*` and related; handbook `presentations.mdx` documents slide system |
| Document editor | `/customers` | Customers index uses **ReaderView + OSTable**; **Editor** used widely elsewhere (about, careers, changelog template) |
| Outlook Express forums | `/questions` | **Inbox** app via AppWindow Router; page stub returns `null` |
| QuickTime clone | `/demo` | **MediaPlayer** (Wistia/YouTube nocookie); `.quicktime-scrubber` CSS |
| Spreadsheet-formatted pages | `/changelog` | Changelog template wraps content in **Editor**; dense table UIs via **OSTable** (spreadsheet *feel*, not Excel engine). Icon map includes `spreadsheet` assets |
| Screensaver + wallpaper library | `/display-options` | Confirmed Screensaver + Wallpapers + Display options |
| Keyboard shortcuts | global | Confirmed in App provider |
| Bookmark app | `/bookmarks` | Explorer + user bookmarks |
| Extra nostalgia | `/paint` | **MSPaint** / HogPaint inside Explorer (`src/components/MSPaint`) |
| WordArt | components | `src/components/WordArt` |
| Hedgehog game | desktop | HedgehogMode embed |

### 4.4 Desktop icon catalogs (`Desktop/index.tsx`)

**Left (productLinks):** Home, Self-driving product, Context warehouse, Pricing, Docs, Demo, Talk to a human  

**Right (apps):** About us, Changelog, Company handbook, Store (`/merch`), Careers, Trash  

Click behavior: `AppLink` → Gatsby `Link` with `state: { newWindow: true }`.

---

## 5. Interaction model (summary for PRD)

1. **Primary navigation** = open/focus windows, not full-page remounts of the chrome.  
2. **In-window navigation** = history stack (`goBack`/`goForward`) + HeaderBar.  
3. **Cross-app links** should declare intent: replace vs new window vs side-by-side.  
4. **Keyboard-first power user** layer (search, snap, close, theme, wallpaper).  
5. **Mobile** = simplified taskbar; dense desktop metaphors degrade; (intended) boring/plain mode.  
6. **Embedded docs** (`compact`) = hide taskbar/desktop chrome; postMessage theme/nav to parent.  
7. **Personalization** = localStorage site settings, not accounts (except bookmarks/user features).  
8. **Share state** = encode window layout in URL for demos/collaboration.  
9. **Content density** = OS apps look like tools (tables, sidebars, slides), not hero landings.

---

## 6. Tech choices (detail)

| Concern | Choice | Why it matters for bashOS |
|---|---|---|
| SSG | Gatsby | SEO + first paint HTML despite client windowing |
| Window motion | Framer Motion drag controls + AnimatePresence | Polished OS feel; cost = bundle + main-thread |
| Styling | Tailwind + design tokens + `data-*` theming | Skin/wallpaper/color without CSS-in-JS explosion |
| Primitives | Radix wrappers under `components/RadixUI` | A11y menus/dialogs; OS prefix for custom |
| Search | Algolia InstantSearch + Spotlight UX | Command palette hybrid |
| Analytics | PostHog on the marketing site itself | dogfood |
| Package manager | pnpm; Node 22 | — |
| Agent docs | `agents/*.md` | They document the OS model for coding agents — mirror this for bashOS |

**SEO approach:** Pages statically generated; each route keeps normal HTML/meta/canonical; windowing is client-only. Crawlers see content without needing to understand windows. (`technical-architecture.md`)

**Framer Motion usage (AppWindow):** `useDragControls`, `AnimatePresence` for mount/unmount and snap indicator fades, `motion.div` for overlays/indicators; compositor flag (`animating || dragging || resizing || closing`) to gate expensive work; frosted surface constants (`MOTION_LAYER`, `WINDOW_BG`).

---

## 7. Implications & recommendations for bashOS L6

bashOS context: terminal-first AI runtime / agent OS with layers L1–L6; L6 is currently shell/TUI/web console. Goal: OS-style frontend without cargo-culting PostHog marketing whimsy unless it serves agent workflows.

### 7.1 Steal these patterns

1. **Single App Provider + window array** as source of truth (path, geometry, zIndex, mode).  
2. **Split contexts** (actions / settings / windows) to keep terminal/log panes from re-rendering on drag.  
3. **Route → window policies** (`appSettings`: min/max, fixed modals, center, toolbar).  
4. **Explicit navigation intents:** `replace` | `new` | `focus` | `sideBySide` (implement all four; don’t leave `new` as docs-only).  
5. **App templates** as content shells: Terminal, Editor, Inbox/Notifications, File tree, Browser/Preview, Agent transcript, Dashboard — map cleanly to L6.  
6. **HeaderBar chrome** shared across apps (back, path/address, search, actions).  
7. **Keyboard OS layer** before mouse polish.  
8. **Plain/boring mode** for accessibility, automation, screenshots, mobile.  
9. **Shareable layouts** (URL or workspace file) for reproducing multi-agent setups.  
10. **Static or SSR-friendly shell** so deep links remain crawlable/linkable if bashOS has a web surface.

### 7.2 Adapt / don’t copy blindly

| PostHog | bashOS adaptation |
|---|---|
| Nostalgic consumer OS metaphors | Prefer **IDE / tiling WM / tmux** metaphors familiar to terminal users; nostalgia optional theme pack |
| Gatsby marketing SSG | Likely Vite/Next + websocket to L1–L5 runtime; keep wrap-at-root idea |
| Algolia Spotlight | Command palette over agents, skills, files, commands |
| Merch Explorer | Workspace / artifact file explorer |
| Ask Max chat overlay | Primary agent chat dock (maybe always-on L6 pane, not only overlay) |
| Hedgehog / confetti | Skip or gate behind “fun mode” |
| Framer-heavy chrome | Consider CSS transforms + lighter drag lib if running beside heavy agent UIs |

### 7.3 Suggested bashOS L6 architecture sketch

```
L6 Shell Provider
├── MenuBar / StatusBar (host, agent count, model, cost)
├── Desktop | Tiling layout (experience: os | tiling | plain)
│   ├── App windows (Terminal, Agent, Editor, Files, Browser, Logs, Settings)
│   └── Optional wallpaper / workspace branding
├── Command Palette (Ctrl+K)
└── Global Agent Dock / Notifications
```

Map PostHog concepts → bashOS:

| PostHog | bashOS |
|---|---|
| `AppWindow` | `ShellWindow` bound to a **pane session** (PTY, agent run, file, URL) |
| `appSettings[route]` | `appSettings[appId]` + resource URI |
| `siteSettings` | `shellSettings` (theme, keymap, layout mode, density) |
| Desktop icons | Pinned agents / skills / workspaces |
| `?windows=` | Saved workspace layouts |
| Inbox | Notification / human-input queue for agents |
| Explorer | Workspace FS + artifact browser |
| MediaPlayer | Run replay / trace viewer |
| Presentation | Structured “run report” decks |
| Editor | Markdown/spec + agent-editable buffers |
| Boring mode | `plain` web console / pure TUI bridge |

### 7.4 PRD-ready requirements (draft seeds)

**Must**

- Multi-window (or multi-pane) with focus, z-order, minimize, close  
- Navigation intents: replace / new / focus-existing  
- Keyboard map documented and testable  
- App template API (chrome slots: title, toolbar, sidebar, main, status)  
- Deep-linkable URLs per window content  
- Plain mode without window chrome  

**Should**

- Snap / split layouts  
- Shareable workspace layout serialization  
- Command palette  
- Per-app min/max size policies  
- Mobile/narrow fallback  

**Could**

- Nostalgic themes, screensaver, custom cursors  
- In-window back/forward history  
- Animated open-from-icon origins  

---

## 8. Key file path checklist

```
gatsby-browser.tsx
gatsby-ssr.js
src/context/App.tsx
src/context/Window.tsx
src/components/Wrapper/index.tsx
src/components/AppContainer/index.tsx
src/components/AppWindow/index.tsx
src/components/Desktop/index.tsx
src/components/Desktop/Wallpapers.tsx
src/components/Desktop/DesktopIcon.tsx
src/components/TaskBarMenu/index.tsx
src/components/TaskBarMenu/menuData.tsx
src/components/TaskBarMenu/README.md
src/components/OSChrome/HeaderBar.tsx
src/components/OSChrome/AddressBar.tsx
src/components/ActiveWindowsPanel/index.tsx
src/components/SpotlightSearch/{index,actions,README}.tsx|md
src/components/Link/index.tsx
src/components/Explorer/index.tsx
src/components/Editor/index.tsx
src/components/ReaderView/…
src/components/Presentation/…
src/components/Inbox/index.tsx
src/components/MediaPlayer/index.tsx
src/components/MSPaint/…
src/components/Screensaver/index.tsx
src/components/OSTable/index.tsx
src/components/OSIcons/AppIcon.tsx
src/pages/display-options.tsx
src/pages/bookmarks.tsx
src/pages/demo/index.tsx
src/pages/paint/index.tsx
src/pages/products/index.tsx
src/pages/merch.tsx
src/templates/merch/Collection.tsx
src/templates/Changelog.tsx
src/hooks/useTheme.tsx
contents/blog/why-os.mdx
contents/handbook/engineering/posthog-com/technical-architecture.md
contents/handbook/engineering/posthog-com/how-posthog-website-works.mdx
agents/apps.md
agents/windows.md
agents/techstack.md
agents/components.md
agents/styling.md
package.json
```

---

## 9. Open questions / needs live UI confirmation

1. **`experience: 'boring'`** — Spotlight writes it; no consumer found in `src/`. Is it WIP, behind a branch, or handled outside scanned extensions?  
2. **`newWindow: true`** — Docs/agents say append; `updatePages` lacks an explicit branch. Verify multitasking from desktop icons vs context-menu “new window” vs side-by-side.  
3. **Product page metaphor** — Blog: PowerPoint; many product routes now `ProductReaderView`. Confirm which products still use Presentation/Slides.  
4. **`/products` Explorer** — Blog: File Explorer; code: `ProductsTest` + Editor. Confirm intended UX.  
5. **`clickBehavior` single vs double** — In `SiteSettings` + Spotlight actions; AppIcon click wiring not clearly consuming it.  
6. **Shortcut cheatsheet** — Handbook `.` and `|` vs code `m` and `\`.  
7. **Classic skin** — Type allows `skinMode: 'classic'` but `getInitialSiteSettings` forces `modern`.  
8. **Mobile UX** — Is “boring” auto-enabled under 768px, or only simplified TaskBar on desktop shell?  
9. **Performance** — Cost of many Framer windows + wallpaper scenes on low-end devices (`performanceBoost` helps).  
10. **Accessibility** — Focus traps, reduced motion, screen reader labeling of window chrome (Spotlight docs a11y; window chrome TBD live).

---

## 10. Source confidence

| Area | Confidence | Basis |
|---|---|---|
| Why OS / product intent | High | why-os.mdx |
| Shell architecture & files | High | handbook + Wrapper/Desktop/AppWindow/App.tsx |
| Types (AppWindow, SiteSettings, AppSetting) | High | Window.tsx + App.tsx |
| Keyboard map | High | App.tsx handler |
| App template inventory | High | agents/apps.md + page imports scan |
| Experience boring mode | Low–medium | Docs vs missing consumer |
| newWindow append semantics | Medium | Docs vs updatePages implementation |
| Exact Framer drag props / resize UX | Medium | AppWindow large; dragControls confirmed; live feel unchecked |
| Visual polish / animations | Low | Needs live UI |

---

## 11. Suggested next steps for bamr87/bashos PRD agent

1. Turn §7.4 into formal requirements + non-goals.  
2. Define bashOS app template IDs and which L1–L5 resources they bind.  
3. Specify window state schema (JSON) compatible with workspace save/load.  
4. Decide layout modes: floating windows vs tiling-first (tmux-like) vs hybrid.  
5. Prototype Provider + two apps (Terminal + Agent) before nostalgia themes.  
6. Optionally re-verify PostHog live site for §9 open questions and attach screenshots.

---

*End of brief. Generated from public GitHub raw/`gh` API reads only; repository was not cloned.*

---

## 12. Live UI confirmation (browser tour, 2026-09-15)

Public marketing site only; no `app.posthog.com` login.

**Confirmed**
- Desktop wallpaper + icons (Home, Self-driving, Context warehouse, Pricing, Docs, Demo, About us, Changelog, Company handbook, Store, Careers, Trash) and fixed top taskbar
- AppWindow chrome: rounded panels, scrollbars, close, maximize/restore (maximize verified)
- Standard navigation replaces the active window; blog/handbook use multi-pane layouts (index/sidebar + article + jump-to)
- `/` opens centered Spotlight/search; Escape closes
- Display Options: System/Light/Dark, scrollbars, cursors, wallpaper selector, screensaver preview, transparency, hedgehog mode
- Screensaver preview (black animated); click to exit; wallpaper can change after
- Apps seen: merch File Explorer, trash archive, docs hub, blog/handbook readers, changelog spreadsheet/timeline, product marketing carousel, presentation/slides, product detail

**Not verified live**
- Drag, resize, snap, minimize-to-taskbar (documented; not independently exercised)

**Key screenshots** (captured during the 2026-09-15 browser tour (not committed; available in research notes)): homepage OS shell, pricing, blog article, technical architecture, search modal, display options, screensaver, trash, merch store + product, docs, products, changelog spreadsheet.
