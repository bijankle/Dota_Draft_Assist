# Dota Draft Assist — domain facts and invariants

Personal-use Windows desktop app that reads the current Dota 2 draft and
shows hero/item recommendations in its own ordinary window. Single user, no
distribution, no installers.

**Draft state comes from GSI and the screen together, because measurement
showed neither is sufficient alone** (see the GSI evidence below). GSI —
Valve's own channel, a config file asking the game to POST JSON to a local
port — supplies the phase and your identity, which is what tells the app a
draft is happening and which bank is yours. It names no hero during hero
selection, so the picks themselves are read from the Dota window by the
vision pipeline until the minimap starts carrying them at strategy time.
Hand-entered slots fill whatever neither produced.

Precedence is strict and never blended: game-reported line-ups > screen >
hand entry > unknown. `HybridProvider` is the default. The two sources are
tick boxes in Settings (`use_gsi`, `use_vision`, both on) rather than
mutually exclusive menu commands — they answer different questions, so
turning one off is a debugging step, never a mode. `--no-vision` and
`--vision` do the same from the command line.

**Capture binds itself.** `LiveProvider` re-looks for the window titled
exactly `Dota 2` every few seconds whenever it is not bound to it, because
binding once at startup left a real session capturing a File Explorer
window called "Dota_Draft_Assist" for a whole draft. A title the user
asked for explicitly is never overridden.

## Non-negotiable boundary

The app **never** injects code into the Dota process, hooks its rendering or
presentation chain, reads its memory, or sends synthetic input to it. It
consumes data the game itself publishes (GSI), plus — only when explicitly
enabled — pixels from a window already visible on the user's own screen. If a
feature seems to require crossing this line, stop and say so instead of
implementing it.

This rules out the Steam Game Coordinator route: libraries that log in as a
second Steam client to read live match data are unofficial, need account
credentials, and put the account at risk. Do not go there.

## Domain facts not guessable from the code

0. **The score is DRAFT FIT, and the hero's own win rate is not in it.**
   `score_all` ranks on `vs_total + with_total` alone: zero means the ten
   heroes on the board neither help nor hurt this candidate. The question
   the list answers is "what does this draft do to this hero", never "is
   this hero good" — a baseline term floats the strong heroes to the top of
   every list regardless of the draft, which is the one thing the list is
   not for. This is one definition used everywhere (ranked list, overlay
   rows, breakdown subtitle) so two surfaces can never disagree about which
   hero is best. The cost is real and is why `ScoredHero.baseline` is still
   carried and still displayed, labelled as not scored: a weak hero with
   good matchups now outranks a strong hero with neutral ones, and nothing
   in the ordering will tell you so.

1. **Matrices hold normalised deltas, never raw win rates.** Every matchup and
   synergy figure is converted at ingestion into a delta relative to what the
   two heroes' individual baseline win rates would predict. Raw rates are
   contaminated by hero main effects; we want only the interaction term. If a
   stored matrix ever contains raw rates, every recommendation is wrong.

2. **All pick-slot coordinates are fractions of Dota's 16:9 HUD box, never
   absolute pixels and never fractions of the raw window.** Dota pillarboxes
   its HUD into a centred 16:9 area, so on 3440x1440 the portraits live in
   the middle 2560 pixels; `layout.hud_box()` supplies that offset and every
   `SlotRect.to_pixels` goes through it. Treating them as fractions of the
   full width put the crop boxes 440px left of the portraits on a real
   ultrawide session. The vertical axis needs no correction — the bar hugs
   the top edge. Calibration nudges are fractional too, and are edited live
   in Debug ▸ Live with the boxes drawn on the picture.

   **When measuring fails, the user DRAWS it** (`ui/framebox.py`,
   `autocal.measure_bank` / `layout_from_banks`). Six numbers, each a
   fraction of the HUD box rather than of the window, is not something
   anyone can convert "the boxes are 135 pixels left of the portraits"
   into — the user could see exactly what was wrong and had no way to say
   it, which is where "how the fuck do I calibrate these boxes" came from.
   Debug ▸ Live takes ONE BOX ROUND EACH BANK, either order, and measures
   the rest.

   A box round five portraits spans four pitches plus one portrait, which
   is one equation for two unknowns — so a first attempt asked for three
   rectangles (first portrait, fifth portrait, other bank) because the gap
   between portraits could not be derived. It does not have to be derived:
   it is IN THE PICTURE. Portrait content differs per hero and repeats
   nothing, but the borders between them are the only periodic feature in
   a pick bar, so `measure_bank` fits (start, pitch, width) against the
   per-column edge profile and takes the fit that lands all ten predicted
   boundaries on an edge. Scored on the sum AND the WEAKEST of the ten,
   because the sum alone cannot tell the right fit from one whose portrait
   width equals its pitch — that one puts every right edge on top of the
   next left edge, scores the same five edges twice, and lands a whole
   portrait out.

   All four sides are FITTED, not taken from the drag, because nobody
   draws a rectangle within a few pixels of anything and a span 2% wide
   misplaces the fifth portrait by a tenth of a portrait. Horizontally
   that is free — ten edges agree with each other. Vertically there are
   only two, so the top and bottom are pulled towards the drawn box rather
   than snapped hard onto whatever row edge happened to be strongest.
   Measured against synthetic bars at four resolutions with the drags up
   to 12px sloppy: within 3px horizontally, 6px vertically. A flat picture
   fits nothing, so it falls back to five equal slots and SAYS SO rather
   than reporting noise as a measurement. Which bank is which is decided
   by x, since Radiant is always the left bank.

   **Use a saved picture…** loads a saved frame off disk so this can be
   done without Dota on screen — `debug_out/<stamp>/frame.png` from Ctrl+S,
   or any `recordings/<stamp>/frames/00042.png` — because making
   calibration wait for a live game is what made it never happen.

   **A MEASUREMENT NEVER OVERWRITES WHAT THE USER CALIBRATED.**
   `_adopt_measured_layout` claimed in its own docstring to save "the first
   time and never again" and had no such guard: it fired on every
   measurement, so boxes dragged onto the portraits and visibly landing
   were silently replaced by whatever the next match measured. A
   calibration the user set is an ANSWER; an automatic measurement is a
   guess, and the guess does not get to overwrite the answer. It is adopted
   only when `CALIBRATION_FILE` does not exist — a fresh install — and
   otherwise says it was kept. Setup ▸ Measure from this game is how you
   ask for the new one deliberately.

   **`load_layout` and `save_calibration` resolve the path at CALL time**,
   never as a default argument. A default is evaluated once at import, so a
   test that repointed `CALIBRATION_FILE` still wrote into the real
   repository — which is how a test run left a stray
   `calibration_local.json` behind and broke an unrelated test on the next
   run. Same rule as `ui_settings.load`.

   **The layout is measured, not guessed** (`vision/autocal.py`). At
   strategy time the app holds a frame AND the ten heroes the minimap named
   in it, so it searches for those portraits by normalised cross-correlation
   and reads the bank starts, pitch, size and top edge off where it finds
   them. This exists because the person who can see the screen and the code
   that sets the numbers are not in the same place — hand calibration
   stalled for days with the boxes hundreds of pixels off and no way to see
   it. Matching is sharply scale-sensitive (0.99 at the true size, 0.12 four
   pixels out), so the size is found on a coarse width x height grid from
   two heroes and then refined a pixel at a time; searching per hero would
   be ten times the work for one answer. Round-trip tested to under a pixel
   on synthetic pick bars at 16:9 and 21:9.

