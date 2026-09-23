---
name: harvest-ui
description: >-
  Apply the Harvest Call visual system to KryptoLens: sage checker field, cream
  paper panels, bark outlines, terracotta and gold chunky controls, Fredoka
  headings, and Nunito body text. Use when changing CSS, templates, empty
  states, or any KryptoLens screen, and when the user mentions Harvest Call
  or harvest-call.vercel.app.
---

# Harvest Call UI

Source: [Harvest Call](https://harvest-call.vercel.app/). This skill sets color, type, and control chrome. Layout stays in `frontend-ui-design` and landing composition stays in `index-landing`.

## Tokens

| Token | Value | Use |
|---|---|---|
| Field | `#b9c78a` | Page background, with a lighter sage checker |
| Paper | `#fbf6ec` | Panels, roster, thread, auth card |
| Inset | `#fff7ee` | Inputs, composer well |
| Ink | `#33291f` | Text on paper and on the field |
| Bark | `#6f5334` | 3px outlines, hard shadows, muted labels |
| Terracotta | `#b8552f` | One primary action, cream label `#fff7ee` |
| Gold | `#f2cf7a` / ink `#6b4d16` | The second button, when a view has two actions |
| Cream headline | `#fff7ee` | Display type that sits directly on the field |

## Controls

- Primary and gold buttons: Fredoka, 3px bark border, 16px radius, hard shadow `0 4px 0 #6f5334`. Press moves the button down and shortens the shadow.
- Landing CTAs can be taller. In the workspace keep the same chrome at the existing control height.
- Fields: cream inset, 2px bark border, 16px radius. Focus ring is 2px gold, 2px offset.
- Panels (window, roster, thread, auth card, toast): cream paper, 3px bark border, 18px radius, shadow `0 6px 0 #6f5334`.

## Type

Fredoka for headings, the brand, and buttons. Nunito for body and UI. Source Code Pro stays on prices, counts, ids, and evidence.

## Field

Both the signed-out pages and the workspace sit on the sage checker. Paper panels float on it. Do not paint a night gradient back over the field.

## Do not import

The farm illustration, crops, wallet connect, test-funds flow, or game copy. KryptoLens keeps its own words. The mark sits in a small terracotta tile so it stays visible on sage and on paper.
