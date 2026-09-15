"""The suggested picks strip.

It is the Analysis tab's ranked list, cut to its head and laid out like the
item strip — same tiles, same order, best on the left. What is checked here
is that it says the same thing as that list, that it stays quiet when there
is nothing to rank, and that it wears the shared tile look rather than one
of its own.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect                             # noqa: E402
from PyQt6.QtGui import QColor, QPixmap                    # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.ui import portraits, theme, tilekit       # noqa: E402
from draft_assist.ui.item_row import ItemTile               # noqa: E402
from draft_assist.ui.suggest_row import (PLACEHOLDERS,      # noqa: E402
                                         SuggestRow, SuggestTile)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def art(tmp_path, monkeypatch):
    pixmap = QPixmap(256, 144)
    pixmap.fill(QColor("#3050a0"))
    pixmap.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    yield tmp_path
    portraits.forget()


def rows(count=3):
    return [(1, f"Hero {i}", 0.05 - 0.01 * i, f"why {i}") for i in range(count)]


def test_it_keeps_the_order_it_was_given(qapp):
    """Best draft fit on the left, descending right — the same order the
    ranked list is in, because it IS that list's head."""
    row = SuggestRow()
    row.show_heroes(rows(4))
    assert row.heroes == ["Hero 0", "Hero 1", "Hero 2", "Hero 3"]


def test_the_cap_belongs_to_the_caller_not_the_row(qapp):
    """How many to show is a SETTING, so the row draws what it is handed.

    A second cap in here would silently overrule it: raising Settings to
    twelve and getting eight is a bug with nothing on screen to explain
    it. The caller cuts the ranked list; the row is the layout.
    """
    row = SuggestRow()
    row.show_heroes(rows(13))
    assert len(row.heroes) == 13


def test_it_swaps_its_contents_without_piling_up(qapp):
    """It is rebuilt on every draft change; leaked tiles would grow the
    strip until it pushed the grids off the screen."""
    row = SuggestRow()
    row.show_heroes(rows(4))
    row.show_heroes(rows(2))
    assert row.heroes == ["Hero 0", "Hero 1"]
    row.show_heroes([])
    assert row.heroes == []
    assert len(row._blanks) == PLACEHOLDERS


def test_a_tile_draws_with_and_without_a_portrait(art, qapp):
    """A missing portrait is normal — a fresh install has none."""
    assert not SuggestTile(1, "Anti-Mage", 0.05).grab().isNull()
    assert not SuggestTile(999, "Nobody", -0.05).grab().isNull()


def test_the_fit_is_shown_the_way_a_drafted_tile_shows_it(art, qapp):
    """Same figure, same corner, same colours, so a suggestion and a pick
    can be compared without translating between two layouts."""
    drawn = []
    badges = []
    import draft_assist.ui.suggest_row as strip
    real = strip.QPainter.drawText

    class Spy(strip.QPainter):
        def drawText(self, *args):        # noqa: N802 - Qt naming
            drawn.append(args[-1])
            return real(self, *args)

    real_badge = strip.tilekit.paint_badge

    def spy_badge(painter, box, text, colour, base):
        badges.append((text, colour))
        return real_badge(painter, box, text, colour, base)

    keep, keep_badge = strip.QPainter, strip.tilekit.paint_badge
    strip.QPainter = Spy
    strip.tilekit.paint_badge = spy_badge
    try:
        SuggestTile(1, "Anti-Mage", 0.0542).grab()
    finally:
        strip.QPainter = keep
        strip.tilekit.paint_badge = keep_badge
    # Through `paint_badge` rather than `drawText`: the number is an
    # OUTLINED path now, so that the portrait shows through around it.
    assert ("+5.4", theme.GOOD) in badges
    # And the NAME is not drawn. The picture is the tile: a player who
    # knows the game reads the face faster than four letters, and a row of
    # pictures reads at a glance where a row of labelled pictures reads as
    # a list. The name is the tooltip's job.
    assert "Anti-Mage" not in drawn


