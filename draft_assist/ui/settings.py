"""Small persisted UI preferences (overlay position, collapsed state).

Deliberately separate from calibration and from the data cache: these are
per-machine conveniences, gitignored, and losing the file costs nothing but
a re-drag of the overlay.
"""

import json
from pathlib import Path

from ..config import REPO_ROOT

SETTINGS_FILE = REPO_ROOT / "ui_settings.json"

# The ceiling on both "how many to show" settings. Twenty suggested picks
# is already more than a draft screen can be read against; past that the
# strip is a list and the point of a strip is that it is not one.
MAX_SHOWN = 20
# The keys that ceiling applies to, clamped on the way IN as well as out —
# a hand-edited file asking for two hundred tiles must not be honoured.
COUNTS = ("suggested_picks", "suggested_items")

# The default fortnight, and the ceiling the settings box offers. A year
# is "stop asking" without being 0, which is off outright.
DATA_REMINDER_DAYS = 14
MAX_REMINDER_DAYS = 365

# THE DEFAULTS ARE THE OWNER'S OWN SETUP, at their request: "have a look
# at the current state of the app — the size of the window, the set points
# in the analysis — and make it the default". Every value below was read
# off their `ui_settings.json` rather than picked, so a fresh install (or
# a second machine) opens on the arrangement they settled on rather than
# on whatever the first version happened to ship.
# Their own file still wins on their own machine — it is gitignored and
# survives every update — so this only ever decides what a copy with no
# settings yet does.
DEFAULTS = {
    # Start a recording by itself when Dota reaches the draft. On by
    # default: the session you most want is the one you were not
    # expecting, and remembering to press Record before queueing is
    # exactly the thing that gets forgotten.
    "auto_record": True,
    # Both sources on by default: they answer different questions and the
    # app wants both. Turning one off is a debugging step, never a mode.
    "use_gsi": True,
    "use_vision": True,
    # How see-through the window is. It HAS to be listed here: `save`
    # writes only the keys DEFAULTS names, so a preference the app set
    # but this dict did not know about was written by the slider, kept in
    # memory, and dropped on the way to disk. FULLY OPAQUE, which is
    # where the owner left it — the see-through window is a thing to
    # reach for rather than a thing to start at.
    "overlay_opacity": 1.0,
    # How many tiles each strip shows AT MOST. A cap is not a quota: the
    # item strip stops at whatever clears the severity floor, so raising
    # this to 20 does not produce 20 items, it only stops truncating the
    # ones that were already worth showing.
    "suggested_picks": 20,
    "suggested_items": 7,
    # HOW MANY SUGGESTIONS GET A MARK, as a share OF THE STRIP.
    #
    # At the user's request, and it replaces three percentile floors:
    # "I don't want a general % cutoff, I want it to be a qty, and this
    # qty is the number of suggested heroes that can get the badge -
    # still based on the criteria, but it's a relative ranking based on
    # what's available in the suggestions." And then: "it makes sense for
    # the setting to remain a percentage, but it will be the proportion
    # of the suggested heroes that will get a symbol... so 50% with 20
    # suggested heroes means 10 with hearts and 10 with shields."
    #
    # THE OLD KEYS ARE GONE RATHER THAN REUSED, and that is deliberate:
    # `shield_pct: 70` meant "the top 30% of every hero in the game", and
    # under the new reading 70 would mean "70% of the strip gets one".
    # Keeping the name would silently double somebody's marks on the
    # update that changed the meaning. New names, and 30 is what the old
    # defaults came to in practice.
    #
    # A SHARE OF THE STRIP rather than of the whole hero pool, which is
    # the change itself: the old question was "is this hero in the top
    # 30% of all of them", the new one is "is it in the best few of the
    # ones I am looking at" - and only the second moves as the board
    # fills and the suggestions change.
    # A COUNT, not a share, at the user's request - "I think a number
    # makes more sense... the number should be a QTY". Capped at however
    # many heroes are actually being suggested, since a mark that cannot
    # be given to anybody is a setting that does nothing.
    #
    # THE KEYS CHANGE AGAIN, for the reason they changed last time: a
    # stored 30 meant "30% of the strip" and would now mean "thirty
    # heroes", which is more than the strip can ever hold.
    # ONE COUNT FOR BOTH MARKS, at the user's request: "I don't think
    # there is value in being able to set the heart and shield counts to
    # separate values... just have a single field for both". They answer
    # the same question - how far down the suggestion strip is worth
    # marking - and two boxes made that look like two decisions. Set it
    # to 2 and the strip carries two hearts AND two shields.
    # TWO COUNTS, ONE PER MARK, at the user's request - the heading
    # now reads "heart = comfort = N" and "shield = counter = N" on
    # separate lines, so one box driving both lines would be a value
    # with two controls. This REVERSES the single `mark_count` that
    # replaced them; see `_picks_controls`.
    "heart_count": 3,
    "shield_count": 3,
    # THE HISTORY TAB'S OWN CONTROLS, remembered ACROSS ACCOUNTS: "if I
    # look up someone else's account, the sorts and filters should be the
    # same as I had on the previous analysis". So they live here rather
    # than beside the remembered accounts, where they would be one
    # person's answer restored over another person's.
    # `history_tables` is {block id: {top, by, sort, desc}} and
    # `history_options` the window, cap and tick boxes above them. Both
    # are whole dicts rather than a key each, because the set of blocks
    # changes when an analysis is added or removed and DEFAULTS is the
    # WRITE FILTER: a per-block key would have to be added here every
    # time. `load` copies each dict value, since `dict(DEFAULTS)` is
    # shallow and the alternative is every caller sharing one object with
    # the defaults.
    # NOT `item_hero`, which the owner's file also carries: that names
    # one account's most played hero, and shipping it would have a fresh
    # install open the item block on somebody who is not in its list. It
    # falls back to the first (most played) hero, which is the right
    # answer for anybody.
    "history_tables": {
        "hero": {"top": 10, "by": "games", "sort": "value", "desc": True},
        "length": {"top": 0, "by": "games", "sort": "value", "desc": True},
        "tod": {"top": 0, "by": "games", "sort": "value", "desc": True},
        "dow": {"top": 0, "by": "value", "sort": "value", "desc": True},
        "session": {"top": 0, "by": "games", "sort": "value", "desc": True},
        "tilt": {"top": 0, "by": "games", "sort": "value", "desc": True},
        "side": {"top": 0, "by": "games", "sort": "value", "desc": True},
        "party": {"top": 0, "by": "games", "sort": "value", "desc": True},
        "items": {"top": 8, "by": "games", "sort": "value", "desc": True},
        "herodmg": {"top": 10, "by": "games", "sort": "value", "desc": True},
        "herokda": {"top": 10, "by": "games", "sort": "value", "desc": True},
    },
    "history_options": {
        "window": "6m", "cap": 5000, "no_turbo": True, "ranked_only": True,
        "picked": {"hero": True, "length": True, "tod": True, "dow": True,
                   "session": True, "tilt": True, "side": True,
                   "party": True, "herodmg": True, "herokda": True,
                   "items": True},
    },
    # How old the statistics have to get before the app says anything at
    # all about it: ONE dialog when the app opens, and nothing on screen
    # for the fortnight before that. Zero turns it off.
    "data_reminder_days": DATA_REMINDER_DAYS,
    # `ads_enabled` was here and is GONE with the slot it switched. A key
    # left in DEFAULTS is not inert: this dict is the WRITE FILTER, so a
    # dead one is a line written into everybody's settings file for ever.
    # HOW STRONG a suggestion has to be in each role: role name -> the
    # LOWEST rating that passes, 1 to 3 on Valve's own scale. A role that
    # is not in the dict is not filtered on, and an empty dict is no
    # filter at all, which is the default.
    # It was a LIST of names — tick or no tick — and became a number at
    # the user's request: "instead of a tick box it would be nice to have
    # a number input (up / down arrow) for each allowing 1, 2, 3 only...
    # that way if you need a really strong support example you can filter
    # the suggested heroes well". A list is read back as every named role
    # at 1, which is exactly what a tick used to mean.
    # ONLY THE ROLES ASKED FOR ARE STORED, never all eight with zeros:
    # the set of roles is Valve's and not ours, and DEFAULTS being the
    # write filter means a dead name would otherwise sit in everybody's
    # file for ever.
    "pick_roles": {},
    # WHETHER THE WINDOW STAYS IN FRONT. True is what this app has always
    # done — it was `WindowStaysOnTopHint` with no way to say otherwise —
    # so the default keeps that and the pin is what makes it a choice
    # rather than a mode. Remembered, because a window that forgets where
    # it sits in the Z order is one you re-pin every session.
    "always_on_top": True,
    "portrait_scale": 1.0,
    "number_scale": 1.0,
    # The size the window opens at, and the size it is closed at is
    # written back over these (`closeEvent`). There is no lock any more:
    # it is freely resizable, floored at what the layout can actually
    # draw. 940x998 is where the owner settled — narrow and tall, which
    # is the shape of a draft read beside a running game.
    # `overlay_x`, `overlay_y`, `overlay_expanded` and `overlay_rows` were
    # here and are GONE: nothing has read any of them since the floating
    # overlay was removed, and DEFAULTS is the write filter, so a dead key
    # is a line written to everybody's settings file for ever.
    "window_w": 940,
    # STILL THE OWNER'S OWN 998, which is what fits a 1080p screen.
    # It was briefly raised to 1150 to stop the Draft tab overflowing
    # once the roles card was added — that was treating a symptom. The
    # tab is in a scroll area now and the two advice strips declare the
    # height their wrap needs, so a window shorter than the content
    # scrolls instead of cropping, and a default taller than the
    # commonest monitor would have been its own bug.
    "window_h": 998,
    # And WHERE it opens, at the user's request: "I don't like that when
    # I close and reopen the app it doesn't open in the location where I
    # closed it... it opens with the same size which is great, just need
    # the same for location on the screen".
    #
    # None means "never saved", which is what a fresh install has and is
    # not the same as a position of (0, 0) — so the first run is placed
    # by the window manager rather than jammed into the top-left corner.
    # They have to be HERE and not only written by `closeEvent`, because
    # this dict is the write FILTER as well as the fallback: a key it
    # does not name is kept for the session and dropped on the way to
    # disk, which is the bug that lost the transparency setting.
    "window_x": None,
    "window_y": None,
}