2b. **The GAME outranks the gate, and until it did the app was blind for
   the whole draft.** The gate (`capture/gate.py`) is an economiser: a
   cheap signature comparison deciding whether this looks like a draft
   screen, so the expensive recognition is skipped in the menus. Its
   references are HARVESTED from whichever screen confirmed first, so a
   set harvested at strategy time does not describe hero selection — one
   real session sat at **gate 0.707 against a 0.50 threshold for the whole
   of hero selection**, recognised nothing, and filled in only once every
   pick was already made. Which is the one moment the app exists for.

   GSI reports `HERO_SELECTION` outright, so `HybridProvider.poll` sets
   `CaptureSession.set_required(...)` from `DRAFTING_STATES` and the guess
   loses its vote. The gate still earns its keep when the game feed is off
   or silent. Recognition then confirms the screen and saves a gate
   reference for it, so the gate learns hero selection as a side effect.
   Two traps in that code: the recognition condition must be re-asked
   AFTER the state machine runs, never reusing the `active` flag computed
   before it — otherwise the tick that deactivates also reads — and
   `last_frame` is published on EVERY tick, not only when recognition
   runs, because a session that never tripped reported `frame=none` and
   left the debug view blank exactly when a picture is what you need.

   **`required` has THREE values, because silence is not a no.** True is
   "the game says a draft is on", False is "the game says it is not", and
   None is "the game is not saying" — `HybridProvider.poll` passes None
   when `game_state` is blank. Collapsing None into False put the gate
   back in sole charge whenever GSI was down, which is exactly when it has
   no help: one real ranked game with the feed dead read four heroes in
   two seconds, missed four gate checks, went idle, and never looked again
   for the remaining twenty seconds of a draft that was still on screen.

   **A silent feed buys a PROBE** (`session._should_probe`, `PROBE_PERIOD`
   3s, `PROBE_SLOTS` 2). The gate is self-sustaining when it is wrong: its
   references are harvested from frames recognition confirmed, so a gate
   that does not recognise hero selection never gets a hero-selection
   reference and goes on not recognising it. The probe is the way out —
   one recognition every few seconds against the gate's advice, and when
   the library resolves two or more heroes INSIDE the calibrated boxes,
   under the distance ceiling and over the margin floor, that outvotes the
   gate and the session goes active. A menu does not produce two confident
   portrait matches at those coordinates. It runs only while `required is
   None`: when the game says a draft is on there is nothing to probe for,
   and when it says one is not, that is an answer.

   **Going idle no longer throws the reading away** (`FORGET_AFTER`, 30s).
   Deactivating used to null `last_read` and reset the stabiliser, so four
   missed gate checks — four seconds — deleted every pick the app had
   already read. That is what "it found four heroes and then showed none"
   was, and a pick does not un-pick. Idle now only drops the cadence; the
   reading is forgotten after thirty continuous seconds of not-the-draft-
   screen, which is a different game rather than a wobble.

3. **An unknown slot is a legitimate state, not an error.** Whether a slot is
   unresolved because GSI did not report it or because a portrait hash margin
   was too small, it is marked unknown and scoring proceeds using only the
   slots that ARE known. Silent about one slot beats wrong about one slot.
   Slots are never guessed; the user can always click one in by hand.

4. **Item rule stacking is sublinear by design.** When several enemies trigger
   the same item, severities are sorted descending and weighted 1.0 / 0.6 /
   0.4 / 0 — the item saturates because one Nullifier answers three enemies.
   A linear sum would surface the generically applicable over the specifically
   urgent. Do not "fix" this.

5. **Input automation into the game is off limits.** See the boundary above.
   The user reads recommendations and switches to Dota to click the pick
   themselves.

## Other standing decisions

- **Bracket is a user setting, not a constant.** The user plays Legend and is
  climbing to Ancient, so the DEFAULT is one bracket above — Ancient and
  Divine **combined** (summed wins / summed picks), two adjacent brackets
  aggregated deliberately for sample size. It is changed in the app (Data >
  Statistics bracket) and stored in `preferences.json`, read at call time by
  `config.target_brackets()` so the app and the pull subprocess always agree.
  Because baselines and matrices are BUILT for the chosen brackets, changing
  it invalidates the cache: the dataset records its own `target_brackets` and
  the UI banners a mismatch rather than showing one bracket's numbers under
  another's label.
- **Do not trust remembered API field names or bracket numbering** — including
  anything in this file. `tools/inspect_apis.py` dumps raw OpenDota/Stratz
  responses; parsing code validates its schema assumptions against real
  responses and fails loudly. Bracket index mappings are asserted, not assumed.
