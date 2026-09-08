# Fonts

Loaded at startup by `draft_assist/ui/fonts.py`, which registers every
`.ttf`/`.otf` here with Qt before the stylesheet is applied. The stylesheet
asks for them by family name and names fallbacks behind them, so removing a
file changes how the app looks and never stops it working.

| File | Family | Used for |
| --- | --- | --- |
| `Alegreya-Regular.ttf` | `Alegreya` | everything |
| `Alegreya-Bold.ttf` | `Alegreya` (bold) | headings, tile names, the tabs |
| `Alegreya-Black.ttf` | `Alegreya Black` | the app's own name in the title bar |

## Why these are in the repository when the artwork is not

**Alegreya is licensed under the SIL Open Font License 1.1** — see
`OFL.txt`, and the licence is stated in the fonts' own metadata. The OFL
permits redistribution, including bundled inside another program, so
nobody has to take anyone's word for it.

That is the bar for anything committed here: **the licence has to say yes
on its own.** The hero portraits, the item icons and a supplied `app.ico`
do not clear it — they are Valve's and Blizzard's artwork, downloaded to
the user's own disk at runtime and never carried here.

Two fonts have already failed that bar and been removed:

* **ITC Novarese** — a commercial retail typeface. Retail EULAs generally
  forbid redistributing the font file at all.
* **LifeCraft** — carries **no copyright and no licence** in its name
  table at all. Absence of a stated licence is not permission.

If a font is ever replaced, change the family name in `ui/fonts.py` AND in
`ui/theme.py` — two spellings of one family is a font that silently never
loads, which `tests/test_fonts.py` checks.
