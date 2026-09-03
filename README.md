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
| **Data** | Statistics bracket | Choose which ranks the numbers come from |
| **Data** | Reload data and library (F5) | After editing files by hand |
| **Game** | Set up game data (GSI) | Once, before first use |
| **Game** | Diagnose game data (Ctrl+G) | When no data is arriving — names the failing step |
| **Game** | Game data status | To see exactly what Dota is reporting |
| **Game** | Record game data | To archive real payloads during a draft |
| **Game** | Clear manual draft | Between games |
| **Capture** | Use game data / Use screen capture | Switching source at runtime |
| **Capture** | Capture source ▸, Bind to Dota client, Force recognition | Screen-capture fallback only |
| **View** | Draft overlay (Ctrl+O) | A small badge over Dota that expands into the picks |
| **Tools** | Save debug snapshot (Ctrl+S) | Grabs the Dota window with the slot boxes drawn on it |
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

**Draft overlay** (Ctrl+O) — a small always-on-top badge you drag wherever
you like. Click it to expand a compact panel of the top picks with their
scores; click again to collapse back to a 30-pixel badge. Position and
collapsed state are remembered. It sits *over* Dota as an ordinary window —
nothing is injected into the game — which means Dota must run in
**borderless windowed** mode, since an exclusive-fullscreen game draws above
everything.

**Ctrl+S** grabs the Dota window whatever the current source is, and saves it
with the slot boxes drawn on top into `debug_out/<timestamp>/`. That frame is
what anchors per-portrait annotations, since GSI reports game state but no
screen coordinates.

### Connecting the game (do this once)

1. **Game ▸ Set up game data (GSI)** — finds the Dota install through Steam's
   library folders and writes the config. **Both steps are required**: the
   launch option only tells Dota to look for config files, so without this
   one there is nothing for it to send.
2. In Steam: right-click **Dota 2 → Properties → Launch Options**, add
   `-gamestateintegration`.
3. Restart Dota.

If no data arrives, **Game ▸ Diagnose game data** (Ctrl+G) tests each
requirement separately — install found, config present, ports agreeing,
launch option set, listener up, Dota running, payloads arriving — and names
the one that is failing. Note that Dota sends GSI data only while you are
**in a match** (the draft counts); the main menu sends nothing.

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

### Statistics bracket

**Data ▸ Statistics bracket** chooses which ranks the hero win rates and
matchups are drawn from. Hero strength genuinely differs by rank, and the
default aims about one bracket above where you play (Ancient + Divine for a
Legend player climbing), so the advice reflects the games you are trying to
win rather than the ones you already do. Two adjacent brackets are combined,
which roughly doubles the sample for a metagame difference smaller than the
noise it removes; a single bracket is allowed but noisier.

This is a data-pull setting, not a display filter — the baselines and
matrices are built for the chosen brackets. Changing it therefore needs a
data update, which the app offers immediately, and until then a banner says
which bracket the cached numbers actually came from.

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
pytest            # 117 tests: normalisation math, scoring views, item
                  # engine, GSI config/listener/parsing/provider/diagnostics,
                  # vision end-to-end on synthetic screens, gate & session
                  # state machine, overlay, and headless UI smoke tests

python -m draft_assist.ui.app                    # game data (GSI)
python -m draft_assist.ui.app --manual           # hand-entered draft
python -m draft_assist.ui.app --vision           # screen-capture fallback
python -m draft_assist.ui.app --demo             # UI on a scripted draft
python tools/probe_gsi.py --minutes 10           # what does GSI really send?
```

See `CLAUDE.md` for the domain invariants (normalised deltas, fractional
coordinates, unknown-slot semantics, sublinear item stacking, the
no-game-interaction boundary).