- **What GSI reports is settled by evidence, and the answer splits by
  phase.** Recordings of three real matches (~17,000 payloads, fixtures in
  `tests/fixtures/gsi/`) say:

  - The `draft` block is **`{}` in every payload ever recorded**, at every
    game state. It is not a shape the parser misreads; there is nothing in
    it. Community lore that `draft` is spectator-only is consistent with
    this. Do not write code that expects it to fill.
  - During `HERO_SELECTION` the feed names **no hero but your own**, and
    only once you have locked it in — as three origin duplicates that carry
    no line-up. One recording named nothing at all across 58 payloads;
    another named only the player's own hero across 156. Either way nothing
    about the other nine picks arrives while picking, which is why the
    screen is read and the quick-entry bar exists.
  - From `STRATEGY_TIME` onward the **minimap carries all ten heroes**, and
    `gsi/minimap.py` reads both line-ups out of it. Too late to choose a
    pick, in time for items and lane matchups.

  How the minimap is read, and what is still unsettled. Five recorded
  matches; none of this is documented by Valve:
  - **The PLACED heroes are the line-up.** Ten placed and the origin is
    ignored entirely. Origin `(0,0)` entries are a mixed bag: duplicates of
    the player's own hero, and in one recording Faceless Void, which was in
    no lane and not in the match at all. Keeping every origin entry that
    was not placed elsewhere gave ELEVEN and refused a good reading.
    Origin entries are drawn on only when fewer than ten are placed (a
    player with no lane chosen), in object order, until exactly ten; if
    that cannot land on ten the reading is refused.
  - What remains is exactly ten heroes. **That part is solid.**
  - **WHICH FIVE ARE YOURS IS NOT SOLVED — but only after the draft.**
    While picking, the picks come from the SCREEN, where Radiant is always
    the left bank of the top bar and Dire the right, and `player.team_name`
    says which of those is yours: no ambiguity, and no swap is offered
    during `HERO_SELECTION`. The problem is confined to the minimap reading
    at strategy time, which is post-pick. Splitting the ten into two runs
    of five in object order and taking the run holding the player's own
    hero looked right on four recordings and came out INVERTED on a fifth,
    putting the player with four heroes from the other team. Nothing found
    so far distinguishes the sides: the `team` field is constant, the lane
    slots are placements (two team-mates share one), and object order is
    not reliably team order. So `Lineups.sides_certain` is False and the
    note says the split is a guess. Do not re-assert it as fact without
    evidence that settles it.

    **The rule is still unsolved, but the app no longer needs it**
    (`vision/lineup.py`). The minimap is reliable about WHICH ten and
    unreliable about whose five; the screen is the other way round, because
    Radiant is always the left bank of the pick bar and `player.team_name`
    says which bank is yours. So `HybridProvider._resolve_sides_by_sight`
    takes the ten from the game and their POSITIONS from the picture, and
    the answer stops being a guess: `sides_certain` becomes True and
    `lineup_source` becomes `minimap+screen`. This is easier than
    recognition proper — the question is "which of THESE TEN is in this
    box", with the answer guaranteed to be a permutation, so a mistake
    needs two heroes to out-match each other in each other's slots rather
    than one hero to beat 125 rivals. Two paths: **placed** scores the ten
    calibrated crop boxes against the ten candidates (a hundred small
    correlations, milliseconds) and **searched** hunts each across the top
    strip at unknown scale (`autocal.locate`, hundreds of correlations), so
    the search runs at most ONCE PER MATCH and the result is latched per
    (match, the ten). Anything short of ten confident distinct heroes in
    two banks of five returns `ok is False` with a reason and the caller
    keeps the guess it had — a wrong split asserted confidently is worse
    than a guess the user is already correcting.

    **The search runs on a WORKER, and it calibrates on the way out.**
    Measured on a real 3440x1440 session it took **25.6 seconds inside one
    tick**, with the window frozen — the freeze the user reported. Three
    things were wrong and all three are fixed. The scale grid searched at
    full resolution: 19 widths x 17 heights x 2 probes is 646 correlations
    over a 3440x432 strip, so `autocal.find_scale` now runs the coarse pass
    on a strip decimated to `SEARCH_WIDTH` and walks back to exact size at
    full resolution — 17.9s to 3.4s on the synthetic bar, with the measured
    layout unchanged to four decimal places. Three seconds is still a
    freeze, so `HybridProvider._read_or_start_search` starts it on a thread
    and the answer is picked up on a later tick, on a COPY of the frame
    because the capture session overwrites its buffer. And it ran EVERY
    match because nothing kept what it found: a successful search has
    already located every portrait's position and size, so
    `_remember_measured_layout` turns that into a `DraftLayout` and
    `MainWindow._adopt_measured_layout` saves it — after which the cheap
    placed path works and the search never runs again.

    Corrections stay, and they are all per-match, cleared on a new match id:
    **drag a hero onto the other team** exchanges it with whatever it is
    dropped on (an exchange, never one-way — a 5v5 cannot become 4v6), and
    **drag within a team** swaps two positions, because the order is meant
    to be the pick bar's and the feed does not reliably give that.
    **Swap teams is gone**, and so is the correction-pattern memory that
    briefly replaced it: flipping all ten was useless for the case that
    actually happens (own hero right, the other four wrong), and a habit
    learned from corrections is not evidence — reading the screen is.
  - Guards on the ten: exactly ten entries after de-duplication, ten
    distinct heroes, all resolvable, own hero among them. A failed check
    yields **nothing**, never a guess.

  **The lane slots ARE the split, which reverses this file's earlier
  conclusion.** Across all five recordings the placed heroes stand in
  exactly five positions — `(176,-370)`, `(176,370)`, `(752,-144)`,
  `(752,144)`, `(1088,0)` — with exactly TWO heroes in each. That is the
  strategy map: your five where you put them, theirs where you predicted.
  `minimap._split_by_lane_pairs` groups by position, orders each pair by
  object index, and takes the set holding the player's own hero. It cannot
  produce a 4-1 team, which is what the run split kept doing.

  The earlier claim that "two team-mates can share a lane (pudge with axe,
  dragon knight with juggernaut)" was read OFF THE RUN SPLIT — the very
  thing in question — so it never was evidence, and the previous attempt's
  failures are explained without the pairing being wrong: recording 4 had
  only nine placed (one player chose no lane) so a slot held one hero, and
  recording 2's pairs contradict the runs, which is evidence against the
  runs.

  **The pairing is corroborated; the TIE-BREAK is not, and is known wrong
  at least once.** In one recording the screen resolved the same ten
  independently and its split took exactly one hero from each lane pair —
  the first confirmation of the pairing from a source that knows nothing
  about it. But it disagreed with the index tie-break on four of the five
  pairs: the screen put the player with the HIGHER-indexed half of each
  pair, while an older recording has the player with the LOWER half.
  Object index does not decide it, and nothing found so far does. Do not
  ship a rule that claims to.

  So `sides_certain` stays False, the note names the rule that produced the
  split ("lane pairs" or the "object order" fallback) and calls the halves
  a coin flip, and the drag correction stays. What the pairing still buys,
  whichever way the coin lands, is a 5-5 split with one hero from each lane
  — the app can no longer show a 4-1 team, which is what it kept doing.
  When the positions do not pair cleanly it falls back to the runs rather
  than refusing.

  **Only `STRATEGY_TIME` is read**, and the first complete reading is
  latched for the match by `GsiProvider`. After strategy time the minimap
  holds real units rather than strategy-map slots and the object order
  means something else: one recorded session produced a correct split at
  16s and a scrambled one at 43s from the same match. The latch clears on
  a new `HERO_SELECTION` or a new match id.
  **The FIRST complete reading, and only the first.** Re-latching on every
  payload that carried ten let the reading wobble for the whole of strategy
  time — one real recording moved heroes between teams eight times in
  thirty seconds while the user was reading it. The guard is
  `self.latched is None`, not just "ten are present".

  **The `team` field is not usable AT STRATEGY TIME**, where every object
  in every recording says `team 2` — with the player on Dire in one and
  Radiant in others. Constant there, so it distinguishes nothing.

  It is NOT constant everywhere, which corrects an earlier claim in this
  file: during `HERO_SELECTION` one recording carried both `team 2` and
  `team 4`. Those hero-selection entries are junk for our purposes — that
  payload named nyx_assassin, venomancer, snapfire, bristleback and oracle,
  and only one of the five (axe) was in the match at all; they are pick-
  screen models and hovers, at scattered positions with odd `yaw`. The
  parser ignores hero selection entirely, which is why this never leaked
  into a reading. Do not start trusting `team` on the strength of the 2/4
  split without establishing what team 4 means.

  **Ground truth, once, and it killed the rule.** For one match the user
  named the real teams: Radiant = Bristleback, Necrophos, Drow Ranger,
  Lion, Witch Doctor; Dire = Axe, Vengeful Spirit, Sven, Warlock, Sniper.
  The two runs of five the app produced were `R D D D D` and `R D R R R` —
  **neither run is a team**, each holds exactly one hero from the other
  side, and only the player's own hero was right. Worse than chance.

  The shape of the error is a SWAP: move Bristleback and Axe between the
  runs and both become clean teams. So the ordering is nearly right and
  two entries are transposed, which is a lead — but the payload for that
  match has not been seen, so nothing has been changed on the strength of
  it. Get the payload before touching the rule again. The session report
  now dumps the fullest payload per DRAFT rather than per session, because
  that session held two games and the one being asked about was never the
  one shown.

  **Open lead:** in `PRE_GAME` the minimap carries exactly five hero
  objects (`o86`–`o90` in one recording, 163 payloads). Five, not ten, is
  what vision-limited data looks like — so those five are plausibly the
  player's own team, which would settle the split. Unverified; measure it
  before building on it.

  **A dead game feed is a BANNER, not a status segment.** It was one
  pipe-separated segment at the bottom of the window, between the capture
  mode and how old the statistics are, and it went unread through a whole
  ranked game — "where is the warning line" is a fair question about that.
  `_update_first_run_banner(snap)` now puts it in the strip at the top,
  ahead of everything about the statistics, because it is the fault that
  costs a draft; the button becomes **Check game data** and opens Game ▸
  Diagnose game data. The banner's button is dispatched through
  `_banner_action` rather than hard-wired to the data download, since the
  banner says several different things. The warning also leads the status
  line instead of coming fourth.
  **Only a fault the user can FIX raises it** (`gsi_setup_broken`,
  `providers.NOT_A_FAULT`). Dota not being open is silence too, and so is
  a match not having started; a banner that is up all evening is one
  nobody reads on the night it matters.

  **"No data from Dota" names the ONE broken link** (`gsi/diagnose.
  run_checks`, `GsiProvider._why_silent`). GSI has several independent
  requirements and gives no feedback when one is missing — Dota simply
  says nothing — so the symptom is identical whichever link is down, and
  the app used to answer it with the whole checklist. The checks already
  test each link separately (install, config file, config/listener port
  agreement, launch option, who owns the port, is Dota running, what
  arrived), so the warning is the FIRST failing one and its fix. Cached
  for `DIAGNOSE_PERIOD`: it reads Steam's `localconfig.vdf` off disk and
  opens a socket, which is not a per-tick cost. `install_hint` is gone —
  it was check 1 of 7, guessed at ahead of the other six.

  `GsiState.lineup_source` says which of these produced the picks, and the
  UI shows it. `PLAYER_COMPONENTS` / `SPECTATOR_COMPONENTS` are a guide to
  what to look for, never a claim about what arrives: the same recordings
  carried `buildings`, `minimap`, `roshan`, `couriers` and `neutralitems`
  in a player's own feed, which this file had listed as spectator-only.
  All of the above is re-derived from a recording, per phase and per match,
  as one section of the session report.
- **The draft panel refuses duplicates, and everything about a pick is on
  the pick.** A hero already in the draft cannot be entered again on either
  side — `_taken_heroes()` is the single source for that. Right-clicking a
  tile changes it, clears it, moves it across, names it as YOUR pick and
  locks it, and sets its role: two dropdowns above the board naming the
  same hero a second time was a worse way to say all of that. The role that
  filters item advice is therefore wherever your own hero and its slot's
  role meet (`_my_role`), so there is no separate answer to keep in sync.
  Roles (Pos 1-5) are assigned per SLOT, not per hero, and survive the hero
  changing: a slot is a lane. `ROLE_BY_LABEL` is the one place "Pos 1"
  becomes "carry". Vision reads the ranked-role icons but is not
  wired to these yet — that waits on the crop geometry being right. Each
  slot reserves a line ABOVE it for the click view's signed number whether
  or not one is showing: slots that grew by a text height on every click
  made the column restless, and a draft panel that moves under the cursor
  is one you misclick.
- **The Draft tab reads top to bottom as one argument**: the board, then
  which hero to take, then what to build. The ten picks are at the very
  top because they are the subject; **Suggested picks** (`ui/suggest_row.
  py`) is the Analysis tab's ranked list cut to its head — best draft fit
  on the left, descending right, the same order and the same numbers,
  because it IS that list rather than a second opinion; the item strip
  follows, and the two grids sit at the bottom under the sides they
  describe. 120 rows of ranking beside the ten picks was why the list
  lived on another tab, and eight tiles is not 120 rows. The strip stays
  blank until at least one hero is on the board: with an empty draft every
  fit is zero, so it would be ranking nothing while looking like a
  recommendation. Nothing in it is clickable — a pick is entered by
  clicking a SLOT, and a second way to do it that behaved differently
  would be worse than no way.
- **The panel that narrated the reading is gone from the Draft tab.** It
  said which source produced the line-up, how many slots were unresolved
  and offered the left/right bank picker — all of which the tab already
  showed: an unresolved slot draws as "+", the source is in the status
  bar, and a wrong side is fixed by dragging the tile rather than by
  reading a sentence about it. The widgets moved to Debug ▸ Live under
  "What the app is reading", where the rest of "what did it conclude and
  from where" lives. Note for tests: a widget on a tab that is not current
  is hidden BY THE TAB WIDGET, so `isVisibleTo(window)` there answers "is
  this the open tab", not "did the app hide this" — ask `isHidden()`.
