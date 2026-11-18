# Liquid Glass Skin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin the HouseKeeper UI to match HA's "Liquid Glass Tinted" theme.
**Architecture:** Replace the `<style>` block and font `<link>` in `family_tracker/app/static/index.html`; no JS/markup/server changes.
**Tech Stack:** Plain CSS served by the add-on's Python http.server.
**Spec:** docs/superpowers/specs/2026-11-17-liquid-glass-skin-design.md

## Global Constraints
- Only `index.html` lines 7–171 (font link + style) change, plus `config.yaml` version "1.2.0" and CHANGELOG.
- Glass: light rgba(245,245,247,.6) / dark rgba(58,58,60,.6); `blur(12px) saturate(1.3)`; card radius 28px.
- Wallpaper URLs: `https://raw.githubusercontent.com/Nezz/homeassistant-visionos-theme/refs/heads/static/macOS_27_{Light,Dark}.webp`.
- Every existing class keeps a rule (no unstyled class from the old sheet).

## Review Focus
- Text contrast over the wallpaper (badges, .note, .hint, table headers) in both modes.
- Modal readability: dialog surface must be more opaque (.8) than cards.
- Low-stock table rows (`tr.low`) and hover states remain distinguishable.
- Browser without backdrop-filter / prefers-contrast: more → near-solid cards.
- Phone width (390px): no horizontal scroll introduced; summary grid still fits.

---

### Task 1: Rewrite the stylesheet
**Files:** Modify `family_tracker/app/static/index.html:7-171`
- [ ] Step 1: Coverage check — every class from the old sheet has a rule in the new one (`comm` diff of selectors → empty).
- [ ] Step 2: Write new tokens (light/dark), wallpaper, glass surfaces, system type, pill controls, fallbacks.
- [ ] Step 3: Run server locally (`FT_DATA=<tmp> python3 app/server.py`), import `samples/starter-backup.json`, screenshot home/garage/parts/home-tasks/detail/modal at 1280 and 390 widths, light + dark. Expected: glass cards over wallpaper, readable text, no horizontal scroll at 390.
- [ ] Step 4: Commit `feat: Liquid Glass skin`.

### Task 2: Ship
**Files:** Modify `family_tracker/config.yaml` (version "1.2.0"), `family_tracker/CHANGELOG.md`
- [ ] Step 1: Bump version + changelog; commit; push to origin main (with user OK).
- [ ] Step 2: Supervisor store reload → add-on update to 1.2.0; open panel; expected: new skin, data intact.

### Task 1b (added): Appearance picker
**Files:** Modify `family_tracker/app/static/index.html` (head inline script, `renderSettings`, click handler, boot)
- `applyAppearance(a: {theme,mode}|null): void` — validates, sets `<html>` data attrs, caches to localStorage `ft-appearance`.
- Boot: `db.doc("meta/appearance").onSnapshot` → `applyAppearance`; re-render if on settings.
- Click `data-act="appearance" data-k="theme|mode" data-v=...` → apply, render, `db.doc("meta/appearance").set(next)`.
- Verify: change on one browser tab → second tab switches within a poll cycle; reload → no flash.
