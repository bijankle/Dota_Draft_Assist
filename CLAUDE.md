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

   **When measuring fails, the user DRAWS it** (`ui/calibrate.py`,
   `ui/framebox.py`, `autocal.measure_bank` / `layout_from_banks`). Six
   numbers, each a fraction of the HUD box rather than of the window, is
   not something anyone can convert "the boxes are 135 pixels left of the
   portraits" into — the user could see exactly what was wrong and had no
   way to say it, which is where "how the fuck do I calibrate these
   boxes" came from. ONE BOX ROUND EACH BANK, either order, and the rest
   is measured.

   **AND IT IS AN ACTION ON THE GAME, NOT A DRAG IN A DEBUG PANEL**
   (`ui/calibrate.py`, File ▸ Calibrate pick boxes, the banner's last
   rung). It was a drag on a small picture of the frame inside Debug ▸
   Live — "it should not be done in this silly debugging menu" — six
   clicks deep, for the setup step the entire draft reading depends on.
   Now two frameless always-on-top rectangles sit over the real Dota
   client, dragged and resized by hand, with a Confirm.
   **TWO BOXES, NOT TEN.** Ten labelled boxes were offered and turned
   down — "just 2 big rectangles that go over all the portraits for
   Radiant and all the portraits for Dire" — and the simpler answer is
   also the only representable one: a `DraftLayout` is seven numbers, so
   ten hand-placed rectangles could describe a pick bar that cannot
   exist.
   **THEY ARE `Qt.Tool` AND THEY EXIST ONLY WHILE CALIBRATING**, because
   two more entries in the taskbar and Alt-Tab is what got the floating
   overlay toggle deleted from this app.
   **OPEN DOTA FIRST**, at the user's request: the boxes go ON the
   client, so with no window there they are two rectangles being dragged
   over the desktop onto nothing. `dota_client_rect` answers None both
   when the game is shut and when this is not Windows, and the sentence
   is the same either way.
   **THE STRIP WITH THE NAME IN IT IS NOT PART OF THE MEASUREMENT**, and
   it flips UNDER the rectangle when there is no room above — which is
   the normal case rather than an edge one, since the pick bar hugs the
   top of the screen and a label at a negative y is clipped off the
   display. `screen_rect` returns the rectangle alone; handing the
   widget's own geometry to the measurer would put every box a label's
   height out.
   **TWO FAULTS HERE WERE INVISIBLE TO THE TESTS AND OBVIOUS ON SCREEN**,
   which is this app's oldest lesson repeating. The opening geometry
   multiplied the WINDOW width by the layout's fractions — they are
   fractions of the 16:9 HUD BOX, which is the mistake that once put the
   crop boxes 440px left of the portraits, and the fix is to go through
   `SlotRect.to_pixels` like everything else. And a bank spans four
   PITCHES plus ONE portrait: `4 * slot_w + 4 * pitch` hung the Dire box
   a hundred pixels off the right edge of the screen, where it could not
   be dragged at all.
   **AND A PANEL'S STYLESHEET CASCADES INTO ITS BUTTONS.** The control
   panel set a background and border on itself unscoped, so each button
   needed `border: none` to undo it — and that beat
   `QPushButton[accent="true"]`, which drew Confirm, the one action the
   window exists for, as a plain button. Naming the rule
   (`QWidget#calPanel`) is the fix; the accent-ordering trap in the
   stylesheet is the same family.
   **AND CONFIRM COULD NEVER FIND A PICTURE TO MEASURE.** `frame_of`
   asked the vision provider for a `last_frame` attribute that no
   provider has ever had — the frame lives on the capture session's
   state and reaches the window on the SNAPSHOT — and `getattr` on a name
   nothing defines is an unconditional None. So the
   first real use of this feature, with both boxes sitting correctly on
   the portraits and the game on screen, refused with "there is no
   picture of the game to measure": a sentence about the state of the
   world that was really about our own attribute name, and one the user
   could not have satisfied by anything they did. Two sources now, in
   order — the live Snapshot, which is free, and failing that a ONE-SHOT
   grab of the Dota window (`_grab_dota_frame`, the snapshot key's own),
   because `use_vision` is a tick box and game-data-only mode has no
   capture session at all: "you cannot calibrate the crop boxes unless
   the crop boxes are already being used" is a circle.
   **AND A REFUSAL NAMES WHAT TO DO ABOUT IT** — "what does this even
   mean... what do I do next". Capture reads the WINDOW, so the one
   thing the user can change is the game's display mode, and the message
   says so. **Which then hit the wrapped-QLabel trap**: a QLabel
   measures itself as one line and `heightForWidth` does not propagate
   up through an already-shown window, so the longer sentence came out
   in a 42px label needing 105 and the reader got the first two lines of
   the answer. `_Panel.say` asks the label what it needs at the width it
   has and grows the panel UPWARDS, since it sits near the bottom of the
   screen and anchoring the top would push Confirm off the display.
   Same fault as the setup wizard's paragraphs drawing over their own
   controls, and caught the same way: by rendering it and looking.

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
   otherwise says it was kept. Measuring from this game is how you
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
    evidence that settles it — which has since happened for ONE of the
    three rules, and only that one: see "the commoner case is now decided"
    below.

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

  So for the PAIRED case `sides_certain` stays False, the note names the
  rule that produced the split and calls the halves a coin flip, and the
  drag correction stays. What the pairing still buys, whichever way the
  coin lands, is a 5-5 split with one hero from each lane — the app can no
  longer show a 4-1 team, which is what it kept doing. When the positions
  do not pair cleanly it falls back to the runs rather than refusing.

  **BUT THE COMMONER CASE IS NOW DECIDED, AND IT IS THE FIRST THING HERE
  THAT IS** (`minimap._split_by_strategy_slots`, fixture
  `tests/fixtures/gsi/strategy_slots_8995290135.json`). Ground truth, for
  the second time and this time it BUILT a rule instead of killing one:
  the user played match 8995290135, the app put Hoodwink on the enemy team
  and Riki on theirs, and they said so. The placed heroes were not two to
  a slot — so `_split_by_lane_pairs` declined and object order, which is
  known to invert, produced exactly that swap. The positions say why:

      axe          (1088,    0)     riki           (3968, -2885)
      storm_spirit ( 176, -370)     grimstroke     (3740, -2972)
      juggernaut   ( 752, -144)     snapfire       (3865, -3513)
      rubick       ( 176,  370)     nyx_assassin   (3917, -3175)
      hoodwink     ( 752,  144)     winter_wyvern  (3634, -2526)

  **FIVE ON THE CANONICAL LANE SLOTS, ONE EACH; FIVE AT REAL WORLD
  COORDINATES.** The left column is the player's team exactly, their own
  hero among them, and the right is the enemy. The strategy screen draws
  YOUR OWN team at the lanes your team chose and has nothing to draw the
  enemy from unless you predicted them, so they come through at their
  positions in the world — a coordinate space that is visibly different,
  four figures against three.
  **IT CANNOT INVERT, which is the fault every other rule here has had.**
  The player's own hero must be among the five on the slots; a
  contradiction DECLINES rather than handing back the halves the other way
  round, so the worst it can do is fall through to the rules that were
  already there. That is what makes it safe to set `sides_certain` True
  where the pairs cannot be.
  **AND IT NEVER TAKES THE PAIRED CASE.** Predict the enemy lanes too and
  all ten stand on the five slots, which is every earlier recording; this
  rule wants exactly five on and five off, so that goes to the pairs
  unchanged. The two rules partition the cases rather than competing.

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

  **THE STATUS LINE IS STATE, and nothing else** (`_update_status`). It
  ran to seven pipe-separated segments — the mode, the line-up source, the
  game state, how old the statistics were, the ranked bracket, a count of
  item rules unverified this patch — most of which are settings the user
  chose and none of which change while a draft runs. Between them they
  buried the one segment that does. What is left is: the warning if there
  is one, whether the app has found a window titled `Dota 2` (or the wrong
  window it bound instead, which is the tell that made a whole draft get
  captured off File Explorer), the mode, the game state, whether it is
  recording, and — only when there are none at all — that there are no
  statistics. Separated by a bare `|`, with no "WARNING:" or "mode:"
  labels: the segments say what they are.
  **A MESSAGE THE USER ASKED FOR HOLDS THE LINE** (`_say`,
  `_quiet_until`). `_update_status` rewrites the whole line four times a
  second with no timeout, and a QStatusBar replaces a timed message with
  the next one it is handed — so every "Board cleared", "Loaded 62 item
  rules" and "Copied to the clipboard" in this app appeared for under a
  quarter of a second and was gone. Pressing a button and seeing nothing
  happen was partly that: the button HAD said something. Every timed
  message goes through `_say`, which claims the line for its own duration,
  and `_update_status` returns early while that claim holds. The state
  line itself must NOT go through `_say` — it would re-claim the line on
  every tick and the guard would then silence it forever.
  **THE STATISTICS' AGE IS ONE DIALOG AT STARTUP AND NOTHING ELSE**
  (`_prompt_if_data_is_old`, `ui_settings.data_reminder_days`, default 14
  days, settable in Settings, 0 turns it off). It used to be a banner at
  the top, a pill on the tab row and a segment of the status line — three
  copies of a number worth acting on about twice a month, on screen for
  the other fortnight. A thing that wants an answer is a dialog; a thing
  that wants no answer should not be on screen at all. `is_empty` still
  raises the first-run banner, because with no statistics nothing below is
  advice, and Debug ▸ Copy everything still prints the age, because that
  is a diagnostic rather than chrome.

  **A dead game feed is a BANNER, not a status segment.** It was one
  pipe-separated segment at the bottom of the window, between the capture
  mode and how old the statistics are, and it went unread through a whole
  ranked game — "where is the warning line" is a fair question about that.
  `_update_first_run_banner(snap)` now puts it in the strip at the top,
  ahead of everything about the statistics, because it is the fault that
  costs a draft; the button becomes **Check game data** and opens
  Settings ▸ Game data ▸ Diagnose game data. The banner's button is dispatched through
  `_banner_action` rather than hard-wired to the data download, since the
  banner says several different things. The warning also leads the status
  line instead of coming fourth.
  **Only a fault the user can FIX raises it** (`gsi_setup_broken`,
  `providers.NOT_A_FAULT`). Dota not being open is silence too, and so is
  a match not having started; a banner that is up all evening is one
  nobody reads on the night it matters.
  **AND THE CROP BOXES ARE THE SECOND RUNG** (`Snapshot.
  crop_boxes_wrong`, `_open_calibration`), because between them these two
  are the ways the app goes blind for a whole draft. A real ranked game
  read **two of the ten slots** for eighty seconds — the picks trickled
  in from the screen late and one was never read at all — and the app
  said so ONLY in the recording's notes, which is after the game is over.
  It is not a guess about recognition being unlucky, which is why it can
  be a banner at all: at strategy time the GAME names the ten heroes that
  are on the screen, `lineup.read_placed` scores the calibrated boxes
  against exactly those ten, and boxes that match none of them are not on
  portraits. The button goes to Settings > Debug > Live, where they are
  drawn on the picture and can be dragged — six clicks deep from a
  banner that exists to send you there.

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
- **A TILE IS ADDRESSED BY ITS HERO, NEVER BY ITS POSITION** (`_clear_slot`,
  `_edit_slot`, `ManualDraft.slot_of` / `first_free` / `replace`). The tiles
  are drawn from a PACKED list — `manual.entered` drops the empty slots and
  `merge` puts the game's picks in front — so the third tile on screen has
  no relationship to `manual.allies[2]`. Both menu actions indexed the
  manual list by display position, and the two lists diverge the moment a
  hero is typed into anything but the first free box: "Clear slot" then
  emptied a slot that was already empty and the hero stayed on the board,
  and "Change hero" wrote the answer into that empty slot, which put the
  new hero on the board BESIDE the one being changed. Both actions now read
  the hero id off the tile and act on whichever slot actually holds it.
  A hero the GAME reported is not clearable by hand — precedence is game >
  hand entry, so the next payload brings it straight back — and the status
  bar says so, because doing nothing silently is indistinguishable from
  being broken.
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
  py`) is the History tab's ranked list cut to its head — best draft fit
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
- **THE HISTORY TAB IS THE MATCH HISTORY ANALYSER** (`draft_assist/
  history/`, `ui/history_tab.py`). It was the ranked list of every hero NOT
  in this game, with "Why this score" and a counters list beside it; all
  three are GONE at the user's request. That list answered "what should I
  pick", which the Draft tab already answers in the one place it belongs —
  under the picks, where Suggested picks is that same list cut to its head
  and clicking a suggestion still shows the terms behind its number. The
  tab now answers the question the app was never asking: across a few
  hundred of your own games, what actually goes with winning.
  It came from a separate repository — a single-file browser page,
  `bijankle/DotaGameHistoryAnalyser` — and the port keeps its statistics
  exactly. **The datum is the player's OWN win rate** across the filtered
  sample, and every split asks whether a bucket is distinguishable from
  sampling noise against it: the standard error on a proportion is
  sqrt(p(1-p)/k), and the sigma is how many of those the bucket sits away.
  Not 50%, not a rank average — any other datum answers a different
  question.
  **TWO FLOORS doing two jobs.** `MIN_BUCKET` (8) is how many games a
  bucket needs before it may produce a FINDING; below it the row still
  appears, muted, so what was measured is visible without inviting anyone
  to act on it. `MIN_DISPLAY` (2) keeps single-game buckets off the screen
  entirely — a rate next to an n of one is noise wearing a number — while
  the workbook still carries them and the block header says how many were
  hidden.
  **ELEVEN ANALYSES RUN AT ONCE**, so some buckets clear the bar by chance
  alone, and the tab says so on its own front page. **Form by month is
  GONE**, at the user's request — a calendar month is not something you
  can act on, and the recent months were always too thin to read. A finding is a
  hypothesis to test against the next hundred games. Do not add a summary
  sentence that reads as a conclusion.
  **THE TWO FAMILIES ARE HEADLINED APART** (`Report.split_findings`).
  Contribution metrics separate far harder than win-rate splits because
  they are partly structural — a mid laner out-damages a hard support by
  construction — so one merged ranking by sigma would be nothing but hero
  damage rows with every behavioural finding buried under them.
  **AN ITEM IS MEASURED AGAINST THAT HERO'S OWN RATE**, never the
  player's: comparing a Pudge item against an overall rate dominated by
  other heroes would measure the hero and not the item. Read that block
  with more suspicion than the rest anyway — items are the FINAL
  inventory, so an expensive one is partly a consequence of the game going
  well rather than a cause of it.
  **EVERY TABLE HAS A CUT AND A SORT, AND THEY ARE NOT THE SAME THING**
  (`history_tab.BucketTable`, `TableControls`). At the user's request:
  "filter the top 10 heroes by number of games played, and then sort by
  win rate". TWO INPUTS, because those are two questions — a number and
  the field that RANKS for it, above the table; and the column headings,
  which re-order what survived. One control doing both would make them
  one answer: the rows shown would always be the rows the sort puts
  first, so asking for the best win rates would quietly reduce the table
  to whichever four-game buckets got lucky. The cut is therefore always
  descending by its own field whichever way the table is being READ, or
  clicking a heading would silently change which rows exist.
  Both default to GAMES, which is the order this table has always been
  in, and nought on the count box means ALL and says the word — a table
  cut to nothing looks the same as a table of nothing.
  **THE MUTED ROWS SINK, in BOTH directions**, at the user's request. A
  muted row is one there is not enough behind to act on, and sorting by
  a figure floated them: three heroes with two, three and four games
  stood above every hero with a real sample, so the numbers at the top
  of the table were the ones least worth reading. It is a PARTITION
  applied after the sort rather than a second sort key — folding "muted"
  into the key would flip with the direction and put them back on top
  the other way round.
  **THE PAGE SCROLLS, AND NOTHING INSIDE IT DOES** (`BucketTable.
  wheelEvent` / `showEvent`, `chrome.Dropdown`, `CountBox.wheelEvent`).
  Two faults with one cause: a control that answers the wheel while the
  reader is scrolling PAST it.
  A section table is sized to hold every row it has, so it should have
  nothing of its own to scroll — but `_fit_height` runs while the rows
  are being filled and a header that has not been shown yet reports a
  stale height, which leaves the fit a few pixels short. With both
  scrollbars off that is invisible except as a page that will not move:
  "there is the slightest little scroll happening". It re-fits on
  `showEvent`, when the header knows its own height — and it IGNORES the
  wheel outright, which is the half that cannot be a pixel out.
  **AND A DROPDOWN NEVER CHANGES UNDER THE WHEEL.** Qt steps a combo box
  and a spin box on every notch, so every one of them is a trap in a
  page that scrolls — "I keep accidentally scrolling and changing them by
  accident", which silently re-cuts a table or re-runs a filter. **Click,
  scroll, click**: `chrome.Dropdown` and `CountBox` ignore the wheel so
  the page beneath takes it, and a popup list that was OPENED
  deliberately still scrolls like any other list. Every combo box in the
  app is a `Dropdown` for that reason — one that was missed is one trap
  left.
  **AND THE PAGE HOLDS STILL WHILE THE COUNT IS STEPPED**
  (`_hold_still`). Removing a row shortens the table, which shortens the
  whole page, and the scroll area then re-clamps — so the arrow moved
  out from under the cursor between one click and the next: "I can't
  spam the arrow, it shifts and I have to track it." The page genuinely
  has fewer rows in it, so what is pinned is the CONTROL: its offset
  from the top of the viewport is measured, the change is made, the
  layout is FORCED to run (Qt defers it, so measuring straight after
  reads the old geometry) and the scrollbar is moved by the difference.
  **A BLOCK CARD IS ITS HEADING, ONE LINE, AND ITS TABLE.** It carried
  three paragraphs — what the split measures, how many single-game
  buckets were left out, and a caveat about reading the figures — and
  between them they pushed the table most of a screen down, so all three
  were cut at the user's request ("just the header is fine"). They have
  since changed their mind about the FIRST: "make it a slightly smaller
  text and italics, and make sure it's not super fluffy — still concise,
  but describes what the metric is." So one line is back, at 82% of the
  body size, italic and dim — and every `desc` was REWRITTEN to earn the
  space: they now say what is measured and stop, where they used to add
  how the floors work and how to read the result. It is the same string
  the tick box shows as its tooltip, because two spellings of what a
  section measures is one of them going stale. `hidden` and `caveat` are
  still computed and still go to the workbook, where a caveat can be read
  at leisure rather than sat over the table every time.
  **ONLY ON THESE CARDS.** The two summary cards get none — "I don't
  want blurbs below Win rate and Impact" — since
  those name a QUESTION rather than a measurement.
  **THE ITEM BLOCK IS ONE HERO AT A TIME, from a dropdown ordered most
  played first** (`_item_block`). It was fixed at your three most played
  and called itself "top 3 heroes", then briefly a count of how many to
  stack down the card, and stacking is the wrong shape for it: each
  hero's items are read against THAT HERO'S own win rate, so two tables
  side by side share nothing but a column heading, and the answer
  anybody wants is about the one hero they are thinking of picking. The
  hero is remembered BY NAME rather than by position — the list is one
  account's own heroes in its own order, so an index means a different
  hero the moment you look somebody else up — and there is ONE item
  control for the card rather than one per hero. `analyse.item_analysis`
  therefore computes EVERY hero with item data rather than a top few; it
  costs one pass over the sample however many that is.
  `fill()` must replace `self._tables["items"]` before it deletes the
  widgets in it: the register holds WIDGETS, and a stale entry is a
  destroyed C++ object behind a live Python wrapper, which raises the
  moment a sibling is told to move with it.
  **IT RE-RENDERS RATHER THAN CALLING `sortItems`.** Qt sorts on the
  item's TEXT, so "10" lands before "9" and "62%" before "9%", and every
  column here is a number wearing a suffix. Re-drawing is also what
  keeps the bar column honest: its fade is relative to the biggest
  sample IN THE TABLE, so a cut that removes the biggest bucket has to
  re-scale the survivors or every remaining bar reads too faint.
  The caret is drawn INTO the heading text rather than through Qt's sort
  indicator — the scrollbars' lesson, that a sub-control the stylesheet
  does not name is handed to the native style.
  **THE SUMMARY IS ONE LINE PER SECTION, AND IT IS A FIXED LIST**
  (`report.summary_rows`, `analyse.section_spread`, `ui/spread_bar.py`,
  `_findings_card`). It began as sentences — "More likely to win on
  Tuesdays: 65% from 49 games" — and seven of those is a paragraph, the
  shape this tab has been trimmed out of everywhere else. It then became
  a ranked list of whatever cleared the significance floor, which was
  worse in a way that took a screenshot to see: four Hero win rate lines
  could push Party size off the card entirely, and a section with a real
  story could be ABSENT because another had louder ones. "Where is hero
  win rate??" was exactly that.
  So at the user's request it is a fixed list: **every section once, in
  section order, carrying its best and its worst** — "make sure there is
  1 key result from each section", then "include the best and worst
  mentality for all headers seen in the left sidebar, even if they seem
  insignificant, like Radiant/Dire win rate or whatever". Nothing in it
  consults the sigma any more. A section with a real deviation and one
  with none look the same except for where the marks fall, which is the
  honest picture and is why the card no longer calls these findings. It
  also reads the same on every run, which is what makes two runs
  comparable.
  The line is the section's NAME, a rule, and the bar — which carries
  both figures itself, each above its own dot. The sample sizes are in
  the bar's tooltip, since naming two buckets would otherwise print two
  counts on every line. The two cards are **Win rate** and **Game
  **Win rate** and **Impact**, renamed twice at the user's request —
  from sentences describing the reader ("What goes with winning", "What
  you do on each hero") to short statements of the measurement, and then
  to one word each. The options card above them went the same way, "What
  to measure" to "Filter", and the tab itself is **History** rather than
  Analysis: it measures your match history, and the word it was called
  before named a shape rather than a subject.
  **A WIN RATE IS DRAWN 0 TO 100%, and that fixes the bar's real
  problem**, at the user's request. Scaled to its own section the bar
  made every section look equally spread — Radiant 55% against Dire 44%
  filled the same track as a hero list running 25% to 61% — so the
  picture said nothing about how much was at stake. On a fixed scale the
  DISTANCE between the two dots IS the size of the effect and it means
  the same thing on every row and in every run. The cost is real and was
  the trade chosen: most win rates live between 30% and 70%, so the dots
  sit in the middle third and the ends are usually empty.
  A CONTRIBUTION SECTION KEEPS ITS OWN RANGE, also at the user's request
  — "damage per minute is an average, so it should be somewhere in the
  middle". There is no 100 to scale it against, and inventing a ceiling
  would be a number nobody measured with a real game able to run off the
  end of it. Its scale must still CONTAIN the datum, since the thin
  buckets left out still counted towards it.
  **THE NAME SITS ABOVE ITS OWN DOT** — "25% Mirana" over the red one,
  "61% Rubick" over the green, sketched by hand — and the middle column
  that printed those same two figures is GONE, because with the label on
  the mark it belongs to that column said everything twice on one line.
  **BOTH NAMES SHARE ONE LINE, AND EACH RUNS AWAY FROM ITS OWN DOT** —
  the red ending just left of the red mark, the green starting just
  right of the green. This REVERSES the two rows, best above worst, that
  stood here: "I don't like that the green is not on the same level as
  the red". The rows existed to stop two close names printing over each
  other while both were centred on their marks, and anchoring each name
  to the INSIDE edge of its own dot does that job without the step,
  because the worst is always the left-hand mark — so the two texts
  point in opposite directions and the gap between them can only widen.
  **A DOT ALREADY ON THE END TURNS AND RUNS INWARD**, which is every
  contribution section, since the scale there IS worst-to-best: "the red
  and green are on either side of the min/max extremes, so it doesn't
  make sense to align them as I said before". One rule covers both — a
  name runs whichever way it has room, preferring outward — and the
  ellipsis is left for the one case it is for, two dots close enough
  that their names would otherwise meet.
  **AND EVERY WORD ON THE BAR IS 20% BIGGER AND HALOED**
  (`SMALL` 0.78 to 0.94, `SpreadBar._write` through `tilekit.stroked`),
  at the user's request. It was sized like the status line — a footnote,
  read when something is wrong — and on this card the labels ARE the
  answer, with a track, three dots and a rule for thin text to get lost
  among. The halo is the app's own rule catching up with the last place
  that skipped it: it is what makes a figure read as the same KIND of
  object wherever it appears, and there is exactly one implementation so
  the badge on a pick and the label on a bar cannot drift apart. Drawing
  through it means resolving the ALIGNMENT here, since `stroked` takes a
  baseline-left origin and `drawText` was doing that invisibly.
  **AND `elidedText` CUTS A STRING THAT MEASURES EXACTLY ITS OWN
  WIDTH.** It lays text out rather than summing advances, so a rectangle
  sized from `horizontalAdvance` came back elided: every label on the
  card read "39% Crystal Maid..." with three hundred empty pixels beside
  it. Ask whether it fits FIRST (`spread_bar._fit`) — the same family as
  the even-width pen and the header's own portrait box, where a number
  that looks like the right one is a pixel out.
  **AND THE PER-BUCKET TICKS ARE GONE**, which REVERSES what stood here
  — "get rid of all those small dashes in between, no one knows what
  they mean". They earned their place under the old scale and only
  there: best and worst were the extremes of the very set that SET the
  bounds, so those two dots sat on the two ends for ever and the ticks
  between them were the only thing carrying information. A fixed scale
  removes that at the root, because the dots move when the scale does
  not. Your own usual figure survives, kept deliberately, since a dot at
  55% says nothing about whether it is good until you know whether your
  rate is 45% or 65% — and it is now **A GREY DOT WITH ITS FIGURE OVER
  IT** rather than a dashed tick, at the user's request. It was the one
  mark on the bar that said nothing about itself: its number lived in
  the tooltip.
  **NAMED WHERE IT CHANGES, which is not every row.** Every win-rate
  section is measured against the same datum on the same 0-to-100 scale,
  so its dot lands at the same x on all eight rows and the column reads
  as one line down the card — "most of them will just be my average win
  rate of 49% or whatever", and printing it against each is the same
  number eight times, which is what the middle column was removed for.
  Each contribution section has an average of its own, so those are all
  named. The card therefore asks what it last said (`name_the_datum`)
  rather than counting rows.
  **AND A BOUND IS NEVER PRINTED TWICE.** On a contribution section the
  scale runs worst-to-best, so the two dots stand exactly on the ends and
  the end labels repeat what the dots' own names say one line above them;
  they are dropped there and kept for win rates, whose 0% and 100% no dot
  is ever on.
  **ONLY BUCKETS WITH ENOUGH GAMES** (`MIN_BUCKET`) are eligible to be
  the best or the worst: a two-game bucket at 100% would be the "best" of
  every section it appeared in, which is why those rows are muted and
  sink in the tables. Fewer than two eligible buckets draws NO row — a
  section with one bucket has no best and no worst, only a figure. A flat
  win-rate section DOES draw now, where it used to be refused: on a fixed
  scale two equal figures are two dots in the same place, which is the
  truth about them rather than a zero-width bar pretending to be a range.
  **ITEMS STAY OUT, and that one is statistics rather than taste.** Every
  item bucket is measured against THAT HERO'S own win rate, so the best
  item on one hero and the worst on another are figures against two
  different datums; one scale would draw a comparison that is not there.
  The block keeps its own card further down, where each hero is read
  against its own rate.
  **THE NAME COLUMN IS ONE WIDTH ACROSS BOTH CARDS, WITH A RULE DOWN IT**
  (`_align_names`), at the user's request — "where the result starts is
  all aligned for each metric", and "maybe even have a vertical line that
  runs down in between section and result". A grid aligns its own rows;
  what it cannot do is agree with the OTHER card's grid, and the two sit
  one above the other, so left alone they reproduce the same raggedness
  one level up. The rule is ONE widget spanning every row — a stack of
  short ones with the row spacing showing between them is a dashed line —
  and it is `section_bar.edge`, the same implementation the sidebar uses,
  because two would be two chances to draw a different grey.
  **AND THE SECTION NAMES ARE SHORT AND OF A LENGTH** (`ANALYSES`), the
  same request: "make them concise as possible, and similar character
  length so it looks proportionally right". They ran 11 to 30 characters,
  and since the longest sets that column's width for the whole card,
  "Hero damage per minute by hero" pushed every bar right while "Day of
  week" left two thirds of the column empty. They are 10 to 16 now.
  **SHORT STOPS WHERE IT STOPS BEING CLEAR**, though, and the building
  metric took two goes to land. It read "Building dmg" beside a figure
  of 116 — "that can't be total building dmg, right?" — so a name that
  invites the wrong unit is worse than a longer one; but "Building
  dmg/min" then wrapped, and it is **Siege dmg/min**, a syllable shorter
  and one line. `Match.tower_per_min` was per minute throughout; only
  the label was ever ambiguous, and every contribution section now
  states its unit: Hero dmg/min, Weighted KDA, Siege dmg/min.
  **AND A DESC SAYS WHAT IS MEASURED IN THE FEWEST WORDS THAT SAY IT.**
  The three contribution lines each ended "against your own average
  across every hero", which is the datum spelled out where the phrase
  "relative to the average" carries it — so all three read that way now,
  and the metric names itself rather than being described a second time
  ("Siege dmg/min on each hero", not "Mean damage to buildings per
  minute on each hero"). The ITEM block keeps its own wording, "against
  that hero's own win rate", because that one is not the average: it is
  a different datum per hero and the whole reason that block is read
  apart from the rest.
  `NAMES` is one list, so the sidebar, each card's heading and this
  column change together and cannot disagree; `DESCS` still carries the
  full explanation as the tick box's tooltip, so shortening cost nothing.
  **FOUR FAULTS HERE WERE INVISIBLE TO TESTS AND OBVIOUS ON SCREEN.**
  Worth listing, because three are the same shape:
  1. `_findings_card` read `self.report` for the baseline while `render`
     had been HANDED the report — and a tab told to render a report it
     was not also given has `self.report is None`, so the datum arrived
     as 0.0 and, because the scale is stretched to contain the datum,
     the bottom of every bar collapsed. Bars all labelled "0%" was the
     tell. **A method drawing a report uses the report it was handed.**
  2. `_font` scaled `pointSizeF()`, and this app sets `font-size` in
     PIXELS — so a widget's font answers `pointSizeF() == -1` and the
     end labels fell to the 6px floor, at which the reserved label
     column measured narrower than "43%" and printed a clipped bound.
  3. The name column was measured with `QFontMetrics(self.font())`,
     which answered 200px where the label itself wanted 245, because
     the font comes from the stylesheet — so the longest name was
     sliced off mid-word at the rule. `ensurePolished` is what makes a
     label answer with the font it will be drawn in.
  4. The throwaway QLabel created to measure with was still a CHILD
     after `deleteLater`, drawing at (0, 0) across the top of the
     sidebar. Same family as the parentless-QWidget trap, one step
     milder. There is no probe now: the real labels are built first and
     then given a common width, since they are the only things that
     know their own size for certain.
  **AND A FIFTH THAT WAS INVISIBLE UNTIL THE WHOLE SUITE RAN.** A
  QApplication is shared by every test in a run and so is its STYLE, and
  five test files set the real stylesheet on the way past without putting
  it back — so everything after them rendered in this app's 18px bold
  rather than Qt's default, and every measured width changed. It had been
  latent for a long time; the first assertion sensitive to it was a page
  width, which passed alone and failed in the full suite. `conftest.py`
  resets the stylesheet either side of every test now, the same way it
  resets the size multipliers and the portrait cache, and the tests that
  were quietly relying on somebody else having set it ask for it
  themselves through a `styled` fixture.
  **THE SECTIONS ARE LISTED DOWN THE LEFT, AND THE LIST IS THE
  SWITCHBOARD** (`ui/section_bar.py`, `HistoryTab._build_sections` /
  `_jump_to` / `_spy` / `_picked`). A report is thirteen cards long and
  the only way to reach the ninth was to scroll past eight, so at the
  user's request the sections are bookmarks in a sidebar that does NOT
  scroll with the page: click one and it jumps, and the row for whatever
  you are reading is lit from the scroll position.
  **AND THE ELEVEN ANALYSIS TICK BOXES LIVE ON THOSE ROWS** — "if you
  can have the tick boxes on the actual bookmarks as well that would be
  nice... don't show tick boxes on the main menu in that case,
  duplication will be confusing". They were a three-column grid on the
  options card naming the same eleven analyses the list already names,
  which is two places to read one thing and two places for it to go
  stale. The row IS the control now: tick it and the section appears
  below, untick it and the section goes and the row dims. What is left
  on that card is which MATCHES to measure, which is why it is called
  "Filter" rather than "What to measure".
  Four rules, each of them a fault avoided:
  **THE LIST IS FIXED AND ALWAYS COMPLETE.** Every analysis has a row
  whether it is ticked or not, always in the same order — listing only
  what is ticked would move every row under the cursor as you tick down
  it, which is the fault `_hold_still` exists to prevent one axis over,
  and it would leave the bar empty before a run, which is the one moment
  somebody wants to see what this tab can measure.
  **A ROW IS DIM WHEN THERE IS NOTHING TO JUMP TO**, and that one rule
  covers every case: an unticked analysis, a findings card with no
  findings in it, and the whole list before a run. Its tick still works,
  since ticking is how the section is turned on.
  **A JUMP HOLDS ITS OWN HIGHLIGHT** until the reader scrolls. The last
  few sections share the bottom of the page, so clicking any of them
  scrolls as far as it will go — and the bottom-of-page rule (which
  exists because a short last section can never reach the top of the
  viewport, so nothing would ever light it) then lit the LAST one
  whichever was clicked. The pin is set BEFORE the scroll, since
  `setValue` runs the spy synchronously, and the value it actually
  reached is recorded afterwards because the bar clamps.
  **TICKING REDRAWS.** Which analyses are drawn has always followed what
  is ticked NOW, but that was only re-read when an ACCOUNT was loaded —
  so ticking wrote the setting and changed nothing on screen. Survivable
  while the boxes sat on a card of their own; unbearable with the box ON
  the bookmark, where the row would light up beside a section that never
  appeared. `_picked` reloads from the cache and puts the scroll back
  where it was, since the page is being rebuilt under whatever you were
  reading. And `sections.picked` is connected AFTER the rows are built,
  because `_build_sections` sets each box to its default and setting a
  control to what it was always going to be is not the user picking it —
  wired first, every box fired during construction, before the card
  holding the rest of the options existed to be asked.
  **THE ORDER IS STATED ONCE, AND IT RANKS BY WHAT YOU CAN ACT ON**
  (`analyse.BLOCK_ORDER`). It was a tuple inlined in `build_blocks`, plus
  the order of `METRICS`, plus wherever `items` happened to be appended —
  three places agreeing by luck, and they did NOT agree with `ANALYSES`.
  A bookmark list in a different order from the page it maps is a
  bookmark list that lies, so `build_blocks`, the sidebar and the
  summary's rows all read one tuple and a test holds it to the same set
  of keys as `ANALYSES`.
  What that one order IS was then decided at the user's request — "show
  the most important sections at the top" — on whether a section names a
  DECISION or an OUTCOME, with two worked examples of their own:
  "Radiant and Dire is silly because it's random, I can't choose the
  side", and "hero win rate means a lot because I can choose the heroes
  that I do better at more often". So: which hero, and what to build on
  it, are the two biggest levers anybody has and they lead; then when to
  queue, when to stop, whether to re-queue after a loss, which day, who
  with. Then the two that are not choices — match length is a
  CONSEQUENCE of how a game went rather than something you set, and the
  side is assigned by the matchmaker. The THREE contribution rankings sit
  last because they are the most caveated in the tab: damage per minute
  is set mostly by what a hero DOES, so they rank heroes as much as they
  rank your play.
  **BUILDING DAMAGE IS THE THIRD OF THEM** (`towerdmg`,
  `Match.tower_per_min`), added at the user's request. `tower_damage` had
  been fetched from OpenDota and stored on every match from the
  beginning — nothing had ever measured it. Read it with the same
  suspicion as the other two and one more besides: it rises with a game
  going WELL, because you cannot hit a building you never reach, so a
  high figure is partly a consequence rather than only a cause. `_spy` nonetheless ranks by
  measured POSITION rather than by list order: the two agree today, and a
  highlight that silently lies the day they stop agreeing is worse than
  one that costs a sort.
  **AND THE FARM FOUR ARE THE NEXT FOUR** (`gold`, `xp`, `cs`,
  `denies`; `Match.cs_per_min`, `Match.denies_per_min`), added at the
  user's request after noticing Dota Plus's battle report measures CS
  and this tab did not. Same story as building damage, four times over:
  `gold_per_min`, `xp_per_min`, `last_hits` and `denies` were fetched in
  `opendota.FIELDS`, stored on every `Match` and written to the
  workbook's raw sheet from the beginning, and NOTHING had ever measured
  them. No new request, no new field, no parsed-match problem — an entry
  in `ANALYSES`, one in `METRICS`, and a place in `BLOCK_ORDER`.
  **GOLD AND XP ARE ALREADY RATES.** OpenDota reports them per minute
  itself, so those two name the row's own field while CS and denies name
  a property that does the division. Dividing gold by the duration a
  second time would report a number nobody measured and it would look
  perfectly plausible; a test holds it.
  **THEY RANK ROLES BEFORE THEY RANK YOU**, harder than hero damage
  does — a safe lane carry out-earns a hard support by construction, on
  the same night and the same skill. That is why they sit at the bottom
  of `BLOCK_ORDER` with the other caveated rankings and why each is
  measured PER HERO against your own average on that hero.
  **AND DENIES IS COUNTED PER GAME, the one figure in this family that
  is NOT a rate** (`Denies/game`, `field="denies"`, and there is
  deliberately no `Match.denies_per_min`). Two reasons, and the user's
  instruction was the first of them: denies run at TENTHS of one a
  minute, so the whole numbers they asked for would print 0 for every
  hero and the section would say nothing at all. That was reported back
  rather than shipped, and the answer that came out of it is better than
  either starting position — denying is a LANING STAGE act, so a 25
  minute game and a 50 minute game hold about the same number, and
  dividing by the length makes a long game read as worse denying with
  nothing about the laning changed. Per game is what a player counts and
  what the data actually supports; a test drives Axe's games to twice
  the length and requires his figure not to move.
  **EVERY FIGURE IS TWO SIGNIFICANT FIGURES** (`analyse.sig`,
  `SIG_FIGURES`), at the user's request — "I basically want all numbers
  in this analysis to be to two significant figures". This REPLACED the
  per-block `dp` decimal-place setting outright rather than joining it,
  because two conventions is one of them drifting. Decimal places could
  not serve these blocks anyway: they span four orders of magnitude —
  gold in the hundreds, CS in single figures, denies in hundredths — so
  the setting had to be chosen by hand per section, which is a number to
  get wrong every time a section is added. The user's first instruction
  here was whole numbers for denies, and it is NOT what shipped: denies
  run at tenths per minute, so rounding to integers prints 0 for every
  hero and the section says nothing at all. Said so rather than
  implementing it.
  Three traps in that one function. It must never use `%g` — `f"{614.7:
  .2g}"` is "6.1e+02", the right number and an unreadable one on a card
  read at a glance. Rounding can CROSS A POWER OF TEN, so 9.99 works its
  places out from 9.99's magnitude and prints "10.0", three figures from
  the line that exists to give two; the magnitude is re-read after the
  round. And there is **NO TRAILING ".0"**, also at the user's request —
  a weighted KDA of 3.04 reads "3", and the trade is theirs, since "3"
  claims one significant figure where "3.0" claimed two. It does not
  reach inside the decimals: 0.30 is not a whole number and keeps the
  second figure the block is drawn at.
  **AND THE ANALYSIS COUNT IS COUNTED, NEVER SPELLED.** The front page
  warned that "Eleven analyses run at once, so some buckets clear that
  bar by chance alone" — a sentence that exists to state the
  multiple-comparisons risk, understating it the moment a twelfth was
  added. It reads `len(ANALYSES)`.
  **THE OPTIONS ROW WRAPS, and that is the sidebar's real cost**
  (`flowlayout.FlowLayout`, the same tool the suggestion strips use).
  A row of fixed controls that cannot wrap sets a MINIMUM WIDTH, and a
  widget's minimum is the window's: laid across one line "Matches to
  measure" asked for 925px, which fitted the derived 940px floor with
  nothing to spare. The sidebar taking 178px down the left therefore put
  a HORIZONTAL SCROLLBAR under the whole report and clipped the
  remembered-accounts dropdown off the right edge. Wrapping drops the
  card's minimum to its widest single control — 949px to 464px. **Caught
  by rendering the tab and looking at it; all 747 tests passed**, which
  is the setup wizard's lesson repeating exactly.
  **AND THE TWO RULES ARE DRAWN, NOT DECLARED.** The edge between the
  sidebar and the page began as `border-right` on the SectionBar, which
  is a QScrollArea with `NoFrame` — frame width nought, so the border had
  nothing to paint into and drew absolutely nothing while reading
  perfectly in the source; it is a 1px widget in the layout now
  (`section_bar.edge`). The separators inside the list began as
  `QFrame.Shape.HLine`, where the shape is drawn BY the frame and the
  `border: none` needed to stop the stylesheet drawing a second one takes
  the first away with it. Both are checked against PIXELS in
  `tests/test_section_bar.py`, because "it is in the stylesheet" has now
  twice not meant "it is on the screen" — the same family as
  `WA_StyledBackground`, the painted tick box and the painted window
  buttons.
  **THE SIDEBAR SCROLLS ITSELF IF IT HAS TO.** Fifteen rows is taller
  than a short window, and a tall child sets the whole WINDOW's floor
  whether or not anybody is looking at it — the Debug tab did exactly
  that and took the entire desktop height with it. Inside its own scroll
  area it asks for nothing.
  **THE VIEW IS REMEMBERED PER BLOCK AND ACROSS ACCOUNTS**
  (`ui_settings.history_tables` / `history_options`), also at the user's
  request: "if I look up someone else's account, the sorts and filters
  should be the same as I had on the previous analysis". So it is keyed
  by the BLOCK rather than by the player and lives in the app's settings
  rather than beside the remembered accounts — and `_apply_remembered`
  no longer restores the options an account was last run with, because
  the controls are the reader's and not the account's. `_apply_options`
  blocks signals while it restores: setting a control to match what was
  already saved is not the user changing it, and unblocked it rewrote
  the settings file on every start. Both preferences are whole DICTS
  because `DEFAULTS` is the write filter and the set of blocks changes;
  `load` copies each dict value, since `dict(DEFAULTS)` is shallow and
  the alternative is every caller sharing one object with the defaults.
  **THE SIGMA DRIVES THE ORDER AND IS NEVER SHOWN**, at the user's
  request — "it means nothing to people". It decides which findings
  appear and in what sequence, which is what it is for; as a figure
  beside a sentence it is a number the reader cannot act on, in the
  column their eye lands on first. What it carried that DOES read is the
  direction, so a small green or red arrow sits where it was. Colouring
  the whole sentence was tried first and made a card of five findings a
  wall of red that reads as five errors.
  **THERE IS NO "THIS RUN" CARD.** It counted the matches, named the
  window and tallied what was dropped — all true, all read once, and it
  stood between the tick boxes and the first thing the run actually
  says. The datum it uniquely carried is on the blocks themselves: every
  table's fourth column is headed "Against 54%". The dim line under the
  account box STAYS — the user changed their mind about that one, and it
  answers a different question: when this account was last measured,
  without measuring it again.
  **RANKED ONLY IS TICKED, AND LANE ROLE IS GONE** — both at the user's
  request. The question this tab asks is what goes with winning RANKED
  games, and turbo and unranked answer a different one, so
  `Options.ranked_only` defaults True and the tick starts checked (a
  remembered run and a fresh tab must not disagree about it). Lane role
  was removed OUTRIGHT rather than left unticked: OpenDota parses a
  minority of matches, so the bucket was mostly "Unparsed" — an analysis
  that mostly reports it could not tell.
  **THE SUMMARY IS A HEADLINE, NOT EVERYTHING THAT CLEARED A FLOOR**
  (`split_findings`, `SUMMARY_PER_METRIC` = 3). Item findings are OUT of
  "What goes with winning": there are three heroes' worth, they separate
  easily because an expensive item is partly a CONSEQUENCE of the game
  going well, and the tab already says to read that block with more
  suspicion. "What you do on each hero" is cut to three at EACH END
  rather than to its head — where you are worst on a hero is as much the
  point as where you are best, and a list cut to its top only flatters.
  Both blocks are still drawn IN FULL further down the tab; what is
  trimmed is the summary above them.

  **NOTHING IS INFERRED TO FILL A GAP.** OpenDota populates the parsed
  fields — `lane_role` above all — on a minority of matches and frequently
  returns a null `party_size`; those go into an explicit unknown bucket
  that never produces a finding. Matches under five minutes are abandons
  and are dropped. A win is `player_slot < 128` agreeing with
  `radiant_win`, and getting that backwards would invert every number in
  the tab. Sessions are cut where more than three hours pass between the
  end of one match and the start of the next, and the tilt check only
  counts the previous result INSIDE a session — a loss you slept on is not
  charged against the next morning.
  **Comparing winning games against losing games is deliberately absent.**
  Winning hands you towers, gold and a lower death count by construction,
  so those comparisons separate at eight to ten sigma and report only that
  wins looked like wins.
  **IT RUNS WHEN ASKED AND NEVER OTHERWISE.** The app's live loop makes no
  network calls and this does not change that: a run is a button, on a
  QThread, and `MainWindow.refresh` never touches it. The thread is
  stopped and WAITED FOR in `closeEvent` — a QThread destroyed while still
  running takes the process with it, and closing mid-fetch is exactly when
  that happens.
  **THE ACCOUNTS ARE REMEMBERED LOCALLY, and that is the feature**
  (`history/store.py`, `history_accounts.json`, gitignored beside
  `ui_settings.json`). The tab opens saying when that account was last
  measured and with what, so running it again is one press — and sending
  someone a copy of this app sends them none of it.
  **THE WHOLE RUN IS KEPT NOW** (`history/cache.py`, `history_cache/`,
  gitignored with the rest), which REVERSES this file's earlier "a
  BOOKMARK, not a copy of anybody's match history". That rule cost a
  fetch every time the tab was looked at: seeing last week's answer meant
  measuring it again over a free API, with the tab blank until it
  finished. At the user's request the run is cached per account and
  re-fetched only when asked — a new account id, or Update on one already
  there, which is why the button RENAMES itself to Update once something
  is on screen. The privacy property that mattered survives unchanged:
  the folder is gitignored exactly like `.env`, so a copy of this app
  still carries nobody's history. What changed is only how much of your
  own run your own machine keeps for you.
  **AN ITEM ID IS NOT A NAME, AND THE MAP IS BUNDLED**
  (`item_names.json`, `cache.bundled_item_names` / `item_names` /
  `save_item_names`). The item block keys its buckets by OpenDota's
  numeric item id and turns them into words with a map fetched from
  `/constants/items`. This went wrong in TWO layers and the second is
  the instructive one.
  First, `cache.rebuild` was handed an EMPTY map, so the names were
  right exactly once — on the run that fetched them — and every later
  opening of that same run printed "Item 1", "Item 63" down the whole
  block. That is the path the tab takes whenever you do not re-run.
  Writing the map beside the runs fixed the rebuild and left a hole the
  user walked straight into: **the file only exists after a run has
  written one**, so an install that updated without re-measuring went on
  printing ids, and then "fixed itself" when they pressed Update with
  nothing having been done differently. A fix that only takes effect
  after an action nobody was told to take is not a fix.
  And underneath both, the fetch fails SILENTLY: `opendota.item_names`
  answers `{}` on any ApiError, `save_item_names({})` writes nothing,
  and the block prints numbers with nothing on screen saying why — the
  item icons' "four causes and one appearance" all over again.
  So the map SHIPS, and the layering is bundled < saved < fetched. A
  fresh install with no run, a cold cache and a dead connection all
  still name their items; a run's own fetch is written beside the runs
  so an item added since the file was cut is named from then on. 500
  items and twelve kilobytes, changed about twice a year, and it is
  factual data rather than anybody's artwork — the same bar
  `rules/items.yaml` already clears by naming items in this repository.
  Every reader's keys come back as INTS, because that is what the
  buckets are keyed by and a map keyed by strings misses every one of
  them silently, which is the same numbers on screen from a third
  cause.
  **THE RAW MATCHES ARE STORED AND THE FINDINGS ARE NOT** (`cache.
  rebuild`). Recomputing the blocks on the way back in costs milliseconds
  and buys two things: the workbook's raw sheet still has something to
  draw from, so Export works with no network at all; and a cached run can
  never show numbers produced by a version of `analyse.py` that is no
  longer in the app — change a floor or a sigma and every cached run
  reflects it at once. Which analyses are drawn follows what is TICKED
  NOW rather than what was ticked when the run happened, so turning one
  on costs nothing. A row the reader cannot parse is dropped rather than
  raised: the file is written by older versions of the app as often as by
  this one, so an unreadable cache must degrade to "no cache".
  **`_load_accounts(select_first=False)` after a run.** Refreshing the
  dropdown is bookkeeping, but ADOPTING a row loads that account's cached
  run — which would replace the report just measured with a copy of
  itself read back off disk. `tests/conftest.py` redirects both the store
  and the cache to `tmp_path` for every test, for the same reason the
  recordings and the settings file are redirected: they live in the
  repository root, and a test that opens this tab would otherwise read
  the developer's own and write its fixtures over them.
  **A DISPLAY NAME IS REFUSED, deliberately.** OpenDota's `/search` scans
  a very large table and times out more often than it answers, so the tab
  says to use the friend ID rather than hanging on it. `opendota.search`
  exists and is not wired to a control.
  **THE OTHER DIRECTION IS CHEAP AND IS DONE** (`opendota.profile`,
  `store.label`). Name to id is a search across every account there has
  ever been; id to name is one row on `/players/<id>`, and the two are not
  the same request wearing different clothes — refusing the first says
  nothing about the second. So a run's FIRST call resolves the display
  name, and the remembered list reads `195286385 (Bijson)`: the number is
  the identity and what the field takes, the name in brackets is what a
  person recognises a fortnight later, which is the whole reason that
  dropdown exists. It happens during a RUN because that is the one moment
  the tab is already allowed on the network — resolving on paste, or on
  the tab opening, would be this feature making a request nobody asked
  for. Cosmetic and never fatal, the rule `heroes` follows: a private
  profile answers 200 with a null profile, a rate limit answers with an
  error, and both come back as "" and show as the bare number. Empty
  brackets are never drawn — that would be the app reporting a failed
  lookup at somebody who did not ask for one. An account remembered
  before this existed gets its name the next time it is run.
  **THAT SAME LOOKUP IS WHAT MAKES A PRIVATE HISTORY DIAGNOSABLE**
  (`opendota.Profile.known`, `runner.PRIVATE` / `UNKNOWN_ACCOUNT` /
  `NO_MATCHES`). An empty match list has three causes and ONE appearance:
  Expose Public Match Data is off in Dota 2, the ID is not the one they
  meant, or the lookup itself could not be made. The profile row tells the
  first two apart — a hidden account still HAS a profile, an account
  OpenDota has never seen does not — so `known` is three-valued for the
  same reason `required` is in the capture session: asked-and-not-answered
  is not a no, and collapsing it would tell somebody their ID was wrong
  because their connection dropped. Each answer is two sentences, what is
  wrong and what to do, and the note is AMBER (`QLabel[warn="true"]`,
  declared after the dim rule so it wins on a label carrying both) because
  a Dota setting the user can change in ten seconds must not read as the
  app having failed at something. One paragraph covering all three was
  what made the commonest case look like a bug.
  **Export is the same button as Run**, at the user's request: accent
  red once there is a report behind it, plainly disabled until then. It
  was an ordinary push button beside an accented one, which read as a
  different KIND of control rather than as the second thing you do here.
  `QPushButton[accent="true"]:disabled` had to be declared AFTER the
  accent rule — the plain `:disabled` above it loses on specificity, so a
  disabled accented button stayed fully red and looked pressable. Same
  ordering lesson as the amber warning label.
  **The export is TWO SHEETS**, at the user's request: every match in one
  under an autofilter, the whole report in the other. The browser version
  wrote one sheet per analysis plus a summary, and thirteen tabs is a
  worse way to read the same thing than one you can scroll. openpyxl is in
  `requirements.txt` for it — a CSV pair cannot carry an autofilter.
