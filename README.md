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

## Daily data pull

```
python tools/pull_data.py           # OpenDota + Stratz -> data_cache/
python tools/inspect_apis.py        # dump raw API responses for schema checks
```

## Development (any OS, no Dota needed)

Everything except live capture runs headlessly:

```
pip install -r requirements.txt
pytest                              # pure-function + replay tests
python tools/build_library.py       # download portraits, build hash library
python -m draft_assist.proving.tune # synthetic proving ground / auto-tune
python tools/replay.py captures/... # run vision+scoring on saved frames
```

See `CLAUDE.md` for the domain invariants (normalised deltas, fractional
coordinates, unknown-slot semantics, sublinear item stacking).
