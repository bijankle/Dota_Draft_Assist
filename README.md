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

### What the game does and does not tell you, measured

Recordings of real matches (~17,000 payloads) settle it, and the answer
splits by phase:

| Phase | What GSI gives you |
| --- | --- |
| Hero selection | Your name, your side, the match — and **no hero but your own**, once you have locked it |
| Strategy time onward | **All ten heroes**, read from the minimap |

The `draft` block is empty (`{}`) in every payload ever recorded, at every
game state, so the picks do not arrive that way. But from strategy time the
minimap names all ten during strategy time, and the app reads them out of
it. **Which ten is reliable; which five are yours is not** — the split is
inferred from the order the game lists them in, and one recorded match came
out reversed. So the app labels it as a guess and gives you **⇅ Swap teams**,
which flips the two rows for the rest of the match. The first reading is
held so a later payload cannot scramble it.

So the app uses **both**, and that is the default — neither is sufficient
alone:

- **Game data says WHEN and WHOSE.** `game_state` means the app knows a draft
  is happening without inferring it from pixels, and `team_name` means the
  left and right banks map to ally and enemy without ever asking you which
  side you are on. Those were the two hardest parts of reading the screen.
- **The screen says WHAT.** During hero selection the picks come from the
  Dota window, via the portrait pipeline.
- **From strategy time**, the minimap line-ups take over — they need no
  pixels at all.
- **Typing still fills the rest.** Precedence is strict and never blended:
  what the game reports outright wins, the screen fills what the game did
  not report, hand-entered slots fill what the screen could not read, and
  whatever is still unknown stays unknown.

`--no-vision` for game data only, `--vision` for the screen only.

### Recording — one button

**You do not have to press anything.** With **Auto** ticked (the default),
the app starts a recording the moment Dota reports hero selection and stops
it a minute after the draft ends. Open the app, play; the session that was
worth keeping is the one you were not expecting.

**Record** is still there to start one by hand — outside a draft, or after
stopping one. Stopping by hand mid-draft stays stopped: Auto will not
restart it until the next match. Everything for one game lands in its own
folder:

```
recordings/2026-09-05_2031/
    meta.json          when it ran and the totals
    gsi/gsi_00001.json every payload Dota sent, verbatim
    frames/00001.png   the Dota window during the draft
    state.jsonl        one line per tick: what the app concluded, and
                       WHICH SOURCE it came from
    report.txt         the above, read back as text
```

The state log is what makes the rest worth keeping: a payload says what the
game sent and a frame says what was on screen, but only the log says what
the app *made* of them, so a wrong pick traces to the source that produced
it instead of being guessed at.

**Every press is its own folder.** Sessions are never pooled — two matches in
one archive made every count meaningless, which is the single thing that most
confused earlier debugging.

**Debug ▸ Recordings** is where everything about a past session lives:
the list, its report, **Copy report**, **Open this folder**, and **Replay
this session** — which sends that recording's payloads back through the app
exactly as Dota sent them. It lists past sessions and shows each one's report — and
it is **one report**, because Record starts the screen and the game feed
together. It covers, in order: what the app concluded tick by tick, where
each reading came from, why it declined when it declined, how the screen's
reading scored against the game's, and what the raw payloads contained.
**Copy report** puts the lot on the clipboard.

#### The report grades recognition against the game itself

During hero selection GSI names no hero, so screen reading cannot be checked
at the time. From strategy time the minimap carries all ten heroes of the
same match — which makes the last screen reading gradeable, hero by hero:

```
SCREEN vs GAME
allies:
  correct : Abaddon, Rubick, Silencer, Windrunner
  missed  : Gyrocopter   (the game had them, the screen did not)
  wrong   : -            (the screen had them, the game did not)
enemies:
  correct : Marci, Sniper, Viper, Zuus
  missed  : Nevermore
  wrong   : Pudge

8/10 heroes read correctly (1 wrong, 2 missed)
A WRONG hero is the serious one: the app advised against a hero that was
never in the game.
```