- **THE APP EXPLAINED ITSELF IN PLACE, AND NOW IT DOES NOT**
  (`ui/handbook.py`, Help ▸ User manual, F1). Four paragraphs in the
  first-run wizard, three under every download button, a banner that ran
  to four lines and an About box describing the product — all true, all
  read once, and all of it standing between somebody and the control
  they had come to that screen for. It is the History tab's block cards,
  the "this run" card and the empty-grid captions again, spread across
  the whole app: "there is a lot of fluff sprinkled around... make it
  all much more concise and instead have a detailed outline of all the
  features in Help ▸ User manual".
  **THE RULE FOR WHAT GOES WHERE: a screen says what a control will DO,
  the manual says how the thing WORKS and what to do when it does not.**
  So every task blurb is one or two sentences, the wizard's paragraphs
  are one line each, and the banners state the fault and stop. Two tests
  hold it — no blurb over 200 characters or carrying a paragraph break,
  no wizard paragraph over 120 — because prose grows back.
  **AND CUTTING IS ONLY HALF A FIX IF THE FACTS GO WITH IT.** Everything
  removed is in the manual, and a test names the ones somebody can be
  stuck on: where the key lives and that it never leaves the machine,
  the `-gamestateintegration` launch option, that variant portraits are
  filed under a NUMERIC hero id, that a download skips what is on disk.
  Ten sections, listed down the left in `SectionBar` — the History tab's
  own sidebar, because two implementations of "anchors that scroll the
  page beside them" would drift.
  **IT IS TEXT IN THE APP RATHER THAN A PAGE ON THE WEB**, at the user's
  request: it answers questions about an app whose commonest fault is
  having no connection, and a manual you need a connection to open is
  missing exactly when it is wanted. **AND IT IS THE ONE PLACE THIS APP
  IS NOT BOLD** (`QLabel[prose="true"]`): everything else here is read
  at a glance over a running game, where weight is legibility, but a
  manual is read at length and a page of 18px bold is a wall whatever it
  says — which is the fault it exists to fix rather than repeat.
  Named `handbook` because `ui/manual.py` was taken years earlier by
  `ManualDraft`, the hand-entered picks.