def clamp_count(value, fallback: int) -> int:
    """A count between 1 and MAX_SHOWN, or the fallback if it is not one."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(MAX_SHOWN, number))


def clean_roles(value) -> dict[str, int]:
    """Whatever was in the file, as role -> lowest rating that passes.

    Three things a stored value must not be able to do, and all three
    have a file somebody could hand-edit behind them: name a role the
    game no longer scores (which would cut the suggestion strip to
    nothing with a name nothing can ever satisfy), ask for a rating
    outside Valve's 1-to-3 scale, or ask for nought, which is not a
    filter and should not be stored as one.

    A LIST is read as every role in it at 1 — the shape this preference
    had while the control was a tick box, where a tick meant "any rating
    above zero". Nobody's saved filter is lost to the change.

    Comes back in Valve's own column order, so the controls read in the
    same order as the Roles card above them however the file was written.
    """
    from ..model.roles import MAX_LEVEL, ROLES
    if isinstance(value, (list, tuple, set)):
        value = {str(name): 1 for name in value}
    if not isinstance(value, dict):
        return {}
    out = {}
    for role in ROLES:
        try:
            level = int(value[role])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= level <= MAX_LEVEL:
            out[role] = level
    return out


def clamp_marks(value, fallback: int) -> int:
    """How many suggestions carry a mark: 0 to MAX_SHOWN.

    Separate from `clamp_count` because NOUGHT IS A REAL ANSWER here and
    is not for a strip: a strip showing nothing is a card with a hole in
    it, where wanting no hearts is ordinary. `clamp_count` floors at one
    for that reason, and reusing it quietly turned "no marks" into "one".
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(MAX_SHOWN, number))


