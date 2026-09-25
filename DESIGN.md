# KryptoLens design

UI work follows `docs/ui-design-skills.md` (hierarchy, proximity, 8px scale, WCAG, fewer borders).

## Scene

Sage checker field, from the Harvest Call system in `.cursor/skills/harvest-ui/SKILL.md`. Cream paper panels sit on the field. Landing composition stays the product window and one primary action. The workspace is a roster of analysts and one transcript. Not a neon terminal, not a farm illustration, not a generic SaaS card grid.

## Strategy

Restrained in the app. Workspace follows **Grok Bot** layout, not grok.com chat: a sidebar roster of analysts | one transcript | a composer. First-run is Create an Analyst (name only). A new analyst opens an empty thread — the user writes the first message. No canned greeting, no preset job chips. The thread shows the question, clarification, research steps, finding, evidence, and verification. No Chat/Routines/Jobs tabs, specialist picker, or computer-control panel. Presence sits on the analyst face and a quiet line under the name (Ready, Investigating, Analyzing, Verifying, Needs attention). A live CMC strip stays in the slim conversation head. Composer placeholder is **Ask {name}…**. One work surface per view.

## Tokens

The field is sage. Paper is cream. Bark is the outline. `body.is-app` only locks the shell (full height, no page scroll).

| Token | Value | Role |
|---|---|---|
| `--bg` | `#b9c78a` | Field |
| `--bg-raise` | `#f3ead8` | Raised paper |
| `--surface` | `#fbf6ec` | Panels |
| `--surface-2` | `#f3ead8` | Hover / second paper |
| `--line` | `#6f5334` | Bark outlines |
| `--primary` | `#b8552f` | Terracotta actions |
| `--accent` | `#f2cf7a` | Gold second action and focus |
| `--radius` | `16px` | Buttons, inputs, rows, modal |

Status color stays sparse: green = active/success; red = negative market move or error; gold = waiting.

## Type

Fredoka for headings and buttons. Nunito for product UI. Source Code Pro for the CMC strip, counts, page ids, and API evidence.

## Motion

180ms state changes. Reduced-motion disables transitions.

## Bans

No neon, iMessage-style chat bubbles, identical auto-fill card grids, display fonts in the workspace, borderless invented form controls, chart walls, side-stripe accents, gradient text, or “demo” chrome. Analyst home is a single-column list of rows. Transcript uses named work-log rows. Create an Analyst asks only for a name.
