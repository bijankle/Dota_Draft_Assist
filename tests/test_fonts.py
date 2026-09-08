"""Fonts loaded from disk rather than installed.

Qt will only use a family it knows about, so a supplied .ttf has to be
registered before the stylesheet asks for it by name. Nothing here is
committed — `assets/fonts/` is gitignored, the same rule the portraits and
a supplied app icon follow — so the interesting case is the one where the
file is NOT there.
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
    assert theme.FONT_STACK.endswith("sans-serif")
    assert theme.FONT_STACK.startswith(f'"{theme.BODY_FAMILY}"')
    # The title is its own face, with the body stack behind it.
    rule = theme.STYLESHEET[theme.STYLESHEET.index("QLabel#titleText"):]
    rule = rule[:rule.index("}")]
    assert theme.TITLE_FAMILY in rule and theme.FONT_STACK in rule


def test_the_names_the_loader_and_the_theme_use_are_the_same():
    """Two spellings of one family is a font that silently never loads."""
    assert fonts.TITLE_FAMILY == theme.TITLE_FAMILY
    assert fonts.BODY_FAMILY == theme.BODY_FAMILY


@pytest.mark.skipif(not (fonts.FONTS_DIR / "LifeCraft.ttf").exists(),
                    reason="the font file is not on this machine")
def test_the_supplied_title_face_actually_resolves(qapp):
    assert theme.TITLE_FAMILY in fonts.load_bundled()
    assert QFont(theme.TITLE_FAMILY).family() == theme.TITLE_FAMILY