A reading that matches the *other* team better than its own is reported as
**SIDES WERE SWAPPED** — a mapping fault, not a recognition one, and the two
want different fixes.

Frames start at the button press rather than at hero selection — the queue
and the loading screen are where a capture-binding fault shows up, and by the
draft it is too late to notice. One every two seconds, 600 at most. A press
with no game behind it gives up after thirty minutes, so nothing runs until
the disk fills. A failed write costs the recording, never the draft window:
errors are swallowed and reported in `meta.json`, along with why the session
ended.

**Game ▸ What did the recording contain?** re-derives all of this from your
own archive — per phase, per match — so none of it has to be taken on trust.

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

| Where | Action | When |
| --- | --- | --- |
| **Toolbar** | Record / Stop, Auto | Auto records every draft by itself; Record is for a session by hand |
| **Toolbar** | Recordings, Report | The archive, and the newest session's report |
| **Setup** | Update statistics and portraits | First run, then ~daily and after patches |
| **Setup** | Statistics bracket | Which ranks the numbers come from |
| **Setup** | Set up game data (GSI) | Once, before first use |
| **Setup** | Settings (Ctrl+,) | What the app reads: game data, the screen, auto-record, overlay |
| **Game** | Diagnose game data (Ctrl+G) | When no data is arriving — names the failing step |
| **Game** | Game data status | What Dota is reporting right now |
| **Game** | Clear manual draft | Between games |
| **Game** | Simulate a draft | Test the whole app with Dota closed |
| **Debug ▸ Recordings** | Replay this session | Send a real recording back through the app |
| **View** | Draft overlay (Ctrl+O) | A small badge over Dota that expands into the picks |
| **View** | Reload data and library (F5) | After editing files by hand |
| **Help** | Update application | Pull the latest code from GitHub |
| **Help ▸ Advanced** | Tune recognition, capture probe, debug snapshot, item rules, folders | Diagnosing the app itself |

**Settings** (Ctrl+,) holds the two sources as tick boxes, both on by
default. They are not alternatives — the game feed says *when* a draft is
happening and *which side* you are on, the screen says *what* the picks are
— so turning one off is a debugging step, never a mode. There is no
capture-source menu: capture binds itself to the window titled exactly
`Dota 2` as soon as that window appears, and rebinds if it was pointed
somewhere else.

The window opens even before anything is downloaded and tells you what to do
next. It also opens when Dota is not running: capture is simply unbound, and
the Capture menu lets you pick a source.

**Draft tab** — the draft itself and the role/pick controls sit on the LEFT
with the ranked hero list (never filtered by role; heroes matching your
queued role are highlighted) and a filter box, leaving the right column to
the panels below.

Entering picks: type a few letters and press **Enter** — the pick lands in
the next empty slot on the active side and the box stays focused for the
next one. **Ctrl+Tab** flips between Enemy and Ally; plain **Tab** walks the
ten slots. Clicking an empty slot opens the picker for that slot only and
never chains into the next. A hero already in the draft cannot be entered
again, on either team. **Right-click a slot** to change it, clear it, or
give it a role (Pos 1–5), which then shows on the slot — the role belongs to
the lane, so it survives the hero being replaced — or **move it to the other
team**, which exchanges it with the hero opposite so the draft stays 5v5.
That is for when the game's line-up comes back with one hero on the wrong
side; **⇅ Swap teams** is for when the whole reading is backwards.

Two panels sit on the right, kept apart on purpose:

- **Why this score** — the selected candidate's terms against the heroes in
  *this* game, allies in one bank and enemies in the other.
- **Counters to a drafted hero** — click a filled slot and the heroes that
  beat it are listed here. These are candidates, not picks in this game,
  which is why they no longer share a panel with the breakdown.

