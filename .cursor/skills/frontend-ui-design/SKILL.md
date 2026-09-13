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
4. No nested cards. One work surface. Group with space or one fill — not a border on every plate.
5. Labels smaller/quieter than values. Hue-matched mute, never gray-on-moss.
6. Composer shares the desk surface. Do not float it in the page void.
7. Empty states have a title, one sentence, and the next action.
8. Spacing from `--space-*` only (4 / 8 / 16 / 24 / 32 / 48 / 64).
9. Text ≥4.5:1, large text ≥3:1, controls/focus ≥3:1. Off-black / off-white, not #000 / #fff.
10. Focus ring: 2px `var(--primary)`, 2px offset.
11. Radius 4px. No pill chips, no 999px tracks, no capsule buttons.
12. Keep required copy: Enter Demo, Intelligence Policy, Your Lenses, Ask KryptoLens, You asked, KryptoLens assumed, Activate, Threshold changes, Telegram, Connect, Disconnect, queued.

## Surfaces

- **Landing:** display headline → high-contrast composer → one primary (Enter Demo in the composer). Spec is an unboxed definition list.
- **Workspace:** roster | blotter | monitor. Blotter = header + desk + composer as one instrument.
- **Receipt:** one region, five numbered blocks, headings hug copy.

## Bans

Neon, chat bubbles, chart walls, side-stripe accents, gradient text, “demo” chrome, glassmorphism, identical card grids, kicker-on-every-section.
