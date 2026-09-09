"""Turning whatever the user pasted into an OpenDota account id.

The field takes a 32-bit friend ID, a 64-bit Steam ID, a steamID3, a
classic STEAM_0: id, or a profile URL from Steam, Dotabuff, OpenDota or
Stratz. Anything else is treated as a display name and searched for.

A `steamcommunity.com/id/<name>` vanity URL cannot be resolved here: that
needs the Steam Web API, which requires a key AND a server — so the name
is searched on OpenDota instead, which is a different thing and is said to
be a different thing.
"""

from dataclasses import dataclass
import re

# The base of Steam's individual account range. A 64-bit id is this plus
# the 32-bit account id, which is the only conversion in this module that
# can lose precision if done in floating point — so it is done in int,
# which in Python is arbitrary precision anyway.
STEAM64_BASE = 76561197960265728
MAX_ACCOUNT_ID = 4294967295

IN_GAME = ("In Dota 2, click your name at the top left of the main menu. "
           "Your Friend ID is on the profile page that opens. That number "
           "is exactly what this field wants.")


@dataclass
class Account:
    """What the entry box resolved to: an id, a name to search, or a fault."""
    account_id: int | None = None
    name: str | None = None
    how: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def parse(raw) -> Account:
    text = str(raw or "").strip()
    if not text:
        return Account(error="Enter a Dota 2 friend ID, a Steam ID, or your "
                             "Dota display name.")

    found = re.search(
        r"(?:dotabuff\.com|opendota\.com|stratz\.com)/(?:players|matches)/(\d+)",
        text, re.I)
    if found:
        return Account(account_id=int(found.group(1)),
                       how="read from a profile URL")

    # A Steam custom URL carries a name, not a number.
    found = re.search(r"steamcommunity\.com/id/([^/?#]+)", text, re.I)
    if found:
        from urllib.parse import unquote
        return Account(name=unquote(found.group(1)),
                       how="searched on the name in a Steam custom URL")

    found = re.search(r"\[?U:1:(\d+)\]?", text, re.I)
    if found:
        return Account(account_id=int(found.group(1)),
                       how="read from a steamID3")

    # Classic steamID, STEAM_0:1:97643192 — account = Z * 2 + Y.
    found = re.search(r"STEAM_[0-5]:([01]):(\d+)", text, re.I)
    if found:
        return Account(account_id=int(found.group(2)) * 2 + int(found.group(1)),
                       how="converted from a classic steamID")

    found = re.search(r"steamcommunity\.com/profiles/(\d+)", text, re.I)
    compact = found.group(1) if found else re.sub(r"[\s,]", "", text)

    if not compact.isdigit():
        return Account(name=text, how="searched by display name")
    if len(compact) > 20:
        return Account(error="That number is too long to be a Steam or Dota "
                             "account ID.")

    value = int(compact)
    # 17 digits, or anything at or above the base, is a 64-bit Steam ID.
    if len(compact) >= 17 or value >= STEAM64_BASE:
        if value < STEAM64_BASE:
            return Account(error="That looks like a 17 digit Steam ID but it "
                                 "is below the individual account range.")
        converted = value - STEAM64_BASE
        if converted <= 0 or converted > MAX_ACCOUNT_ID:
            return Account(error="Converting that Steam ID gave an account ID "
                                 "outside the valid 32 bit range.")
        return Account(account_id=converted,
                       how="converted from a 64 bit Steam ID")

    if value <= 0 or value > MAX_ACCOUNT_ID:
        return Account(error="That account ID is outside the valid 32 bit "
                             "range.")
    return Account(account_id=value, how="read as a 32 bit friend ID")
