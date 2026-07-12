"""M4: text folding and Sackmann alias-key generation for entity resolution."""

import pytest

from tennisdb.resolve.text import fold, sackmann_alias_keys

pytestmark = pytest.mark.m4


class TestFold:
    def test_lowercases_and_keeps_initial_dots(self):
        assert fold("Federer R.") == "federer r."

    def test_strips_diacritics(self):
        assert fold("Söderling R.") == "soderling r."
        assert fold("Muñoz-De La Nava D.") == "munoz de la nava d."

    def test_maps_letters_nfkd_cannot_decompose(self):
        assert fold("Đere L.") == "dere l."
        assert fold("Rønneberg") == "ronneberg"
        assert fold("Łukasz") == "lukasz"
        assert fold("Groß") == "gross"
        assert fold("Særen") == "saeren"

    def test_apostrophes_become_spaces_like_tennisdata_writes_them(self):
        assert fold("O'Connell C.") == "o connell c."
        assert fold("D’Agostini") == "d agostini"

    def test_turns_hyphens_into_spaces(self):
        assert fold("Garcia-Lopez G.") == "garcia lopez g."
        assert fold("Auger-Aliassime F.") == "auger aliassime f."

    def test_collapses_whitespace(self):
        assert fold("  De  Minaur   A. ") == "de minaur a."

    def test_empty_and_none_like_input(self):
        assert fold("") == ""
        assert fold("   ") == ""


class TestSackmannAliasKeys:
    def test_single_first_name_yields_initial_and_prefix_keys(self):
        keys = sackmann_alias_keys("Roger", "Federer")
        assert keys == {"federer r.", "federer ro.", "federer rog."}

    def test_hyphenated_first_name_yields_multi_initial_key(self):
        keys = sackmann_alias_keys("Jo-Wilfried", "Tsonga")
        assert "tsonga j.w." in keys
        assert "tsonga j." in keys

    def test_two_word_first_name_yields_multi_initial_key(self):
        keys = sackmann_alias_keys("Juan Martin", "Del Potro")
        assert "del potro j.m." in keys
        assert "del potro j." in keys

    def test_prefix_keys_disambiguate_shared_initials(self):
        karolina = sackmann_alias_keys("Karolina", "Pliskova")
        kristyna = sackmann_alias_keys("Kristyna", "Pliskova")
        assert "pliskova ka." in karolina
        assert "pliskova kr." in kristyna
        assert "pliskova ka." not in kristyna

    def test_last_name_diacritics_are_folded(self):
        keys = sackmann_alias_keys("Grigor", "Dimitrov")
        assert "dimitrov g." in keys

    def test_missing_first_name_yields_bare_last_name(self):
        assert sackmann_alias_keys(None, "Unknown") == {"unknown"}
        assert sackmann_alias_keys("", "Unknown") == {"unknown"}

    def test_short_first_name_does_not_duplicate_keys(self):
        keys = sackmann_alias_keys("Bo", "Li")
        assert keys == {"li b.", "li bo."}
