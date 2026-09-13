"""The suggested picks: the ranked list, as a strip, above the items.

The History tab already ranks every hero the draft has not taken by draft
fit. That answer belongs on the Draft tab too — it is the question a draft
screen is actually asking — but 120 rows of it is a table, and a table
beside the ten picks makes the ten harder to read. So the top handful come
across as tiles: best on the left, descending to the right, exactly the way
the item strip reads.

The tiles are the item strip's tiles with a hero in them (`tilekit`), and
each carries its fit in the same bottom-right badge the ten picks use — the
same number, in the same place, in the same colours, so a suggestion and a
pick can be compared without translating between two layouts.

CLICKING ONE FOCUSES IT, at the user's request: the ten picks then show
what that candidate would be worth beside each of them — "with +5.2"
under an ally, "vs -1.8" under an enemy — and the tile wears the gold
ring. It used to open a box listing the terms behind its own number, and
that box is gone: the numbers it summarised are now written on the ten
portraits the question is actually about, which is a better answer in the
place the eye already is.

Clicking one still does NOT enter it. A pick is entered by clicking a
SLOT, and a strip that also entered picks would be a second way to do it
that behaves differently.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from . import theme, tilekit
from .flowlayout import FlowLayout
from .portraits import scaled

# The FALLBACK box only. The real one comes from the draft panel above
# (`SuggestRow.set_tile_size`), because every tile in the app is the same
# tile and a suggestion the size of a pick can be compared with one
# without the eye doing any conversion. These stand in until the panel has
# been laid out and had something to say.
WIDTH = tilekit.STRIP_W
ART_H = tilekit.STRIP_ART_H
BAND_H = tilekit.STRIP_BAND_H
# HOW MANY IS THE CALLER'S DECISION, not this widget's: it is a setting
# (Settings ▸ How much each strip shows), and a second cap in here would
# silently overrule it — raising the setting to twelve and getting eight
# is a bug with nothing on screen to explain it. The row draws the rows it
# is handed.
PLACEHOLDERS = 5


class SuggestTile(QWidget):
    """One candidate: the portrait, with a number in the corner.

    The number is its DRAFT FIT normally and its relation to the focused
    hero while one is clicked, in the same badge either way — the tile
    answers whatever question the board is currently asking.
    """

    clicked_hero = pyqtSignal(int)

    def __init__(self, hero_id: int, name: str, fit_value: float,
                 tooltip: str = "", parent=None,
                 size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.hero_id = hero_id
        self.hero_name = name
        self.fit = float(fit_value)
        self._delta: str = ""
        self._delta_colour: str = theme.GOOD
        # What the badge is currently a relation TO, for the tooltip:
        # the figure, whether it is a matchup or a synergy, and whose.
        self._relation: tuple[float, str, str] | None = None
        self._focused = False
        self._starred = False
        self._shielded = False
        self._star_rank = None
        self._shield_rank = None
        self._why_shield = ""
        self._tip = tooltip or name
        self._why_star = ""
        self.setFixedSize(*(size or (WIDTH, ART_H)))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(self._tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked_hero.emit(self.hero_id)
        super().mouseReleaseEvent(event)

    # ---- what the badge says --------------------------------------------
    def show_delta(self, delta: float, kind: str | None = None,
                   against: str = "") -> None:
        """Its relation to the focused hero, INSTEAD of its own fit.

        Instead rather than beside: two numbers in one corner is two
        numbers to tell apart at a glance, which is why neither grid draws
        a total any more.
        """
        self._delta = tilekit.delta_text(delta, kind)
        self._delta_colour = theme.GOOD if delta >= 0 else theme.BAD
        # `against` NAMES the focused hero for the tooltip. The badge has
        # no room for it and does not need it — you just clicked that
        # hero — but a tooltip line reading "with +5.20" beside four
        # labelled ones is the odd one out, and "With Lion" is what the
        # label wants to say anyway.
        self._relation = (delta, kind or "", against)
        self._refresh_tip()
        self.update()

    def clear_delta(self) -> None:
        self._delta = ""
        self._relation = None
        self._refresh_tip()
        self.update()

    def delta_text(self) -> str:
        return self._delta

    def set_focused(self, on: bool) -> None:
        self._focused = bool(on)
        self.update()

    def set_star(self, on: bool, why: str = "") -> None:
        """A PINK HEART: a hero the last History run says you are good on.

        It was a gold star; at the user's request the mark is a heart and
        the colour is pink. Pink is the better half of that change and
        theirs: every signed number in this app is green or red, and the
        red first asked for would have sat directly above a red "-2.4" on
        the same tile. Pink belongs to nothing else here.

        The method keeps its name because the whole path from the History
        run down to this tile is spelled "star", and renaming half of it
        is how two names for one thing start.

        The reason rides along and goes in the TOOLTIP rather than on the
        tile: the mark's job is to be seen without being read, and a
        figure beside it would be a third number in a corner that already
        has the fit in it.
        """
        # A RANK, NOT A FLAG. `on` is an int (1 is the best of the
        # suggestions on screen), or None/False for no mark - and 0 is
        # NOT a rank, so it has to be told apart from False rather than
        # tested for truth. Ranks count from one.
        self._star_rank = int(on) if isinstance(on, int) and not isinstance(
            on, bool) else None
        self._starred = self._star_rank is not None or bool(on) is True
        self._why_star = why
        self._refresh_tip()
        self.update()

    def set_shield(self, on: bool, why: str = "") -> None:
        """A GOLD SHIELD: a hero the field struggles to counter.

        NOT ABOUT YOU, which is what makes it worth a second mark rather
        than a second condition on the first. The heart is your own
        history; this is a property of the hero, read out of the ranked
        dataset, so it appears on heroes you have never picked - which is
        exactly where it tells you something you did not know.
        """
        self._shield_rank = int(on) if isinstance(on, int) and not isinstance(
            on, bool) else None
        self._shielded = self._shield_rank is not None or bool(on) is True
        self._why_shield = why
        self._refresh_tip()
        self.update()

    @property
    def starred(self) -> bool:
        return self._starred

    @property
    def shielded(self) -> bool:
        return self._shielded

    def _refresh_tip(self) -> None:
        """EVERY LINE NAMES ITSELF AND THEN GIVES A FIGURE, so the
        numbers are read down a column rather than picked out of prose."""
        lines = [self._tip]
        if self._relation is not None:
            delta, kind, against = self._relation
            label = "With" if kind == "with" else "Vs"
            lines.append(f"{label} {against or 'the clicked hero'}"
                         f" = {delta * 100:+.1f}")
        if self._starred and self._why_star:
            lines.append(self._why_star)
        if self._shielded and self._why_shield:
            lines.append(self._why_shield)
        self.setToolTip("\n".join(part for part in lines if part))

    @property
    def focused(self) -> bool:
        return self._focused

    def paintEvent(self, event) -> None:        # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, True)
        box = self.rect()
        if not tilekit.paint_art(painter, box,
                                 scaled(self.hero_id, box.width(),
                                        box.height())):
            # No portrait on disk — a fresh install has none — so the name
            # goes back, because a blank plate names nothing.
            tilekit.paint_plate(painter, box)
            # Most of the tile rather than a band across the top: there
            # is no art competing for the space, and a name squeezed into
            # a 22px strip can fail to fit at all and draw NOTHING, which
            # is a tile that says neither picture nor name. The bottom
            # quarter is left clear so the badge does not land on it.
            tilekit.paint_band(painter,
                               box.adjusted(0, 0, 0, -box.height() // 4),
                               self.hero_name, self.font())
        # Same figure, same corner, same colours as a drafted tile: a
        # suggestion and a pick have to be comparable at a glance.
        if self._delta:
            tilekit.paint_badge(painter, box, self._delta,
                                self._delta_colour, self.font())
        else:
            tilekit.paint_badge(painter, box,
                                f"{self.fit * 100:+.1f}",
                                theme.GOOD if self.fit >= 0 else theme.BAD,
                                self.font())
        # UNDER the ring, not over it: the ring is the window's frame and
        # runs round the tile's edge, so a mark drawn afterwards would sit
        # on top of the one line that says what the whole board is being
        # measured against.
        if self._starred:
            tilekit.paint_heart(painter, box, self._star_rank)
        if self._shielded:
            tilekit.paint_shield(painter, box, self._shield_rank)
        if self._focused:
            tilekit.paint_focus_ring(painter, box)
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class PlaceholderTile(QWidget):
    """The shape a suggestion will be. Same reason as the item strip's."""

    def __init__(self, parent=None, size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.setFixedSize(*(size or (WIDTH, ART_H)))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:        # noqa: N802
        painter = QPainter(self)
        # ITS OWN RECT. It used to draw a plate `BAND_H + ART_H` tall into
        # a widget only `ART_H` tall, so the dashed bottom edge fell off
        # the bottom of the tile — which is exactly what "the squares are a
        # different size before the game starts" looked like: same box,
        # three sides of an outline.
        tilekit.paint_plate(painter, self.rect(), dashed=True)
        painter.end()

    def sizeHint(self) -> QSize:                # noqa: N802
        return self.size()


class SuggestRow(QWidget):
    """A line of suggestion tiles, best first."""

    clicked_hero = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # WRAPS rather than scrolls: a strip you have to scroll to read is
        # a strip you do not read at a glance, which is the one thing it is
        # for. Past the width it has been given the tiles go to a new row.
        self.row = FlowLayout(self, spacing=8)
        self.message = QLabel("")
        self.message.setProperty("dim", True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.row.addWidget(self.message)
        self._tiles: list[SuggestTile] = []
        self._blanks: list[PlaceholderTile] = []
        self._tile_size = (WIDTH, ART_H)

    def set_tile_size(self, width: int, height: int) -> None:
        """Match the ten picks above. The draft panel is the one place
        that decides how big a tile is; this is how the decision arrives."""
        size = (max(1, int(width)), max(1, int(height)))
        if size == self._tile_size:
            return
        self._tile_size = size
        for tile in self._tiles + self._blanks:
            tile.setFixedSize(*size)
        # A FlowLayout answers heightForWidth, so a taller tile is a taller
        # strip and the window above has to be told to ask again.
        self.row.invalidate()
        self.updateGeometry()

    def tile_width(self) -> int:
        """What "how many fit on one row" has to divide by."""
        return self._tile_size[0]

    def show_heroes(self, rows: list[tuple[int, str, float, str]],
                    empty: str = "") -> None:
        """`rows` is (hero id, name, fit, tooltip), already in order."""
        for tile in self._tiles + self._blanks:
            self.row.removeWidget(tile)
            tile.deleteLater()
        self._tiles, self._blanks = [], []
        self.message.setText(empty if not rows else "")
        self.message.setVisible(bool(empty) and not rows)
        if not rows:
            for _ in range(PLACEHOLDERS):
                blank = PlaceholderTile(self, self._tile_size)
                self.row.insertWidget(len(self._blanks), blank)
                self._blanks.append(blank)
            return
        for hero_id, name, fit_value, tip in rows:
            tile = SuggestTile(hero_id, name, fit_value, tip, self,
                               self._tile_size)
            tile.clicked_hero.connect(self.clicked_hero)
            self.row.insertWidget(len(self._tiles), tile)
            self._tiles.append(tile)

    @property
    def heroes(self) -> list[str]:
        return [tile.hero_name for tile in self._tiles]

    @property
    def hero_ids(self) -> list[int]:
        """Which candidates are actually on screen.

        The strip is cut to a count the user sets, so a hero can be
        focused and then fall off the end of it as the draft fills in —
        and numbers on the board measured against a hero nobody can see
        is worse than no numbers at all. The caller drops the focus.
        """
        return [tile.hero_id for tile in self._tiles]

    @property
    def tiles(self) -> list["SuggestTile"]:
        return list(self._tiles)

    # ---- what the strip is measuring against ----------------------------
    def set_focus(self, hero_id: int | None) -> None:
        """The gold ring goes on one tile, or on none of them."""
        for tile in self._tiles:
            tile.set_focused(tile.hero_id == hero_id)

    def show_deltas(self, values: dict[int, tuple[float, str]],
                    against: str = "") -> None:
        """Relations to the focused hero, one per candidate.

        A candidate with nothing to say — no row in the dataset — keeps
        its fit rather than going blank: a hole in the strip reads as the
        tile being broken.
        """
        for tile in self._tiles:
            found = values.get(tile.hero_id)
            if found is None:
                tile.clear_delta()
            else:
                tile.show_delta(found[0], found[1], against)

    def clear_deltas(self) -> None:
        """Back to draft fit, which is what the strip says on its own."""
        for tile in self._tiles:
            tile.clear_delta()
            tile.set_focused(False)

    @staticmethod
    def _how_many(share: int, tiles: int) -> int:
        """How many marks a share of the strip comes to.

        The setting is a PERCENTAGE OF WHAT IS ON SCREEN, at the user's
        request - "if I set it to 50% and I have 20 suggested heroes,
        that means I expect to have 10 heroes with hearts" - which is a
        different question from the percentile floor it replaces. That
        one asked "is this hero in the top 30% of every hero you have
        ever played"; this asks "is it in the best half of the ones I am
        looking at", and only the second changes as the board fills.

        Rounded to nearest, and never nought while the share is above it:
        a setting that is on should mark something.
        """
        if share <= 0 or tiles <= 0:
            return 0
        return max(1, min(tiles, round(tiles * share / 100.0)))

    def _rank_tiles(self, scores: dict, share: int) -> dict:
        """{hero id: rank} for the best `share`% of the tiles on screen.

        RELATIVE TO THE STRIP, which is the whole point of the change and
        the reason this lives here rather than in `history/stars.py` or
        `analyse.py`. Neither of those knows what is being suggested; the
        strip is the only place that does.

        TIES TAKE THE BETTER RANK and both are marked, the rule
        `rank_fraction` already follows: two heroes the criterion cannot
        separate must not be separated by whatever `sorted` did.
        """
        ranked = sorted(((value, hero) for hero, value in scores.items()
                         if value is not None), reverse=True)
        wanted = self._how_many(share, len(self._tiles))
        out, place, seen = {}, 0, None
        for index, (value, hero) in enumerate(ranked, 1):
            if value != seen:
                place, seen = index, value
            if place > wanted:
                break
            out[hero] = place
        return out

    def set_stars(self, stars, share: int = 0) -> None:
        """Heart the best `share`% of the strip on your own history.

        Takes the whole `Stars` rather than a set of ids, because the
        tile wants the SENTENCE for its tooltip too, and handing the set
        one way and the reasons another is two things to keep in step.
        None clears every heart - no run loaded is not the same claim as
        a run that marked nobody, but it draws the same, and there is
        nothing honest to put on a tile either way.

        A hero under `stars.MIN_GAMES` scores None and cannot be ranked
        at all, so a short history yields fewer marks than the share asks
        for rather than marking a hero played once.
        """
        if stars is None:
            for tile in self._tiles:
                tile.set_star(None, "")
            return
        ranks = self._rank_tiles(
            {tile.hero_id: stars.score(tile.hero_id)
             for tile in self._tiles}, share)
        for tile in self._tiles:
            rank = ranks.get(tile.hero_id)
            why = stars.why(tile.hero_id) if rank else ""
            if rank and why:
                why = f"{why}\nMy Form Rank = {rank} of these suggestions"
            tile.set_star(rank, why)

    def set_shields(self, shields: dict | None, share: int = 0) -> None:
        """Shield the `share`% of the strip hardest to counter.

        A PLAIN MAPPING rather than a `Stars`, because this one needs no
        history object behind it: {hero id: (difficulty, sentence)},
        worked out from the ranked dataset alone. Called AFTER
        `show_heroes` for the same reason the hearts are - that rebuilds
        every tile, so a mark set before it is a mark on a widget that no
        longer exists.
        """
        rows = shields or {}
        ranks = self._rank_tiles(
            {tile.hero_id: (rows[tile.hero_id][0]
                            if tile.hero_id in rows else None)
             for tile in self._tiles}, share)
        for tile in self._tiles:
            rank = ranks.get(tile.hero_id)
            why = rows.get(tile.hero_id, (0.0, ""))[1] if rank else ""
            if rank and why:
                why = f"{why}\nCounter Rank = {rank} of these suggestions"
            tile.set_shield(rank, why)