- **ABOUT IS WHICH ONE YOU HAVE GOT, NOT WHAT IT DOES** (`_about`,
  `draft_assist/version.py`). It carried three paragraphs on what the app
  reads, where the numbers come from and what it will not touch — the
  manual's first page — and answered none of the question somebody opens
  an About box with. It is the name, the version, the build, the Python
  and Qt it is running on, the trademark line, and a button to the
  manual.
  **A VERSION AND A BUILD ARE TWO DIFFERENT ANSWERS.** `VERSION` is what
  a person says out loud, spelled in one place and raised by hand. The
  BUILD is what identifies the code, and it is read from wherever this
  copy came from, because the two kinds of install know different
  things: a clone asks git, a copy unzipped from GitHub reads the sha
  out of `installed_version.json`, which the updater wrote. A first
  unzip has neither and says "unknown" — nothing in that module may
  raise, since it is read by a dialog and by the diagnostic paste and
  neither is worth an exception.
- **The Draft tab is the whole board and nothing else.** Your five on the
  left, theirs on the right (`ui/teams.py`), because that is where they sit
  on the pick bar, with the two grids directly under the sides they
  describe: counters (`scoring.matchup_matrix`) on the left, synergy
  (`scoring.team_synergy_grid`) on the right. A comfortable total can
  conceal one lane losing badly, which is what the grids exist to show.
