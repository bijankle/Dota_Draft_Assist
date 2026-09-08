# Fonts

Loaded at startup by `draft_assist/ui/fonts.py`, which registers every
`.ttf`/`.otf` here with Qt before the stylesheet is applied. The stylesheet
asks for them by family name and names fallbacks behind them, so removing a
file changes how the app looks and never stops it working.

| File | Family | Used for |
| --- | --- | --- |
| `LifeCraft.ttf` | `LifeCraft` | the app's own name in the title bar |
| `NovareseStdMedium.otf` | `ITC Novarese Std` | everything else |

Both were supplied by the project's owner, who confirmed their licences
permit redistribution — which is why these are committed while the hero
portraits, the item icons and any supplied `app.ico` are not. That
distinction is the whole rule: those are Valve's and Blizzard's artwork,
downloaded to the user's own disk at runtime and never carried here.

If a font is ever replaced, change the family name in `ui/fonts.py` AND in
`ui/theme.py` — two spellings of one family is a font that silently never
loads, which is what `tests/test_fonts.py` checks.
