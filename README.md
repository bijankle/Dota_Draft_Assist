# Dota Draft Assist

Personal Dota 2 drafting assistant. Watches the Dota 2 client with Windows
Graphics Capture, reads the Ranked All Pick draft off the screen with
perceptual-hash portrait matching, and shows hero and item recommendations in
an ordinary desktop window. Single-player personal tool — not a product.

It never touches the game: no injection, no memory reading, no input
automation. It only reads pixels from a window already on the user's screen.

## Setup (Windows)

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-windows.txt
copy .env.example .env    # then paste your Stratz API key into .env
```

## Step 1 — confirm occluded capture (do this before anything else)

The app's window sits in front of Dota, so capture must read the Dota window's
own buffer, not the desktop. Whether Dota keeps producing frames while fully
covered and unfocused varies by driver/Windows version. Verify it:

1. Start Dota 2 in **borderless windowed** mode, sit in the main menu.
2. Run `python tools/probe_capture.py` — it finds the Dota window, captures a
   frame every 2 s, and writes numbered PNGs to `captures/probe/`.
3. Cover the Dota window completely (maximize any other window over it) and
   click something else so Dota is unfocused. Wait ~30 s.
4. Look at the newest PNGs: they should show Dota's menu (with its idle
   animations advancing between frames), **not** the covering window. The
   probe also prints a changed/static verdict comparing consecutive frames.

If frames freeze while covered, the fallback is sizing the assist window to
leave the Dota team panels visible; say so and we adjust the plan.

## Step 2 — data and portraits (network, run ~daily / after patches)

```
python tools/pull_data.py        # OpenDota + Stratz -> data_cache/ (verifies
                                 # bracket indexing across sources first)
python tools/build_library.py    # download portraits, build hash library
python tools/inspect_apis.py     # raw API dumps, when parsing breaks
```

The live scoring loop never makes network calls — it reads only these caches.

## Step 3 — tune recognition in the proving ground (no Dota needed)

```
python -m draft_assist.proving.tune              # real portraits
python -m draft_assist.proving.tune --procedural # smoke run, no downloads
```

Composites synthetic draft screens (resolution changes, brightness drift,
compression, crop misalignment, pick-dimming) from the portrait library,
grid-searches hash size / distance ceiling / margin floor, and saves the
best operating point. Any WRONG match disqualifies a candidate before
unknown-rate is considered — unknown slots are legitimate; wrong ones are not.

## Run

```
python -m draft_assist.ui.app            # live capture (Windows, Dota running)
python -m draft_assist.ui.app --demo     # scripted fake draft, runs anywhere
python -m draft_assist.ui.app --replay captures/probe   # saved frames
```

An ordinary draggable window — no overlay, no always-on-top. The Debug tab
shows the captured frame with crop boxes and match confidences. If the draft
gate doesn't trip, tick **Force recognition** (a confirmed draft then saves a
gate reference so the gate works by itself next time). Nudge crop boxes by
editing `calibration_local.json` (fractions of window size) while watching
the Debug tab.

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
pytest            # 42 tests: normalisation math, scoring views, item
                  # engine, vision end-to-end on synthetic screens, gate &
                  # session state machine, headless UI smoke tests
```

See `CLAUDE.md` for the domain invariants (normalised deltas, fractional
coordinates, unknown-slot semantics, sublinear item stacking, the
no-game-interaction boundary).