- **The Draft tab is the whole board and nothing else.** Your five on the
  left, theirs on the right (`ui/teams.py`), because that is where they sit
  on the pick bar, with the two grids directly under the sides they
  describe: counters (`scoring.matchup_matrix`) on the left, synergy
  (`scoring.synergy_matrix`) on the right. A comfortable total can conceal
  one lane losing badly, which is what the grids exist to show; the synergy
  grid fills only the upper triangle, since synergy is symmetric and the
  diagonal means nothing. Everything that ranks heroes NOT in the game —
  the ranked list, the filter, "Why this score", the counters list and the
  items panel — moved to the **Analysis** tab, because 120 candidates
  beside the ten picks made the ten harder to read. There is no longer a
  separate Matrix tab.
- **Every tile in the app is the same tile** (`ui/tilekit.py`). There are
  three strips of them — the ten picks, the suggested picks and the items
  — and they had drifted into three designs: hero names 11pt bold on a
  tinted band above the art, item names 9pt plain with no band under it,
  and nothing saying they were the same kind of object. The name band, the
  number badge, the fitted art and the point sizes now live in one module
  and the tiles are the layout around them. One size for both names, 10pt,
  between the two they had. A change to how a tile looks belongs there,
  not in one of the three.
- **Each pick is a TILE, not a row** (`teams.HeroTile`): the hero's own
  portrait behind, the name across the top, the signed number in the
  bottom-right, five across per team. That is the shape the same ten picks
  have on Dota's own pick bar, so the eye arrives knowing the layout, and
  it costs a fifth of the height five full-width name buttons did. The art
  is the recognition library's (`ui/portraits.py`,
  `assets/portraits/base/`), so it costs nothing to draw — but a missing
  portrait is NORMAL, not an error: a fresh install has none and the tile
  draws plain. `text()` still reads "Pos 3 · Necrophos", so the tile is a
  drop-in for the button it replaced.
  **The name does not sit on the art**: it gets its own strip above it,
  because a label over a portrait hides the half of the portrait you
  recognise the hero by, and the art is only worth drawing because it is
  quicker to read than the name. The number sits in a small tinted badge in
  the bottom-right, the same tint as the strip and cut to the size of the
  digits — a full-width bar there would hide as much as the name used to.
  **A tile is SQUARE and capped, and the panel sizes it** (`TeamPanel.
  _resize_tiles`, `TILE_MIN`/`TILE_MAX`). Letting Qt hand each tile the
  leftover width at a fixed height meant full-screening the window
  stretched every portrait into a wide slice with the hero's head cropped
  off; the panel now computes one square edge from the width available and
  gives the remainder to the margins. The art is then scaled to FIT that
  square, never to fill it, so the whole portrait is visible and the window
  aspect can never distort it — the dead space above and below a wide
  portrait is where the name band and the number go. Names shrink to fit
  and wrap to two lines before they elide, because the name is the thing
  the panel exists to show. Tests must actually RENDER every tile state:
  the portrait branch shipped once with a mistyped Qt enum and nothing
  caught it, because no test had a portrait on disk to take that branch.
- **The item strip lives under the draft and is live from the first enemy
  pick** (`ui/item_row.py`, `ui/item_icons.py`). It was a paragraph of
  prose in a side panel gated behind locking your own hero, so on the
  screen where items matter it was blank, and by the time it filled the
  decision it informed was made. Icons rather than names because the strip
  is read in the corner of the eye — a player recognises a BKB by its shape
  long before reading the words — with the strongest trigger's severity as
  the whole reasoning in the tooltip and behind a click, since a strip
  that explained itself in place would be the paragraph again. **There is
  no severity bar under the icon**: the strip is already ORDERED by
  severity, so the bar said in colour what position was already saying.
  **Each strip's tile takes its own art's aspect** — a hero portrait is
  16:9, an item icon is Valve's 88x64 — sharing only the HEIGHT, so the
  strips line up with each other without any icon sitting in a box wider
  than itself. A tile wider than its picture is dead space either side of
  every icon, which reads as the items being spaced further apart than the
  heroes above them. Icons are
  downloaded with the portraits into `assets/items/`, named by a slug of
  the DISPLAY name so `rules/items.yaml` can go on saying "Black King Bar"
  the way a person writes it; a missing icon draws the name and is normal,
  not an error. Role and own-hero filtering still apply once known — they
  just no longer gate the panel.
- **There is no hero-entry bar.** Typing a pick, the ally/enemy toggle and
  Undo are gone at the user's request; a pick is entered by clicking a slot
  and using the picker. `_taken_heroes()` still refuses duplicates.
- **Fixing the draft by hand is a DRAG** (`HeroTile.dropped_on`,
  `_on_slot_dropped`). Onto the other team, it EXCHANGES the two heroes,
  because a 5v5 cannot become 4v6 and a hero on the wrong side almost
  always has an opposite number in the same boat. Within a team, it swaps
  their two positions (`_swap_positions` → `slot_order`, applied by
  `_apply_order`), because the order is meant to be the pick bar's and the
  feed does not reliably give that. Both are per-match and cleared on a new
  match id, and the order override is stored as an explicit list rather
  than a permutation so a reading that changes underneath it degrades to a
  partial order rather than dropping a pick. **Test the Qt drag path, not
  just the handler**: the handler had tests and the machinery reaching it
  did not, and a drag that never starts looks exactly like a feature that
  does not exist.
- **Captions are gone from the grids.** The card heading says which grid it
  is ("Counters", "Synergy") and the row and column headers say what the
  axes are; a paragraph repeating both only stands between the reader and
  the numbers. `MatrixTable.set_compact(short_names=...)` separates the two
  jobs: dropping the caption is for everywhere, while short names, fixed
  narrow columns and a height fitted to the rows are the in-game callout's
  layout alone — applying them in the main window shrank the grid to a
  fitted block floating in a half-empty card.
