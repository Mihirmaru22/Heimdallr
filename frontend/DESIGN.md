# WebData AI frontend: design notes

Written so later changes stay consistent. The app is a working tool, so the theatre is kept small:
one signature (the Lens) and calm, precise everything else.

## Concept card

```
Idea:        A watchtower over the web. Every source the research touches lands on a slowly turning
             lens as a point of light, and what is kept stays lit.
Metaphor:    Heimdallr's lookout: a lighthouse beam sweeping a globe of sources.
Signature:   The Lens (src/components/Lens.tsx). On the job page it is driven by the real activity
             feed: a search sends a scan ring across the globe, a site read lights a point, a kept
             site turns the beacon colour and is wired to the core, a dropped site fades out.
Emotion:     Calm watchfulness. You can see the research working without reading a line.
Motion verb: Sweep like a beam. Things arrive with a short sweep or settle, never bounce.
Screenshot:  The job page mid-run: the lens full of lit points on the left, the feed scrolling on the right.
```

The same lens idles on the sign-in page and the project page (an illustration, with points lit at
random), so the first thing you see is the thing the product does.

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
