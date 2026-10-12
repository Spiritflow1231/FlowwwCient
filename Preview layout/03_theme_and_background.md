# 03 – Theme and background

## Mood
Dark translucent "glass" panels over a purple-blue gradient. Light text. Red brand accent for primary actions. Green and red are used only for state (enabled / disabled / errors).
(`images/03_reference_background.jpg` is the mood; ship `images/bg_1920x1080.jpg` as `assets/bg.jpg`.)

## Background
- Dominant colors sampled from the reference: #05010F, #0E031E, #1F0535, #2F0F59, #140D41, #24266E, #423B98. Purple glow top-left, blue glow bottom-right, dark band across the middle, fine grain texture.
- Draw `assets/bg.jpg` once behind the whole window (a CTkLabel/Canvas placed at relx=0, rely=0, relwidth=1, relheight=1 and lowered). Resize with "cover" scaling (crop, do not stretch). Cache the resized PIL image and re-render only 150 ms after the last `<Configure>` event.
- Add a dark overlay of 25-35 percent over the background so text always has contrast.

## Glass panels (CustomTkinter has no alpha)
Recipe, applied to every card, sidebar and list panel:
1. Crop the part of the (resized) background that sits behind the panel.
2. Darken it (multiply by 0.35-0.45), blur it (Gaussian radius 14-18), then tint with panel color #0D0B1A at 20 percent.
3. Draw it as the panel's background image (CTkLabel image, or a Canvas rectangle), with a 1 px border at rgba(255,255,255,0.08) simulated by a slightly lighter outer frame.
4. Cache by (panel size, panel position, background version). Re-render panels only after resize settles. If the compositing is too slow on a given page, fall back to solid panel colors from the tokens below.

## Tokens (see also `theme_tokens.json`)
| Token | Value | Use |
|---|---|---|
| bg_overlay | #05010F @ 30% | over the background image |
| panel | #0D0B1A (alpha look 70-80%) | cards, sidebars |
| panel_alt | #14112A | rows, inputs |
| row_hover | #1C1838 | hover |
| border | #FFFFFF @ 8% (fallback #2A2745) | 1 px borders |
| text | #F4F3FA | primary text |
| text_muted | #9A97B5 | secondary text |
| accent | #E63946 | PLAY, primary buttons, active nav, active chip |
| accent_dark | #C22F3B | accent hover |
| enabled | #1FA86A | ENABLED buttons, switches on, success |
| disabled_outline | #E0525F | DISABLED outline buttons |
| link | #4DA3FF | link-style text |
| warning | #F0A030 | incompatible / needs attention |
| danger | #E0525F | delete / errors |

## Shape, spacing, type
- Radius: panels 14, cards 12, buttons 10, chips 8, inputs 10, icons tiles 10.
- Spacing grid: 4 / 8 / 12 / 16 / 24. Page padding 24. Gap between cards 12-16.
- Buttons 38-44 px high (primary 48). Rows 72-84 px. Sidebar item 40 px.
- Keep the current font family. Page title 24 bold, section title 18 bold, body 12-13, caption 10-11 caps with letter spacing for labels.
- Nothing may clip or overflow at 1040x660 or maximized. Long names truncate with an ellipsis and show a tooltip.

## Motion (cheap, consistent)
- Page / section switch: new content slides 16 px and fades in over 160-200 ms with ease-out (animate `place` offsets or interpolate colors). Cancel any running animation on a new click.
- Hover / press on buttons, rows, cards: interpolate fill color in 5-6 steps over about 120 ms.
- Rows fade in with a stagger of at most 30 ms, only the first 8 rows. Progress bars animate smoothly.
- Settings checkbox "Animations" (default on). Skip animations while installing or when the window is minimized.