def test_the_three_strips_are_one_look(qapp):
    """Items, suggestions and picks were three tile designs; the point of
    `tilekit` is that they cannot drift apart again.

    Same HEIGHT, not the same size: each strip takes its own art's aspect
    — a hero portrait is 16:9 and an item icon is 88x64 — because a tile
    wider than its picture is dead space either side of every icon, which
    reads as the items being spaced further apart than the heroes.
    """
    from draft_assist.model.items import ItemAdvice
    from draft_assist.ui import teams
    suggestion = SuggestTile(1, "Anti-Mage", 0.05)
    item = ItemTile(ItemAdvice(item="Black King Bar", score=1.0,
                               any_stale=False, triggers=[]))
    assert suggestion.height() == item.height()
    assert abs(suggestion.width() / suggestion.height() - 16 / 9) < 0.06
    assert abs(item.width() / item.height() - 88 / 64) < 0.06
    assert teams.NAME_MAX_PT == tilekit.NAME_MAX_PT
    assert teams.CHROME == tilekit.CHROME


def test_without_a_portrait_the_name_comes_back(qapp, monkeypatch):
    """A blank plate names nothing, and a fresh install has no art at all.

    So the band is a FALLBACK rather than gone: no picture, no tile — put
    the name back and the strip still says something.
    """
    import draft_assist.ui.suggest_row as strip
    monkeypatch.setattr(strip, "scaled", lambda *a, **k: None)
    drawn = []
    real = strip.QPainter.drawText

    class Spy(strip.QPainter):
        def drawText(self, *args):        # noqa: N802 - Qt naming
            drawn.append(args[-1])
            return real(self, *args)

    keep = strip.QPainter
    strip.QPainter = Spy
    try:
        tile = SuggestTile(1, "Anti-Mage", 0.0542)
        tile.grab()
    finally:
        strip.QPainter = keep
    assert "Anti-Mage" in drawn
    assert "Anti-Mage" in tile.toolTip()


def test_a_focused_suggestion_wears_the_same_ring_as_a_pick(qapp):
    """One selection, one ring. A suggestion and a pick can each be the
    hero the board is measured against, and two implementations of "draw
    the gold box" is two rings that drift apart."""
    from PyQt6.QtGui import QColor
    from draft_assist.ui import tilekit
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    tile.resize(120, 68)

    def gold() -> int:
        image = tile.grab().toImage()
        want = QColor(tilekit.focus_colour())
        return sum(QColor(image.pixel(x, y)) == want
                   for y in range(image.height())
                   for x in range(image.width()))

    assert gold() == 0
    tile.set_focused(True)
    assert gold() > 0


def test_a_suggestion_shows_a_relation_instead_of_its_fit(qapp):
    """Instead, not beside: two numbers in one corner is two numbers to
    tell apart at a glance, which is what both grids dropped their totals
    for."""
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    assert tile.delta_text() == ""
    # THE WORDS ARE GONE FROM THE FIGURE. It read "with +5.2" and "vs
    # -1.8" until the user asked for the mark to stop being characters:
    # "just use a gold rectangle aroudn the score (bottom right)", "no
    # delta required at all". So the text is the number and `_boxed` is
    # what says it is a relation.
    tile.show_delta(0.052, "with")
    assert (tile.delta_text(), tile._boxed) == ("+5.2", True)
    tile.show_delta(-0.018, "vs")
    assert (tile.delta_text(), tile._boxed) == ("-1.8", True)
    tile.clear_delta()
    assert (tile.delta_text(), tile._boxed) == ("", False)


def test_the_row_hands_the_numbers_round_and_takes_them_back(qapp):
    """And a candidate the dataset has nothing to say about keeps its own
    fit rather than going blank — a hole in the strip reads as the tile
    being broken."""
    row = SuggestRow()
    row.show_heroes([(1, "Anti-Mage", 0.05, ""), (2, "Axe", 0.04, ""),
                     (3, "Bane", 0.03, "")])
    assert row.hero_ids == [1, 2, 3]
    row.show_deltas({1: (0.02, "with"), 3: (-0.01, "vs")})
    assert [t.delta_text() for t in row.tiles] == ["+2.0", "", "-1.0"]
    # The gold box is what marks the two that are relations.
    assert [t._boxed for t in row.tiles] == [True, False, True]
    row.set_focus(2)
    assert [t.focused for t in row.tiles] == [False, True, False]
    row.clear_deltas()
    assert not any(t.delta_text() for t in row.tiles)
    assert not any(t.focused for t in row.tiles)


