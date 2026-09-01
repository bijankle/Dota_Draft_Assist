# Dota Draft Assist — domain facts and invariants

Personal-use Windows desktop app that watches the Dota 2 client via Windows
Graphics Capture, reads the draft off the screen, and shows hero/item
recommendations in its own ordinary window. Single user, no distribution,
no installers.

## Non-negotiable boundary

The app **never** injects code into the Dota process, hooks its rendering or
presentation chain, reads its memory, or sends synthetic input to it. It reads
pixels from a window already visible on the user's own screen and does nothing
else to the game. If a feature seems to require crossing this line, stop and
say so instead of implementing it.

## Domain facts not guessable from the code

1. **Matrices hold normalised deltas, never raw win rates.** Every matchup and
   synergy figure is converted at ingestion into a delta relative to what the
   two heroes' individual baseline win rates would predict. Raw rates are
   contaminated by hero main effects; we want only the interaction term. If a
   stored matrix ever contains raw rates, every recommendation is wrong.

2. **All pick-slot coordinates are fractions of window width/height, never
   absolute pixels.** The Dota window is measured from its handle at capture
   time. Calibration nudges are stored as fractional offsets too.

3. **An unknown slot is a legitimate state, not an error.** When the perceptual
   hash margin between best and second-best portrait match is too small, the
   slot is marked unknown and scoring proceeds using only confidently resolved
   slots. Silent about one slot beats wrong about one slot.

4. **Item rule stacking is sublinear by design.** When several enemies trigger
   the same item, severities are sorted descending and weighted 1.0 / 0.6 /
   0.4 / 0 — the item saturates because one Nullifier answers three enemies.
   A linear sum would surface the generically applicable over the specifically
   urgent. Do not "fix" this.

5. **Input automation into the game is off limits.** See the boundary above.
   The user reads recommendations in this window and switches to Dota to click
   the pick themselves.

## Other standing decisions

- **Bracket**: user is Legend–Ancient; statistics come from one bracket above —
  Ancient and Divine **combined** (summed wins / summed picks). Two adjacent
  brackets are aggregated deliberately for sample size.
- **Do not trust remembered API field names or bracket numbering** — including
  anything in this file. `tools/inspect_apis.py` dumps raw OpenDota/Stratz
  responses; parsing code validates its schema assumptions against real
  responses and fails loudly. Bracket index mappings are asserted, not assumed.
- **The live scoring loop never makes network calls.** Data is pulled at most
  once daily and cached to disk with a timestamp.
- **Portrait matching is many-to-one**: persona/arcana portrait variants are
  separate library entries mapping to the same hero id. No OCR anywhere.
- **Ranked-role-queue role icons are ground truth** for roles, read from the
  draft screen; a manual override exists in the UI for when reading fails.
- **The item panel is measured vs. asserted**: hero scores come from data; item
  rules are hand-authored in `rules/items.yaml`. The UI labels them as such.
  Item panel shows at most 5 items above a severity floor, only after the
  user's pick is locked. Silence in many games is correct — do not tune it away.
- **Stratz API key** lives in `.env` (`STRATZ_API_KEY=...`), gitignored since
  the first commit, read at runtime. Never hardcode, never commit.

## Development environment split

Claude Code runs on Linux and cannot run Dota, Windows Graphics Capture, or
see the screen. Only the `capture` module needs Windows + Dota; everything
else runs headlessly from saved frames, cached data, or synthetic screens.

- `tools/probe_capture.py` — step-1 probe the user runs on Windows to confirm
  occluded-window capture works before anything is built on top of it.
- The **proving ground** (`draft_assist/proving/`) composites synthetic draft
  screens from downloaded hero portraits and runs the full vision pipeline
  against them, so recognition can be trained/tuned/regression-tested without
  the user sending screenshots.
- The **replay path** runs vision + scoring against saved frames on disk;
  awkward real cases (arcana, persona, empty slot) accumulate there as
  regression fixtures under `tests/fixtures/`.
- Windows-only deps (`windows-capture`, `pywin32`, PyQt6 runtime) are in
  `requirements-windows.txt`; the Linux dev container installs
  `requirements.txt` only.

## Out of scope for the prototype

Ban-phase handling and the personal match-history review tool. Don't preclude
them architecturally; don't build them.
