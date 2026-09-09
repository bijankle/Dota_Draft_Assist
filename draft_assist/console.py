"""Make a console tool's output survive the console it lands in.

A Windows console — and a pipe on a Windows machine — is cp1252 unless
somebody says otherwise, and cp1252 cannot encode the characters this app
uses freely everywhere else: the menu arrow, a sigma, a box-drawing rule.
Printing one raises `UnicodeEncodeError`, which is a fine failure in a
place that can report it and a terrible one anywhere else.

It went wrong in the worst possible place. `fetch_assets.run` catches
every failure so that one part going wrong cannot take the others down —
and the message it printed to SAY so contained a `▸`, so on the
first machine that ever hit that path the handler died reporting the
error it had successfully caught. The original fault (no dataset) was
never printed at all. **A report of a failure must not be able to fail.**

So two rules, and this module is the first:

1. Output never raises. `plain_output()` puts the stream on
   `errors="replace"`, so a character the console cannot draw comes out
   as `?` and the sentence around it still arrives.
2. Nothing writes a character it does not need. The arrows in this app's
   MENU TRAILS are Qt widget text — Qt is Unicode throughout and they
   are right there. A console is not a Qt widget, so console text spells
   the same trail with ASCII.

`ui/tasks.py` covers the other half: the tools it spawns are told to
speak UTF-8 (`PYTHONIOENCODING`) and it decodes them as UTF-8, so a tool
run from the app keeps its glyphs rather than degrading them. This is
the fallback for a tool run by hand in a console, where the codepage is
whatever the machine says it is.
"""

import sys


def plain_output() -> None:
    """Never raise while printing, whatever the console's encoding is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue                      # pythonw: no stream at all
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):     # a stream that will not be told
            pass


def say(text: str) -> None:
    """Print, and if even that fails, print what can be printed.

    `plain_output` normally makes this unnecessary. It is here for the
    one place that must not fail under any circumstances — the handler
    reporting that something else already has — because a stream can
    refuse to be reconfigured and the text may be an exception's own
    message, carrying a path or a library's wording nobody chose.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))