- **Each grid sits under the team whose heroes head it, and its headers
  are their portraits.** Synergy is ally-by-ally so it goes under your five
  on the LEFT; counters are read against theirs, so its columns go under
  theirs on the RIGHT. A column then reads straight down from the tile it
  is about — which is the whole reason the headers are the same pictures
  rather than the names a second time. **Qt will not draw those icons.** A
  QHeaderView under a stylesheet ignores `iconSize` and falls back to the
  style's 16px small-icon metric, and no property changes it; `tables.
  PortraitHeader` paints the pixmap in `paintSection` instead, which is a
  dozen lines and the only reliable way.
  **Both headers must be given ONE box** (`_apply_icon_box`,
  `PortraitHeader.set_box`), because they scale from different
  measurements and nothing on screen says why: a column header's section
  is (stretched column width) x (fixed header height) while a row
  header's is (fixed header width) x (row height), so each portrait is
  limited by a different number — which is how a wide window ended up with
  large portraits along one axis and small ones along the other. One WIDTH
  is chosen for both, growing with the columns to `HEADER_ICON_MAX`, and
  the sections are then cut to what that actually draws: a portrait is
  256x144, so a square section would be 40% empty space and every row 40%
  too tall. The height is MEASURED off the scaled pixmap rather than
  assumed. With no portraits downloaded the headers fall back to names and
  the box stays at the floor — growing a text header to 68px elides
  "Tidehunter" and makes every row 68px tall for nothing.
  The Σ row and column are OFF in the main window (`set_margins(False)`):
  each tile already carries that hero's total in its corner and the same
  figure twice is once too many. They stay available for the callout, and
  `Matrix.row_totals` / `col_totals` / `total` still sum what is DRAWN —
  in the synergy grid only the upper triangle is filled, so a hero's row
  and column totals are each partial, and consistency with the cells above
  the number was chosen over completeness. Columns STRETCH rather than fit
  their contents: nothing should be pushed off the right edge.
- **Clicking a pick is the matrix read one row at a time**
  (`scoring.relations_to`, `MainWindow.focus` / `_update_relations`). It is
  context-aware, because an ally and an enemy are different questions: an
  ally shows synergy above your other four AND matchup above all five
  enemies; an enemy shows matchup above your five and says nothing about
  the other enemies — their pair-ups are their synergy, not ours. Clicking
  the focused hero again clears it, so the way out is the way in.
  **Every number reads from YOUR team's point of view**: positive is good
  for you whichever portrait it sits under. Without that rule a green
  number under an enemy would mean the opposite of a green number under an
  ally, which is the misreading the view exists to prevent.
  With nothing clicked the tiles rest on `scoring.net_contributions` — what
  each pick is worth overall — rather than going blank, since the tile
  reserves the line either way. An ALLY's figure is its synergy with your
  four plus its matchups against their five; an ENEMY's is how your five
  fare against it LESS its synergy with its own four, sign flipped, because
  a hero that combos with their line-up is our problem, not their bonus.
- **The palette is Discord's dark theme, deliberately borrowed**
  (`ui/theme.py`). The app is read at a glance while a draft timer runs, so
  a palette the user already parses fluently every day costs no attention.
  **The FACES are bundled, not installed** (`ui/fonts.load_bundled`,
  `assets/fonts/`). Alegreya, in three weights: regular and bold for the
  body, black for the app's own name in the title bar — one family at two
  ends of its range rather than two typefaces arguing with each other. Qt
  will only use a family it knows about, so they are registered with
  `QFontDatabase` BEFORE the stylesheet is applied — a family registered
  afterwards is not picked up by rules already resolved, and the app opens
  in the fallback face. `FONT_STACK` names Alegreya first and system
  serifs behind it, and the title rule names Alegreya Black with
  `FONT_STACK` behind that, so a checkout WITHOUT the files still opens a
  readable app; a missing font is normal, not an error.
  **The bar for committing a font is that its LICENCE says yes on its
  own.** Alegreya is under the SIL Open Font License 1.1 — stated in the
  fonts' own name table, with `OFL.txt` beside them — which permits
  redistribution outright, so nobody has to take anyone's word for it.
  `test_every_committed_font_states_its_own_licence` READS the name table
  rather than trusting the filename, because two fonts have already failed
  this bar and been removed: ITC Novarese (a commercial retail face, whose
  EULA generally forbids redistributing the file at all) and LifeCraft
  (**no copyright and no licence in the font at all** — absence of a
  stated licence is not permission, whoever supplied it). None of this
  generalises to the artwork: the hero portraits, the item icons and a
  supplied `app.ico` are Valve's and Blizzard's and stay out, downloaded
  to the user's own disk at runtime.
  The family name is spelled in TWO places (`ui/fonts.py` and
  `ui/theme.py`) and they have to agree — two spellings of one family is a
  font that silently never loads, which `tests/test_fonts.py` checks.
  The title is the FRAME'S OWN GOLD (`theme.FRAME_GOLD`, the same value
  `ornate.LIGHT` paints the border with), so the name and the border round
  it read as one piece.
  Colour is reserved for meaning — green/red for signed deltas, the accent
  for the one action a screen wants, amber for warnings — and everything
  else is grey, so a number in colour is always worth reading.
  **The accent is RED, not blurple**, at the user's request and because it
  sits with the Warcraft-inspired frame where a blue did not. It is a
  DEEPER red than `BAD` on purpose: `BAD` is the bright coral a negative
  number is printed in, and if the two matched, a selected tab would read
  as a warning. Keep them apart if either is ever retuned.
  **The team headings are Dota's own colours** — Radiant green, Dire red —
  and they say only the side name. "Your team — Bijson · Radiant" said
  three things where one does, and the side is what the eye is looking for.
- **Recording needs no interaction at all** (`record.py`,
  `recordings/<timestamp>/`). With `auto_record` on (the default),
  `_consider_auto_record` starts a session the moment `game_state` reaches a
  drafting state, and `Recorder.observe()` ends it `POST_DRAFT_GRACE` after
  the game leaves one, with `MAX_SESSION` as a backstop. Frames run from the
  start of the session, not from the draft: the queue and loading screen are
  where a capture-binding fault shows up, and by hero selection it is too
  late to notice. Three cases that look like edges and are not: a blank
  `game_state` is Dota going quiet rather than the draft ending; re-entering
  a drafting state cancels the countdown; and stopping by hand mid-draft sets
  `_auto_blocked` so Auto does not immediately start another, cleared when
  the match ends. One folder per session, never pooled. Contents: payloads, draft frames, and `state.jsonl` — one
  line per tick saying what the app concluded and which source produced it.
  Sessions are never pooled; two matches in one archive made every count in
  the report meaningless. The session report grades the screen's reading
  against the minimap line-ups from the same match — the only ground truth
  available — and distinguishes a WRONG hero (advice given against a hero not
  in the game) from a MISSED one, and both from swapped sides, which is a
  mapping fault rather than a recognition one. Recorder writes are
  failure-tolerant by design: a full disk costs the recording, never the
  draft window. **The report is ONE document** — screen and game feed start
  together, so their accounts belong together: timeline, where each reading
  came from, the notes explaining every decline, the screen-vs-game score,
  then the raw payload analysis. A session of `source: none` is unreadable
  without the notes, so `snapshot_record` logs them along with whether a
  frame was captured and whether anything was recognised — capture failing
  and recognition failing are different bugs.
- **One site supplies the pairwise numbers, never two** (`config.pair_source`,
  `data/build.py`). OpenDota supplies hero constants and bracket-indexed
  baselines either way; the SETTING chooses who supplies the matchup and
  synergy counts, and it is exactly one, because averaging two sites'
  interaction terms would produce a figure neither site would recognise.
  Stratz is the default and the only complete one. **OpenDota's cost is
  real and must stay visible**: it publishes no ally-pair endpoint and no
  rank filter, so a dataset built from it has an ALL-ZERO synergy matrix
  and matchups pooled across every bracket while the baselines are
  Ancient+Divine. The build records `has_synergy` and `pair_brackets` in
  the dataset meta rather than leaving it to be inferred, `normalize.
  sanity_check(expect_synergy=...)` refuses to call an empty synergy matrix
  healthy by accident, and the UI says the source publishes none instead of
  drawing a grid of +0.00 that reads as "no synergy anywhere". The choice
  lives in `preferences.json`, not the UI settings file, because the pull
  runs in a subprocess; `_write_prefs` merges, since saving one preference
  used to wipe the other.
- **Bracket comparisons across sites are not apples to apples.** Stratz buckets
  whole matches by average rank; OpenDota counts each player at their own rank.
  That makes cross-source win rates disagree slightly even when tier labels are
  correct, so `data/verify.py` decides tier alignment on match volumes and pick
  shares, and only fails the win-rate check on an essentially-full shift.
- **The live scoring loop never makes network calls.** Data is pulled at most
  once daily and cached to disk with a timestamp.
- **Portrait matching is many-to-one**: persona/arcana portrait variants are
  separate library entries mapping to the same hero id. No OCR anywhere.
  **The library LEARNS the ones it does not have** (`vision/harvest.py`).
  It is built from Valve's one base image per hero, so a hero wearing a
  persona, an arcana or a set that changes the top-bar picture sits at
  UNKNOWN while the other nine resolve. That artwork does not have to be
  found anywhere: it is on screen at the right size with the HUD's own
  badge and border on it, and at strategy time the game NAMES all ten — so
  ten from the game, minus nine matched, leaves exactly one answer. That is
  elimination, not a guess.
  Every condition in `by_elimination` is a guard, because a mislabelled
  crop teaches the library that one hero looks like another and never
  expires: exactly one unresolved slot, at least `MIN_RESOLVED` matched,
  and every hero the screen named must be one the game named — a stray
  means one of the two sources is wrong and neither can pin the third. When
  a frame does not qualify the answer is "not this frame"; a draft is
  hundreds of frames and being right on one is enough. `save_variant`
  deduplicates by perceptual distance rather than by frame number, because
  four frames a second of one portrait is four frames a second of one
  picture, and refuses a near-flat crop outright — flat is an empty slot or
  a bad crop box, and a black rectangle filed under a hero is the worst
  thing this could do.
  **`library.load` rebuilds when a source is newer than the cache.** A crop
  learned mid-draft, or a file dropped in by hand, used to sit in the
  variants folder doing nothing until somebody remembered to run
  `build_library` — so the app learned a portrait and then went on not
  recognising it.
  **Downloaded alternatives are a supplement, not the mechanism**
  (`tools/fetch_custom_portraits.py`, Setup ▸ Download ▸ Alternative
  portraits). The community's collection is published at 128x72, 256x144,
  268x151 and 384x216 — the same 16:9 top-bar portrait, NOT the square
  hero icon, which was the open question about whether it was usable at
  all. The hero is read out of the filename by the longest hero name
  appearing as whole words, which is what keeps "Crown of the One True
  King Wraith King" off Monkey King and "Davion of Dragon Hold Dragon
  Knight" on Dragon Knight; all 24 real filenames map. To the user's disk
  at runtime, never committed — the same rule `build_library` follows for
  the base portraits, and the reason is that these are Valve's artwork.
  It has never been run against the real API: the network policy where it
  was written blocks the site, so `--dry-run` prints the whole mapping and
  names any hero in `EXPECTED` that came back with nothing.
  **Everything filed under a hero goes in `assets/portraits/variants/<HERO
  ID>/`** — the numeric id, not the name, and the same folder the app's own
  learned crops go to. So `variants/` itself looks empty when it is full,
  which is what "I can't see them in the variants folder" was; the
  downloader prints the path on every run and the task blurb says it.
- **Ranked-role-queue role icons are ground truth** for roles, read from the
  draft screen; a manual override exists in the UI for when reading fails.
- **How many tiles each strip shows is set ON the strip, and it is a CAP
  rather than a quota** (`chrome.CountBox` beside each heading,
  `ui_settings.suggested_picks` / `suggested_items`, `MAX_SHOWN` 20,
  `MainWindow._how_many`). It was in Settings, two menus away from the
  thing it sizes, which is the wrong place for a number you tune by
  looking at the result. Items are filtered by severity FIRST and then cut
  to the cap, so raising it to twenty does not produce twenty items — it
  only stops advice that already cleared the floor being truncated.
  **Nought means "as many as fit on one row"**, and that is the default,
  because a fixed eight is too many on a narrow window and too few on a
  wide one (`flowlayout.fits_in_one_row`). Setting the box makes the
  number yours and it stops moving with the window.
  The cap lives in ONE place per strip — neither `suggest_row` nor
  `item_row` caps what it is handed any more, because a second cap
  silently overruling the setting is a bug with nothing on screen to
  explain it — and `clamp_count` applies the ceiling on the way IN as well
  as out, since a hand-edited file must not be able to ask for two hundred
  tiles. Changing it also calls `_refresh_views`: the strips are redrawn
  when a PICK changes, so otherwise the new number would sit in the file
  until the next hero was picked.
- **The strips WRAP; they never scroll** (`ui/flowlayout.py`). Twenty
  fixed-width tiles in a row is 1700px of layout minimum, and a widget's
  minimum is the WINDOW's minimum, so a long strip would otherwise leave a
  window that cannot be made narrow again — the same bug as the Debug tab
  setting the height floor, in the other axis. A scroll area fixed that
  and bought two worse problems: a strip you have to scroll to read is a
  strip you do not read at a glance, which is the one thing it is for, and
  the wrapper kept getting its own height wrong. Its first version stamped
  `setMinimumHeight(strip.sizeHint().height())` at BUILD time — measuring
  a strip holding nothing but a hidden label — so every tile added
  afterwards was sliced and the portraits drew as a band with their
  bottoms cut off. Wrapping answers all of it: the strip is one tile wide
  at its narrowest, as tall as the rows it needs, and every tile is on
  screen. `heightForWidth` is the whole mechanism and a layout that does
  not answer it honestly gets its last row cut off.
- **THE TILES HAVE NO NAMES ON THEM.** The user plays the game: a face is
  read faster than four letters, and a row of pictures reads at a glance
  where a row of labelled pictures reads as a list. The name band in
  `tilekit` is now a FALLBACK — drawn only when there is no art — because
  a tile with neither picture nor name is nothing, and a fresh install has
  no art at all. The name is the tooltip either way. Two consequences: the
  pick tiles are 16:9 rather than square (the band used to take the
  difference, so a square tile became a portrait with a dead strip above
  and below it on all ten picks), and the fallback name is given most of
  the tile rather than a 22px strip — squeezed into a strip it can fail to
  fit at ALL and draw nothing, which is the one outcome worse than a name.
- **Clicking a suggestion says what is behind its number, and never more**
  (`ui/reasons.py`, `SuggestTile.asked_why` / `ItemTile.asked_why`). A sum
  is exactly the thing that can look reasonable for bad reasons: a +5 out
  of one enormous matchup is a different suggestion from a +5 out of five
  small ones and the tile cannot say which. **The hero popup must not
  explain.** The dataset knows this hero wins more than expected against
  that one; it does not know why, and neither does the app — so it lists
  the terms that made the number and says outright that the reason is not
  in the data. An invented sentence about lane pressure would be worse
  than the blank it replaced. Item rules are the other way round: they are
  hand-authored, so they carry a reason in words, and it is quoted with
  "hand-authored, not measured" attached. Clicking a suggestion still does
  not ENTER it — a pick is entered by clicking a slot.
- **The item panel is measured vs. asserted**: hero scores come from data; item
  rules are hand-authored in `rules/items.yaml`. The UI labels them as such.
  At most `suggested_items` items above a severity floor. Silence in many games is correct
  — do not tune it away, and note that "silence" is what a coverage hole
  looks like too, which is why both of these were bugs rather than taste:
  **"(no role)" must not mean "discard every role-specific rule".** It is
  the default in the UI, 55 of the file's 62 rules carried a role tag, and
  reading an unknown role as a filter that excludes threw nine tenths of
  the file away — one item where five belonged. An unset role does not
  narrow; a set one does.
  **Coverage is a feature, not a nicety.** The file named 41 of 126 heroes,
  so a typical draft tripped one or two rules and the strip read as broken.
  It now names 94; a hero with no rule is still a silent hero, so new ones
  are worth adding whenever a draft goes quiet that should not have.
- **The WINDOW is the overlay** (`ui/chrome.py`). There used to be three:
  a badge that expanded into a callout, numbers painted under the ten
  portraits, and this window — three copies of the same information, each
  with its own layout and its own bugs. All that is gone. The main window
  is frameless, always-on-top, see-through (`overlay_opacity`, 0.7 by
  default, on a toolbar slider) and resizable, and a small always-on-top
  `OverlayToggle` carrying the app's icon hides and shows it. The toggle
  never closes with the window: it is the only way back, and closing both
  would strand the app running and invisible. It is checkable so it reads
  as on or off, and it is draggable by the same press-becomes-a-drag rule
  the old badge used, so moving it never also toggles the window.
  **A PARENTLESS QWidget IS A WINDOW.** Not a hidden widget — a top-level
  window, the moment anything shows it. `force_check` was created, wired
  up, and added to no layout, so `_sync_source_controls` calling
  `setVisible(True)` on it opened a second "Dota Draft Assist" holding one
  checkbox. Two more (`update_button`, `capture_pill`) were sitting there
  invisible for the same reason — kept alive so the code touching them
  would not crash, which is exactly how the first one happened. Everything
  the window creates now has a parent, and
  `test_no_widget_is_left_without_a_parent` walks the window's own
  attributes to keep it that way, because this class of bug is invisible
  until the one line that shows it runs.
  **THE FLOATING TOGGLE IS GONE, and so is hiding the window.** Making it
  appear only when the window was hidden was not enough: it is a second
  top-level window, so the app still showed up twice in the taskbar and in
  Alt-Tab, and it was the thing the user kept noticing. It was removed
  outright — and the hide path had to go with it, because hiding a window
  with nothing left to click strands the app running and invisible. What is
  left is an ordinary window: minimise, maximise, close. `overlay_enabled`,
  `toggle_x` and `toggle_y` went too.
- **Frameless means the chrome is ours to draw.** Windows' own title bar is
  a white strip above a dark app and reads as a different program bolted on
  top. `TitleBar` replaces it, and the menu bar goes INSIDE it — NOT
  `self.menuBar()`, which QMainWindow would place above the central widget
  as a second strip on top of the first. The toolbar is added to the shell
  layout for the same reason rather than through `addToolBar`. What the
  system bar was providing has to be put back by hand and that is the whole
  cost of the decision: dragging lives on the bar, and one `ResizeGrip` in
  the bottom-right does the sizing. **The toolbar rides on the TAB STRIP**
  (`tabs.setCornerWidget`), not in a band of its own: Record, Auto and
  Transparency are three controls and did not need a whole row of window
  height beside a half-empty tab row. It carries no expanding spacer there
  — a corner widget is sized to its contents and a spacer pushes the
  controls off the right edge. View ▸ Reset window position exists
  because a frameless window has no system menu to rescue itself from.
  **The tab strip is one ROW THAT WE LAY OUT** (`chrome.BandedTabs`).
  It began as a QTabWidget with the toolbar in its top-right corner
  widget, and that arrangement produced FOUR versions of the same bug: the
  gap between the tabs and the toolbar showing the content colour, a
  lighter strip above the controls, three pixels of toolbar hanging below
  the band onto the pane, and the controls' middle sitting below the tab
  labels' middle. Every fix was a correction applied against geometry
  QTabWidget had already decided — one was a pixel out, one fought the
  height adjustment and flipped between two placements forever, and one
  scheduled a zero-delay timer that never stopped firing.

  So the corner widget is gone. Qt's own tab bar is HIDDEN and never
  shown, and `strip` is a plain widget holding OUR `QTabBar` and the
  toolbar, both added with `AlignVCenter` — the one arrangement where "on
  the same line" is not a calculation. The pages are still the
  QTabWidget's, so `addTab`, `currentIndex` and `tabText` all still work;
  the two bars are kept in step in both directions. Do not put anything
  back in the corner widget.
  Every child of the strip is given the band's colour explicitly: a
  QSlider left to the base `QWidget` rule painted a rectangle of CONTENT
  colour inside the dark row, which is the same discontinuity from the
  other direction. A test SCANS the strip for content-coloured pixels
  rather than asserting about the widgets, because each of these gaps was
  somewhere nobody thought to look.
  **A stylesheet background on a plain QWidget subclass needs
  `WA_StyledBackground`.** `QWidget#titleBar { background: ... }` was
  parsed and then IGNORED, so the title bar drew in the body's grey while
  the tab row below it was properly dark. It was invisible for as long as
  everything above the tabs was that same grey, and became the step in the
  padding the moment the band went dark — three separate attempts at the
  tab strip missed it because the fault was in the strip ABOVE the one
  being looked at. Every label on the bar needs `background: transparent`
  too: the app icon is letterboxed into a square, so a QLabel taking the
  base rule drew a box of content colour behind it, and the menu bar's
  own overflow button drew another.
  **A pill is for something being WRONG.** The data age wore a green
  outline when it was healthy — a badge for the absence of a problem, and
  its border was part of what made the toolbar taller than the tab bar.
  Fresh data is plain dim text (`pill="quiet"`); stale or missing data
  keeps the amber pill. The record control is a round red dot
  (`chrome.RecordButton`) — circle to record, square to stop, no label,
  because the symbol needs no words and this row has to stay readable at
  the window's minimum width — and Auto is a `chrome.TickBox`, which
  paints an actual TICK: Qt's stylesheet can colour the indicator but
  cannot put a mark in it without an image file, and a filled square says
  something is different about a control, not that it is switched on.
  **The whole window wears a painted frame** (`ui/ornate.py`,
  `chrome.FramedShell`). A bevelled bronze hairline, the shape of the
  Warcraft frame the user asked for — the artwork itself is Blizzard's and
  is not in this repository, so this is the vocabulary and not their
  carving. **Three pixels, and no ornament.** The first attempt was ten
  pixels of band with amethyst studs at the corners and mid-sides and read
  as jewellery round a tool: the frame's job is to give a frameless
  always-on-top window an edge against whatever is behind it, and past a
  few pixels it competes with the draft instead. Two rules it lives by: it
  is painted by the SHELL and not by the window, because a QWidget under
  the app's stylesheet paints its background across its whole rectangle
  including the margins and covered a window-painted frame completely; and
  the hole in the middle is FILLED with the app's background rather than
  cleared, since clearing leaves black anywhere the content does not cover
  to the pixel. The status bar is OUR OWN, inside the shell layout, rather
  than `QMainWindow.statusBar()` — hung off the window it sat outside the
  frame — and the `ResizeGrip` sits INSIDE it rather than in a row of its
  own below, which had left a strip of empty window under the status
  message. The message ends where the window does.
  **Everything on the bar is centred on the bar's middle line.** A layout
  left to itself stretches each child to the bar's full height, and a
  QMenuBar given 48px draws its titles hard against the top edge — which is
  what "Setup Game View Help" riding high in the strip was. The menu bar is
  pinned to its own `sizeHint` height and every child is added with
  `AlignVCenter`.
  **The title bar's close signal is `close_clicked`, not `close`.** A
  pyqtSignal named `close` shadows `QWidget.close()`, so the bar could
  never be closed programmatically and the failure read "native Qt signal
  is not callable" — which names nothing.
  **The floating toggle paints its own plate and icon.** It used to hand
  the icon to QPushButton, and a translucent frameless top-level button
  under a stylesheet drew the plate and nothing else, so the one thing on
  screen with the window hidden was a blank square. Same class of bug as
  QHeaderView refusing to honour `iconSize`, and the same answer: draw it.
