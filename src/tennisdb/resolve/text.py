"""Text folding shared by all resolvers, plus tennis-data-style alias keys for
Sackmann players ("Federer R.", "Tsonga J.W.", "Pliskova Ka.")."""

import re
import unicodedata

_NFKD_RESISTANT = str.maketrans(
    {
        "ø": "o",
        "ł": "l",
        "đ": "d",
        "æ": "ae",
        "œ": "oe",
        "'": " ",
        "’": " ",
        "-": " ",
    }
)

_WHITESPACE = re.compile(r"\s+")


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", without_marks.translate(_NFKD_RESISTANT)).strip()


def sackmann_alias_keys(name_first: str | None, name_last: str) -> set[str]:
    last = fold(name_last)
    first = fold(name_first or "")
    if not first:
        return {last}
    tokens = first.split()
    multi_initial = ".".join(token[0] for token in tokens) + "."
    return {
        f"{last} {first[0]}.",
        f"{last} {multi_initial}",
        f"{last} {tokens[0][:2]}.",
        f"{last} {tokens[0][:3]}.",
    }
