"""Everything the app can be asked to do, and a search that finds it.

The menu bar is three headings now — File, View, Help — and everything
that used to be spread across Setup and Game is a tab in Settings. That
is a better place to KEEP a control and a worse place to FIND one: a
person who knows the app can do a thing no longer has a menu to hunt
through. So the app carries a list of what it can do and Help searches it.

**IT IS NOT KEYWORD MATCHING.** "Anything which is in Setup and Game" is
now several tabs deep, and somebody looking for it will type what they
call it rather than what the menu calls it — "pictures" for artwork,
"broken" for diagnose, "transparent" for opacity, "hotkey" for shortcut.
So every entry carries the words a person might reach for as well as its
own label, and the query is matched against all of them. A term that is
nobody's synonym still matches as a prefix of a real word, which is what
makes typing three letters useful.

The ranking is deliberately simple and explainable rather than clever:
a whole-word hit on the label beats a prefix of it, which beats a
synonym, which beats a hit in the description. Nothing here needs a
model, and a search that cannot say why it ranked something is a search
nobody trusts.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Command:
    """One thing the app can do, and how a person might ask for it.

    `where` is the trail shown beside the result — "Settings ▸ Downloads"
    — because knowing where a thing lives is most of what somebody
    searching for it actually wanted.
    """

    label: str
    where: str = ""
    detail: str = ""
    words: tuple[str, ...] = ()
    run: object = None           # a callable, or None for a heading

    @property
    def title(self) -> str:
        return f"{self.where} ▸ {self.label}" if self.where else self.label


# Words a person is likely to type for things the app calls something
# else. Keyed by the word they type; the values are words that appear in
# the entries. Two-way is NOT wanted: typing "artwork" should find the
# portraits, and typing "portrait" should not drag in everything filed
# under artwork.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "picture": ("portrait", "artwork", "icon", "image"),
    "pictures": ("portrait", "artwork", "icon", "image"),
    "image": ("portrait", "artwork", "icon"),
    "art": ("artwork", "portrait"),
    "download": ("fetch", "get", "artwork", "update"),
    "get": ("download", "fetch"),
    "fetch": ("download",),
    "install": ("set", "setup", "download"),
    "broken": ("diagnose", "check", "problem", "fault"),
    "problem": ("diagnose", "check", "broken"),
    "wrong": ("diagnose", "check", "broken"),
    "fix": ("diagnose", "repair", "check"),
    "help": ("diagnose", "about"),
    "transparent": ("transparency", "opacity", "see"),
    "opacity": ("transparency",),
    "seethrough": ("transparency", "opacity"),
    "size": ("sizes", "scale", "bigger", "smaller", "portraits"),
    "bigger": ("sizes", "scale"),
    "smaller": ("sizes", "scale"),
    "zoom": ("sizes", "scale"),
    "font": ("sizes", "numbers"),
    "hotkey": ("shortcut", "key"),
    "shortcut": ("hotkey", "key"),
    "rank": ("bracket", "brackets", "legend", "ancient", "divine"),
    "bracket": ("rank", "ranks"),
    "mmr": ("bracket", "rank"),
    "stats": ("statistics", "numbers", "data"),
    "data": ("statistics", "numbers"),
    "numbers": ("statistics", "data"),
    "gsi": ("game", "integration", "state"),
    "dota": ("game",),
    "screen": ("vision", "capture", "window"),
    "capture": ("screen", "vision", "record"),
    "record": ("recording", "capture", "session"),
    "log": ("debug", "recording", "report"),
    "version": ("update", "upgrade"),
    "upgrade": ("update",),
    "new": ("update", "latest"),
    "latest": ("update",),
    "newest": ("update", "latest"),
    "reset": ("clear", "default"),
    "clear": ("reset", "empty"),
    "theme": ("colour", "color", "appearance"),
    "colour": ("theme", "appearance"),
    "color": ("theme", "appearance"),
    "key": ("stratz", "api", "token"),
    "api": ("key", "stratz"),
    "token": ("key", "api"),
    "lock": ("resize", "window", "fixed"),
    "move": ("position", "reset", "window"),
    "item": ("items", "rules", "build"),
    "build": ("items", "rules"),
}

# Words too common to rank anything on. Wider than it looks it needs to
# be, deliberately: every term has to hit something or the entry is
# dropped, so a filler word left in here is a whole query answered with
# nothing — "it's broken" and "nothing from dota" both found the right
# answer for "broken" and "dota" and were then sunk by "its" and "from".
STOP = frozenset(("the", "a", "an", "of", "and", "to", "for", "in", "on",
                  "is", "it", "its", "my", "me", "i", "how", "do", "does",
                  "with", "from", "at", "by", "that", "this", "am", "are",
                  "was", "be", "can", "cant", "cannot", "wont", "will",
                  "please", "some", "any", "all", "up", "out", "s", "t"))

# What a hit is worth, and the order is the whole ranking rule.
WORD_HIT = 10           # a whole word of the label
PREFIX_HIT = 6          # the start of a word of the label
SYNONYM_HIT = 4         # a word the entry declares itself findable by
DETAIL_HIT = 2          # somewhere in the explanation or the trail


def _words(text: str) -> list[str]:
    """Lower-cased words, punctuation dropped. `&` is a menu mnemonic and
    must not survive into a word, or "&Update" never matches "update"."""
    out, current = [], []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def expand(term: str) -> set[str]:
    """A search term and everything it is a person's word FOR."""
    return {term, *SYNONYMS.get(term, ())}


def score(query: str, command: Command) -> int:
    """How well one entry answers one query. 0 means it does not.

    EVERY term has to hit something. Searching "item icons" for a thing
    that mentions items but nothing about icons is how a search ends up
    returning its whole list ranked by coincidence — and a list that
    always has an answer is one where the top match means nothing.
    """
    terms = [t for t in _words(query) if t not in STOP]
    if not terms:
        return 0
    label = _words(command.label)
    declared = set(command.words)
    detail = set(_words(command.detail)) | set(_words(command.where))
    total = 0
    for term in terms:
        wanted = expand(term)
        best = 0
        if wanted & set(label):
            best = WORD_HIT
        elif any(word.startswith(term) for word in label):
            best = PREFIX_HIT
        elif wanted & declared:
            best = SYNONYM_HIT
        elif wanted & detail or any(word.startswith(term) for word in detail):
            best = DETAIL_HIT
        if not best:
            return 0                # a term nothing answers sinks the entry
        total += best
    # A shorter label matching the same terms is the more specific answer:
    # "Item icons…" should beat "All artwork…" for "item icons".
    return total * 100 - len(label)


def search(query: str, commands) -> list:
    """The entries that answer this query, best first."""
    scored = [(score(query, c), i, c) for i, c in enumerate(commands)
              if c.run is not None]
    return [c for value, _i, c in sorted(scored, key=lambda row: (-row[0],
                                                                 row[1]))
            if value > 0]