def _ink(tile, colour) -> int:
    """How many pixels of exactly this colour the tile is drawing."""
    from PyQt6.QtGui import QColor
    image = tile.grab().toImage()
    want = QColor(colour)
    return sum(QColor(image.pixel(x, y)) == want
               for y in range(image.height())
               for x in range(image.width()))


def test_the_heart_is_pink_and_the_shield_is_the_frames_gold(qapp):
    """TWO MARKS, at the user's request, and they answer different
    questions: the heart is about YOU (a hero you play and win on), the
    shield is about the HERO (the field struggles to counter it).

    The heart is PINK rather than the red first asked for, on the user's
    own second thought. Every signed number in this app is green or red,
    and a red mark would sit directly above a red "-2.4" on the same
    tile; pink belongs to nothing else here. The shield keeps the gold,
    which means "this one" everywhere it appears.
    """
    from draft_assist.ui import theme, tilekit
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    tile.resize(120, 68)

    assert _ink(tile, theme.HEART_PINK) == 0
    assert _ink(tile, tilekit.focus_colour()) == 0

    tile.set_star(True, "40 games at 65%")
    assert _ink(tile, theme.HEART_PINK) > 0, "the heart draws"
    assert tile.starred
    # The heart must NOT be gold, or the two marks would be one colour
    # saying two things.
    assert _ink(tile, tilekit.focus_colour()) == 0

    tile.set_shield(True, "Hard to counter = 1.8 vs the field (top 12%)")
    assert _ink(tile, tilekit.focus_colour()) > 0, "the shield draws"
    assert tile.shielded
    assert _ink(tile, theme.HEART_PINK) > 0, "both at once"

    tile.set_star(False)
    tile.set_shield(False)
    assert _ink(tile, theme.HEART_PINK) == 0
    assert _ink(tile, tilekit.focus_colour()) == 0


def test_the_two_marks_take_opposite_corners(qapp):
    """The bottom-right is the number's and the border is the ring's, so
    the two top corners are the only ones free. The heart keeps the
    right, where the star it replaces always sat."""
    from draft_assist.ui import theme, tilekit
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    tile.resize(120, 68)
    tile.set_star(True, "why")
    tile.set_shield(True, "why")

    from PyQt6.QtGui import QColor
    image = tile.grab().toImage()

    def middle_x(colour) -> float:
        want = QColor(colour)
        xs = [x for y in range(image.height()) for x in range(image.width())
              if QColor(image.pixel(x, y)) == want]
        return sum(xs) / len(xs)

    assert middle_x(tilekit.focus_colour()) < image.width() / 2, "shield left"
    assert middle_x(theme.HEART_PINK) > image.width() / 2, "heart right"


def test_the_star_keeps_out_of_the_numbers_corner(qapp):
    """The bottom-right is the fit's and the whole border is the focus
    ring's, so the top right is the one corner with nothing in it."""
    from PyQt6.QtCore import QRect
    from draft_assist.ui import tilekit
    box = QRect(0, 0, 120, 68)
    star = tilekit.star_box(box)
    assert star.right() < box.right() and star.top() > box.top()
    assert star.bottom() < box.height() // 2, "top half, clear of the badge"
    # It scales with the tile and stops scaling before it eats one.
    small = tilekit.star_box(QRect(0, 0, 48, 27)).width()
    huge = tilekit.star_box(QRect(0, 0, 600, 338)).width()
    assert tilekit.STAR_MIN_PX <= small < huge == tilekit.STAR_MAX_PX


def test_every_tooltip_line_names_itself(qapp):
    """One label and one figure per line, at the user's request, so the
    numbers are read down a column rather than picked out of prose."""
    tile = SuggestTile(1, "Anti-Mage", 0.05,
                       "Anti-Mage\nCounter Score = +6.5"
                       "\nSynergy Score = +6.0")
    tile.set_star(True, "My Pick Rate = 40 games (top 10%)")
    assert tile.toolTip().splitlines() == [
        "Anti-Mage", "Counter Score = +6.5", "Synergy Score = +6.0",
        "My Pick Rate = 40 games (top 10%)"]

    # The relation line is labelled too, and NAMES the clicked hero: the
    # badge has no room for it, but a line reading "with +5.2" beside
    # four labelled ones is the odd one out.
    tile.show_delta(0.052, "with", "Lion")
    assert "With Lion = +5.2" in tile.toolTip()
    tile.show_delta(-0.018, "vs", "Axe")
    assert "Vs Axe = -1.8" in tile.toolTip()
    assert "My Pick Rate" in tile.toolTip(), "the star's lines survive it"
    tile.clear_delta()
    assert "Lion" not in tile.toolTip() and "Axe" not in tile.toolTip()


