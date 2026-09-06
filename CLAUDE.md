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
- **The item strip lives under the draft and is live from the first enemy
  pick** (`ui/item_row.py`, `ui/item_icons.py`). It was a paragraph of
  prose in a side panel gated behind locking your own hero, so on the
  screen where items matter it was blank, and by the time it filled the
  decision it informed was made. Icons rather than names because the strip
  is read in the corner of the eye — a player recognises a BKB by its shape
  long before reading the words — with the strongest trigger's severity as
  a colour bar and the whole reasoning in the tooltip, since a strip that
  explained itself in place would be the paragraph again. Icons are
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
  At most 5 items above a severity floor. Silence in many games is correct
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
- **Frameless means the chrome is ours to draw.** Windows' own title bar is
  a white strip above a dark app and reads as a different program bolted on
  top. `TitleBar` replaces it, and the menu bar goes INSIDE it — NOT
  `self.menuBar()`, which QMainWindow would place above the central widget
  as a second strip on top of the first. The toolbar is added to the shell
  layout for the same reason rather than through `addToolBar`. What the
  system bar was providing has to be put back by hand and that is the whole
  cost of the decision: dragging lives on the bar, and one `ResizeGrip` in
  the bottom-right does the sizing. View ▸ Reset window position exists
  because a frameless window has no system menu to rescue itself from.
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
  `tools/make_shortcut.py` (Setup ▸ Add to the Start menu) writes a .lnk
  carrying the icon; a .bat cannot be pinned usefully, because Windows pins
  the shell rather than the app and the icon is the console's.
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
  back. The outline needs its grid lines turned back ON for that state
  alone: the app's stylesheet sets `gridline-color: transparent`, which is
  right for a filled grid — the numbers are the structure — but leaves an
  empty one a blank rectangle rather than a grid. A reason still worth
  saying ("Fill in both teams", "this source publishes no ally-pair data")
  sits beside the outline, never in place of it.
- **Update restarts the app, and it lives in Help** (`_update_and_restart`,
  `_update_app`).
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