- **THE SYNERGY GRID IS TWO TRIANGLES, and the row headers are IN the
  cells** (`scoring.team_synergy_grid`, `tables.PairCellDelegate`,
  `MatrixTable.show_pairs`). Synergy is symmetric, so a team's own pairings
  only ever fill half a square — and that blank half is exactly the shape
  of the other team's. So the one square carries both: YOURS in the lower
  left, read against your portraits along the BOTTOM, and THEIRS in the
  upper right, read against their portraits along the TOP. The bottom axis
  is an ordinary last ROW of the table rather than a second header, because
  Qt has no bottom header and a separate widget under the table would not
  keep its columns in step with it.
  **THE TWO TRIANGLES ARE ONE COLUMN APART, and that is why this grid is
  SIX wide for five a side** (`scoring.team_synergy_grid`,
  `tables.ENEMY_SHIFT`). They used to TOUCH along the stepped diagonal,
  which is the tightest the pairs can be packed — ten pairs each is
  exactly a four-by-five rectangle with no cell to spare — and it made
  this card FIVE across where counters beside it is six (five columns
  plus the portrait column down its side). Two cards of the same width
  divided into a different number of portraits draw those portraits at
  different sizes, so the same hero was visibly bigger in one grid than
  in the other.
  At the user's request each half moves half a portrait outward: yours
  flush LEFT, theirs flush RIGHT, one empty cell walking down the
  diagonal between them. Six sections against counters' six, so the two
  scale to one portrait with neither told anything about the other —
  the same way their heights already agreed. **Everything about the
  enemy half is therefore off by one**: at body (row, col), `col <= row`
  is your pair (ally row+1, ally col), `col == row + 1` is the gap, and
  `col >= row + 2` is their pair (enemy row, enemy **col - 1**). The
  enemy AXIS moved with its triangle — enemy `i` heads column `i + 1`
  and column 0 heads nothing — because a face standing over a column it
  does not name is an axis that lies. The ally axis stays flush left
  with the last column blank, and that blank still needs an ITEM: the
  outline reads `PAIR_SIDE` off whatever is there and a missing item is
  a cell it cannot ask about.
  The lower triangle is still LIFTED ONE ROW (it starts at ally 1),
  which is what keeps the body one row shorter than it is wide and the
  card the same height as counters. The first version left the diagonal
  empty on the grounds that a hero with itself means nothing, and paid a
  whole ROW for a gap; this pays a COLUMN for one deliberately, and buys
  the matching portrait size with it.
  **The two only agree once both teams are full.** Counters is as wide
  as the ENEMY line-up plus its portrait column while synergy is as wide
  as the LONGER team plus the gap, so at 5v4 counters is five sections
  and synergy six. That is the honest answer to a half-drafted board
  rather than a mismatch — on the 5v5 the card is read at, they are
  equal.
  **WHICH TEAM GETS WHICH TRIANGLE: yours is the lower left**, at the
  user's request. The card sits under your own five and the lower-left
  triangle reaches the same edge that panel does; play Radiant — the left
  panel, and the usual case — and that is Radiant bottom-left in green,
  which is how it was asked for. Play Dire and the whole card has already
  moved right with its team, and the colours move with it.
  **EACH TRIANGLE IS OUTLINED IN ITS TEAM'S COLOUR** — Radiant green, Dire
  red, Dota's own two — because two triangles that touch need something
  between them saying which is which. The rule is per cell: every cell
  asks its four neighbours which side they are on and an edge is drawn
  where the answer differs, which gives the stepped diagonal for free, in
  both colours, and cannot go stale when the columns resize the way a
  path computed from row and column numbers would.
  **AND IT IS DRAWN ROUND THE PICTURE THE PAINTER ACTUALLY DREW**
  (`PairCellDelegate.drawn`, `PairGrid._edges` / `_end`, `_ring`,
  `_reach`). Four rounds were spent placing this line by ARITHMETIC — an
  inset derived from `CELL_PAD` — and every one of them landed a pixel or
  two inside the portraits, which is what "the border still looks like
  shit" and "they cut into the portraits" were both about. The sum can
  never be right, for three separate reasons that do not appear in it:
  Qt's own grid line takes a column out of `visualRect`, so a cell is not
  the width the column was set to; a fitted 16:9 portrait lands wherever
  the rounding puts it; and **an even-width pen is not centred on its
  coordinate** — a width-2 pen at x paints x-1 and x — so one number
  clears the art on the left and covers a column of it on the right.
  So the delegate RECORDS the rectangle it drew each portrait in, and the
  border traces that. `_ring` turns a picture into the four coordinates
  that put the pen flush against it, per side, and cannot be off by
  construction. The two teams' lines therefore sit back to back in the
  gutter with a hairline of background between them, which is both the
  "only just visible" gap that was asked for and the reason both colours
  are always visible — an edge drawn IN the gutter is drawn at the same
  coordinates by the cell on each side, so one simply painted over the
  other and which one won depended on iteration order.
  **AND THE CELL'S PORTRAIT IS THE HEADER'S PORTRAIT.** The delegate
  fitted its art to the whole cell rect while the header fitted its own
  to `set_box`, so the same hero was drawn a few pixels WIDER in the body
  than in the strip above it, touching the cell edge with no margin for a
  border to sit in — which is why a line placed to clear the picture ran
  straight across it, and why "the portraits at the top have a gap
  between them" and the ragged border were one fault rather than two.
  `_apply_icon_box` hands the delegate the same box it hands both
  headers.
  **THE SPAN OF EACH EDGE IS THE OTHER HALF**, and a run stopping at its
  own portrait is what made this read as a box round every cell rather
  than as two outlines. Each end asks the cell along its own line: it
  carries on over the grid line where that cell draws the same edge; it
  stops on THIS cell's ring where that cell is the other team, because
  the perpendicular edge is there waiting; and where that cell is ours
  but the one diagonally beyond it is too, the border steps out — the
  perpendicular edge belongs to that DIAGONAL cell and the run has to
  reach its ring to meet it. That third case is what a staircase is made
  of and it was the one missing. `_reach` adds the half-pen a line needs
  to cover the corner it lands on, or every step keeps a one-pixel notch.
  A union of rectangles was tried early and is NOT the answer:
  `QPainterPath.simplified` leaves rectangles that merely touch as
  separate subpaths, so every cell came out boxed.
  The inset fixed a third thing for free — the outer border used to be
  drawn a pixel OUTSIDE the first column with a centred pen, so half of
  it fell beyond the viewport and was clipped, which is what "a missing
  green line down the entire left side" was.
  `tests/test_matrix_grid.py` checks this against the PIXELS rather than
  the arithmetic — the outermost row and column of each picture untouched,
  and the line nonetheless hard against it — because four rounds of
  reasoning about pixel sums got it wrong four times.

  **It is DRAWN over the viewport, not by the delegate** (`PairGrid.
  paintEvent`), and that is what makes it a line rather than a row of
  dashes. A delegate paints inside its own cell rectangle, and between two
  rectangles there is the GRID LINE — so every edge stopped a pixel short
  of the next one and the border broke at every portrait. Painting it over
  the viewport puts the line IN that gap (`PairGrid.GAP`) and runs it the
  full span plus the gap at each end, so the segment along one cell meets
  the segment along the next and the corners close. A union of rectangles
  was tried first and is NOT the answer: `QPainterPath.simplified` leaves
  rectangles that merely touch as separate subpaths, so every cell came
  out with a box round it — which says the boundary is between every
  portrait rather than between the two teams.
  The axis row carries the same side as the triangle it sits under, so the
  outline encloses a team and its own faces as one region rather than
  drawing a line between them — and the HEADER strip at the top is joined
  the same way, by leaving out the edge facing the grid wherever the cells
  below it are the same team (`PortraitHeader.set_outline(open_edges=...)`,
  `_pair_open_edges`). Without that, one axis strip had a box round it
  while the other was part of its triangle. A header's long edges run
  the section's WHOLE width and one pixel over into the next: a run that
  stops at its own section is a border with a break at every portrait.
  Its line is placed by `_ring` round the portrait it drew, exactly as a
  cell's is — deriving an inset from the pen instead put the strip's
  border hard against the section edge while the cells' sat somewhere
  else, and a visible jog where the two meet is worse than either. The model says `ally` and
  `enemy`, never `radiant` and `dire`: which team is which side is
  something only the UI knows (`MatrixTable.set_team_colours`, set from
  `_update_team_labels`), and on Dire your own triangle is the red one.
  **NEITHER GRID DRAWS A TOTAL ANY MORE**, at the user's request — "it
  causes more confusion than anything", and it REVERSES what this file
  said two rounds ago. The axis portraits briefly carried each hero's
  sum with its own team, wearing a capital sigma to say it was a sum;
  counters' row and column headers took the same treatment so the two
  cards would agree. The trouble is that every other figure on these
  cards is ONE PAIR — this hero against that one — and a sum of five of
  them sat in the same badge, at the same size, in the same corner,
  distinguished only by a glyph most people do not read as an operator.
  Two kinds of number that look identical is worse than one kind and a
  gap. `Matrix.row_totals` / `col_totals` and `SynergyGrid.ally_totals`
  are still computed and still reach the workbook; what changed is only
  that the grids stopped printing them, and the Sigma row and column
  were already off.
  So a column is measured against `WIDEST_CELL` again rather than
  `WIDEST_TOTAL`. That mattered while the totals were drawn — the sigma
  sits ahead of the digits, so measuring the bare number put "..." where
  a total was — and now it is the narrower measure that is correct,
  which also stops it forcing a floor under the portrait size the card
  did not need.
  **THE AXIS ROWS ARE NOT VEILED.** They are the subject: they name the ten
  heroes the card is about. Knocking them back the way a cell behind a
  number is made the bottom row read as a different kind of thing from the
  identical portraits along the top.
  The left-hand portrait column is GONE — every cell is backed by its own
  ROW hero's portrait with the figure over it, so the pair names itself and
  the width that column took goes back to the numbers. The portrait is
  FITTED, the same way the header above fits its own, so one portrait has
  one shape everywhere in the grid; filling the cell instead (expand and
  crop) read as STRETCHED, because a cell is wider than it is tall and
  covering it threw away the top and bottom of a 16:9 head shot. It is
  veiled (`PAIR_VEIL`) so the number stays the subject, and the number is
  `tilekit.paint_badge` — the SAME font, size and corner as the figure on a
  pick at the top of the window, so the two are read one way rather than as
  two conventions.
  **Both grids are TOP-aligned in their cards** (`AlignTop` on the table).
  `_fit_height` gives each table a fixed height, so a QVBoxLayout put the
  slack above it as well as below — and the moment the synergy grid grew
  its bottom header row the shorter counters grid floated down the middle
  of its own card and the two stopped lining up.
  **The enemy half is NOT sign-flipped**, and this is the one place in the
  app where a green number is not good for you. It is deliberate and it is
  the user's call: each triangle is read as "how well does THIS team's pair
  work", so a strong enemy pairing is a big green number on their side —
  theirs green is bad for you, yours red is bad for you. The HALVES are the
  rule there, not the colour. `relations_to` and `net_contributions` still
  flip, because there the enemy figures sit among your own with no line
  between them.
  **COUNTERS KEEPS ITS SHAPE**: it is a full 5x5 of your five against their
  five, so it has no spare half to reclaim and it keeps its portrait column
  down the left. What it gained is the same two colours — one GREEN BOX
  round the ally header strip and one RED round the enemy one
  (`PortraitHeader.set_outline`) — because your five down the side against
  their five across the top looked symmetrical while meaning two different
  things by its axes, and the numbers are read from your point of view
  either way. Drawn a section at a time, since a header paints one section
  at a time: the two long edges on every section and an end cap on the
  first and last, and only round sections that actually have a hero, since
  a box round the spare column of a 5v4 claims a pick nobody has made.
  **BOTH GRIDS ARE SNUG IN BOTH AXES, and the slack is on the RIGHT**
  (`_apply_icon_box`, `_fit_width`, `AlignLeft`). The rows were always the
  height of the picture in them while the columns stretched to the card, so
  there was a gap between every pair of columns and none between any pair
  of rows — the grid read as having come apart horizontally. Each column is
  now cut to what it draws and the table is aligned left in its card, so
  the grid still begins under the heading above it and the leftover is
  plain background. Two traps in that. The column must be as wide as
  "+12.34" as well as the portrait, MEASURED against the real font
  (`WIDEST_CELL`), because a portrait is narrower than the number at the
  app's body size and cutting to the picture alone put "..." where the
  numbers were; the number is therefore also what sets the portrait's size,
  and `HEADER_ICON_MAX` is no longer the ceiling. And the room a portrait
  is allowed is measured from the WINDOW, never from the table's own
  viewport: the columns are fixed to what that measurement chooses, so
  measuring inside the table would be measuring the last answer, and the
  portraits shrank a few pixels on every layout pass. The empty outline
  works the same numbers out (`_blank_metrics`) rather than using a
  constant, so the shape does not change when the first hero arrives.
  Everything that ranked heroes NOT in the game — the list, the filter,
  "Why this score" and the counters list — is GONE rather than moved: it
  went to the History tab when it left the draft screen, and the Analysis
  tab is now the match history analyser. The item advice stayed, as the
  strip under the picks.
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
  quicker to read than the name. The number sits in the bottom-right
  corner, snug against it.
  **AND THE DIGITS STAND ON THE BOTTOM EDGE** (`tilekit.paint_badge`).
  The baseline was held a DESCENT off the bottom so that a badge which
  had to shrink to fit still stood on the same line as its full-size
  neighbours — and not one of these figures has a descender. "+0.52", a
  total, a sigma: every glyph stands on the baseline, so the reserved
  room was a band of empty portrait under the digits on every tile in the
  app. Putting the baseline itself on the bottom edge keeps what the
  descent was for and costs nothing, because the line then depends on the
  font not at all; only the stroke reaches below it, and `BADGE_INSET`
  plus half the stroke is what leaves it room.
  **IT IS OUTLINED, NOT PLATED** (`tilekit.paint_badge`, `STROKE`,
  `stroke_width`). It sat on a solid black rounded plate, and the plate is
  the part that hides the hero: even cut to the digits it is a rectangle
  of the portrait gone, and on a small tile that rectangle is most of the
  face you read the tile by. A black stroke traced round the letterforms
  separates the number from whatever colour is behind it just as well and
  costs only the ink of the outline — the art shows through between and
  around the characters. Coverage went from about a fifth of the tile to
  under a tenth. The stroke is drawn FIRST and the colour filled over it,
  because a centred stroke eats half its width into the letter; painting
  the fill on top leaves the digit its full weight with the black only
  outside. (`CHROME` still exists and is still opaque — the NAME band uses
  it, and that is only ever drawn when there is no art to see through.)
  **IT IS ONE FIXED SIZE, AND IT IS THE GRIDS'** (`NUMBER_PX` =
  `theme.BODY_PX`). It was briefly scaled to the tile, to stop a badge
  covering the portrait on a narrow window — and that made the digits
  unreadable at exactly the size where the window is smallest and the
  number matters most. With the plate gone the size no longer has to buy
  back space from the art, so it is fixed and it stays fixed: shrink the
  window and the tiles get smaller under a number that goes on being
  legible. It was briefly the CARD HEADING's size, so a figure on a
  portrait was the height of the "-3.0" beside "Radiant"; at the user's
  request it is now the BODY size, which is what the grids print their
  deltas at. EVERY signed number in the app is therefore one size —
  on a pick, on a suggestion, in a triangle, in a counters cell — and
  there is one value to change rather than two to keep in step.
  **THE USER SETS THE BASE, AND ONLY THE BASE** (View ▸ Sizes,
  `ui_settings.portrait_scale` / `number_scale`, `teams.set_scale`,
  `tilekit.set_scale`). Two sliders, 50% to 200%, one for every portrait
  in the app and one for every signed number — a setting that has to be
  applied in four places is four settings. They move the CAP, not the
  behaviour: a portrait still grows and shrinks with the window between
  its own floor and this ceiling, which is what "size dynamically, but
  from a base I choose" means. The floor is deliberately NOT scaled:
  `minimum_panel_width` is derived from it and the window's minimum width
  from that, so turning the portraits up would otherwise leave a window
  that cannot be made narrow again. Only the PANELS are told about a new
  portrait size — they decide the box and the strips and grids follow the
  signal they raise, which is the same path a window drag takes, so there
  is one way for a tile to change size rather than two. A new number size
  is a REPAINT and not a rebuild: nothing about the layout changes, and
  rebuilding the strips on every step of a slider drag would score the
  whole draft a hundred times to change a font size. Both are module
  state, so `tests/conftest.py` resets them either side of every test —
  a test that turns them down and then fails would otherwise leave every
  test after it measuring smaller tiles.
  **AND EVERY ONE OF THEM IS HALOED** (`tilekit.paint_number`,
  `tables.DeltaCellDelegate`). The two grids printed their deltas as
  ordinary table text, which made them the one place in the app where a
  signed number had no outline round it. The halo is not decoration: it
  separates the figure from whatever is behind it, and it is what makes a
  number in a cell and a number on a portrait read as the same kind of
  object rather than as two conventions. `tilekit.stroked` is the one
  place the stroke-then-fill happens, so the corner badge and the centred
  cell cannot drift apart.
  **Except when it will not fit** (`NUMBER_MIN_PX`). At the window's
  narrowest a "+21.7" is wider than the tile, and a number clipped to
  "+21." is not a smaller number, it is a WRONG one — so there, and only
  there, it steps down far enough to fit.
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
  **EVERY REGION FILLS ITS OWN CARD, AND THE PICKS SET THE BOX**
  (`teams.tile_cap`, `TeamPanel._resize_tiles`, `MatrixTable.
  set_tile_width` / `_portrait_room`, `MainWindow._match_grid_portraits`).
  This REVERSES the rule that stood here before, which took the SMALLEST
  of what the two grid cards could draw and brought the picks down to
  meet it — one number for every portrait in the window, at a price paid
  in the wrong place. Counters is SIX sections across (five columns plus
  the portrait column down its side) where everything else is five, so on
  a real 5v5 it decided the size of the ten picks at the top of the
  window: they came down to about five sixths of what their own card
  could hold and sat small in the middle of it with a wide margin either
  side. "They should be scaling to reach the end margins."
  So the picks fill their card, which sets the app's box, and everything
  else follows it: the strips take it outright, and a grid takes it as a
  CEILING and goes smaller only when its own sections will not fit
  (`_portrait_room`). **BOTH GRIDS ARE SIX ACROSS** — counters' five
  columns plus its portrait column, and synergy's five plus the gap
  between its triangles — so the two agree with each other exactly and
  both come out about five sixths of a pick tile. That is the trade the
  user chose when the synergy grid was widened: the two matrices
  matching each other was the point, and five picks filling a card
  cannot equal six sections filling an equal card. All three being one
  size would need counters to drop its portrait column, putting each
  row's face into its own cells the way synergy does, and that has NOT
  been done.
  `TILE_MAX` is a sanity ceiling rather than a working size for the same
  reason. At 132 it was a size an ordinary window reaches and passes, so
  past about 1500px the picks stopped growing and the complaint came
  straight back on a bigger monitor; at 256 it only stops a full-screen
  window on a very wide display turning the draft into five posters, and
  the user's multiplier still moves it.
  `_match_grid_portraits` must stay IDEMPOTENT. It runs from
  `resizeEvent`, and telling the strips a size resizes them, which lays
  the window out again, which calls it again — an unbounded loop, and Qt
  ABORTS the process rather than raising, so there is no traceback and no
  test failure, only an app that stops. The guard has to move with
  whatever value the function applies.

    `set_grid_cap` still exists and is still MODULE state, so
  `tests/conftest.py` resets it either side of every test for the same
  reason it resets the two scales — but nothing calls it to hold the
  picks down any more.

  **EVERY PORTRAIT IN THE APP IS THE PICK TILE'S BOX** (`app.
  STRIP_OF_PICK` = 1.0, `MatrixTable.set_tile_width`). The strips were
  briefly 70% of a pick, so the ten picks read as the subject and the
  advice under them as advice; at the user's request that is reversed, and
  the two GRIDS were brought into it as well — they had a size of their
  own, so the same hero was one size at the top of the window, another in
  the strip below it and a third in the grid under that. The draft panel
  decides one box for all of them and everything else follows it. A grid
  may only make it SMALLER, when six will not fit across its card
  (`_portrait_room`), which is the one place the rule gives way.
  **EVERY TILE IN THE APP IS ONE BOX, and the draft panel decides it**
  (`TeamPanel.tile_resized` → `MainWindow._resize_strips` →
  `SuggestRow.set_tile_size` / `ItemRow.set_tile_size`). The strips were
  fixed at 78x44 while the ten picks grew with the window between 64 and
  132, so a suggestion was never the size of a pick — and the constants in
  `tilekit` are now the FALLBACK for before the panel has been laid out,
  not the size. `_row_capacity` divides by the strip's LIVE tile width,
  since a fixed 78 answers "how many fit on one row" for a size the strip
  stopped being.
  **EVERY EMPTY PLATE IS THE SAME RECTANGLE** (`tilekit.PLATE_RADIUS`,
  `ItemRow._blank_size`). A freshly opened app is three rows of identical
  holes, and they were not identical: the pick slots rounded their corners
  while the strips squared theirs, and the item plates were narrower than
  the rest. The radius is now one number both use, and an empty item plate
  takes the whole pick box — a FILLED item tile keeps its 88x64 shape,
  because a 16:9 box round an icon is dead space either side of it, but an
  empty plate has no icon whose shape to respect. The "+" on a pick slot
  is the only thing that distinguishes the three.
  **A placeholder paints into its OWN rect.** Both blank plates drew a
  plate `BAND_H` taller than the widget, so the dashed bottom edge fell
  off the tile and an empty strip read as a different size from a full
  one — which is what "the squares are a different size before the game
  starts" actually was: the same box with three sides of an outline.
  **Each strip's tile takes its own art's aspect** — a hero portrait is
  16:9, an item icon is Valve's 88x64 — sharing only the HEIGHT, so the
  strips line up with each other without any icon sitting in a box wider
  than itself. That still holds under one shared box: the suggested picks
  take the pick tile's whole size, the items take its height and derive
  their width from 88:64 (`item_row.width_for`). A tile wider than its picture is dead space either side of
  every icon, which reads as the items being spaced further apart than the
  heroes above them. Icons are
  downloaded with the portraits into `assets/items/`, named by a slug of
  the DISPLAY name so `rules/items.yaml` can go on saying "Black King Bar"
  the way a person writes it; a missing icon draws the name and is normal,
  not an error.
  **A MISSING ICON HAS FOUR CAUSES AND ONE APPEARANCE**, so there is a tool
  that tells them apart (`tools/check_item_icons.py`, which no longer has a menu
  item — see the menu-bar note below). The download 404'd, the rules name an item OpenDota
  does not list, the rule name is a prefix of TWO icons and is refused
  rather than guessed at (`item_icons._resolve` — drawing the wrong item is
  worse than drawing the name), or the file on disk will not decode. All
  four draw the name, which is why "Eul's Scepter isn't showing the image"
  cannot be answered from the picture. Ambiguity is NOT resolved by taking
  the shortest match: a rule saying "Boots" would then silently draw Boots
  of Travel. A file that was never written is fixed by re-running the
  download, which skips what is already there and so retries exactly the
  ones that failed.
  **AND THE TILE ITSELF NOW SAYS WHICH CAUSE IT IS** (`item_icons.
  why_missing`, in the tooltip). The tool that tells them apart lost its
  menu item on the grounds that "the strip already draws the name and the
  download reports what failed" — and neither of those answers "Eul's
  still doesn't have artwork" for somebody looking at the tile. The
  answer is four lines of set arithmetic against what is on disk, so it
  goes where that person already is.
  Role and own-hero filtering still apply once known — they
  just no longer gate the panel.
- **DEMO fills the board in one press, and the two "Simulate a draft" menu
  items are gone** (`_demo_draft`). They each started a SUBPROCESS posting
  invented payloads at the real GSI listener and left it running — a whole
  second moving part to answer "show me what a full board looks like", and
  one that then had to be noticed and stopped. Demo writes ten random
  heroes into the MANUAL slots instead: nothing outlives the press, and
  Clear all empties it like any other hand entry.
- **The ad slot is a PLACEHOLDER and it is off by default**
  (`ui/adslot.py`, `ui_settings.ads_enabled`). No network is touched and no
  ad network is wired in; what exists is the SPACE an ad would take on the
  schedule it would appear on, five seconds in every fifteen, above the two
  team panels — so "what does the window look like with this in it" can be
  answered now and living with it for an evening is something the owner can
  try before committing.
  **The creative is a REAL ad unit**: 728x90, the IAB leaderboard, which is
  the size a banner slot is actually sold as — the layout is worth testing
  against the real thing rather than a placeholder that turns out to be the
  wrong shape. It is CENTRED in a full-width slot rather than stretched,
  because a leaderboard is a fixed-size creative wherever it is served, and
  it fits inside the window's own ~1464px floor.
  **ON MEANS ON: the banner is up the whole time**, at the user's request.
  It began as five seconds in every fifteen, which was worse in both
  directions — an ad that appears out of nothing mid-draft pulls the eye
  at exactly the wrong moment, and one that is always there is furniture
  after ten minutes. There is no timer in the widget at all now.
  **It reserves its height while ads are ON and NONE while they are off.**
  A banner that came and went while pushing the ten picks up and down
  would be a board that moves under the cursor mid-draft, which is how a
  pick gets misclicked. With the feature switched off there is nothing to
  hold still for, and reserving the space anyway was a strip of dead
  window above the draft for something nobody turned on.
  **THE CREATIVE IS PAINTED, and it is nobody's real advertisement**
  (`adslot.leaderboard`). A genuine banner off the web is somebody's
  copyrighted artwork, and this repository carries no artwork that is not
  its own — the same rule that keeps Valve's portraits out of it. So the
  slot is filled by a house creative drawn in code for a product that does
  not exist: brand, headline, one line of copy, a call to action and the
  "Ad" marker every network requires, at the right size and with the right
  amount of noise beside a draft. The copy is ELIDED against the button's
  left edge rather than positioned by hand, because a line of copy running
  under the call to action is the one mistake a real banner never makes
  and the one a fixed x position makes as soon as the wording changes.
  Whatever eventually fills it must fetch on its own timer, off the draft
  path — the live loop still never makes network calls.
  **THE REVENUE PLAN DEPENDS ON THE WEB VERSION, which is parked.** The ad
  networks worth using (AdSense and the rest) serve into WEB PAGES and
  their terms are written that way; there is no supported path for a
  PyQt desktop window, and embedding a browser view to get around that is
  the kind of thing that gets an account closed rather than paid. So this
  slot is the layout and the switch, and nothing beyond that can be honest
  until there is a page to serve into.
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
  is ("Counters", "Synergies") and the row and column headers say what the
  axes are; a paragraph repeating both only stands between the reader and
  the numbers. `MatrixTable.set_compact(short_names=...)` separates the two
  jobs: dropping the caption is for everywhere, while short names, fixed
  narrow columns and a height fitted to the rows are the in-game callout's
  layout alone — applying them in the main window shrank the grid to a
  fitted block floating in a half-empty card.
- **SYNERGIES LEFT, COUNTERS RIGHT, ALWAYS — the cards are NEVER
  re-seated**, at the user's request, and this REVERSES the rule that
  each grid sits under the team whose heroes head it. That held while
  synergy was ally-by-ally and counters was read against theirs; it
  expired when the cards changed and nobody noticed. Synergy is TWO
  TRIANGLES carrying both line-ups, and counters is your five against
  theirs with a coloured box round each axis — so **both cards carry both
  teams**, neither belongs to a side, and there is nothing left for the
  seating to follow. What it produced instead was a Draft tab whose
  bottom half changed places depending on which team the matchmaker put
  you on: "the counters matrix switched position to the synergies
  matrix... it used to be synergies on the left", and "it should never
  swap because both synergies and counters has both radiant and dire on
  it anyway". The PANELS still swap (see `_order_panels`) and the
  COLOURS still follow the teams — on Dire your own triangle is the red
  one, and counters boxes your axis in red — because those track which
  team a thing is about rather than where a card sits.
  **Its headers are their portraits.** A column reads straight down from
  the tile it is about — which is the whole reason the headers are the
  same pictures rather than the names a second time. **Qt will not draw those icons.** A
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
  (`scoring.relations_to`, `MainWindow.focus` / `_update_relations`).
  **BOTH sides answer the same two questions**: an ally shows synergy above
  your other four AND matchup above all five enemies; an enemy shows
  matchup above your five AND its synergy with its own four. This file used
  to say the second half was not our business — "their pair-ups are their
  synergy, not ours" — and that was wrong in the way that matters
  mid-draft: an enemy that combos with two of its team-mates is a bigger
  problem than its own matchups say, and the click view was the one place
  that could show it and did not. Clicking the focused hero again clears
  it, so the way out is the way in.
  **Every number reads from YOUR team's point of view**: positive is good
  for you whichever portrait it sits under. Without that rule a green
  number under an enemy would mean the opposite of a green number under an
  ally, which is the misreading the view exists to prevent.
  An ENEMY PAIR'S SYNERGY IS SIGN-FLIPPED, for exactly that rule: a combo
  that works for them is a problem for us, so it prints red — the same
  convention `net_contributions` already applies to the enemy half of the
  board, and the one that keeps a green number meaning one thing.
  With nothing clicked the tiles rest on `scoring.net_contributions` — what
  each pick is worth overall — rather than going blank, since the tile
  reserves the line either way. An ALLY's figure is its synergy with your
  four plus its matchups against their five; an ENEMY's is how your five
  fare against it LESS its synergy with its own four, sign flipped, because
  a hero that combos with their line-up is our problem, not their bonus.
  **THERE IS ONE SELECTION AND FOUR SURFACES ANSWER IT** (`MainWindow.
  focus` as `(where, hero id)` with `where` in ally/enemy/suggest,
  `_update_relations`, `_update_suggestion_relations`,
  `_update_grid_focus`). A hero can be clicked on a pick tile, on a
  suggestion, or on either grid's axis, and every one of those is the
  same question — so a new click REPLACES the old one wherever it came
  from, and clicking the selected hero again clears it. Two selections
  living side by side would put two sets of numbers on the board with
  nothing saying which was which.
  **THE RING IS THE WINDOW'S OWN FRAME** (`tilekit.paint_focus_ring`,
  `FOCUS_COLOUR` = `theme.FRAME_GOLD`, `FOCUS_WIDTH` = `ornate.WIDTH`),
  at the user's request: the same gold and the same three pixels
  `ornate` paints round the whole app. It was `theme.ACCENT` at 2px —
  the deep red that means "the one ACTION this screen wants" everywhere
  else — sitting on a portrait to say "this is the hero everything else
  is measured against", which is not an action at all. Spelled ONCE, in
  `tilekit`, because a pick, a suggestion and two grid axes all draw it.
  **HALF A PEN IN, IN FLOAT.** An odd pen is centred on its coordinate,
  so a width-3 ring drawn on the widget's edge loses one pixel outside
  (clipped) and blends the third one inside: two solid pixels and a
  smudge, visibly thinner than the frame it is matching. Centred at 1.5
  it covers 0, 1 and 2 exactly. Same family as the even-width pen in the
  grid borders. And both tiles hand it their FULL rect — one of them was
  passing the inset box its other pens use, which put the gold a pixel
  off the edge on two sides and flush on the other two.
  **A DROP TARGET STILL OUTRANKS IT.** Dragging a hero onto the focused
  tile has to go on saying "drop here": the amber says what is about to
  happen, the gold says what is being measured, and the one in progress
  wins.
  **AND THE GRID AXES ARE CLICKABLE, showing that hero's row alone**
  (`MatrixTable.hero_clicked` / `set_focus`, `PortraitHeader.set_focus`,
  `PairGrid.axis_clicked`, `tables.cell_is_about`), also at the user's
  request. Counters heads both axes with portraits, so those are
  `sectionClicked`; synergy's ally axis is an ordinary last ROW — Qt has
  no bottom header — and every item in that grid carries `NoItemFlags` so
  nothing is selectable, which means Qt emits no activation for it
  either and the click is read off the position in `mouseReleaseEvent`.
  ONLY THE AXES: a body cell is a PAIR, so a click on one names two
  heroes and could not say which was being asked for.
  It is a FILTER AND A REPAINT, never a rebuild — the cells already hold
  every number, so re-running `show_matrix` would rebuild ten portraits
  and re-measure every column to change what is drawn, and the card would
  flicker on a click. The grid keeps every row, every column and every
  portrait; only the numbers that do not answer the question go quiet.
  **A CELL HAD TO LEARN ITS SECOND HERO** (`PAIR_OTHER`, `CELL_ROW_HERO`,
  `CELL_COL_HERO`). A synergy cell knew only whose portrait backs it and
  a counters cell knew neither of its two, so neither could say whether
  it was one of the ones the clicked hero asked for.
  **AND THE SIDE COMES FROM THE DRAFT, NOT FROM WHICH AXIS WAS CLICKED.**
  Counters heads its rows with your five and its columns with theirs, and
  synergy's triangles are the other way up; asking the draft which team a
  hero is on is one question with one answer where working it out from
  the axis is four. A hero in neither team has no side and the click does
  nothing rather than inventing one.
  **A FOCUSED SUGGESTION CLEARS THE GRIDS RATHER THAN BLANKING THEM.** It
  is not on either card — it is not in the draft — so every cell would
  fail the test and both would go completely empty, which reads as the
  grids having broken rather than as the hero not being in them.
  **AND A SELECTION THAT GOES OFF SCREEN IS DROPPED**
  (`_drop_focus_if_off_screen`). The strip is cut to a count the user
  sets and re-ranked on every pick, so a focused candidate can fall off
  the end of it — and numbers all over the board measured against a hero
  with no ring on it anywhere is worse than no numbers at all. When the
  focused candidate is PICKED instead, the ring FOLLOWS IT onto the
  board: it is still the same hero, and dropping the selection at the
  moment the pick lands would clear the board exactly when the answer
  became real.
  **THE SIGN CONVENTION IS NOW IN ONE FUNCTION** (`scoring.pair_delta`).
  Four cases — ally with ally, ally against enemy, enemy against ally,
  enemy with enemy — and every caller that wrote them out again was a
  fresh chance to get one backwards. `relations_to`, `relations_from` and
  the enemy-pair flip all read it.
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
  **Everything is bold, and 38% larger than it was** (+20%, then another
  +15%), at the user's request: the app is read in the corner of the eye over a running game,
  so weight is legibility rather than decoration, and Alegreya's bold is
  one of the bundled files so it resolves rather than being synthesised.
  Raising the body size RAISES THE WINDOW'S MINIMUM WIDTH — the floor is
  derived from what it takes to print "+12.34" without eliding
  (`tables.minimum_grid_width`), so bigger text means a wider narrowest
  window. It has gone ~1234 → ~1324 → ~1464 across the two rises. That is
  the derivation working, not a regression, but it is the budget any
  further increase spends.
  **A QLabel is TRANSPARENT by default** — one rule under the base one. A
  label inherits `QWidget {{ background: BG }}`, so every label in the app
  painted a rectangle of CONTENT colour wherever it sat: on a card
  (`BG_ELEVATED`, darker) that is a lighter box round the heading and
  round the count box, and where an empty label was still in the layout it
  is a 3mm stub of the same thing — which is what "a weird little square
  at the end of Your team" was. This had already been patched twice, once
  for the title bar and once for the tab strip, and each patch covered
  only the widget somebody happened to be looking at; the default is the
  fix, and the pills still set their own background and win on
  specificity. An empty label is also HIDDEN rather than left in the
  layout (`TeamPanel.set_note`): a widget saying nothing should not occupy
  anything. The count boxes get the same treatment — a transparent
  `QSpinBox` with a border, so they read as controls rather than as
  lighter rectangles.
  Colour is reserved for meaning — green/red for signed deltas, the accent
  for the one action a screen wants, amber for warnings — and everything
  else is grey, so a number in colour is always worth reading.
  **The accent is RED, not blurple**, at the user's request and because it
  sits with the Warcraft-inspired frame where a blue did not. It is a
  DEEPER red than `BAD` on purpose: `BAD` is the bright coral a negative
  number is printed in, and if the two matched, a selected tab would read
  as a warning. Keep them apart if either is ever retuned.
  **The team headings are PLAIN WHITE**, and they say only the side name.
  "Your team — Bijson · Radiant" said three things where one does, and the
  side is what the eye is looking for. They were briefly Dota's own green
  and red, which put the two colours that mean "good for you" and "bad for
  you" on two words that judge nothing — with the side's own signed total
  sitting right beside them wearing the same two colours for the opposite
  reason. The TOTAL keeps its colour, because that one IS a judgement.
  **AND IT IS HALOED** (`teams.HaloLabel`). It was the last signed number
  in the window drawn as plain text, while every other one is stroked —
  the badge on a pick, the figure in a grid cell, the sigma on an axis
  portrait. The halo is not decoration: it separates a figure from
  whatever is behind it and it is what makes two numbers read as the same
  kind of object, so the one that skipped it read as a different kind of
  thing from the five tiles it is the sum of. PAINTED, because a
  stylesheet cannot put a stroke round a glyph — the tick box, the window
  buttons and the count box's arrows are all painted for the same reason —
  and the colour therefore comes in through `set_value` and is read back
  off `HaloLabel.colour`, since a `color:` rule cannot reach text a widget
  draws itself.
  **They ALWAYS say Radiant and Dire, and LEFT IS ALWAYS RADIANT**
  (`_order_panels`). "Your team" / "Enemy team" was the fallback whenever
  the game had not reported a side, and it named the one thing the user
  can already see — the panel with their own hero in it. So the headings
  are the side names unconditionally, and when the player turns out to be
  Dire the PANELS SWAP rather than the labels: Radiant is the left bank of
  Dota's own pick bar, and a panel on the left labelled Dire is the one
  arrangement that disagrees with the screen it is read beside. The dict
  keys stay ally/enemy, because everything else in the app reasons in
  those terms; only the PANELS' seating changes. The two grid cards below
  them do NOT move — see the pinned-cards note above. With no side
  reported the left panel is Radiant.
  **Each heading carries that side's total** — "Radiant | +11.2" — the sum
  of what `net_contributions` says its five heroes are worth, which is the
  five tiles' own numbers added up. It is ALWAYS that sum, even while a
  hero is clicked and the tiles have switched to that hero's relations,
  because a heading that moved every time a portrait was clicked is one
  you have to stop and re-read. The two totals are NOT a scoreline: every
  number in the app is read from your side, so yours is what your draft is
  worth and theirs is how well their five are handled. A side with nothing
  resolved shows no total at all rather than "+0.0", which would claim a
  measurement nobody made.
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
  (`tools/fetch_custom_portraits.py`, Settings ▸ Downloads ▸ Alternative
  portraits). The community's collection is published at 128x72, 256x144,
  268x151 and 384x216 — the same 16:9 top-bar portrait, NOT the square
  hero icon, which was the open question about whether it was usable at
  all. The hero is read out of the filename by the longest hero name
  appearing as whole words, which is what keeps "Crown of the One True
  King Wraith King" off Monkey King and "Davion of Dragon Hold Dragon
  Knight" on Dragon Knight; all 24 real filenames map. To the user's disk
  at runtime, never committed — the same rule `build_library` follows for
  the base portraits, and the reason is that these are Valve's artwork.
  **IT HAS NOW RUN AGAINST THE REAL API, and the mapping is confirmed**,
  which reverses the warning that stood here. It was written where the
  network policy blocks the site, so for a long time only `--dry-run` had
  ever been read. The first live run, on the user's own machine: **32
  files in the category, 32 mapped, 0 unplaced, and every one of the 23
  heroes in `EXPECTED` covered.** The cases the matcher exists for came
  out right — "Crown of the One True King Wraith King" on Wraith King and
  not Monkey King, "Davion of Dragon Hold Dragon Knight" on Dragon Knight
  — and several heroes correctly took more than one file (Pudge three,
  and each "Alt" style beside its base arcana). What is still unverified
  is only what a future patch adds to the category, which is what
  `EXPECTED` is for — and that check now runs on a REAL run as well as a
  dry one (`report_missing`), because a dry run is the check nobody
  remembers to do.
  **AND IT NEEDS NO STRATZ KEY, which it used to and should never have**
  (`fetch_custom_portraits.hero_names`). All it wants from the dataset is
  hero NAMES, to find one inside a filename — and it took them from
  `store.load()`, the STATISTICS cache, which `pull_data.py` builds and
  which needs a key. So on a fresh install where the user skipped the key
  at setup (which the wizard explicitly offers), this step raised
  `FileNotFoundError: No dataset cache at ...\data_cache\dataset.npz` and
  told them to go and pull statistics they had deliberately not asked
  for. The two steps beside it — 127 portraits and 484 item icons — need
  no account of any kind, had already succeeded, and this one failed the
  whole run. Hero names are not statistics: `build_library`, the step
  that downloads the base portraits this one supplements, has always
  taken them from OpenDota's public `constants/heroes`. So the layering
  is the dataset if it happens to be on disk (free, offline, already
  parsed) and those public constants otherwise, which this tool is on the
  network for anyway. `fetch_assets.py`'s docstring has said "NEEDS NO
  API KEY" throughout; one of its three steps did not, and nothing
  checked.
  **AND A REPORT OF A FAILURE MUST NOT ITSELF FAIL** (`draft_assist/
  console.py`, `fetch_assets.run`, `ui/tasks.py`). This is the worse half
  of that same install, because it hid the first: `run` caught the
  FileNotFoundError exactly as designed — one part failing must never
  take the others down — and then **died inside its own `except`**
  printing the message, which contained a U+25B8 arrow. A Windows console
  is cp1252 and cp1252 cannot encode it. What the user saw was a
  `UnicodeEncodeError` raised from the error handler; the cause it had
  successfully caught was never printed at all. Three things hold it
  shut, at three different levels. `console.plain_output()` puts the
  streams on `errors="replace"`, so an unprintable character degrades to
  `?` and the sentence around it still arrives; `console.say` is the last
  resort for the one line that must land, since an exception's message
  carries paths and other libraries' wording that is not ours to keep
  printable; and `ui/tasks.py` — which is how these tools are actually
  run, as a subprocess behind a progress dialog — now **declares one
  encoding at BOTH ends**, `PYTHONIOENCODING=utf-8:replace` into the child
  and `encoding="utf-8", errors="replace"` on the pipe. `text=True` alone
  means the machine's locale, which is the cp1252 that caused this.
  Console text is therefore ASCII: a menu trail is spelled "Settings >
  Downloads" in a tool and with the arrow in the Qt widgets, where Qt
  draws it properly. That covers DOCSTRINGS too — argparse prints
  `__doc__` for `--help` — which is why the paragraph in `fetch_assets`
  describing this bug names the character rather than containing one, and
  why `tests/test_asset_tools.py` scans the whole file rather than only
  the calls to `print`. It also catches the STALE TRAIL that message
  carried: it named "Setup ▸ Download", two menus that no longer exist.
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
- **CLICKING A SUGGESTION MEASURES THE BOARD AGAINST IT, and the hero
  reasons box is GONE** (`SuggestTile.clicked_hero`,
  `_on_suggestion_clicked`, `scoring.relations_from`), at the user's
  request. It used to open a popup listing the six biggest terms behind
  that tile's own number, on the grounds that a sum can look reasonable
  for bad reasons — a +5 out of one enormous matchup is a different
  suggestion from a +5 out of five small ones. That is still true, and
  those terms ARE these numbers: the synergy with each of your five and
  the matchup against each of theirs. So they go on the ten portraits the
  question is about — "with +5.2" under an ally, "vs -1.8" under an
  enemy — where the eye already is, instead of into a box printed over the
  strip. "I don't need the reason box, as the synergies/counters should
  now shift to show on the 5/5 portraits."
  **A CANDIDATE IS READ AS A POSSIBLE ALLY**, which is the one thing
  `relations_to` could not be left to infer: a hero that is not among your
  five looks exactly like one of theirs, so it answered how your team
  fares AGAINST the hero you are thinking of picking — the opposite of
  what the strip is for. `side="ally"` says to read it as the pick it
  would be.
  Item rules keep their popup, and that is not an inconsistency: a rule is
  hand-authored PROSE, quoted with "hand-authored, not measured"
  attached, and no portrait can show a sentence.
  Clicking a suggestion still does not ENTER it — a pick is entered by
  clicking a slot.
  **AND THE OTHER SUGGESTIONS KEEP THEIR OWN FIT.** A focused candidate
  could show its synergy with every other candidate; it does not, at the
  user's request — "suggestion versus suggestion is too hypothetical",
  and it is: neither hero is on the board, so the pair is a guess about
  two picks nobody has made. **The strip never re-orders either**, also
  asked for: only the numbers on the tiles change, so a hero stays where
  it was last seen instead of the whole strip reshuffling on every click.
- **A STAR IS WHERE THE TWO TABS MEET** (`history/stars.py`,
  `SuggestTile.set_star`, `tilekit.paint_star`,
  `MainWindow._history_run_changed`), at the user's request. The
  suggestion strip ranks by DRAFT FIT — what the ten heroes on the board
  do to this hero — and that number knows nothing about you; the History
  tab knows a great deal about you and nothing about the board. The star
  says "and this is a hero you play a lot and win on", drawn on the tile
  the fit is already on, which is the one place the two answers can be
  read together.
  **ONLY ON THE SUGGESTIONS**, also asked for: "no need to show it on
  the portrait if the hero ends up being picked". That falls out for
  free — a picked hero leaves the strip, since the strip ranks heroes
  NOT in the draft — and the ten picks were never given one.
  **TWO PERCENTILE FLOORS, BOTH THE USER'S TO SET** (`star_pick_pct`,
  `star_win_pct`, Settings ▸ General). The rule is theirs verbatim:
  "rank all the hero picks for that period — only the heroes that rank
  in the top 30% pick rate would be a candidate for the star, same goes
  for win rate, and if both are satisfied they get a star".
  **PERCENTILES RATHER THAN COUNTS** because the History tab's window is
  a DROPDOWN: "8 games" means something quite different over six months
  than over two years, and a bar that moves with the window is a bar
  that stops meaning what it did. A percentile is read against whatever
  was actually measured.
  **THE BOX SAYS "TOP 30%" WHERE THE SETTING STORES 70.** A percentile
  floor is what the rule needs and "top 30%" is what a person means, so
  the conversion happens once, at the control — the alternative is a
  number that goes the opposite way to the words beside it.
  **STRICTLY ABOVE THE FLOOR.** Standing AT the 70th percentile means
  70% are at or below you, which puts you at the top of the bottom 70%
  rather than in the top 30% — with ten heroes the fourth best sits
  exactly on 0.70, so `>=` quietly made "top 30%" four heroes out of
  ten. Ties still move together, because they share one percentile:
  two heroes on the same games and the same rate are the same hero as
  far as this rule can tell, and splitting them by whatever `sorted`
  did would star one and not the other on identical evidence.
  **AND THERE IS STILL A GAMES FLOOR** (`stars.MIN_GAMES`, 2, the same
  number as `analyse.MIN_DISPLAY`). The pick percentile very nearly does
  this by itself — a one-game hero sinks to the bottom of that ranking —
  and "nearly" fails in the degenerate case every floor in `analyse`
  exists for: three games across three heroes and the top third by win
  rate is a hero you played ONCE, at 100%.
  **IT FOLLOWS WHICHEVER RUN IS ON THE TAB**, at the user's request
  rather than being pinned to one account, so looking somebody else up
  re-stars the strip against their history. `HistoryTab.report` is a
  PROPERTY that emits `report_changed`: three places assign it today —
  a run finishing, a cached run loading, and a load that came back
  empty — and the fourth is the one that would forget to announce
  itself, leaving the Draft tab starring the heroes of an account
  nobody is looking at.
  **MEASURED ONCE PER RUN, NOT PER TILE.** It is one pass over a few
  hundred matches and two rankings; the strip is rebuilt on every pick,
  so doing it there would rank the same run again for every hero of
  every draft. And `set_stars` runs AFTER `show_heroes`, which destroys
  every tile — a star applied before that is a star on a widget that no
  longer exists. Moving either bar RE-MEASURES rather than re-filtering:
  the setting is an input to the ranking, not a filter over its result.
  **KEYED BY HERO ID, NEVER BY NAME.** The hero block's buckets are
  keyed by the DISPLAY NAME OpenDota gave the match and the Draft tab
  knows its candidates by the numeric id from its own dataset; matching
  those two strings would be one rename away from a strip with no stars
  on it and nothing anywhere saying why. `stars.measure` walks the raw
  matches, which carry `hero_id`.
  **THE STAR IS THE FRAME'S GOLD**, the third thing in this app wearing
  it beside the window's border and the focus ring — and all three mean
  "this one" rather than "this is good" or "this is wrong". Green and
  red are spoken for by every signed number in the app, so a star in
  either would read as a judgement about the fit beside it. TOP-RIGHT,
  the one corner of a tile with nothing in it: the bottom right is the
  number's and the whole border is the ring's. PAINTED and STROKED like
  every other mark here — a glyph would resize with whatever font the
  tile carries and could not be coloured apart from it, and an unstroked
  mark on a portrait disappears into whatever is behind it. Drawn UNDER
  the focus ring, since the ring is the one line saying what the whole
  board is measured against.
  **AND THE REASON IS A TOOLTIP.** The star's job is to be seen without
  being read; a figure beside it would be a third number in a corner
  that already has the fit in it.
  **EVERY LINE OF THAT TOOLTIP NAMES ITSELF AND THEN GIVES A FIGURE**
  (`_update_suggestions`, `SuggestTile._refresh_tip`, `Stars.why`), at
  the user's request — "Counter Score = +6.46 / Synergy Score = +5.97 /
  My Pick Rate = 17 games (top 32%) / My Win Rate = 53% (top 50%)". It
  was one sentence of prose per fact; five numbers now read down a
  column instead of being picked out of it.
  **AND THE FIT ITSELF IS NOT ON IT.** The line used to be "fit +12.43
  (vs +6.46, with +5.97)" — a total and the two halves that make it, in
  a tooltip hanging off a tile whose badge IS that total. So the parts
  are named and the sum is left where it is drawn.
  The relation line is labelled too and NAMES the clicked hero ("With
  Lion = +5.20"): the badge has no room for a name and does not need
  one, since you just clicked that hero, but a line reading "with +5.20"
  beside four labelled ones is the odd one out.
  **EACH FIGURE CARRIES ITS OWN STANDING IN BRACKETS** (`Stars.why`),
  at the user's request — "after 17 games say (top XXX%), and after the
  win rate say (top XXX%)". It used to name the two FLOORS and say the
  hero was inside them, which is exactly what the STAR says: "having
  the star is evidence of this already". So the line was spending its
  words repeating the mark it was attached to, and could not say the
  one thing brackets are for — HOW FAR inside. "17 games (top 32%) at
  53% (top 50%)" separates a hero you play constantly and win on
  averagely from one you rarely pick and almost always win.
  **AND "IN THE TOP X%" IS NOT ONE MINUS THE PERCENTILE**, which is why
  the floors were named first. `pick_pct` is "the fraction of heroes at
  or below this one", so the most played scores 1.0 and the naive
  complement reads **"top 0%"** — a claim about nobody. It is in the top
  ONE of however many; the share is `1 - pct + 1/N`, so the best of ten
  is the top 10% and the third is the top 30%. The two live side by side
  on `HeroForm` as `_pct` and `_top` because they answer different
  questions: one is compared against a floor, the other is read by a
  person. Ties keep the generous answer they already share, so two
  heroes the rule cannot tell apart print the same number.
- **A COUNT BOX IS NOT WIDE ENOUGH FOR A SUFFIX IT WAS GIVEN LATER**
  (`chrome.CountBox._fit_width`). `QSpinBox.minimumSizeHint` IS CACHED
  and `setSuffix` does not invalidate it: it answered 75px both before
  and after `setSuffix(" days")`, while the text needs 78, so the
  statistics reminder printed **"14 day"** — a number clipped by its own
  units. Re-asking Qt is not enough; the widest value the range can hold
  has to be MEASURED with its prefix and suffix. It is still a FLOOR
  RAISED rather than a replacement, which is the rule this width has
  always had — arithmetic alone once came out narrower than the widget's
  own minimum and clipped the number to its left half — so the chrome
  the font metrics cannot see (the stylesheet's padding and border) is
  recovered as the difference between Qt's hint and the bare digits it
  measured. `ensurePolished` first, or the font is not the stylesheet's.
  This surfaced by moving that box off a bare `QSpinBox` onto `CountBox`
  for the WHEEL: the settings page scrolls, and Qt steps a spin box on
  every notch — the same trap the History tab's controls were all
  converted for, left standing two menus deep where a silently changed
  reminder interval would never be noticed.
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
- **THE MENU BAR IS FILE | VIEW | HELP, AND EVERYTHING ELSE IS A TAB IN
  SETTINGS** (`ui/settings_window.py`, `MainWindow._build_menus` /
  `_command_groups`). It was Setup | Game | View | Help, and most of what
  those two held is done ONCE — install the game config, fetch the
  artwork, pick your ranks — sitting permanently across the top of a
  window that is read at a glance while a draft timer runs. At the user's
  request everything out of Setup and Game is a tab in a settings window
  "like any typical application": General, Downloads, Game data,
  Appearance, Advanced and **Debug**, which is no longer a tab of the
  main window at all. File is Settings… and Update application… and
  **no Quit** — the window's close button is where everybody closes a
  window.
  **FOUR ITEMS WENT ENTIRELY rather than moving**, also at the user's
  request, because each asked for something the app now does for itself
  or says somewhere better: *Make a pinnable shortcut…* (written
  automatically at every start), *Run first-time setup…* (the wizard
  opens itself when needed and the banner is the way back), *Check item
  icons…* (the strip already draws the name and the download reports what
  failed) and *Game data status…* (Diagnose answers the same question by
  naming the ONE broken link).
  **THE SETTINGS WINDOW IS MODELESS AND APPLIES AS YOU GO**, and the
  second half of that is what decides it. A preferences window with OK
  and Cancel is fine for a page of tick boxes — but this one holds the
  DEBUG VIEW, a live picture of what the app is reading, and a live view
  inside a modal dialog cannot be watched while using the thing it is
  showing. So it is built ONCE, kept, and **owns the debug pages
  outright**: borrowing them per opening would mean handing a live widget
  back and forth between two parents, which is exactly the
  parentless-QWidget trap that has produced a second taskbar window three
  times in this app. `_update_debug` goes on asking whether they are
  VISIBLE, which they are not while the window is shut, so it still costs
  nothing when nobody is looking. `_apply_settings` runs on EVERY edit,
  so it has to be idempotent, and is: each branch compares against what
  is already in `self.settings`.
- **HELP ▸ SEARCH IS THE WAY BACK** (`ui/commands.py`,
  `ui/search_dialog.py`, Ctrl+K). Folding two menus into tabs is a better
  place to KEEP a control and a worse place to FIND one, so the app
  carries a list of what it can do and Help searches it. **ONE list, used
  twice**: it builds the Settings tabs and it is what the search
  searches, because two lists would be one of them going stale and it
  would be the search — the half nobody notices is wrong until they
  cannot find something. `test_every_command_the_app_offers_can_be_found_
  by_its_own_name` holds that.
  **IT IS NOT KEYWORD MATCHING**, and that is the whole point: somebody
  looking for a thing types what THEY call it, not what the menu called
  it — "pictures" for artwork, "broken" for diagnose, "my mmr" for the
  rank bracket, "see through" for transparency. Every entry declares the
  words a person might reach for, `SYNONYMS` maps the rest, and the
  ranking is deliberately explainable rather than clever: a whole word of
  the label beats a prefix of it, beats a declared synonym, beats a hit
  in the explanation, and a shorter label on the same terms wins as the
  more specific answer. **EVERY term must hit something** or the entry is
  dropped — a search that always has an answer is one where the top match
  means nothing — which makes `STOP` load-bearing rather than cosmetic:
  a filler word left out of it sinks a whole query, and "it's broken" and
  "nothing from dota" both found the right answer and were then sunk by
  "its" and "from". Enter takes the top match and any result is
  CLICKABLE, at the user's request: a box that only obeys Enter makes the
  list a display rather than a control, and the list is the part that
  answers "what else is there". An empty box shows everything, for the
  same reason. Transparency and Sizes are SLIDERS inside the View menu
  with no dialog to open, so a result for them drops that menu open
  rather than pretending to apply a value.
  **A LIST IS STYLED OR IT IS NATIVE**, the scrollbars' lesson again: the
  results and the session list were painting their selection in Qt's own
  blue — the one colour in this app that means nothing — until
  `QListWidget::item:selected` was named in the stylesheet.
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
  the bottom-right does the sizing.
  **THE WINDOW IS FREELY RESIZABLE AND REMEMBERS ITS SIZE**, which
  REVERSES the lock this file used to describe. It shipped locked
  (`window_locked`, View ▸ Resize window (lock)) because a draft is read
  at a glance with the cursor moving fast near the window's edges, and a
  window that resizes when you meant to click a pick has cost the pick.
  At the user's request the lock is GONE: the grip is always live, the
  floor is the derived `_floor_w` and nothing caps the ceiling, and
  `closeEvent` writes `window_w` / `window_h` — which is what the lock
  was really buying, and it never needed a mode of its own. The
  protection against a stray drag near the edge went with it; that was
  the trade, stated.
  **Two more View items went at the same time and for the same kind of
  reason.** *Reset window position* rescued a window dragged off-screen
  or onto a monitor that is no longer attached — a real hazard for a
  frameless window with no system menu, and one that has not happened.
  *Reload data and library* (F5) re-read the downloaded data from disk,
  which every download task already does for itself and an update does
  by relaunching the app, so the only moment it was reachable was one
  where nothing needed it. `reload_backend` itself STAYS — the tasks
  call it — and so does the method behind the banner. View is
  Transparency and Sizes now, and nothing else.
  **The toolbar rides on the TAB STRIP**
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
  **A pill is for something being WRONG**, and the one that wore one has
  gone. The data age had a green outline when it was healthy — a badge for
  the absence of a problem, and its border was part of what made the
  toolbar taller than the tab bar — then plain dim text, and now nothing
  at all: the age is one startup dialog and no longer appears on the row.
  The pill styles stay for whatever needs one next.
  **Clear all and Detect all sit on the tab row** beside Record and Auto.
  Correcting a bad reading one pick at a time is five right-clicks and a
  picker each, so when the whole board is wrong there has to be a way to
  start over in one gesture and fill it again in another. **Clear all**
  wipes everything the user told the app about THIS match — the
  hand-entered slots, the side corrections, the dragged order, which hero
  is theirs — and then asks for a fresh reading, because otherwise the
  screen's own last answer survives the wipe.
  **A BLANKED BOARD STILL TAKES HAND ENTRY, and that took two goes.**
  While the board is blanked the game's ten are not on it, so `_sides`
  returns the MANUAL slots alone and `_taken_heroes` stops reserving the
  heroes the blanking is hiding. The first version returned `([], [])` and
  kept reserving them, which made hand entry impossible after Clear all:
  `merge` puts the game's five first and cuts to five, so a typed hero was
  dropped on the way in, the board key never changed, the blanking never
  lifted, and clicking a slot appeared to do nothing whatever. The expiry
  lives in `refresh`, once a tick, rather than as a side effect of
  whichever caller asks `_is_cleared` first.
  **THE GAME'S READING SURVIVES IT TOO, so the board is BLANKED**
  (`_cleared`, `_is_cleared`, `_board_key`). Precedence is game > hand
  entry, so on a live match wiping the hand-entered slots changed nothing
  whatever on screen and the next payload put all ten back — "hitting
  clear all didn't work" is exactly right about that. So the board being
  cleared is REMEMBERED and drawn as empty, and it stops being blanked
  when there is a different BOARD to show: a new match, a draft starting,
  or Detect all.
  **The key is the MATCH, not the line-up** (`_board_key`). Keyed on the
  ten heroes it was fragile in both directions: Clear all and Detect all
  both drop the capture session's reading, so recognition comes back a
  hero at a time and any of those partial readings is a different
  line-up — which lifted the blanking and put a half-read board on screen,
  one hero showing where none should be. A hand-entered hero perturbed it
  too. The match id and whether a draft is on are the two things that mean
  "a different board now" and neither wobbles; everything else is lifted
  deliberately, by pressing Detect all. Blanked, never SUPPRESSED — a board
  stuck empty for the rest of the evening would be worse than the thing
  being fixed — and Detect all cancels the blanking BEFORE it looks for a
  capture session, so a cleared board in game-data-only mode still has a
  way back. **Detect all**
  (`CaptureSession.detect_now`) is a ONE-SHOT, deliberately not the Force
  recognition switch: "re-read the board" is something you press once, and
  a mode you have to remember to turn off is a mode left on. It forgets
  `last_read` and resets the stabiliser first — the reason for pressing it
  is that the screen and the app disagree, and the stabiliser would
  otherwise let the old answer outvote the new frame for several ticks.
  With no capture bound it says so rather than appearing to do nothing.
  **There is a RULE between every control** (`chrome.Divider`,
  `paint_rules`, `RuledMenuBar`, `RuledTabBar`, `theme.RULE` = `#808080`,
  the grey exactly halfway between black and white at the user's request).
  Menus, tabs and toolbar controls all get one, and all three are PAINTED:
  neither QMenuBar nor QTabBar has a between-items sub-control a stylesheet
  can reach, `QToolBar.addSeparator` under a stylesheet drew nothing at
  all, and a "|" typed into a label is a glyph that resizes with the font
  and cannot be coloured apart from the label holding it. Same lesson as
  the tick box, the window buttons and the count box's arrows.
  **A SCROLLBAR IS SIX PIECES AND ALL SIX MUST BE NAMED** (`theme`,
  `QScrollBar::*`, `SCROLL` / `SCROLL_HOVER`). The stylesheet styled the
  groove and the handle and stopped there, so `add-page` and `sub-page` —
  the track either side of the handle, which is most of what the eye
  reads as "the bar" — were left to the NATIVE style, along with the
  stepper buttons and their arrows. On Windows that draws a dithered
  texture, and through a translucent always-on-top window it reads as a
  clump of white specks with more specks at each end. This is the tick
  box's lesson from the other direction: once a stylesheet touches a
  widget, the parts it does not name are not left alone, they are handed
  to somebody else to draw. Zero width and height on the steppers is NOT
  enough either — they need `background: none` and `border: none`, or
  there is still a surface to paint into. `QAbstractScrollArea::corner`
  is its own sub-control again, and drew as a grey notch where two bars
  meet. The handle was `BG_DEEP`, DARKER than every surface it sits on,
  so it read as a hole rather than as something to grab; `SCROLL` is
  lighter than the content, a card and a log panel alike.
  This cannot be reproduced on the development machine at all — Linux
  renders with Fusion, and the fault is a Windows-native fallback — so
  `tests/test_scrollbars.py` checks the thing that DECIDES it (every
  sub-control named) rather than how it looks.
  **The count box draws its own arrows** (`chrome.CountBox`), which is the
  tick box's lesson again: styling `QSpinBox::up-button` puts Qt on the
  stylesheet path for that sub-control, and a stylesheet can colour one
  but cannot put a MARK in it without an image file — so giving the box a
  background rule took its arrows off entirely and left a field that could
  not be stepped. `ButtonSymbols.NoButtons`, two painted triangles that
  dim at each end of the range, and `mousePressEvent` handles the clicks
  on them because we drew them. It is also FIXED rather than Minimum,
  because a Minimum policy let the layout hand it whatever was going and a
  two-digit box came out the width of a heading. The width is **Qt's own
  `minimumSizeHint` plus our arrow strip**, never arithmetic: adding up the
  digits and a guess at the padding produced a box NARROWER than the
  widget's own minimum, so the number was clipped to its left half. The
  stylesheet's padding and border are part of the box too, and Qt already
  measures all of it against the real font for the widest value the range
  can hold. The only thing it cannot know about is the strip we took for
  the arrows, because we draw those ourselves.
  **The last control keeps `BandedTabs.EDGE_GAP` clear of the frame.** The
  transparency slider ran its handle into the window's edge, which reads
  as the row having been cut off rather than as it ending.
  **AND THE GAP EITHER SIDE OF EVERY RULE IS MEASURED FROM THE INK**
  (`theme.TOOL_GAP`), at the user's request: "the gap between the last
  character and the |, or the last pixel of the record button and the |
  — it's the effective spacing to the human eye". The widget
  RECTANGLES were already evenly spaced, 8px apart to the pixel, which
  is why nothing in the code looked wrong. What was uneven was the
  PADDING INSIDE them: the three text buttons carried `QTabBar::tab`'s
  own `8px 18px`, so their words sat 34px from their rules while the
  record dot and the tick box — which have no padding at all — sat 10
  and 15. Twice the distance, from a row whose spacing was identical
  everywhere.
  So the buttons keep the VERTICAL padding, which is what puts them on
  the tabs' line, and give up the horizontal; the gap comes from the
  row instead, where one number covers every control whatever it is
  made of. `TOOL_GAP` is read by the toolbar's stylesheet AND by the
  strip that holds the leading rule — that rule lives outside the
  toolbar, so at spacing 0 it sat 10px off the record dot while every
  rule inside sat 22 — and the toolbar's LEFT padding went with it for
  the same reason. `TickBox` gave up two pixels of trailing slack: its
  hint reserved three past the end of the label, and a gap measured
  from ink counts them.
  Measured 21 to 23 across every rule on the row, where it was 10 to
  34. `test_every_control_sits_the_same_distance_from_its_rule` SCANS
  the strip for ink and rules rather than asking the widgets, because a
  rectangle being in the right place is exactly what this looked like
  from the code. Its `styled` fixture comes FIRST: pytest builds
  fixtures in the order they are listed, and a window constructed
  before the stylesheet is applied measures itself against Qt's default
  font and lays the strip out to different numbers.
  **THE CONTROLS ON THIS ROW ARE TAB LABELS, not buttons.** They sit on
  the tab bar's own line and read as one series with Draft / Analysis /
  Debug, so a raised plate in `BG_INPUT` with a radius round it was a
  second kind of object on a row that only has one kind. The stylesheet
  rule copies `QTabBar::tab` deliberately — same padding, same `TEXT_DIM`,
  same lift to `TEXT` under the cursor — and has to repeat `font-weight:
  bold`, because the base `QPushButton` rule sets 500 and would otherwise
  beat the app's bold.
  **TRANSPARENCY IS IN THE VIEW MENU** (`_add_transparency_menu`), not on
  the row: it is set once and left alone for the evening, and this row
  should hold the things pressed mid-draft. It is still a SLIDER, in a
  `QWidgetAction` — a submenu of fixed percentages would have been more
  menu-like and worse, since this is a value tuned by eye against a
  running game a few percent at a time. The menu stays open while the
  handle is dragged, which is the whole point.
  **A widget that paints its own text must ASK for its colour.**
  `TickBox` drew its label in `theme.TEXT` outright, so the `color:` rule
  that dims every other label on the row never reached it and "Auto" sat
  brighter than the tabs and buttons beside it — the same class of bug as
  the label backgrounds, from the other direction. It reads
  `palette().color(foregroundRole())` now, which is where a stylesheet's
  `color` lands, and does the tabs' hover lift itself because a
  pseudo-state colour does not reach a widget that paints its own text.
  **The status line is a FOOTNOTE**, 70% of the body size at the user's
  request: it is read when something is wrong and ignored the rest of the
  time, so at the body size it competed with the draft above it.
  The record control is a round red dot
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
  **The window buttons are PAINTED too** (`chrome.WindowButton`). They
  were the characters "─", "□" and "✕", and a hollow square has no ink in
  the middle of it: at one point size it reads visibly smaller than a dash
  and a cross, and every change of the app's font resized the three by
  different amounts. Three lines and a rectangle are the same size in
  every font there has ever been. `test_the_window_buttons_are_the_same_
  size_as_each_other` measures the INK's bounding box rather than the
  widget, because that is what the eye compares.
  **The floating toggle paints its own plate and icon.** It used to hand
  the icon to QPushButton, and a translucent frameless top-level button
  under a stylesheet drew the plate and nothing else, so the one thing on
  screen with the window hidden was a blank square. Same class of bug as
  QHeaderView refusing to honour `iconSize`, and the same answer: draw it.
