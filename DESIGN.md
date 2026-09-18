# KryptoLens design

UI work follows `docs/ui-design-skills.md` (hierarchy, proximity, 8px scale, WCAG, fewer borders).

## Scene

Night desk. Landing is a committed moss field whose hero is the product window: Ask composer plus the You asked / assumed split. The workspace is a restrained tool: roster of named teammates and one transcript. Not a neon terminal, not a magazine spread, not a generic SaaS card grid.

## Strategy

Restrained in the app. Workspace follows **Grok Bot** layout, not grok.com chat: a sidebar roster of persistent Agents | one transcript | a composer. First-run is Create Agent. A new Agent opens an empty thread — the user writes the first message. No canned greeting, no preset job chips. After a job exists, the thread is named message rows + inline CMC activity. No Chat/Routines/Jobs tabs, Watching badge, Pause, Check now, or profile menu in the chat header — those are messages. Presence sits on the Bot face and a quiet line under the name. A live CMC strip stays in the slim conversation head. One work surface per view.

## Tokens

Workspace is moss-tinted charcoal. Accent is moss; the surface is not. `body.is-app` only locks the shell (full height, no page scroll).

| Token | Value | Role |
|---|---|---|
| `--bg` | `oklch(0.11 0.008 130)` | Stage |
| `--bg-raise` | `oklch(0.135 0.010 130)` | Roster |
| `--surface` | `oklch(0.155 0.008 130)` | Thread |
| `--surface-2` | `oklch(0.19 0.010 130)` | Elevated / hover |
| `--line` | `oklch(0.28 0.014 130)` | Hairlines |
| `--primary` | `oklch(0.68 0.12 130)` | Actions, status, selection accent |
| `--accent` | `oklch(0.72 0.12 75)` | Waiting / attention |
| `--radius` | `8px` | Buttons, inputs, rows, modal |

Landing keeps the moss field. Status color is sparse: green = active/success; red = negative market move or error; yellow = waiting.

## Type

Source Sans 3 for product UI. Literata only on the landing headline. Source Code Pro for the CMC strip, counts, page ids, and API evidence.

## Motion

180ms state changes. Reduced-motion disables transitions.

## Bans

No neon, iMessage-style chat bubbles, identical auto-fill card grids, display fonts in the workspace, borderless invented form controls, chart walls, side-stripe accents, gradient text, or “demo” chrome. Agent Home is a single-column list of rows. Transcript uses named message rows. Create Agent does not expose model, temperature, or tools.
