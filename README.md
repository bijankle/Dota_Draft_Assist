# Dota Draft Assist

Personal Dota 2 drafting assistant. Reads the current Ranked All Pick draft
and shows hero and item recommendations in an ordinary desktop window.
Single-player personal tool — not a product.

**Draft state comes from Dota's own Game State Integration feed.** GSI is
Valve's documented mechanism: a config file in the Dota install asks the game
to POST JSON about itself to a local port. The game volunteers its state, so
there is no screen reading, no per-frame compute, and nothing to
misidentify.

It never touches the game: no injection, no memory reading, no input
automation, and no logging in as a second Steam client.

### One caveat, and the app is honest about it

GSI's `draft` component is understood to be a spectator/observer feature. In
your own ranked match the feed reliably reports **your** hero, your team, the
match ID and the game state — but probably **not** the enemy line-up. So:

- whatever the game reports is used automatically;
- anything it does not report is **clicked in** — click an empty draft slot,
  type a few letters, done;
- screen capture is still available behind `--vision` as a fallback.

**Game ▸ Record game data…** archives real payloads during a draft and prints
a verdict on what GSI actually sends. If it turns out the draft block does
arrive, the manual slots simply stop being needed — nothing else changes.

## Install and run (Windows)

Double-click **`Dota Draft Assist.bat`**. That is the only file you launch,
ever.

The first run installs a private Python environment beside the app and opens
`.env` for your Stratz API key (free from https://stratz.com/api). Every run
after that just starts the application — no console window, no other scripts.

Requires Python 3.11+ from python.org, installed with "Add python.exe to
PATH" ticked.

## Using the application

Everything that used to be a separate script is a menu item that runs inside
the app, with live progress and readable errors.

| Menu | Action | When |
| --- | --- | --- |
| **Data** | Update statistics and portraits | First run, then ~daily and after patches |
| **Data** | Reload data and library (F5) | After editing files by hand |
| **Game** | Set up game data (GSI) | Once, before first use |
| **Game** | Game data status | To see exactly what Dota is reporting |
| **Game** | Record game data | To archive real payloads during a draft |
| **Game** | Clear manual draft | Between games |
| **Capture** | Use game data / Use screen capture | Switching source at runtime |
| **Capture** | Capture source ▸, Bind to Dota client, Force recognition | Screen-capture fallback only |
| **Tools** | Save debug snapshot (Ctrl+S) | When the capture fallback looks wrong |
| **Tools** | Edit / reload item rules | Tweaking `rules/items.yaml` |
| **Help** | Update application | Pull the latest code from GitHub |

The window opens even before anything is downloaded and tells you what to do
next. It also opens when Dota is not running: capture is simply unbound, and
the Capture menu lets you pick a source.

**Draft tab** — the full ranked hero list (never filtered by role; heroes
matching your queued role are highlighted), a filter box, your team and the
enemy team as clickable slots, the component breakdown for whichever hero is
selected, and the item panel once your pick is locked.

**Debug tab** — the captured frame with the crop boxes drawn on it and the
match confidence beside each slot. This answers almost every recognition
question at a glance, because most vision bugs are just the wrong rectangle
being cropped.

### Connecting the game (do this once)

1. **Game ▸ Set up game data (GSI)** — finds the Dota install through Steam's
   library folders and writes the config.
2. In Steam: right-click **Dota 2 → Properties → Launch Options**, add
   `-gamestateintegration`.
3. Restart Dota.

**Game ▸ Game data status** then shows what is arriving and which components
the feed carries. Nothing leaves your machine: the listener binds
`127.0.0.1` only and checks the auth token Dota sends.

### The screen-capture fallback

Only if you want it (`--vision`, or **Capture ▸ Use screen capture**). The
app's window covers Dota, so capture reads the Dota window's own buffer
rather than the desktop; whether Dota keeps producing frames while covered
varies by driver, so verify with **Capture ▸ Run capture probe…** while the
Dota window is covered. Frames land in `captures/probe/`.

### Calibration (screen-capture fallback only)

Slot coordinates are fractions of the window size, so they survive
resolution changes. If the crop boxes in the Debug tab do not sit on the
hero portraits, nudge them in `calibration_local.json` while watching that
tab.

## Self-training on real frames

```
python tools/replay.py captures/somedir --harvest
```

Runs the full pipeline on saved frames and writes picture-first debug dumps
(`debug_out/<timestamp>/` with overlay, crops, and per-slot match records).
With `--harvest`, confident crops are added to the many-to-one variants
library (dim states, new art), and unknown crops queue in
`debug_out/unlabeled/` for:

```
python tools/label_slot.py debug_out/unlabeled/<crop>.png "Anti-Mage"
python tools/build_library.py    # rebuild to include new labels
```

This is how personas, arcanas, and odd UI states accumulate into regression
coverage without repeatedly sending screenshots.

## Development

```
pip install -r requirements.txt
pytest            # 89 tests: normalisation math, scoring views, item
                  # engine, GSI config/listener/parsing/provider, vision
                  # end-to-end on synthetic screens, gate & session state
                  # machine, and headless UI smoke tests

python -m draft_assist.ui.app                    # game data (GSI)
python -m draft_assist.ui.app --manual           # hand-entered draft
python -m draft_assist.ui.app --vision           # screen-capture fallback
python -m draft_assist.ui.app --demo             # UI on a scripted draft
python tools/probe_gsi.py --minutes 10           # what does GSI really send?
```

See `CLAUDE.md` for the domain invariants (normalised deltas, fractional
coordinates, unknown-slot semantics, sublinear item stacking, the
no-game-interaction boundary).