- **The app icon has three sources and ships none of them**
  (`ui/appicon.py`): `assets/app.ico` or `.png` if the user put one there,
  else **Bloodseeker's portrait out of `assets/portraits/base/`**, else a
  drawn fallback. The user asked first for the Frozen Throne icon and then
  for Bloodseeker's; both are someone else's artwork and this repository
  does not carry either. But the recogniser has ALREADY downloaded that
  portrait onto their disk, by a step they ran themselves, and pointing a
  window at a file that exists is not redistribution. The last-resort icon
  is PAINTED rather than committed as a binary: no image blobs nobody can
  diff, and it only has to read as "this app" at 16 pixels.
  **That drawn icon is the one the app SHIPS**, so it has to be worth
  looking at rather than a placeholder: two wedges meeting across a
  diagonal — your side, theirs, and the line between them — which is a
  draft in one shape and survives being drawn sixteen pixels wide. It is
  original because it has to be: the icons asked for were Warcraft's and
  Valve's, and committing either is redistributing it the moment anyone
  else clones this. `assets/app.ico` still overrides it, so the user keeps
  whatever they like locally without it reaching anybody else.
  **An icon attached to a chat message is not a file**, which is the whole
  reason `appicon.install` and Setup ▸ Choose app icon… exist: a file
  picker copies the user's own .ico or .png into `assets/`, where source 1
  finds it, and `_apply_app_icon` pushes it at all four places that draw
  one — the window, the application (taskbar), the title bar and the
  floating toggle — without a restart. Handing them a picker is the only
  honest answer to "use the icon I gave you".
  **Every pixmap the module hands out is SQUARE and letterboxed, never
  cropped.** Source 2 is a 256x144 head shot — Dota's own crop — so filling
  a square box with it slices the top and bottom off the hero's head, which
  is exactly what the title bar looked like. Fitting it inside a
  transparent square keeps the whole picture and lets a square icon fill
  the bar edge to edge, which is what the title bar's ICON (bar height less
  a few pixels) assumes.
  **The taskbar is a separate problem, and it has two halves.** A Python
  process is grouped under python.exe and shows Python's icon whatever
  `setWindowIcon` says, unless it declares an AppUserModelID before the
  first window — `claim_taskbar_identity`, called from `main`. And the
  shell asks the icon for specific sizes (16 for the title, 32/48 for the
  taskbar, 256 for Alt-Tab), so a QIcon carrying ONE pixmap gets scaled by
  the shell into something blurry: the icon is built at every size in
  `SIZES`. A supplied .ico is used as it is, since it already carries them.
  **Pinning the RUNNING WINDOW is a third problem, and the WINDOW answers
  it.** Right-clicking a running window's taskbar button and choosing Pin
  does not pin the window: Windows pins the app IDENTITY and then has to
  decide what to launch and what to draw for it. An AppUserModelID alone
  does not tell it — it goes looking for a Start-menu shortcut carrying the
  same string, and with none it falls back to the executable, so the pinned
  button became pythonw.exe's icon over the label "Python" while the live
  window went on showing ours. The jump list headed **Python** is the tell:
  that is the shell naming the .exe it resolved to.
  A window can answer the question itself, and that is the fix that works
  with nothing installed anywhere: `PKEY_AppUserModel_RelaunchCommand`,
  `_RelaunchIconResource` and `_RelaunchDisplayNameResource` on the
  WINDOW'S OWN property store (`SHGetPropertyStoreForWindow`,
  `appicon.claim_window_identity`) are what the shell builds the pin from.
  They must be set BEFORE the window is shown, because the taskbar reads
  them when it creates the button — so the call sits at the end of
  `MainWindow.__init__` on `int(self.winId())`, and again in
  `_apply_app_icon` because the relaunch icon is a FILE and a newly chosen
  icon has to be written out for it.
  **The relaunch command has no working directory**, which is why
  `draft_assist/__main__.py` exists: the shell runs that string from
  wherever it likes, `-m draft_assist.ui.app` needs the repository as the
  cwd, and a file inside the package would put the package's own folder on
  `sys.path` and fail to import `draft_assist`. `__main__.py` puts the root
  on the path itself. Both halves of the command are quoted — "Dota Draft
  Assist" has a space in it.
  The Start-menu shortcut is still made and is still the fallback:
  `tools/make_shortcut.py` (Setup ▸ Make a pinnable shortcut…) writes
  `PKEY_AppUserModel_ID` into the .lnk, which means building it through
  IShellLink and IPropertyStore — WScript.Shell cannot write a
  property-store value — and it launches the same `__main__.py`. Either
  way **a pin keeps whatever identity it was made with**: an existing pin
  has to be removed, the app restarted, and the pin made again.
  The shortcut's icon must be a real .ico; `IconLocation` pointed at a
  .png draws blank. `appicon.write_ico` writes a multi-size one (PNG-
  compressed entries, which every Windows since Vista reads) from whatever
  the app's icon currently is, so there is always one to point at, and
  `appicon.shell_ico` is the one place that decides between a supplied
  `app.ico` and a generated `app-generated.ico` — the shortcut and the
  window's relaunch icon must not disagree about which file that is. A
  .bat cannot be pinned usefully at all, because Windows pins the shell rather
  than the app and the icon is the console's.
  **Nothing can pin to the taskbar on the user's behalf** — Windows removed
  the verb — so the tool opens the shortcut's folder and they drag it. And
  `propsys.PROPVARIANTType` must be called with ONE argument: handing it an
  explicit variant type killed the interpreter with
  STATUS_STACK_BUFFER_OVERRUN (exit 3221226505), which no `except` can
  catch. The identity is stamped before the file is written and its failure
  is survivable, because a shortcut without the identity is still a usable
  shortcut.