- **The app icon has FOUR sources** (`ui/appicon.py`): `assets/app.ico`
  or `.png` if the user put one there, else **`assets/app-default.png`
  (or `.ico`) if this repository ships one**, else **Bloodseeker's
  portrait out of `assets/portraits/base/`**, else a drawn fallback.
  **THE SHIPPED DEFAULT HAS A DIFFERENT NAME FROM THE USER'S, and that
  is the whole point of it** (`DEFAULT_CANDIDATES`, `default_path`).
  Settings ▸ Appearance ▸ Choose app icon… writes `app.ico`; if the
  committed default
  used that name too, the ZIP updater would stamp on a choice somebody
  made on their own machine every single update. Two names, two owners,
  and the user's wins. `assets/app.*` stays gitignored for exactly that
  reason and `assets/app-default.*` deliberately is not — a committed
  file that is ignored would silently do nothing.
  Whatever goes in the default slot has to be THE PROJECT'S TO
  DISTRIBUTE: the same bar the bundled fonts had to clear, and the one
  Valve's and Blizzard's artwork does not.
  **"IS AN .ico" MEANS THE CONTAINER, NOT THE NAME** (`is_ico`). Qt
  sniffs an image's content and ignores its extension, so a PNG renamed
  to `.ico` loads perfectly and the TITLE BAR looks right — while the
  Windows shell, which needs a genuine ICO container for a taskbar
  button, a pin and a shortcut, quietly draws something else. Title bar
  correct and taskbar wrong is the whole signature of that mistake, and
  it is the obvious way to "convert" an image. So the six-byte header is
  READ (zero, a 1 for icon, and a non-zero image count — a header
  claiming zero images is not a usable icon either), and a file that is
  not really one is rebuilt at every size like any other raster and a
  proper `app-generated.ico` is rendered for the shell. The picture was
  never the problem; the wrapper was.
  **AND AN `.ico` IS A DIRECTORY OF IMAGES, WHICH MAY HOLD ONE**
  (`ico_sizes`, `covers_the_shell`, `PASS_THROUGH_MIN` 128). A genuine
  icon file carrying a single 32x32 passes every header check, draws a
  title bar perfectly, and leaves a TASKBAR button — which asks for 40,
  48 and 256 depending on the display's scaling — nothing to work from.
  Title bar right and taskbar wrong for the second time, from a
  completely different cause than the renamed PNG. So the DIRECTORY is
  parsed too, and a file whose biggest image is under 128 is rebuilt
  around that image rather than handed over: upscaling a 32 to a 256 is
  not pretty, but a button drawn from something beats one drawn from
  nothing, and the real fix is to supply the PNG and let the app render
  the .ico itself.
  **AND THE TWO NAMES ARE NOT TRIED IN ORDER** (`biggest_image`,
  `_best`, `chosen_path`). `DEFAULT_CANDIDATES` named `app-default.ico`
  ahead of `app-default.png` and `default_path` returned the first that
  existed, so a 1024x1024 PNG dropped in beside an `.ico` holding a
  single 32x32 was never opened — and the advice that produced that
  state was "supply the PNG and let the app render the `.ico` itself".
  Following it changed nothing whatever, with the ignored file sitting
  in the folder: **title bar right and taskbar wrong for the THIRD
  time**, from a third cause, and the only one of the three where the
  fix was already on disk. So the question is not which name sorts
  first, it is which file has the most to draw with — `biggest_image`
  reads an `.ico`'s directory or a raster's header, never decoding a
  megabyte to find out, and a zero doubles as "Qt cannot read this",
  so a corrupt file can never beat a good one. A real `.ico` wins a
  TIE, since it is handed over untouched; the list order breaks the tie
  after that. Two files can no longer produce a worse icon than either
  of them alone, which is the property that was missing. A 32x32 on its
  own is still used and still rebuilt around — that was asked for
  outright and ranking by size must not become refusing the small one.
  `shell_ico` asks `chosen_path` rather than carrying its own pair of
  filenames: two lists that can disagree is how the window and the pin
  end up drawing two different pictures, which is worse than either
  being wrong. `describe()` puts the file, what is inside it and
  whether it is passed through or rebuilt into Debug ▸ Copy everything,
  because none of the three causes is visible in the picture and all
  three are one line.

  **AND THE ENTRIES BELOW 256 MUST BE DIBs, NOT PNGs** (`write_ico`,
  `_dib_entry`, `PNG_ENTRY_MIN`). This is the FOURTH cause of the same
  symptom and the one that survived fixing the other three: with the
  right file chosen and every size baked, the shell's copy was still
  wrong. `write_ico` PNG-compressed every entry on the strength of
  "every Windows since Vista reads PNG icons" — but what Vista added was
  PNG at **256**, for the extra-large view. The shell's older icon paths,
  the ones that draw a TASKBAR BUTTON, a pin and a shortcut at 16, 32 and
  48, expect the original DIB layout and draw nothing when handed a PNG
  at those sizes. Qt reads either, which is exactly why the window's own
  icon was perfect throughout while only the shell's copy was wrong —
  and why the picture never showed which of the four faults was in play.
  So 256 stays PNG (it is huge as a DIB, and it is the size the format
  documents as PNG) and everything the taskbar actually asks for is
  written the way icons have been written since 1985. Three silent traps
  in that encoder: the BITMAPINFOHEADER's **height is DOUBLED** because
  it counts the colour bitmap and the AND mask as one image, the mask's
  rows are padded to four bytes, and a DIB is stored **BOTTOM-UP** — so
  the rows are reversed, and the test compares every entry read back
  against what the app draws AND against its own vertical flip, since a
  16px icon is far too small for an upside-down one to be obvious.
  `identity_note` NAMES THE ICON FILE (`_identity_summary`): it used to
  read identically whether `shell_ico` had returned a path or None, so a
  report saying "set on hwnd ..." was consistent both with the shell
  having been handed a picture and with it having been handed none —
  the one question the note exists to answer.

  **A SUPPLIED FILE IS REBUILT AT EVERY SIZE UNLESS IT IS AN `.ico`**
  (`_from_file`). A real .ico already carries each size drawn or hinted
  for it, so it is used exactly as supplied. Everything else is ONE
  image — a 1024x1024 PNG is the normal thing to be handed — and a QIcon
  carrying a single pixmap is precisely how a taskbar button comes out
  blurry: Windows asks for 16, 32, 48 and 256, finds only the one, and
  scales it itself. So a raster file is downsampled once per size in
  `SIZES` with a smooth transform, which the drawn and portrait sources
  always did and this branch was skipping. The user asked first for the Frozen Throne icon and then
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
  reason `appicon.install` and Settings ▸ Appearance ▸ Choose app icon…
  exist: a file
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
  **AND THE LIVE TASKBAR BUTTON IS NOT DRAWN FROM ANY OF THAT**
  (`push_native_icon`, `window_icon_note`). Fifth cause, and the first
  one outside the files: with the right source file chosen, every size
  baked, a valid DIB `.ico` written and the relaunch properties set and
  NAMED in the diagnostic, the button was still wrong. Everything above
  is what a PIN and a jump list are built from. A button for a window
  that is RUNNING comes from the window itself — `WM_GETICON`, then the
  window class, then the executable — and the only thing addressing that
  was Qt's `setWindowIcon`.
  Which this app then undermined by ORDER. `setWindowIcon` ran at the
  top of `MainWindow.__init__` and `setWindowFlags(FramelessWindowHint |
  WindowStaysOnTopHint)` five lines later — and changing a window's
  flags on Windows DESTROYS AND RECREATES the native handle, so the icon
  went to an HWND that no longer existed and the button fell back to
  pythonw.exe. Note the shape, because it is the same one five times
  over: our own painted title bar reads `appicon.pixmap` directly and
  was right throughout, while every mechanism the SHELL reads had
  nothing in it. So the icon is re-applied after the flags, and
  `push_native_icon` sets it explicitly through `WM_SETICON` from the
  `.ico` already rendered, at `SM_CXICON`/`SM_CXSMICON` rather than at
  guessed sizes because a display at 150% asks for different numbers.
  Two traps in that ctypes call, both silent: **`restype` is not
  optional** — the default is a 32-bit `int`, so a 64-bit `HICON` comes
  back TRUNCATED and the call cheerfully sets a handle to nothing — and
  **the handles must outlive the call**, since Windows does not copy
  them, so they are kept in a module list. It READS THE ICON BACK with
  `WM_GETICON` rather than reporting that a message was sent, and
  `window_icon_note` carries that into the paste beside `identity_note`:
  the two fail independently, for different reasons, and a report naming
  one cannot say which is at fault.

  **AND NOTHING IN THIS MODULE MAY RUN BEFORE THE QApplication**
  (`gui_ready`). Touching a QPixmap without one does not raise: Qt
  prints "QPixmap: Must construct a QGuiApplication before a QPixmap"
  and **ABORTS THE PROCESS**, so no `except` anywhere catches it and
  there is no traceback — from outside it is simply an app that does not
  open, which is exactly what shipping the shortcut fix did. It was
  called from `main()` beside `claim_taskbar_identity`, and it reaches a
  QPixmap through `shell_ico` → `write_ico` → `pixmap`.
  `claim_taskbar_identity` is pure ctypes and MUST run before the first
  window, so it stays there; everything else about the icon waits, and
  that is the distinction that was missed. `icon` and `write_ico` now
  RAISE (catchable) rather than abort, `shell_ico` answers None, and
  `ensure_start_menu_shortcut` says "called before the QApplication
  existed" — the worst a caller can now do is get no icon rather than no
  application. The test runs every painting entry point in a SUBPROCESS
  with no QApplication and requires it to survive, because an abort
  cannot be observed from inside the process it kills.

  **AND AN AppUserModelID OBLIGES THE APP TO PROVIDE THE SHORTCUT IT
  RESOLVES TO** (`ensure_start_menu_shortcut`, `write_shortcut`,
  `shortcut_note`). SIXTH cause, and the evidence that isolated it was
  the readback added for the fifth: `window icon: ... reads back
  big=217317543 small=69338861` says the window HAS its icon at both
  sizes, and the button was still wrong — so the window is not the
  source, and nothing about files is either.
  Declaring an ID stops Windows treating the process as pythonw.exe and
  makes it its own application; the shell then resolves that
  application's icon and name through the Start-menu shortcut carrying
  the same string. `claim_taskbar_identity` did the first half and
  nothing did the second, so the button had **stopped being Python and
  had not become anything** — which is why it drew as a BLANK PAGE
  rather than as Python's logo. That distinction is the whole diagnosis
  and it was in the user's words for several rounds before it was
  used: Python's logo would have meant the ID was not taking, a blank
  page means it took and resolved to nothing.
  So the shortcut is written AUTOMATICALLY at startup, at the user's
  request ("it should be all auto anyway") — it was Setup ▸ Make a
  pinnable shortcut…, a menu item that has since been DELETED outright, which is a step nobody who has just unzipped this
  app would know to take. One file, inside the user's own Start menu.
  **REWRITTEN ON EVERY START, not only when missing**, because the thing
  it points at moves: this app is normally run from an unzipped folder,
  and downloading a newer ZIP produces a SECOND folder beside the first,
  so a shortcut left pointing at the old one is worse than none. A few
  milliseconds against a fault that is invisible until somebody clicks
  it. Once per process, never fatal, and silent — a Start-menu entry is
  not worth interrupting a first run about.
  **AND WRITING THE FILE IS NOT ENOUGH ON THE RUN THAT WRITES IT**
  (`announce_shortcut`, `SHChangeNotify`). The shell resolves an
  AppUserModelID against its own INDEX of Start-menu shortcuts, and a
  `.lnk` that has just appeared is not in it yet — so the taskbar button,
  created moments later when the window is shown, still finds nothing.
  By the next launch the index has caught up, which is exactly the shape
  reported: blank on a fresh unzip, correct once an update has restarted
  the app, "so its progress - but not fulling auto yet".
  `SHChangeNotify` is the documented way to say "notice this now", and
  BOTH the file and its folder are announced because they are indexed
  separately. Never fatal — an un-announced shortcut is still a shortcut
  and is picked up on the next start regardless, which is the behaviour
  it is replacing rather than relying on.
  Deciding WHICH icon file (`chosen_path`, `biggest_image`,
  `covers_the_shell`) is byte reads and an image HEADER read, so it is
  safe before a QApplication; only RENDERING is not. That is checked in
  a subprocess, because if it ever stops being true the app stops
  opening rather than failing a test.
  `write_shortcut` is the ONE implementation and `tools/make_shortcut.py`
  calls it: two copies could write two different shortcuts for one
  AppUserModelID, which is the same disagreement that had `shell_ico` and
  `_build` choosing different files. The tool keeps only what is its own
  — the printing and opening the folder — and the shortcut NAME is spelled
  once, for the reason the font family is.

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
  `tools/make_shortcut.py` (no menu item any more) writes
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
- **AN EMPTY GRID IS THE SHAPE THE FILLED ONE WILL BE, and it was not**
  (`_show_outline(columns)`, `_size_blank`, `_blank_metrics`,
  `_apply_icon_box`). Reported from a real draft: "the placeholder empty
  table size was not accurate to what is shown once the heroes are
  selected". The whole argument for drawing an outline is that it is the
  shape of the answer standing where the answer will appear, so a
  placeholder of the wrong size is worse than none — the card changes
  size under the reader the moment the first pick lands.
  TWO CAUSES, both of them "the empty state was written once and the
  filled state moved".
  **SIX SECTIONS, NOT FIVE.** Both cards are six across once they hold
  something — counters is five columns plus the portrait column down its
  side, synergy is five plus the gap between its triangles and has no
  side column at all — and the outline was five columns for both. So the
  empty synergy card was a section narrower than the grid replacing it,
  and worse, `sections()` answered 5, `_portrait_room` divided the card
  into five, and its placeholder portraits came out visibly BIGGER than
  the real ones. `_show_outline` takes the count from its caller, which
  is the only place that knows which grid this is.
  **AND `_apply_icon_box` UNDID THE REST.** It runs after `_show_outline`,
  from the window's own resize path, and read "no heroes in the headers"
  as "the portraits are not downloaded" — where falling back to names is
  right, since a 68px row header elides "Tidehunter" for nothing. An
  EMPTY grid has no heroes either, and there the names fallback collapsed
  every placeholder row to the height of a line of digits a moment after
  it had been sized correctly. Two different states wearing one test;
  `_outline` tells them apart. `_blank_metrics` now also spells the same
  `size` line the filled path uses, floor included, because two spellings
  of one measurement is one of them drifting.
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
  saying ("this source publishes no ally-pair data") sits beside the
  outline, never in place of it — but **"Fill in both teams" and "Fill in
  your own team" were not among them and are gone**: the empty 5x5 already
  says the grid is waiting for picks, and a sentence saying so underneath
  it is read once and skipped forever. `MatrixTable.show_matrix` still
  takes an `empty_text`; the caller just has nothing to put in it. **"Nothing urgent
  flagged" is not one of those reasons**: silence IS the answer there, the
  plates already say the strip is working, and a sentence explaining that
  nothing is wrong is read once and skipped forever.
