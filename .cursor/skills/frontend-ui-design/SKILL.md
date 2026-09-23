---
name: frontend-ui-design
description: Apply researched product-UI skills (hierarchy, proximity, spacing scale, WCAG contrast, fewer borders) when changing KryptoLens CSS, templates, or empty states. Use when editing the landing, workspace, lens, receipt, or settings UI.
---

# Frontend UI design (KryptoLens)

Read `docs/ui-design-skills.md` and `DESIGN.md` before changing visuals.

## Squint test (must pass)

1. One primary action per view. Everything else recedes.
2. Three type sizes only: body, subhead, title. Landing may add one display size.
3. Related items are closer than unrelated ones. Heading hugs its block.
4. One work surface. Grok Bot layout: sidebar roster of Agents, slim Bot head (name + presence), transcript, composer. No Chat/Routines/Jobs tabs, status badge, Pause, Check now, or profile ellipsis in the chat header.
5. Labels smaller/quieter than values. Hue-matched mute.
6. Composer shares the desk surface. Do not float it in the page void.
7. Empty states have a title, one sentence, and the next action.
8. Spacing from `--space-*` only (4 / 8 / 16 / 24 / 32 / 48 / 64).
9. Text ≥4.5:1, large text ≥3:1, controls/focus ≥3:1. Off-black / off-white, not #000 / #fff.
10. Focus ring: 2px `var(--primary)`, 2px offset.
11. Radius, color, type, and control chrome come from `harvest-ui`. No pill chips and no 999px tracks.
12. Keep required copy: Get Started, Log In, Ask KryptoLens, You asked, KryptoLens assumed, Activate, Threshold changes, Telegram, Connect, Disconnect, queued.

## Surfaces

- **Landing:** follow `index-landing` for composition. Color and chrome follow `harvest-ui`. One filled Create a Lens.
- **Workspace:** Grok Bot messenger. Sidebar of named Agents with geometric faces. Slim head: name + presence + CMC strip. New Agent opens an empty thread; the user writes first. Transcript of messages and work cards. Composer docked as a rounded field. Pause, check now, and activate are messages.
- **Receipt / job trace:** one region, persisted stages, headings hug copy.

## Type

Fredoka for headings and buttons. Nunito for UI text. Source Code Pro for CMC prices, counts, ids, JSON. See `harvest-ui`.

## Bans

Neon, chat bubbles, identical auto-fill card grids, display fonts in the workspace, borderless invented form controls, chart walls, side-stripe accents, gradient text, “demo” chrome, glassmorphism, kicker-on-every-section, exposing model/temperature/tools in Create Agent, fake progress percents.
