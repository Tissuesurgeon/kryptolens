---
name: index-landing
description: >-
  Compose the KryptoLens landing page using the INDEX 0 homepage structure:
  a fact line, a stance headline, one primary action, a track-switched product
  window, and a numbered path beside a labeled transcript. Use when redesigning
  or editing templates/landing.html, landing CSS, or when the user mentions
  INDEX 0, index-0.in, or a landing-page redesign.
---

# INDEX 0 landing composition

Source: [INDEX 0](https://www.index-0.in/). Apply the composition. Keep KryptoLens tokens from `frontend-ui-design` and `DESIGN.md`.

## Keep

- Moss field, Source Sans 3, Literata only on the landing headline, Source Code Pro for the fact line and step indexes.
- Spacing from `--space-*`. Radius 8px. Focus ring 2px primary, 2px offset.
- One filled primary per view: **Create a Lens**. Log In stays quiet.
- The existing write-up. Restructure it into the scenes below. Do not invent metrics, logos, testimonials, or market numbers.

## Scenes

1. **Bar.** Wordmark, two in-page links, Log In, one filled Create a Lens.
2. **Hero, two columns.** Left: one mono fact line with middots (Persistent, live CoinMarketCap data, one Lens). Display headline with a single primary-colored phrase, not a gradient. One or two paragraphs. One filled action. One quiet proof line. Right: a track switcher, then the real Lens window (face, name, presence, turns, composer that POSTs `intent`), then one caption for the active track.
3. **Coaching split.** Section title, one paragraph, then two columns. Left: numbered stages, hairline between them, mono index, title, one sentence. Right: a labeled transcript (You / KryptoLens) plus the inspectable result fields. Sticky on wide screens.
4. **Later sections.** One headline, one paragraph, then one structure: a question list, a hairline definition list, or a data list. Do not repeat a quote that already appears in the hero window.
5. **Close.** One headline, one short paragraph, Create Your Lens, ghost Log In.
6. **Footer.** Name, then the three quiet lines already in the write-up.

## Adapt, do not copy

INDEX 0 uses macOS window chrome, chat bubbles, fully rounded tabs, a mint word-gradient, download buttons per platform, a stat strip, a map, reviews, and a coffee widget. Do not bring those over.

- Tracks are 8px bordered buttons (`.landing-jobs`), not pills. `aria-selected` sets the primary border.
- Turns are a quiet label plus the sentence, not bubbles.
- The window is the Lens, not a fake desktop frame.
- No second primary button in the hero.

## Tracks

Four tracks, each with a Lens name, two turns, and a caption:

| Track | Lens | Shows |
|---|---|---|
| Watch | Market Watch | The 2% BTC watch, then a clarifying question |
| Reaction | BTC Reaction | Top-100 reaction, then the threshold question |
| Volume | Altcoin Monitor | Unusual volume, then the universe question |
| Compare | Market Research | Historical comparison, then a note that missing data is not zero |

Switching a track changes the name, the turns, and the caption. The composer stays put and still posts to `/`.
