# WebData AI frontend: design notes

Written so later changes stay consistent. The app is a working tool: the run screen is the one place
for theatre (the Globe), and the forms are calm, sectioned and precise.

## Concept card

```
Idea:        A watchtower over the web. Every source the research touches lands on a slowly turning
             lens as a point of light, and what is kept stays lit.
Metaphor:    Heimdallr's lookout: a lighthouse beam sweeping a globe of sources.
Signature:   The Globe (src/geo/scene.ts, wrapped by src/components/Globe.tsx). A dotted Earth from
             Natural Earth country shapes (world-atlas). Every activity line reacts: each search
             provider is a satellite that fires beams at the land, a site read lights its country
             (by ccTLD, otherwise a stable land dot) with a hop arc from the last site, a kept site
             ripples, raises a pillar and flies an arc into the vault ring (no counter there; totals live only in the HUD strip), a found detail throws
             sparks, dropped and blocked sites ripple grey and red. The countries the plan targets
             are tinted and turned to face you. The run page (Mission.tsx) puts it full-bleed with a
             HUD: current step, the reading stream, the live wire and counters.
Emotion:     Calm watchfulness. You can see the research working without reading a line.
Motion verb: Sweep like a beam. Things arrive with a short sweep or settle, never bounce.
Screenshot:  The job page mid-run: the lens full of lit points on the left, the feed scrolling on the right.
```

The same globe idles in demo mode on the sign-in page and the home page, so the first thing you see is
the thing the product does. The globe stage is always dark (`.force-dark`), in both themes.

Forms are built from `components/form.tsx`: numbered, bordered sections that open one at a time and
show a one-line summary when closed, tile pickers, tag inputs and grouped detail chips. A sticky rail
on the right keeps the research brief and the main action in view.

## System

- **Palette** (tokens in `src/styles.css`, both themes designed):
  - ground `#f4f4f1` / `#0d0e11`, panel `#ffffff` / `#16181c`, ink `#141518` / `#ecebe7`
  - muted `#595d65` / `#9ba0a8`, line: ink at 11% / white at 9%
  - accent "beacon" `#c2410c` / `#ff7a45`, used for the primary action, kept sites and focus only
  - status: ok green, warn amber, bad red, info slate blue; text-strength versions pass AA on panel
- **Type:** Bricolage Grotesque (display: page titles, the hero question), Instrument Sans (all UI and
  reading text), Martian Mono (timecodes, counts, ids, the feed's clock). Self-hosted via Fontsource,
  so the app works offline.
- **Shape:** panels 14px radius, inputs and buttons 10px, chips and pills fully round.
- **Motion:** one ease (`--ease`, a fast-out settle). Feed lines sweep in from the left over 280 ms;
  panels settle up 6px. The lens runs on one requestAnimationFrame loop, paused off screen and when
  the tab is hidden. Under reduced motion: no loop (the lens renders once per change), no line
  animations, the pulse dot stays still.
- **Themes:** system by default, with a three-way switch (system, light, dark) in the top bar,
  remembered per browser. `html[data-theme]` drives the tokens; the lens recolours on change.

## Genericness check

A generic build would land on a blue SaaS card grid with a gradient hero. Changed: the hero is the
lens (the product's own behaviour), the accent is a warm beacon instead of blue, the form reads as a
sentence ("Find … where one row is … each row must …") instead of a stack of labelled boxes.
