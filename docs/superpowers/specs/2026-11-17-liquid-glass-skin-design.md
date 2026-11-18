# HouseKeeper — Liquid Glass skin

## Intent
Make the HouseKeeper app look like part of the same family as the HA Controls
dashboard (theme "Liquid Glass Tinted"). The owner chose option A: fully adopt the glass look,
including Apple-style system typography, rather than keeping the workshop/condensed type.

## Goals
- Same wallpaper, frosted surfaces, radii, edge highlight, palette and accent as Liquid Glass Tinted.
- Light and dark modes, following the device setting (the ingress iframe can't read HA's theme mode).
- Readable over the wallpaper on a phone.

## Non-goals
- No layout, feature, JS or server changes. Same views, same markup.

## Anti-goals
- Low-contrast text over busy wallpaper; janky scrolling from blurring every table row.

## Approaches
1. **CSS-only rewrite of the existing <style> block (chosen).** Every visual is already class + CSS-variable
   driven, so only index.html lines ~7–171 change. Lowest risk.
2. Inject HA's theme variables at runtime from the parent frame. Rejected: ingress iframe access to
   parent theme is fragile, and the app also must work when opened directly.
3. Restyle via a separate stylesheet file served by server.py. Rejected: needs a server change for no gain.

## Design
- **Tokens** copied from the theme: light card rgba(245,245,247,.6), dark rgba(58,58,60,.6);
  backdrop blur(12px) saturate(1.3); Apple system colors (dark: orange #FF9F0A, green #32D74B,
  yellow #FFD60A, red #FF453A; light: #FF9500/#34C759/#FFCC00→darkened for text/#FF3B30);
  text rgba(0,0,0,.85)/rgba(60,60,67,.6) light, white .96 / rgba(235,235,245,.6) dark.
- **Wallpaper:** same macOS_27_Light/Dark.webp URLs the theme uses, fixed, cover; solid
  fallback color if it fails to load.
- **Surfaces** (stat, upcoming, card, panel, tile, tablewrap, rowlist, modal box): glass fill, blur,
  no border, theme's inset highlight shadow, radius 28px (inner pieces like .st/.form/inputs 16px/12px).
  Rows inside lists/tables are NOT blurred; they use a quiet translucent hover fill.
- **Type:** -apple-system / SF Pro / Segoe UI / system-ui; Google Fonts link removed; headings semibold,
  normal case, tighter tracking; mono → ui-monospace.
- **Controls:** buttons are pills with a quiet translucent fill, primary = orange; nav becomes a glass
  segmented pill bar; status badges are tinted translucent pills; checkboxes use the accent.
- **Fallbacks:** @supports not (backdrop-filter) → more opaque cards; prefers-contrast: more → near-solid
  cards with outline (as the theme does).

## Shipping
Bump config.yaml version to 1.2.0 (1.1.0 was used then reverted), CHANGELOG entry, push to GitHub,
then update the add-on in HA (Supervisor rebuild).

## Left to the builder
Exact spacing tweaks, hover/transition details, local preview method.

## Addendum (2026-11-17): theme picker
The owner asked to choose the theme from the tracker's Settings. Decisions (owner's): **household-wide**, options
**Liquid Glass + Classic** (today's look, unchanged), each with **Auto / Light / Dark** mode.
- Stored in the tracker DB at doc `meta/appearance` = `{theme: "glass"|"classic", mode: "auto"|"light"|"dark"}`;
  default glass/auto. Included in backups; live-updates other devices via the existing change poll.
- Applied as `<html data-theme data-mode>`. A tiny inline head script applies the last-seen value from
  localStorage key `ft-appearance` before first paint (my call, avoids a flash), then the DB value wins.
- Settings gets an "Appearance" panel with two segmented pill controls.
- CSS: Classic = existing sheet; Glass = a scoped `[data-theme=glass]` layer on top. Dark tokens apply under
  `data-mode=dark`, or `data-mode=auto` + prefers-color-scheme: dark.
- This supersedes "No JS changes" in Non-goals; markup/server still unchanged. Google Fonts link stays (Classic uses it).

## Correction (2026-11-17): Frosted Glass, not Liquid Glass Tinted
The live Controls dashboard uses **Frosted Glass Dark** (Home view) and **Frosted Glass** (other views);
the local dashboard.yaml was stale. Glass layer re-based on those theme values: wallpaper
`frosted-glass-{light,dark}-background.jpg` (jsdelivr, wessamlauf/homeassistant-frosted-glass-themes),
transparent cards + blur(10px dark / 8px light) saturate(1.25), 0.5px edge rgba(234,235,238,.22) dark /
rgba(255,255,255,.3) light, 18px radius, theme inset reflection + depth shadow, accent rgb(122,162,190) dark /
rgb(106,116,211) light, heading weight 500, popups rgba(.35) + blur(18px). Picker label: "Frosted Glass" (key stays `glass`).
My call: light-mode status colors darkened from the theme's pastels so they're readable as text.