def test_a_relation_with_nobody_named_still_reads(qapp):
    """`show_delta` is reachable without a name — the tooltip says what
    it can rather than printing "With  = +5.2"."""
    tile = SuggestTile(1, "Anti-Mage", 0.05)
    tile.show_delta(0.052, "with")
    assert "With the clicked hero = +5.2" in tile.toolTip()


def test_the_row_stars_from_a_measurement(qapp):
    from draft_assist.history import stars as stars_mod
    from dataclasses import dataclass

    @dataclass
    class Played:
        hero_id: int
        win: bool

    matches = ([Played(1, True)] * 20 + [Played(1, False)] * 10
               + [Played(2, False)] * 20 + [Played(3, True)] * 2)
    row = SuggestRow()
    row.show_heroes([(1, "Anti-Mage", 0.05, ""), (2, "Axe", 0.04, ""),
                     (3, "Bane", 0.03, "")])
    # A COUNT: one mark, and it goes to the hero ranked best on pick
    # rate and win rate together.
    row.set_stars(stars_mod.measure(matches), 1)
    assert [t.starred for t in row.tiles] == [True, False, False]
    assert row.tiles[0]._star_rank == 1, "the mark carries its rank"
    assert "My Form Rank = 1" in row.tiles[0].toolTip()

    # RAISING THE COUNT MARKS MORE OF THEM, in ranked order. Bane has
    # two games so it can be ranked; Axe never won, so it ranks last.
    row.set_stars(stars_mod.measure(matches), 3)
    assert [t._star_rank for t in row.tiles] == [1, 3, 2]

    # AND NOUGHT MARKS NOTHING, which is a count of none rather than a
    # special case.
    row.set_stars(stars_mod.measure(matches), 0)
    assert [t.starred for t in row.tiles] == [False, False, False]

    # A COUNT ABOVE THE NUMBER OF TILES IS CAPPED, never an error: "make
    # sure that the number can't be larger than the number of suggested
    # heroes".
    row.set_stars(stars_mod.measure(matches), 99)
    assert sum(1 for t in row.tiles if t.starred) == 3
    row.set_stars(stars_mod.measure(matches), 1)
    # No run loaded draws the same as a run that starred nobody, because
    # there is nothing honest to put on a tile either way.
    row.set_stars(None)
    assert not any(t.starred for t in row.tiles)


# --------------------------------------------------------------------
# THE MARK CARRIES ITS RANK, at the user's request: "the symbol should be
# 20% larger and have a non-bold black number in the middle... if the
# shield has a 1 in it, that means that out of all the suggested heroes
# this particular hero is the hardest to counter."


def _mark_pixels(tile_px, rank, shield=False):
    """How much BLACK ink lands inside the mark — i.e. is there a digit.

    Counted off a render rather than asserted about the code, because
    "the number is drawn" and "the number can be read" are different
    claims and only the second matters. At 13px the mark's own outline
    took most of its interior and the rank came out as two stray dark
    pixels: drawn, unreadable, and worse than absent.
    """
    from PyQt6.QtGui import QImage, QPainter, QColor
    box = QRect(0, 0, tile_px, round(tile_px * 9 / 16))
    picture = QImage(box.size(), QImage.Format.Format_ARGB32)
    picture.fill(QColor("#202225"))
    painter = QPainter(picture)
    if shield:
        tilekit.paint_shield(painter, box, rank)
    else:
        tilekit.paint_heart(painter, box, rank)
    painter.end()
    where = tilekit.star_box(box, left=shield)
    dark = 0
    for y in range(where.top() + 2, where.bottom() - 2):
        for x in range(where.left() + 2, where.right() - 2):
            colour = QColor(picture.pixel(x, y))
            if (colour.red() < 70 and colour.green() < 70
                    and colour.blue() < 70):
                dark += 1
    return dark