- **Update restarts the app, and it lives in Help** (`_update_and_restart`,
  `_update_app`).
  **IT RESOLVES WHAT TO PULL RATHER THAN ASSUMING IT**
  (`tools/update_app.py`). The step was a bare `git pull --rebase
  --autostash`, which fails outright on a branch with no upstream —
  *"There is no tracking information for the current branch"* — and that
  is not an exotic state: a branch made locally has no upstream until
  something sets one, and THIS repository's remote has never carried a
  `main` or a `master`, so a checkout sitting on `master` has nothing to
  track and nothing to guess from. The target is worked out in order: the
  branch's own upstream, then `origin/<same name>`, then the remote's
  default branch, then — when the remote has exactly ONE branch — that
  one, which is unambiguous whenever it holds. Several branches and no
  match is REFUSED with the command to run, because pulling somebody's
  half-finished branch into their working copy because it sorted first is
  worse than saying so. The upstream is then set, so the next update is an
  ordinary pull and the ladder is skipped.
  **IT ONLY EVER UPDATES THIS REPOSITORY.** `origin` is checked against
  the app's own name before anything is fetched. The match history
  analyser was folded in from another repository and nothing may reach
  back to it; an origin that is not this app is named and refused.
  **THERE ARE TWO KINDS OF INSTALL AND THE BUTTON WORKS ON BOTH**, which
  reverses this file's earlier position that git is a REQUIREMENT of
  updating. That held while the only copy of this app was the one it was
  written on. It stops holding the moment a stranger has one: installing
  git is where most people give up, GitHub's Download ZIP button is what
  they will actually press, and "install git and clone it properly" is a
  fine answer for the author and a useless one for somebody who just
  wants the new version.
  A CLONE (`.git` present) is still updated by git, unchanged, because
  git is the only thing that brings new code down while keeping the
  user's own edits and re-applying them on top.
  A DOWNLOADED COPY (no `.git`) downloads the release branch's archive and
  writes the files out (`zip_update`, `download`, `unpack`, `apply_tree`).
  **THE ARCHIVE IS THE MANIFEST, and that is the whole safety argument.**
  A GitHub archive carries exactly the files the repository TRACKS, so
  everything gitignored — the Stratz key in `.env`, `ui_settings.json`,
  `preferences.json`, `calibration_local.json`, `history_accounts.json`,
  `data_cache/`, every downloaded portrait and item icon, `recordings/` —
  is not in it and therefore cannot be written over. The user's key
  survives every update BY CONSTRUCTION rather than by a list somebody
  has to remember to maintain, which is what the earlier objection
  ("copying a fresh download over the top would take `rules/items.yaml`
  with it") was actually about. `NEVER_WRITE` is belt and braces for the
  day somebody commits a `.env` by accident. Deletions are handled by
  remembering what was written last time (`installed_version.json`,
  gitignored, path resolved at CALL time by `install_file()` for the same
  reason `load_layout` is): a stale module left on disk is not inert, it
  is importable. An archive path containing `..` is refused before
  anything is extracted.
  **ALREADY UP TO DATE IS A SUCCESS, NOT AN ERROR.** The head commit is
  read off GitHub's API and compared with what was installed; equal means
  say so and stop. And a version check that FAILS (rate limit, outage)
  does not stop the update — unknown means download, because the check
  breaking the thing it exists to help is the worse way to be wrong.
  **THE RELEASE BRANCH IS `main`** (`RELEASE_BRANCH`), and it is what
  makes this safe to hand out: development happens on branches and `main`
  is what a stranger's copy follows, so half-finished work never reaches
  anybody. `choose_target` prefers it over `origin/HEAD` — a clone still
  follows whatever it is actually tracking, so the author's own checkout
  is unaffected.
  **THREE FAILURES THAT ARE NOT BUGS, each with its own sentence.** No
  `origin` remote at all; an `origin` that is not this app; and a folder
  that is a clone (`.git` present) on a machine with no git, which is the
  one case git is still needed for — answered with the install link AND
  with the fact that deleting `.git` makes the same button download the
  new version instead.
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
  **THE UPDATE IS THE CODE AND NOTHING ELSE**, which REVERSES this
  file's earlier "the update fetches the artwork too". That step ran
  `tools/fetch_assets.py` last, on the reasoning that nobody handed this
  app should be left short of a picture — and in practice it made Update
  sit for minutes pulling 126 portraits, every item icon and the
  community's alternative portraits, behind a progress box that reads as
  a FROZEN APPLICATION. On a press whose whole point is "get the new
  code and reopen", minutes of network is the wrong trade, and the user
  said so. So the task is `update_app.py` and a `pip install`, and it
  takes seconds.
  Nothing about the artwork is lost, because five other paths already
  reach it: `fetch_assets` is its own task (Settings ▸ Downloads ▸ All
  artwork), the first-run wizard runs it, the recurring statistics job
  (`update_data`) still tops it up — that is the one that is MEANT to
  take a few minutes — and the banner flags what is missing with a
  button that fetches it. Both halves still skip what is on disk, so a
  retry costs only what is absent.
  **THE COST OF THAT IS A NEW BANNER RUNG** (`portraits.missing_for`).
  `any_downloaded` answers "is there artwork AT ALL", which goes true on
  the first download and stays true for ever — so a hero added in a
  patch had no picture and nothing anywhere said so. That was invisibly
  covered by the update fetching artwork every single time; with that
  gone, this is the only thing that notices. It is the LAST rung on
  purpose: a wrong rank bracket and stale statistics are the ADVICE
  being wrong, while a missing portrait is one tile drawing blank. And
  it must come after the "no statistics" rung either way — `missing_for`
  reads `_index`, which caches ABSENCE, so asking it on a fresh install
  from a strip the live loop refreshes would cache "there are no
  portraits" on the first tick and never revisit it.
  **A FRESH INSTALL IS A WIZARD, NOT A BANNER NAMING A FILE**
  (`ui/setup_wizard.py`, `MainWindow.offer_setup` / `_run_setup`). The
  app opened to empty tiles over a strip telling the user to go and edit
  `.env`, which is fine for the person who wrote it and no use to
  somebody who has just unzipped it. One dialog on first open instead:
  what this needs, the key, tick boxes for the ranks, Finish. **TICKING
  THE BOXES IS THE WHOLE INTERACTION** — Finish writes `.env`, saves the
  brackets and starts the download; an install that ends by telling the
  user to find a menu item has not finished installing. `needed()` asks
  only about the KEY, so an existing install never sees it and a fresh
  one sees it once. The menu item that reopened it is GONE at the user's
  request, so the banner's button is the one way back.
  **THE KEY IS VERIFIED BEFORE IT IS TRUSTED** (`stratz.check_key`), or a
  typo surfaces three minutes later inside a progress dialog and reads as
  the app being broken. The query is `{__typename}` — part of the GraphQL
  SPECIFICATION rather than Stratz's schema, so it cannot start reporting
  "bad key" the day they rename a field, and what is actually being
  tested is the HTTP status. `KeyCheck.ok` is three-valued for the usual
  reason: 401/403 is a rejection, but a rate limit, a 500 or a dead
  connection is asked-and-not-answered and must NEVER block Finish —
  telling somebody with flaky wifi that their key is bad sends them off
  to get another one they did not need. Editing the box clears the last
  verdict, or a rejected key corrected by one character would inherit it.
  It is SKIPPABLE at the user's request, and skipping writes nothing at
  all; the banner is the way back.
  **A WRAPPED QLabel MEASURES ITSELF AS ONE LINE** (`setup_wizard.
  paragraph`), and `heightForWidth` does not propagate up through nested
  layouts — so both long paragraphs in this dialog were drawn ON TOP of
  the controls beneath them, with the preset buttons squashed to no
  height at all. The fix is to ask the LABEL what it needs at the width
  it will get (`heightForWidth`, never a font-metrics bounding rect,
  which came out a line short because it measures the string rather than
  what the label lays out) and make that its minimum. It holds at any
  size at or above the dialog's minimum, since a wider label only ever
  needs fewer lines. The ranks and the presets are GRIDS for the same
  reason: eight brackets and five pairs across one line each elided to
  "Guardi", "Crusad", "ald – Crusa", which is a rank picker you cannot
  read the ranks off. This was caught by rendering the dialog and looking
  at it, not by a test — the tests all passed.
  `config.save_stratz_key` rewrites only the key's LINE — `.env` is
  exactly the sort of file people add variables to — and sets
  `os.environ` as well, because `load_dotenv` does not overwrite a
  variable already in the environment and the key would otherwise be
  ignored until a restart.
  **A FRESH INSTALL STILL LEADS WITH THE ARTWORK** (`portraits.
  any_downloaded`, `_update_first_run_banner`), because the pictures need
  no account while the statistics need a key the user has to go and get,
  and leading with the key leaves somebody staring at empty plates while
  they sign up for something.
  **THE BANNER LADDER IS: game feed, no artwork at all, no statistics,
  bracket changed, statistics stale, SOME artwork missing.** The last two are at the user's request and
  the fifth REPLACES `_prompt_if_data_is_old` rather than joining it —
  the age was once a banner, a pill AND a status segment, was cut to one
  startup dialog for that reason, and a dialog dismissed on the way to a
  draft is dismissed forever while the thing it asked about stays true.
  So it is one strip with the days on it and a button that fixes it,
  showing nothing at all under the reminder interval. The bracket case is
  checked FIRST because those numbers are the wrong RANK rather than
  merely old, and the user reaches it by changing the setting and coming
  straight back to this screen. Both buttons run `_update_everything` —
  statistics and artwork in one task, which is what a button saying
  "update" should mean.
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
- **THE DEFAULTS ARE THE OWNER'S OWN SETUP** (`ui_settings.DEFAULTS`), at
  their request: "have a look at the current state of the app — the size
  of the window, the set points in the analysis — and make it the
  default". Every value in that dict was read off their own
  `ui_settings.json` rather than picked, so a fresh install (or a second
  machine) opens on the arrangement they settled on: a 940x998 window,
  fully opaque, 20 suggested picks and 7 items, the History tab over six
  months and 5000 matches with every split ticked and each table's own
  top-N and sort. Their own file still wins on their own machine — it is
  gitignored and survives every update — so this only ever decides what a
  copy with no settings yet does.
  Two things were deliberately NOT taken from that file. `item_hero`
  names one account's most played hero, and shipping it would have a
  fresh install open the item block on somebody who is not in its list;
  it falls back to the first (most played) hero, which is right for
  anybody. And `overlay_x`, `overlay_y`, `overlay_expanded` and
  `overlay_rows` were REMOVED rather than updated: nothing has read any
  of them since the floating overlay went, and because DEFAULTS is the
  write filter a dead key is a line written into everybody's settings
  file for ever.
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
  **IT IS A cmd.exe SCRIPT AND NOTHING HERE CAN RUN IT**, which is the
  whole reason `tests/test_launcher.py` READS it instead. Its failures
  land on somebody else's machine on their first run, where there is no
  traceback and nobody to ask for one. Two rules it broke and now cannot
  break again: redirect to **`nul`**, never `/dev/null` — the Unix null
  device is a PATH to cmd.exe, which cannot find it and prints "The
  system cannot find the path specified." — and silence **both streams**
  on a `where` probe, since `where` reports a miss on stderr and
  `>nul` alone still prints "INFO: Could not find files…" at the user.
  It shipped in the two `where` lines that pick the Python command, which
  is the worst possible place: they run before anything else, so the
  error was the first thing a new user ever saw. The file's line endings
  are **CRLF** and must stay that way.
  **THE KEY IS THE APP'S JOB, NOT THE LAUNCHER'S.** The script used to
  copy `.env.example` over and open it in Notepad, so a new user was
  asked for a Stratz key TWICE — once by a text editor before the app had
  opened, and again by the first-run wizard inside it. The wizard wins:
  it checks the key against Stratz before accepting it and takes the rank
  brackets in the same pass, neither of which a text editor can do. The
  launcher builds the environment and starts the app, and nothing else;
  `save_stratz_key` writes `.env` when it needs to. `.env.example` stays
  in the repository as documentation for anyone who would rather do it by
  hand.

## Out of scope for the prototype

Ban-phase handling. Don't preclude it architecturally; don't build it.

The personal match-history review tool WAS on this list and is now built —
see the History tab above. It arrived as a whole separate repository
(`bijankle/DotaGameHistoryAnalyser`, a single-file browser page) and was
folded in at the user's request; that repository is theirs to archive.