**Matrix tab** — what a summed score hides. **Your team against theirs** is
every ally-versus-enemy pairing in a 5x5 grid, positive favouring you: a
comfortable total can conceal one lane that loses badly, and only the cells
show it. **Your team with itself** is the synergy grid, each pair appearing
once — synergy is symmetric, so the lower half would only repeat the upper.

Every table sorts on click, and on the **numbers behind** the cells rather
than their text — sorted as text, `+9.0` lands above `+10.0` and a percentage
column comes out alphabetical. A sort you choose survives the once-a-second
refresh. **Why this score** puts allies and enemies in two banks side by
side, each ordered by size so the terms that actually moved the number are on
top; clicking one bank's heading re-sorts only that bank.

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

### Calibration

Slot coordinates are fractions of **Dota's 16:9 HUD area**, not of the
window: Dota pillarboxes its HUD, so on a 3440x1440 ultrawide the portraits
occupy the middle 2560 pixels and a fraction of the full width lands 440
pixels to the left. The app accounts for that, so one calibration holds
across resolutions.

If the crop boxes in **Debug ▸ Live** still do not sit on the portraits
during hero selection, the **Crop boxes** panel underneath nudges them —
left bank, right bank, top, width, height, spacing — and the boxes move on
the picture as you turn the numbers. **Save** writes
`calibration_local.json`; **Reset to defaults** undoes it.

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

## Testing without Dota

Four options, in increasing fidelity:

| Option | Exercises | Needs |
| --- | --- | --- |
| `--demo` | The interface only — state is injected straight into the UI | nothing |
| `--manual` | Scoring, the hero picker, item rules | nothing |
| **Game ▸ Simulate a draft — full teams** | **The real path: HTTP listener, auth, parser, provider, UI, overlay** | nothing |
| **Game ▸ Replay recorded game data** | The same path, with payloads Dota actually sent | one recorded match |

The simulator is the useful one. It POSTs Game State Integration payloads to
the running app exactly as Dota would, so the plumbing gets tested rather
than bypassed — every bug found here so far (auth token mismatch, two copies
sharing a port, a stale status bar) lived in that plumbing, and `--demo`
would have caught none of them.

```
python tools/simulate_gsi.py --with-draft --loop   # what the menu runs:
                                             # both teams fill in, repeating
python tools/simulate_gsi.py --loop          # as real GSI behaves: your
                                             # hero only, enemy slots stay
                                             # empty on purpose
python tools/simulate_gsi.py --from data_cache/gsi   # replay REAL payloads
```

Every line it prints is derived from the payload actually sent — game state,
whether your hero is in it, how many picks the draft block carries — so the
log can never claim content the data does not contain.

Start the app first, then run it (or use the menu item). The simulate and
replay dialogs are **modeless on purpose** — they feed the draft panel, so
you keep clicking heroes and reading the synergy/counter breakdown while the
picks arrive. Closing the dialog stops the feed.

Note the honest limit: modelled payloads are this codebase's own belief about the format
echoed back, so they can confirm the app handles what it expects, but they
cannot discover that a real field is shaped differently. Recording one real
match with the toolbar's **Record** button and replaying it is a strictly
stronger test.

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
pytest            # 275 tests: normalisation math, scoring views, item
                  # engine, GSI config/listener/parsing/provider/diagnostics,
                  # vision end-to-end on synthetic screens, gate & session
                  # state machine, overlay, and headless UI smoke tests

python -m draft_assist.ui.app                    # game data (GSI)
python -m draft_assist.ui.app --manual           # hand-entered draft
python -m draft_assist.ui.app --vision           # screen-capture fallback
python -m draft_assist.ui.app --demo             # UI on a scripted draft
python tools/probe_gsi.py --minutes 10           # what does GSI really send?
python tools/inspect_recording.py               # the newest session's report
python tools/inspect_recording.py --from recordings/2026-09-05_2031
```

See `CLAUDE.md` for the domain invariants (normalised deltas, fractional
coordinates, unknown-slot semantics, sublinear item stacking, the
no-game-interaction boundary).
