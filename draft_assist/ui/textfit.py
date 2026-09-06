"""Fit a label into a box by shrinking it, then wrapping it, then eliding.

Both the hero tiles and the item strip need the same thing: a name that is
the whole point of the tile, in a box sized by the layout rather than by
the text. Letting the text win would move the tile; letting the box win
shears the name in half. So the FONT gives way first, and only when it has
run out does the text.
"""

from PyQt6.QtGui import QFont, QFontMetricsF


def split_two(text: str) -> list[str]:
    """Two lines, broken at the gap that leaves the halves most even."""
    words = text.split()
    if len(words) < 2:
        return [text]
    best = min(range(1, len(words)),
               key=lambda i: abs(len(" ".join(words[:i]))
                                 - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def fit(text: str, width: float, height: float, base: QFont,
        max_pt: int, min_pt: int, bold: bool = False
        ) -> tuple[int, list[str]]:
    """(point size, lines) for `text` inside width x height.

    One line at the largest size that fits, else two lines at the largest
    size where two still fit the height, else the smallest size and let the
    caller elide. Never returns a size outside [min_pt, max_pt].
    """
    def sized(points: int) -> QFontMetricsF:
        font = QFont(base)
        font.setPointSize(points)
        font.setBold(bold)
        return QFontMetricsF(font)

    for points in range(max_pt, min_pt - 1, -1):
        metrics = sized(points)
        if (metrics.horizontalAdvance(text) <= width
                and metrics.height() <= height):
            return points, [text]
    for points in range(max_pt, min_pt - 1, -1):
        metrics = sized(points)
        if metrics.height() * 2 > height:
            continue
        lines = split_two(text)
        if len(lines) == 2 and all(
                metrics.horizontalAdvance(line) <= width for line in lines):
            return points, lines
    return min_pt, split_two(text)
