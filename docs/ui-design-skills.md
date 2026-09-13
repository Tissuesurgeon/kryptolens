# Frontend UI design skills

Research saved 13 Sep 2026. Apply these rules on every KryptoLens UI change. Actionable checklist lives in [`.cursor/skills/frontend-ui-design/SKILL.md`](../.cursor/skills/frontend-ui-design/SKILL.md). Tokens stay in `DESIGN.md`.

## What the research said

### Visual hierarchy

A page has a clear hierarchy when the eye is guided to elements in order of importance. Hierarchy is built from **color/contrast, scale, and grouping** — not from adding more chrome. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)

- Use **no more than three sizes** (small / medium / large). The most important element is the biggest; at most two elements may be large. Typical web range: body 14–16px, subhead 18–22px, header up to 32px in product UI. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)
- Contrast comes from **value and saturation against context**, not from “more color.” Limit to about two primary and two secondary colors. If everything is contrasted, nothing stands out. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)
- Do not rely on color alone; color-blind users miss hue-only cues. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)
- **De-emphasize to emphasize.** Soften secondary text with weight and a hue-matched mute — not with tiny type or gray-on-color. [Refactoring UI](https://refactoringui.com/) · [Notes: Refactoring UI](https://mohitkhare.me/blog/notes-refactoring-ui/)
- Squint / blur the layout. If groupings and the primary action disappear, the hierarchy failed. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)

### Grouping, proximity, chunking

Items that sit close together are read as one group. Space between groups must exceed space inside a group. [NN/G — Proximity](https://www.nngroup.com/articles/gestalt-proximity/)

- Put a heading nearer its content than the previous section. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)
- Put a label nearer its field than the next field. Top-aligned labels scan in one fixation. [NN/G — Form whitespace](https://www.nngroup.com/articles/form-design-white-space/)
- Chunk long content into short units (about 50–75 characters per line; short paragraphs; lists). [NN/G — Chunking](https://www.nngroup.com/articles/chunking/)
- Use a container (border or fill) only when space is not enough. Extra boxes create clutter. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/) · [Refactoring UI — use fewer borders](https://refactoringui.com/)

### Spacing and density

- Pick from a **constrained scale** (4 / 8 / 16 / 24 / 32 / 48 / 64). Arbitrary values look “off.” [Notes: Refactoring UI](https://mohitkhare.me/blog/notes-refactoring-ui/)
- Material layouts sit on an **8dp grid**; 4dp is for fine alignment. Density is for data-heavy views, not for emptying a page. [Material Design 3 — Grids & spacing](https://m3.material.io/foundations/layout/grids-spacing)
- Bigger elements need more space around them. A heading needs more margin than a paragraph. [Notes: Refactoring UI](https://mohitkhare.me/blog/notes-refactoring-ui/)
- You do not have to fill the viewport — but a thin strip in a black void is not “restraint.” One continuous work surface beats nested cards in empty space. [Refactoring UI](https://refactoringui.com/)

### Typography

- Combine **size, weight, and color**. Size alone produces huge titles and unreadable body. Two weights (400–500 body, 600–700 emphasis) are enough. [Notes: Refactoring UI](https://mohitkhare.me/blog/notes-refactoring-ui/)
- Labels are smaller and quieter than values. [refactoring-ui skill notes](https://github.com/wondelai/skills/blob/dd37ee506ff558e939b3d421557987cced49b866/refactoring-ui/SKILL.md)
- Left-align anything longer than two or three lines. Center only short independent lines. [Refactoring UI](https://refactoringui.com/)
- Line length ~45–75 characters. [NN/G — Chunking](https://www.nngroup.com/articles/chunking/) · [Refactoring UI](https://refactoringui.com/)

### Contrast and dark surfaces

WCAG 2.2 AA: normal text **4.5:1**, large text **3:1**, UI component boundaries and states **3:1**. [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/)

- Pure white on pure black maximises the ratio but causes halo/smear. Use off-black surfaces and off-white ink. [Color Contrast WCAG 2.2](https://www.a11yflow.dev/blog/color-contrast-wcag-developer-guide)
- Do not use gray text on a colored fill. Shift the mute toward the fill’s hue. [Refactoring UI](https://refactoringui.com/)
- Focus must stay visible: a 2px ring with ≥3:1 against adjacent color. [W3C Focus Appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance)
- Dark elevation is a **tonal overlay from the primary**, not a copied light-theme shadow. [Material 3 Compose](https://developer.android.com/develop/ui/compose/designsystems/material3)
- Place `on-primary` ink on primary fills. [Material 3 Compose](https://developer.android.com/develop/ui/compose/designsystems/material3)

### Composition

- Scale, hierarchy, balance, contrast, Gestalt. Asymmetry is energetic; symmetry is quiet. [NN/G — 5 Principles](https://www.nngroup.com/articles/principles-visual-design/)
- One primary action per view. Secondary actions recede (ghost / text), they do not compete as a second filled button. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)
- Empty states are designed surfaces: a title, one sentence, the next action. [Refactoring UI](https://refactoringui.com/)
- Design the template **and** the content that fills it. A loud nested object can steal the intended focus. [NN/G — Visual Hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)

## Apply to this product

| Surface | Hierarchy (squint test) | Grouping |
|---|---|---|
| Landing | Headline → composer field → Enter Demo. Spec is tertiary. | Composer is one common region. Spec is proximity-only (no card). |
| Workspace home | Ask heading → blotter → composer. Chips are secondary. | Desk + composer share one surface. No floating bar in the void. |
| Lens | Name + Activate/Run → You asked / assumed → policy → scan. | Labels hug values. Sections separated by space, not nested plates. |
| Settings | Telegram heading → fields → Connect. | Label above field. Related actions in one row. |
| Receipt | Symbol → five numbered blocks. | Blocks share one region; headings hug copy. |

Keep moss tokens, Source Sans 3, Literata on the landing headline only, Source Code Pro for ids/JSON. No neon, chat bubbles, chart walls, side-stripe accents, gradient text, or “demo” chrome.

## Sources

- [Visual Hierarchy in UX: Definition — Nielsen Norman Group](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/) (Jan 2021)
- [5 Principles of Visual Design in UX — Nielsen Norman Group](https://www.nngroup.com/articles/principles-visual-design/) (reviewed Sep 2026)
- [Proximity Principle in Visual Design — Nielsen Norman Group](https://www.nngroup.com/articles/gestalt-proximity/)
- [Group Form Elements Effectively Using White Space — Nielsen Norman Group](https://www.nngroup.com/articles/form-design-white-space/)
- [How Chunking Helps Content Processing — Nielsen Norman Group](https://www.nngroup.com/articles/chunking/)
- [Refactoring UI — Adam Wathan & Steve Schoger](https://refactoringui.com/)
- [Notes: Refactoring UI — Mohit Khare](https://mohitkhare.me/blog/notes-refactoring-ui/) (Jun 2020)
- [Grids & spacing — Material Design 3](https://m3.material.io/foundations/layout/grids-spacing)
- [Applying spacing — Material Design 3](https://m3.material.io/styles/spacing/applying-spacing)
- [Material Design 3 in Compose — Android Developers](https://developer.android.com/develop/ui/compose/designsystems/material3)
- [WCAG 2.2 — W3C](https://www.w3.org/TR/WCAG22/)
- [Understanding Focus Appearance — W3C](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance)
