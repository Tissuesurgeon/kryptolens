# KryptoLens design

UI work follows `docs/ui-design-skills.md` (hierarchy, proximity, 8px scale, WCAG, fewer borders).

## Scene

Night desk, scan-and-trust. The product is a darkened optical instrument, not a neon terminal and not a generic SaaS dashboard.

## Strategy

Restrained in the app. Landing is a committed moss field: one claim, one action, a spec list. Ochre is reserved for medium severity. One work surface per view. Composer shares the desk.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--bg` | `oklch(0.10 0.012 130)` | Night-desk stage, tinted to moss |
| `--surface` | `oklch(0.155 0.016 130)` | Instruments |
| `--ink` | `oklch(0.95 0.014 130)` | Body |
| `--muted` | `oklch(0.78 0.024 130)` | Secondary, contrast-safe |
| `--primary` | `oklch(0.68 0.12 130)` | Moss |
| `--accent` | `oklch(0.72 0.12 75)` | Ochre |

## Type

Source Sans 3 for product UI. Literata only on the landing headline. Source Code Pro for policy JSON, page ids, and API evidence.

## Motion

180ms state changes. Reduced-motion disables transitions.

## Bans

No neon, chat bubbles, chart walls, side-stripe accents, gradient text, or “demo” chrome.