- **The refresh loop runs four times a second, so nothing in it may be
  expensive.** Two things were, and both showed up as stutter over a live
  game. `_update_debug` drew an overlay onto a full-resolution frame,
  converted it to a QImage and smooth-scaled it — every tick, into a
  widget on a hidden tab; it now returns immediately unless the view is
  actually visible, and the hero-name map it needed is built once per
  dataset rather than per tick. And every portrait and item icon was being
  rescaled with a smooth transform INSIDE `paintEvent`, thirty widgets at a
  time, for pictures that never change: `portraits.scaled` and
  `item_row._fitted` cache by (id, size) and the caches clear with
  `forget()`. A smooth rescale in a paint handler is the classic Qt
  performance mistake; do not reintroduce it.
  **The gate computes ONE signature per tick.** `gate.score` followed by
  `gate.is_draft_screen` measured the same frame twice, and `signature`
  colour-converts and area-resizes whatever it is handed — 97ms of every
  tick on a 3440x1440 frame, for a 24x14 thumbnail. The second call is now
  a comparison against the first, and `signature` decimates by plain
  slicing before the expensive steps (a slice is a view, so it is free,
  and dropping three quarters of the rows cannot move a 24x14 average).
  **The loop is measured, not guessed** (`draft_assist/timing.py`). Every
  stage — capture and recognition inside `CaptureSession.tick`, the
  rebuild, recording, status and the debug view — runs inside
  `LOOP.stage(...)`, and Debug ▸ Live prints the last, mean and worst
  milliseconds per stage over a rolling window of forty ticks. Always on:
  two `perf_counter` calls against stages measured in milliseconds, and a
  profiler you have to switch on is off when the thing you wanted to catch
  happens. A ROLLING window, not a lifetime mean — an average over an hour
  in the menu hides the ten seconds of draft that were bad. This exists
  because guessing has already been wrong once: the stutter that looked
  like scoring was a hidden widget being smooth-scaled.
