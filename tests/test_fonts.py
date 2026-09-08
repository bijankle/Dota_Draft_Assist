"""Fonts loaded from disk rather than installed.

Qt will only use a family it knows about, so a supplied .ttf has to be
registered before the stylesheet asks for it by name. These ARE committed, because Alegreya is under the SIL Open Font License
and that permits it outright. The interesting case is still the one where
the files are NOT there — a checkout without them has to open a readable
app, the same way a missing portrait is normal rather than an error.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFont                              # noqa: E402
from PyQt6.QtWidgets import QApplication                   # noqa: E402

from draft_assist.ui import fonts, theme                   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_no_fonts_folder_is_not_an_error(qapp, tmp_path):
    assert fonts.load_bundled(tmp_path / "nothing here") == []


def test_it_registers_what_it_finds_and_ignores_what_it_does_not(qapp,
                                                                 tmp_path):
    (tmp_path / "notes.txt").write_text("not a font", encoding="utf-8")
    (tmp_path / "broken.ttf").write_bytes(b"this is not a font either")
    # Neither one registers, and neither one raises.
    assert fonts.load_bundled(tmp_path) == []


def test_the_stylesheet_names_both_supplied_faces_and_a_fallback():
    """A machine without the files still has to open a readable app."""
    assert f'"{theme.TITLE_FAMILY}"' in theme.STYLESHEET
    assert f'"{theme.BODY_FAMILY}"' in theme.STYLESHEET
    # A generic family last, so there is always something to fall back to.
    assert theme.FONT_STACK.rsplit(",", 1)[-1].strip() in (
        "serif", "sans-serif", "system-ui")
    assert theme.FONT_STACK.startswith(f'"{theme.BODY_FAMILY}"')
    # The title is its own face, with the body stack behind it.
    rule = theme.STYLESHEET[theme.STYLESHEET.index("QLabel#titleText"):]
    rule = rule[:rule.index("}")]
    assert theme.TITLE_FAMILY in rule and theme.FONT_STACK in rule


def test_the_names_the_loader_and_the_theme_use_are_the_same():
    """Two spellings of one family is a font that silently never loads."""
    assert fonts.TITLE_FAMILY == theme.TITLE_FAMILY
    assert fonts.BODY_FAMILY == theme.BODY_FAMILY


def test_the_bundled_faces_actually_resolve(qapp):
    """They are in the repository, so this is not conditional."""
    families = fonts.load_bundled()
    assert theme.TITLE_FAMILY in families
    assert theme.BODY_FAMILY in families
    assert QFont(theme.TITLE_FAMILY).family() == theme.TITLE_FAMILY
    assert QFont(theme.BODY_FAMILY).family() == theme.BODY_FAMILY


def test_every_committed_font_states_its_own_licence(qapp):
    """The bar for putting a font in the repository is that its LICENCE
    says yes on its own, not that somebody said it was fine.

    Two have already failed it and been removed: a commercial retail face,
    and one carrying no copyright and no licence at all. Absence of a
    stated licence is not permission, so this reads the name table rather
    than trusting the filename.
    """
    import struct

    def licence_of(path):
        data = path.read_bytes()
        count = struct.unpack(">H", data[4:6])[0]
        table = None
        for i in range(count):
            record = 12 + 16 * i
            if data[record:record + 4] == b"name":
                table = struct.unpack(">II", data[record + 8:record + 16])[0]
                break
        if table is None:
            return ""
        _fmt, n, strings = struct.unpack(">HHH", data[table:table + 6])
        found = []
        for i in range(n):
            r = table + 6 + 12 * i
            pid, _eid, _lid, nid, length, off = struct.unpack(
                ">HHHHHH", data[r:r + 12])
            if nid not in (0, 13):
                continue
            raw = data[table + strings + off:table + strings + off + length]
            try:
                found.append(raw.decode("utf-16-be" if pid == 3 else "latin-1"))
            except UnicodeDecodeError:
                pass
        return " ".join(found)

    fonts_dir = fonts.FONTS_DIR
    files = [p for p in fonts_dir.iterdir()
             if p.suffix.lower() in (".ttf", ".otf")]
    assert files, "no fonts are committed; this test has nothing to check"
    assert (fonts_dir / "OFL.txt").exists(), "the licence text is missing"
    for path in files:
        text = licence_of(path)
        assert "Open Font License" in text, (
            f"{path.name} does not state an open licence in its own "
            "metadata — see assets/fonts/README.md")
