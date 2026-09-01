"""Loud schema validation for external API responses.

Field names and bracket numbering must never be trusted from memory (see
CLAUDE.md). Every parser in this package validates the shape of what it got
and raises SchemaError pointing at the raw dump so the mismatch can be
inspected, instead of silently mis-parsing.
"""


class SchemaError(RuntimeError):
    def __init__(self, source: str, problem: str, hint: str = ""):
        msg = (
            f"{source} response did not match expectations: {problem}\n"
            "Run `python tools/inspect_apis.py` and inspect the raw dump in "
            "data_cache/raw/ — the API schema may have changed and the "
            "parser needs updating."
        )
        if hint:
            msg += f"\n{hint}"
        super().__init__(msg)


def require(condition: bool, source: str, problem: str, hint: str = "") -> None:
    if not condition:
        raise SchemaError(source, problem, hint)