- **A TAB WIDGET'S MINIMUM IS ITS TALLEST PAGE, whether or not you are
  looking at it** (`app._scrolling`). The Debug tab holds a
  full-resolution picture, a log, a timing table and the calibration row —
  1200px of minimum between them — and that set the floor for the WHOLE
  WINDOW while the Draft tab, which needs 656, was the one on screen. The
  window took the entire desktop height and would not shrink, and nothing
  about the tab being shown pointed at the tab that was not. Long pages go
  in a `QScrollArea`, where they ask for nothing; the floor went from 1321
  to 571. `test_a_tall_tab_does_not_set_the_windows_floor` keeps it there,
  because the next long panel added to Debug would do it again silently.
- **A grid is exactly as tall as its rows, and it NEVER SCROLLS**
  (`MatrixTable._fit_height`,
  applied everywhere rather than only in the callout). A five-row table
  left to stretch fills whatever height the layout hands it, and the
  leftover is dead space INSIDE the widget: half the window was blank and,
  worse, the window had no shorter size to offer, because a stretching
  widget never asks for less. The stretch goes at the BOTTOM of the tab
  instead, so every card is its own height and the slack is slack.
  Both scrollbars are off: five rows sized to fit means a scrollbar can
  only mean the fit was wrong, and it hides part of the answer while
  making the widget look correct — off, so a bad fit shows up as a
  squashed grid instead of as a grid that quietly stopped showing a row.
  The height is measured from `verticalHeader().length()` and the larger
  of the header's `height()` and its size hint, because adding up
  `rowHeight` before the layout has run — and reading a header height that
  is stale until it has been shown — is short by a few pixels, and a few
  pixels short is exactly what puts a scrollbar on a five-row grid.
- **The window has a minimum width, and it is derived rather than picked**
  (`tables.minimum_grid_width`, `teams.minimum_panel_width`). Two things
  compete for it: five matrix columns wide enough to print "+12.34"
  without eliding, and five pick tiles wide enough to still show a
  portrait. The floor is whichever needs more, doubled for the two halves.
  Numbers that elide to "..." are a grid that has stopped being a grid,
  and a tile with no room for art is not a picture of a hero.
- **An empty panel shows the SHAPE of its answer, not a sentence about
  it.** The item strip draws five blank plates (`item_row.PlaceholderTile`)
  and both grids draw a 5x5 outline (`tables._show_outline`) before there
  is anything to put in them. A line saying "items appear as the draft
  fills in" is read once and skipped forever, and a card that vanishes
  until the draft fills in makes everything below it jump when it comes
  back. **Grid lines are ON everywhere**, filled grid and empty outline
  alike. They used to be transparent on the theory that the numbers are
  the structure, and across five columns of signed deltas they are not —
  the eye loses which column it is in halfway across, and an empty grid
  was a blank rectangle rather than a grid. One app-wide rule now, so
  there is no per-state stylesheet to keep in step. A reason still worth
  saying ("Fill in both teams", "this source publishes no ally-pair data")
  sits beside the outline, never in place of it. **"Nothing urgent
  flagged" is not one of those reasons**: silence IS the answer there, the
  plates already say the strip is working, and a sentence explaining that
  nothing is wrong is read once and skipped forever.
- **Update restarts the app, and it lives in Help** (`_update_and_restart`,
  `_update_app`).
  **BOTH task paths must end in `_task_finished`.** It was connected only
  to the modeless one, so a modal task's restart request was recorded and
  then never acted on — Update pulled the new version and left the old
  process running, waiting to be closed and reopened by hand, which is the
  one thing the button exists to avoid. And a task that is going to
  relaunch sets `TaskDialog.close_on_success`, because pressing Close on a
  progress box and then watching the app restart anyway is a click for
  nothing. The relaunch targets `draft_assist/__main__.py` rather than
  `-m`, so it does not depend on inheriting a working directory.
  Reloading in place works and `reload_backend` does it, but the restart is
  the only way to be certain nothing is still holding the old data, and the
  user asked not to close and reopen by hand. It relaunches ONLY after the
  update task, and only when that task succeeded — a relaunch after a
  failure would close the dialog showing the error.
  Both the data update and the code update relaunch: a `git pull` that
  leaves the old process running has done half the job. It was a toolbar
  button and is now Help ▸ Update application… — pressed once a patch, and
  the toolbar row has to stay readable at the window's minimum width.
  **`reload_backend` must forget the picture caches.** `portraits` and
  `item_icons` each index their folder once and remember that it was empty,
  so a download that happens while the app is running never appears. That
  is exactly what "I ran the update and the item icons are still blank"
  looks like from the outside, and it was a real bug.
- **A view that rewrites itself four times a second cannot be copied**
  (`app.set_log`, `app.set_label`). `setPlainText` replaces the whole
  document, dropping the selection AND the scroll position, so the debug
  log could not be selected — the selection vanished the instant it was
  made, which reads as a Qt bug rather than as our own refresh. Both
  helpers skip the write when the text is unchanged and skip it entirely
  while the user has a selection, and `set_log` restores the scroll
  position. Any label the user is meant to copy also needs
  `TextSelectableByMouse`; a QLabel is not selectable by default.
  **Debug ▸ Copy everything** gathers the status line, the reading, the
  recognition log and the loop timings into one paste, because four panels
  selected by hand is a chore nobody does.
  **The recognition log says WHICH SCREEN it read and what it is a picture
  of.** Ten UNKNOWNs is the CORRECT answer when the pick bar is not up,
  and the log has already been read as "the crop boxes are broken" from a
  `TEAM_SHOWCASE` frame — every slot failed because there was nothing
  there to match. It now names the game state and says so outright when
  that state is not a drafting one, and prints the bound window title
  beside the frame size, because a frame that is the wrong size for the
  monitor is the tell that capture bound to something other than Dota and
  the size alone never said what it was a picture of.
- **GSI carries no screen geometry.** It reports game state, not pixels (the
  only coordinates in it are hero world positions). So the overlay anchors
  itself to the Dota window rectangle, which Windows supplies from the window
  handle; anything drawn against specific portraits needs coordinates from a
  saved frame, which is what the snapshot key exists for.
- **`ui_settings.DEFAULTS` is the write filter, not just a fallback.**
  `save` writes only the keys DEFAULTS names, so a preference the app set
  but that dict did not know about was written by the widget, kept in
  memory for the session and dropped on the way to disk. That is what
  "transparency does not remember what I set it to" was, and the floating
  toggle's position had the same bug. A new preference means a new DEFAULTS
  entry, every time.
- **Stratz API key** lives in `.env` (`STRATZ_API_KEY=...`), gitignored since
  the first commit, read at runtime. Never hardcode, never commit.

## Development environment split

Claude Code runs on Linux and cannot run Dota, Windows Graphics Capture, or
see the screen. Only the `capture` module needs Windows + Dota, and only the
GSI listener needs a running game; everything else runs headlessly from saved
frames, cached data, archived GSI payloads, or synthetic screens. The GSI
listener itself is testable by POSTing payloads to it, which the tests do.

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
- The app is launched by exactly one file, `Dota Draft Assist.bat`. Every
  maintenance action is a menu item running in a progress dialog; do not add
  new .bat files.

## Out of scope for the prototype

Ban-phase handling and the personal match-history review tool. Don't preclude
them architecturally; don't build them.
