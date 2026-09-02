# Dota Draft Assist

Personal Dota 2 drafting assistant. Watches the Dota 2 client with Windows
Graphics Capture, reads the Ranked All Pick draft off the screen with
perceptual-hash portrait matching, and shows hero and item recommendations in
an ordinary desktop window. Single-player personal tool — not a product.

It never touches the game: no injection, no memory reading, no input
automation. It only reads pixels from a window already on the user's screen.

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
| **Data** | Tune recognition | After updating portraits or labelling new crops |
| **Data** | Reload data and library (F5) | After editing files by hand |
| **Capture** | Capture source ▸ | Choose which window to read |
| **Capture** | Bind to Dota client (Ctrl+D) | Re-bind after starting Dota |
| **Capture** | Force recognition (Ctrl+F) | When the draft gate does not trip |
| **Capture** | List capture sources / Run capture probe | Diagnosing capture |
| **Tools** | Save debug snapshot (Ctrl+S) | When recognition looks wrong |
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

### Step 1 — confirm occluded capture

The app's window covers Dota, so capture reads the Dota window's own buffer
rather than the desktop. Whether Dota keeps producing frames while fully
covered varies by driver and Windows version, so verify it once:

1. Start Dota 2 in **borderless windowed** mode.
2. **Capture ▸ Run capture probe…**
3. Cover the Dota window completely and unfocus it while the probe runs.

Frames land in `captures/probe/`. They should keep showing Dota and keep
reporting CHANGED. If they freeze, the fallback is sizing the assist window
to leave the Dota team panels visible.

### Calibration

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
pytest            # 67 tests: normalisation math, scoring views, item
                  # engine, vision end-to-end on synthetic screens, gate &
                  # session state machine, capture-source binding, and
                  # headless UI smoke tests

python -m draft_assist.ui.app --demo             # UI on a scripted draft
python -m draft_assist.ui.app --replay DIR       # UI on saved frames
python -m draft_assist.proving.tune --procedural # recognition, no downloads
```

See `CLAUDE.md` for the domain invariants (normalised deltas, fractional
coordinates, unknown-slot semantics, sublinear item stacking, the
no-game-interaction boundary).
