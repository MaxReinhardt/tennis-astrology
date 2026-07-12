"""Canonical id namespacing: Sackmann ATP and WTA id spaces collide, so WTA
player ids are offset and WTA edition ids prefixed everywhere in tennis.*."""

WTA_PLAYER_ID_OFFSET = 10_000_000
WTA_EDITION_PREFIX = "wta-"


def canonical_player_id(tour: str, player_id: int) -> int:
    return player_id + WTA_PLAYER_ID_OFFSET if tour == "wta" else player_id


def canonical_edition_id(tour: str, tourney_id: str) -> str:
    return WTA_EDITION_PREFIX + tourney_id if tour == "wta" else tourney_id
