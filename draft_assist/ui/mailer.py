"""Open the user's own mail client with the report already attached.

WHY THIS IS NOT A `mailto:` LINK. `mailto:` cannot carry an attachment.
The scheme has an `attach=` parameter and no mainstream client honours
it: Outlook removed it around 2002 as a security hole, and Thunderbird
and Windows Mail never accepted it. A link that quietly drops the file
is worse than one that says it cannot take it, because the person hits
send on an empty report and nobody ever learns anything.

SO IT IS SIMPLE MAPI. `MAPISendMail` in `mapi32.dll` is the documented
Windows call that opens the default client with the message filled in
AND the file attached, and `MAPI_DIALOG` is what makes it show the
message rather than send behind the user's back - which matters here
more than convenience: the report carries pictures of that person's own
screen, and they see exactly what is going before they press send.

AND IT IS BEST-EFFORT, WHICH HAS TO BE SAID RATHER THAN HOPED. The NEW
Outlook that ships as the Windows 11 default is a web app and registers
no MAPI provider at all, so on a lot of machines this simply will not
take. The fallback is therefore not a formality: a `mailto:` carries
the subject and the body, and the zip is REVEALED IN EXPLORER already
selected, so attaching it is one drag. `Sent.how` says which happened,
because "it opened an empty email" and "it opened one with your file on
it" must not look the same from here.

NOTHING IN HERE MAY BE FATAL. A mail client that will not open is a
nuisance; an app that dies because it could not is worse. Every path
returns a `Sent` and the caller reads `how`.
"""

import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from .. import console

# MAPI's own constants, spelled here rather than guessed at a call site.
MAPI_DIALOG = 0x00000008
MAPI_TO = 1
SUCCESS_SUCCESS = 0
MAPI_E_USER_ABORT = 1


@dataclass(frozen=True)
class Sent:
    """What actually happened, in terms the UI can put on screen."""

    how: str          # "attached" | "typed" | "folder" | "nothing"
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.how != "nothing"

    @property
    def carried_the_file(self) -> bool:
        return self.how == "attached"


def _mapi(to: str, subject: str, body: str, attachment: Path) -> bool:
    """Simple MAPI. True when the client took the message AND the file."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class MapiRecipDesc(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG),
                    ("ulRecipClass", wintypes.ULONG),
                    ("lpszName", ctypes.c_char_p),
                    ("lpszAddress", ctypes.c_char_p),
                    ("ulEIDSize", wintypes.ULONG),
                    ("lpEntryID", ctypes.c_void_p)]

    class MapiFileDesc(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG),
                    ("flFlags", wintypes.ULONG),
                    ("nPosition", wintypes.ULONG),
                    ("lpszPathName", ctypes.c_char_p),
                    ("lpszFileName", ctypes.c_char_p),
                    ("lpFileType", ctypes.c_void_p)]

    class MapiMessage(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG),
                    ("lpszSubject", ctypes.c_char_p),
                    ("lpszNoteText", ctypes.c_char_p),
                    ("lpszMessageType", ctypes.c_char_p),
                    ("lpszDateReceived", ctypes.c_char_p),
                    ("lpszConversationID", ctypes.c_char_p),
                    ("flFlags", wintypes.ULONG),
                    ("lpOriginator", ctypes.c_void_p),
                    ("nRecipCount", wintypes.ULONG),
                    ("lpRecips", ctypes.POINTER(MapiRecipDesc)),
                    ("nFileCount", wintypes.ULONG),
                    ("lpFiles", ctypes.POINTER(MapiFileDesc))]

    try:
        mapi = ctypes.WinDLL("mapi32.dll")
        send = mapi.MAPISendMail
        # RESTYPE IS NOT OPTIONAL. The default is a 32-bit int, and this
        # app has already paid for that assumption once in `appicon`,
        # where a 64-bit handle came back truncated and the call
        # cheerfully set an icon to nothing.
        send.restype = wintypes.ULONG
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.POINTER(MapiMessage),
                         wintypes.DWORD, wintypes.ULONG]

        # ANSI throughout - this is the A form of the call - so every
        # string is encoded once, here, with anything the codepage
        # cannot carry degraded rather than raising. Same rule as
        # `console.plain_output`: a report of a failure must not fail.
        def ansi(text: str) -> bytes:
            return text.encode("mbcs", errors="replace")

        who = MapiRecipDesc(0, MAPI_TO, ansi(to), ansi(f"SMTP:{to}"), 0, None)
        # The structures must OUTLIVE the call - Windows does not copy
        # them - so they are named locals rather than temporaries.
        files = MapiFileDesc(0, 0, 0xFFFFFFFF,
                             ansi(str(attachment)), ansi(attachment.name),
                             None)
        message = MapiMessage(
            0, ansi(subject), ansi(body), None, None, None, 0, None,
            1, ctypes.pointer(who), 1, ctypes.pointer(files))
        result = send(None, None, ctypes.byref(message), MAPI_DIALOG, 0)
    except (OSError, AttributeError, ValueError):       # noqa: BLE001
        return False
    # A USER WHO CLOSED THE DRAFT IS NOT A FAILURE OF THIS CALL. They
    # saw the message and decided not to send it, which is the whole
    # point of showing it to them; falling through to the fallback there
    # would open a second empty email at somebody who just said no.
    return result in (SUCCESS_SUCCESS, MAPI_E_USER_ABORT)


def reveal(path: Path) -> bool:
    """Open the file manager with this file already selected.

    SELECTED rather than merely opening its folder: the folder holds
    every report ever written, and "it is one of these" is a worse
    answer than pointing at the one.
    """
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)],
                             **console.no_window())
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
        return True
    except OSError:
        return False


def _mailto(to: str, subject: str, body: str) -> bool:
    query = urllib.parse.urlencode(
        {"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    url = f"mailto:{to}?{query}"
    try:
        if sys.platform == "win32":
            import os
            os.startfile(url)   # noqa: S606 - the user's own mail client
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        return True
    except OSError:
        return False


def send(to: str, subject: str, body: str, attachment: Path) -> Sent:
    """Hand the report to the user's mail client, however far it gets."""
    if _mapi(to, subject, body, attachment):
        return Sent("attached",
                    "Your mail program has it, with the file attached.")
    # THE FILE IS REVEALED FIRST, so it is already on screen and selected
    # by the time the empty message appears - otherwise the person is
    # looking at a draft that needs an attachment with no idea where it
    # is. The message then says to drag it across.
    shown = reveal(attachment)
    if _mailto(to, subject, body):
        return Sent("typed" if shown else "typed",
                    "Your mail program could not take the attachment "
                    "automatically, so the file is open in a folder "
                    "beside it - drag it onto the message and send.")
    if shown:
        return Sent("folder",
                    f"No mail program answered. The file is ready at "
                    f"{attachment} - email it to {to} when you can.")
    return Sent("nothing",
                f"The report was written to {attachment}, but neither a "
                "mail program nor a file manager would open.")