@pytest.mark.parametrize("tile_px", [64, 80, 96, 132, 200])
@pytest.mark.parametrize("shield", [False, True])
def test_the_rank_is_legible_at_every_tile_size(qapp, tile_px, shield):
    with_rank = _mark_pixels(tile_px, 8, shield)
    without = _mark_pixels(tile_px, None, shield)
    assert with_rank - without >= 6, (
        f"{tile_px}px tile: the rank drew {with_rank - without} pixels, "
        "which is dirt on a portrait rather than a number")


def test_no_rank_draws_no_number(qapp):
    """The mark still has to work with nothing to say — a hero can be
    shown before a History run has ever been loaded."""
    assert _mark_pixels(132, None) < _mark_pixels(132, 1)


def test_the_mark_is_larger_than_it_was(qapp):
    """Twenty per cent, and it is the number inside that needs it: a
    mark only had to be NOTICED before, and now it has to be read."""
    # 20% when the rank went in, then 10% twice more. The second of
    # those is what "make the number 10% bigger" comes to: the digit is
    # already at the largest share a HEART can hold, so the only way
    # left to grow it is to grow what it sits in.
    assert tilekit.STAR_OF_TILE >= 0.30 * 1.2 * 1.1 * 1.05
    assert tilekit.STAR_MAX_PX >= round(22 * 1.2 * 1.1)


def test_the_rank_is_centred_on_the_SHAPE_not_its_box(qapp):
    """"I want it smack bang in the middle of the symbol." Neither of
    these shapes has its mass in the middle of the rectangle drawn round
    it: a heart is wide at the top and tapers to a point, so its centre
    of area sits ABOVE the box's. Both earlier attempts were wrong and in
    OPPOSITE directions - the heart centred on the box (5% low), the
    shield on a guessed 0.82-height body (7% high) - which is why these
    are measured rather than nudged.
    """
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import QPointF
    for shield, want in ((False, tilekit.HEART_CENTRE),
                         (True, tilekit.SHIELD_CENTRE)):
        side = 200
        picture = QImage(side, side, QImage.Format.Format_ARGB32)
        picture.fill(QColor("white"))       # nothing dark but the digit
        box = QRect(0, 0, side, side)
        shape = tilekit._shape(box, tilekit.SHIELD if shield
                               else tilekit.HEART)
        painter = QPainter(picture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(shape, QColor("red"))
        tilekit._paint_rank(painter, box, 8, want)
        painter.end()
        rows = [y for y in range(side)
                for x in range(side)
                if QColor(picture.pixel(x, y)).red() < 80
                and QColor(picture.pixel(x, y)).green() < 80]
        middle = (min(rows) + max(rows)) / 2 / side
        assert abs(middle - want) <= 0.03, (
            f"{'shield' if shield else 'heart'}: digit centred at "
            f"{middle:.3f}, the shape's middle is {want}")


@pytest.mark.parametrize("rank", [1, 8, 12, 20])
def test_the_rank_stays_inside_the_shape(qapp, rank):
    """Sized by rendering and counting the ink that escapes the outline.
    Two-digit ranks are real - twenty suggestions means ranks to 20 - and
    one share big enough for "20" would have left "1" far smaller than
    the doubling that was asked for, so the size follows the DIGITS."""
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import QPointF
    for shield, centre in ((False, tilekit.HEART_CENTRE),
                           (True, tilekit.SHIELD_CENTRE)):
        side = 200
        picture = QImage(side, side, QImage.Format.Format_ARGB32)
        picture.fill(QColor("white"))
        box = QRect(0, 0, side, side)
        shape = tilekit._shape(box, tilekit.SHIELD if shield
                               else tilekit.HEART)
        painter = QPainter(picture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(shape, QColor("red"))
        tilekit._paint_rank(painter, box, rank, centre)
        painter.end()
        ink = outside = 0
        for y in range(side):
            for x in range(side):
                colour = QColor(picture.pixel(x, y))
                if colour.red() < 80 and colour.green() < 80:
                    ink += 1
                    if not shape.contains(QPointF(x + 0.5, y + 0.5)):
                        outside += 1
        assert ink > 0, "no digit drawn"
        assert outside <= max(4, ink * 0.01), (
            f"{'shield' if shield else 'heart'} rank {rank}: {outside} of "
            f"{ink} pixels fell outside the mark")
