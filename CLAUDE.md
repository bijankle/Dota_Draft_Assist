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

  **The lane slots are NOT a check.** They are where a hero was placed on
  the strategy map — yours in the lane you chose, theirs in the lane you
  predicted — and two team-mates can share a lane (pudge with axe, dragon
  knight with juggernaut in two recordings). Two attempts at using them to
  validate the split were both wrong. Do not reintroduce it.

  **Only `STRATEGY_TIME` is read**, and the first complete reading is
  latched for the match by `GsiProvider`. After strategy time the minimap
  holds real units rather than strategy-map slots and the object order
  means something else: one recorded session produced a correct split at
  16s and a scrambled one at 43s from the same match. The latch clears on
  a new `HERO_SELECTION` or a new match id.

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

  `GsiState.lineup_source` says which of these produced the picks, and the
  UI shows it. `PLAYER_COMPONENTS` / `SPECTATOR_COMPONENTS` are a guide to
  what to look for, never a claim about what arrives: the same recordings
  carried `buildings`, `minimap`, `roshan`, `couriers` and `neutralitems`
  in a player's own feed, which this file had listed as spectator-only.
  All of the above is re-derived from a recording, per phase and per match,
  as one section of the session report.
- **The draft panel is keyboard-first and refuses duplicates.** A hero
  already in the draft cannot be entered again on either side —
  `_taken_heroes()` is the single source for that, so typing and the picker
  cannot disagree. Enter leaves focus in the entry box for the next pick;
  clicking a slot opens one picker and never chains. Tab walks the ten
  slots (they are `StrongFocus`), so the entry side moved to Ctrl+Tab.
  Roles (Pos 1-5) are assigned per SLOT, not per hero, and survive the hero
  changing: a slot is a lane. Vision reads the ranked-role icons but is not
  wired to these yet — that waits on the crop geometry being right. Each
  slot reserves a line ABOVE it for the click view's signed number whether
  or not one is showing: slots that grew by a text height on every click
  made the column restless, and a draft panel that moves under the cursor
  is one you misclick.
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
- **Every grid carries its margins** (`Matrix.row_totals` / `col_totals` /
  `total`, drawn as a Σ row and column). The grid says which PAIRING is
  bad; the margins say which HERO is, which is the question you act on
  while you still have a pick to make. The totals are the sum of what is
  DRAWN, deliberately: in the synergy grid only the upper triangle is
  filled, so a hero's row total and column total are each partial and
  neither is its full synergy — consistency with the cells above the number
  was chosen over completeness, because a total nobody can check against
  the grid is worse than no total. The grand total sums the cells rather
  than the margins, so each pair counts once in both grids. Main-window
  columns STRETCH rather than fit their contents: the Σ column must never
  be the one pushed off the right edge.
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
  Colour is reserved for meaning — green/red for signed deltas, blurple for
  the one action a screen wants, amber for warnings — and everything else
  is grey, so a number in colour is always worth reading.
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
- **Ranked-role-queue role icons are ground truth** for roles, read from the
  draft screen; a manual override exists in the UI for when reading fails.
- **The item panel is measured vs. asserted**: hero scores come from data; item
  rules are hand-authored in `rules/items.yaml`. The UI labels them as such.
  Item panel shows at most 5 items above a severity floor, only after the
  user's pick is locked. Silence in many games is correct — do not tune it away.
- **The in-game numbers hang off the crop boxes** (`ui/portrait_overlay.py`).
  The click view again, painted under the ten portraits where the eye
  already is. No panel and no background — a halo (a dark stroke around the
  glyphs) is what makes text legible over an arbitrary screen, and a filled
  box over the pick bar would hide the thing it annotates. It uses
  `snapshot.left` / `.right`, the SCREEN banks, never ally/enemy: left and
  right are facts about pixels, ally and enemy are facts about the draft,
  and putting your team's numbers over their portraits would be worse than
  showing none. With nothing clicked it falls back to
  `scoring.net_contributions` so every portrait still carries a figure.
  Locked it is click-through (`WA_TransparentForMouseEvents` plus
  `WindowTransparentForInput`) — an overlay strip that ate clicks meant for
  Dota would be worse than no overlay — and View ▸ Unlock overlay anchors
  takes the mouse so the numbers can be dragged, saving a FRACTIONAL nudge
  (`portrait_dx` / `portrait_dy`), in the same units as every other
  coordinate here. Hiding the overlay re-locks it, or it would come back
  swallowing clicks.
  **The badge is the switch, not the menu tick** (`_sync_portrait_overlay`):
  collapsing the callout takes the numbers with it and expanding brings
  them back, because the badge is the only part of the overlay visible from
  inside Dota and a tick you cannot see mid-draft is not a toggle. The
  badge is also the drag handle — an event filter turns a press into a drag
  once it passes `DRAG_THRESHOLD` and then swallows the release, so moving
  it never also flips the panel.
- **The overlay sits OVER Dota, never inside it.** `ui/overlay.py` is an
  ordinary frameless always-on-top window: no DLL injection, no hooking of the
  present chain, no input sent to the game — which is what keeps it on the
  safe side of the boundary above. It needs Dota in borderless windowed mode,
  and it is deliberately interactive (not click-through) because the badge has
  to be clickable and draggable. This reverses the original spec's "no
  overlay" decision, at the user's request; the main window is unchanged.
  The callout carries the same two grids as the Draft tab, compact
  (`MatrixTable.set_compact`: no caption, shortened names, fixed columns,
  height fitted to the rows) — mid-draft it is the only surface being
  looked at, and a ranked list of candidates does not answer which lane
  loses.
- **GSI carries no screen geometry.** It reports game state, not pixels (the
  only coordinates in it are hero world positions). So the overlay anchors
  itself to the Dota window rectangle, which Windows supplies from the window
  handle; anything drawn against specific portraits needs coordinates from a
  saved frame, which is what the snapshot key exists for.
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
