"""The one place this feature talks to the network.

Kept apart from everything else so the rule the rest of the app lives by —
the live scoring loop never makes network calls — is visible rather than
implied: nothing in `ui/app.py`'s tick reaches this module, and the tab
that does calls it on a worker thread.

Every failure is an `ApiError` carrying a KIND and a sentence a person can
act on. The kinds matter: a 404 is a wrong id, a 429 is a free API asking
you to wait, a 500 is theirs and not yours, and a timeout is the search
endpoint being what it is. Answering all four with "request failed" is
what makes an outage look like a bug in the app.
"""

import time

API = "https://api.opendota.com/api"

# Every field the analyses read, named explicitly. OpenDota's `project`
# has been documented as extending the default projection and observed to
# REPLACE it; naming them all is correct either way — harmless duplication
# under one behaviour, essential under the other.
FIELDS = ("match_id", "player_slot", "radiant_win", "duration", "start_time",
          "hero_id", "kills", "deaths", "assists", "party_size", "lobby_type",
          "game_mode", "gold_per_min", "xp_per_min", "hero_damage",
          "tower_damage", "last_hits", "denies", "level", "lane_role",
          "item_0", "item_1", "item_2", "item_3", "item_4", "item_5")


class ApiError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _get(url: str, timeout: int = 60):
    import requests
    try:
        response = requests.get(url, timeout=timeout,
                                headers={"Accept": "application/json"})
    except requests.Timeout:
        raise ApiError("timeout",
                       f"OpenDota did not answer within {timeout} seconds, so "
                       "the request was given up on rather than left hanging. "
                       "Their API is free and does go slow under load. Wait a "
                       "minute and try again.")
    except requests.RequestException as exc:
        raise ApiError("network",
                       "The request to OpenDota did not complete: "
                       f"{exc.__class__.__name__}. Check the machine is "
                       "online and that nothing is blocking the request.")
    if response.status_code == 404:
        raise ApiError("notfound",
                       "OpenDota returned 404 for that account ID. The ID is "
                       "wrong. Check the friend ID on your Dota 2 profile, "
                       "and note that it is not your 17 digit Steam ID.")
    if response.status_code == 429:
        raise ApiError("rate",
                       "OpenDota rate limited the request (429). The free API "
                       "allows a limited number of calls a minute. Wait about "
                       "a minute and run it again.")
    if response.status_code >= 500:
        raise ApiError("server",
                       f"OpenDota returned a {response.status_code}. That is "
                       "their server, not your ID and not this app. Try again "
                       "shortly.")
    if not response.ok:
        raise ApiError("http",
                       f"OpenDota returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError:
        raise ApiError("http", "OpenDota's answer was not JSON.")


def matches(account_id: int, cap: int, days: int | None) -> list:
    from urllib.parse import urlencode
    query = [("limit", str(cap))]
    if days:
        query.append(("date", str(days)))
    query += [("project", field) for field in FIELDS]
    rows = _get(f"{API}/players/{account_id}/matches?{urlencode(query)}")
    return rows if isinstance(rows, list) else []


def heroes() -> dict:
    """Hero id -> name. Cosmetic, so a failure here is never fatal."""
    try:
        rows = _get(f"{API}/heroes", timeout=45)
    except ApiError:
        return {}
    return {row["id"]: row.get("localized_name") or row.get("name")
            or f"Hero {row['id']}"
            for row in rows if isinstance(row, dict) and row.get("id")}


def item_names() -> dict:
    """Item id -> display name, out of a map keyed by internal name."""
    try:
        raw = _get(f"{API}/constants/items", timeout=45)
    except ApiError:
        return {}
    out = {}
    if isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(item, dict) and item.get("id") is not None:
                out[item["id"]] = item.get("dname") or key.replace("_", " ")
    return out


def search(name: str) -> list:
    """Accounts by display name, most recently seen first.

    This endpoint scans a very large table and times out often — thirty
    seconds and then give up, because a hang here reads as the whole app
    being broken. A search timeout says nothing about the account.
    """
    from urllib.parse import quote
    rows = _get(f"{API}/search?q={quote(name)}", timeout=30)
    if not isinstance(rows, list):
        return []
    found = [{"account_id": row.get("account_id"),
              "name": row.get("personaname") or "(no name)",
              "last": row.get("last_match_time")}
             for row in rows
             if isinstance(row, dict) and row.get("account_id") is not None]
    # Most recently seen first. Reversed, "has a timestamp" sorts ahead of
    # "has none", so an account that has never played sinks to the bottom
    # instead of sorting as though it last played at the epoch.
    found.sort(key=lambda row: (row["last"] is not None, row["last"] or ""),
               reverse=True)
    return found[:25]


def one_match(match_id: int) -> dict:
    return _get(f"{API}/matches/{match_id}", timeout=30)


# One request per match against a free API, so the item fetch is paced
# rather than fired off in a loop, and it backs off rather than hammering
# when it is told to slow down.
ITEM_PACE = 1.15           # seconds between requests, about fifty a minute
ITEM_BACKOFF = 20.0        # after a 429
ITEM_STRIKES = 3           # consecutive 429s before giving up


def sleep(seconds: float) -> None:
    """Wrapped so a test can make the pacing free."""
    time.sleep(seconds)
