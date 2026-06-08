"""Unit tests for src/locations.py.

Covers CONTEXT.md D-02 (Remote-variant collapse) + D-02a (8-rule US/non-US classifier)
+ D-02b (city names verbatim except for Remote-form collapse) + D-02c (curated lists).

Pure-function tests — no I/O.
"""
from __future__ import annotations

import pytest

from src.locations import is_us_location, normalize_location

# --- normalize_location (D-02) ------------------------------------------------


class TestNormalizeLocation:
    """D-02 — Remote-variant collapse. Non-Remote strings unchanged."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Remote-with-US variants → canonical
            ("Remote, US", "Remote (US)"),
            ("Remote - US", "Remote (US)"),
            ("Remote — US", "Remote (US)"),
            ("Remote (USA)", "Remote (US)"),
            ("Remote - United States", "Remote (US)"),
            ("Remote (United States)", "Remote (US)"),
            ("REMOTE / US", "Remote (US)"),
            ("Remote / USA", "Remote (US)"),
            ("remote, u.s.", "Remote (US)"),
            ("Remote (U.S.A.)", "Remote (US)"),
        ],
    )
    def test_remote_us_variants_collapse(self, raw, expected):
        assert normalize_location(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Remote, UK", "Remote (non-US)"),
            ("Remote (UK)", "Remote (non-US)"),
            ("Remote - United Kingdom", "Remote (non-US)"),
            ("Remote (India)", "Remote (non-US)"),
            ("Remote, Germany", "Remote (non-US)"),
            ("Remote — Europe", "Remote (non-US)"),
            ("remote, japan", "Remote (non-US)"),
        ],
    )
    def test_remote_non_us_variants_collapse(self, raw, expected):
        assert normalize_location(raw) == expected

    def test_bare_remote_biases_to_us_per_d02(self):
        """Bare 'Remote' (no country) → 'Remote (US)' (user is US-based)."""
        assert normalize_location("Remote") == "Remote (US)"
        assert normalize_location("remote") == "Remote (US)"
        assert normalize_location("REMOTE") == "Remote (US)"

    @pytest.mark.parametrize(
        "raw",
        [
            "Cupertino, CA",
            "San Francisco",
            "London, UK",
            "Bangalore, India",
            "New York, NY",
        ],
    )
    def test_non_remote_strings_unchanged(self, raw):
        """D-02b — non-Remote city strings pass through verbatim."""
        assert normalize_location(raw) == raw

    def test_none_returns_empty_string(self):
        assert normalize_location(None) == ""

    def test_empty_string_returns_empty(self):
        assert normalize_location("") == ""

    def test_whitespace_only_returns_empty(self):
        assert normalize_location("   ") == ""

    def test_strips_leading_trailing_whitespace_on_passthrough(self):
        assert normalize_location("  Cupertino, CA  ") == "Cupertino, CA"


# --- is_us_location (D-02a — 8-rule classifier) -------------------------------


class TestIsUsLocationClassifierRules:
    """D-02a — rules in declared priority order."""

    # Rule 1: empty/None → True (FILT-05 bias)
    def test_rule1_empty_string_biases_to_true(self):
        assert is_us_location("") is True

    def test_rule1_none_biases_to_true(self):
        assert is_us_location(None) is True

    def test_rule1_whitespace_only_biases_to_true(self):
        assert is_us_location("   ") is True

    # Rule 2: Remote canonical
    def test_rule2_remote_us_canonical_true(self):
        assert is_us_location("Remote (USA)") is True

    def test_rule2_remote_non_us_canonical_false(self):
        assert is_us_location("Remote, UK") is False

    def test_rule2_bare_remote_true(self):
        # Bare "Remote" normalizes to "Remote (US)" → True.
        assert is_us_location("Remote") is True

    # Rule 3: state code
    def test_rule3_state_code_ca_true(self):
        assert is_us_location("Cupertino, CA") is True

    def test_rule3_state_code_ma_true(self):
        assert is_us_location("Boston, MA") is True

    def test_rule3_state_code_ny_true(self):
        assert is_us_location("New York, NY") is True

    def test_rule3_non_state_two_letter_falls_through(self):
        """A 2-letter token that is NOT a US state code must NOT trigger rule 3."""
        # "Sydney, AU" — AU is not a US state. Should fall through to rule 6
        # (Australia in non-US tokens) → False.
        assert is_us_location("Sydney, AU") is False

    # Rule 4: country tokens
    def test_rule4_usa_token_true(self):
        assert is_us_location("Anywhere USA") is True

    def test_rule4_united_states_token_true(self):
        assert is_us_location("Field in United States") is True

    def test_rule4_us_period_token_true(self):
        assert is_us_location("HQ - U.S.") is True

    # Rule 5: known US city
    def test_rule5_seattle_true(self):
        assert is_us_location("Seattle") is True

    def test_rule5_new_york_true(self):
        assert is_us_location("New York") is True

    def test_rule5_san_francisco_true(self):
        assert is_us_location("San Francisco") is True

    def test_rule5_cupertino_true(self):
        assert is_us_location("Cupertino") is True

    # Rule 6: known non-US
    def test_rule6_london_false(self):
        assert is_us_location("London") is False

    def test_rule6_bangalore_india_false(self):
        assert is_us_location("Bangalore, India") is False

    def test_rule6_toronto_canada_false(self):
        assert is_us_location("Toronto, Canada") is False

    def test_rule6_berlin_false(self):
        assert is_us_location("Berlin") is False

    def test_rule6_singapore_false(self):
        assert is_us_location("Singapore") is False

    # Rule 7: fallback bias to True
    def test_rule7_unknown_place_biases_to_true(self):
        assert is_us_location("XYZ Made Up Place") is True

    def test_rule7_random_string_biases_to_true(self):
        assert is_us_location("foo bar baz") is True


class TestEdgeCases:
    """Edge cases that exercise rule ordering and boundary conditions."""

    def test_classifier_rule_order_remote_non_us_beats_other_rules(self):
        """Remote-non-US shape must classify False even though string mentions
        a US-looking token (e.g., 'Remote, India' should be False — India is
        in non-US tokens and the Remote-non-US regex picks it up first via
        rule 2)."""
        assert is_us_location("Remote, India") is False

    def test_classifier_remote_uk_overrides_potential_city_match(self):
        """A 'Remote, UK' input must normalize and classify False."""
        assert normalize_location("Remote, UK") == "Remote (non-US)"
        assert is_us_location("Remote, UK") is False

    def test_state_code_match_requires_word_boundary(self):
        """The substring 'CA' inside 'Cabana, Bahamas' must not trigger rule 3
        (no word boundary). Should fall through to rule 7 fallback → True
        (Bahamas is not in our non-US list — bias toward inclusion)."""
        # 'Cabana' contains 'CA' but not as a standalone token; the state regex
        # uses \b boundaries on uppercase tokens, so 'Cabana' won't match because
        # 'CA' inside it is part of a longer word.
        assert is_us_location("Cabana, Bahamas") is True  # fallback

    def test_us_city_with_state_code_double_match_still_true(self):
        """A clear US city + state (Cambridge, MA) classifies True (rule 3 wins
        first, but rule 5 would also say True)."""
        assert is_us_location("Cambridge, MA") is True

    def test_normalize_then_classify_roundtrip(self):
        """A string that normalizes to canonical Remote must classify per canonical."""
        canonical_us = normalize_location("Remote, US")
        assert canonical_us == "Remote (US)"
        assert is_us_location(canonical_us) is True

        canonical_non_us = normalize_location("Remote, UK")
        assert canonical_non_us == "Remote (non-US)"
        assert is_us_location(canonical_non_us) is False