def clamp_days(value, fallback: int) -> int:
    """Whole days between 0 (never ask) and MAX_REMINDER_DAYS."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(MAX_REMINDER_DAYS, number))


def clamp_pct(value, fallback: int) -> int:
    """A percentile floor, 0 to 99.

    NOT 100. At 100 a hero would have to stand above every hero
    including itself, so nothing could ever qualify and the strip would
    lose its stars with nothing on screen saying why — a setting whose
    top end silently turns the feature off is one somebody reaches by
    dragging rather than by deciding. 99 is "the very top", 0 is "no bar
    on this axis".
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(99, number))


def load(path: Path | None = None) -> dict:
    """Path is resolved at call time, never bound as a default, so the
    destination can be repointed (tests do this)."""
    path = path or SETTINGS_FILE
    # A COPY PER VALUE, not just a copy of the dict. `dict(DEFAULTS)` is
    # shallow, so the two dict-valued preferences would be the SAME object
    # every caller shares — the History tab writing a table's sort order
    # would edit DEFAULTS itself, and the next fresh load would come back
    # carrying it as though it had always been the default.
    # LISTS ARE COPIED AS WELL AS DICTS, for the same reason: one shared
    # object would let a caller edit DEFAULTS itself, and the next fresh
    # load would come back carrying the edit as though it were default.
    settings = {k: (dict(v) if isinstance(v, dict)
                    else list(v) if isinstance(v, list) else v)
                for k, v in DEFAULTS.items()}
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return settings
        if isinstance(stored, dict):
            # Only known keys, so a stale file can never inject surprises.
            settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
            # A FILE WRITTEN WHILE THE TWO WERE ONE. `mark_count` drove
            # both marks, so both take it - the reader's setting is
            # carried across the split rather than reset to the default,
            # and neither mark appears or disappears on the update.
            merged = stored.get("mark_count")
            if isinstance(merged, int):
                for key in ("heart_count", "shield_count"):
                    if not isinstance(stored.get(key), int):
                        settings[key] = clamp_marks(merged, 3)
    for key in COUNTS:
        settings[key] = clamp_count(settings.get(key), DEFAULTS[key])
    settings["data_reminder_days"] = clamp_days(
        settings.get("data_reminder_days"), DATA_REMINDER_DAYS)
    return settings


def save(settings: dict, path: Path | None = None) -> None:
    path = path or SETTINGS_FILE
    settings = dict(settings)
    for key in COUNTS:
        settings[key] = clamp_count(settings.get(key), DEFAULTS[key])
    settings["data_reminder_days"] = clamp_days(
        settings.get("data_reminder_days"), DATA_REMINDER_DAYS)
    try:
        path.write_text(
            json.dumps({k: settings.get(k, v) for k, v in DEFAULTS.items()},
                       indent=2),
            encoding="utf-8")
    except OSError:
        pass          # a preference failing to save must never break the app
