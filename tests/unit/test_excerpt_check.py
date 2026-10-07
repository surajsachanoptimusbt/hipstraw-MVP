"""T009: Unit tests for the excerpt check (research R4, FR-007, FR-018)."""

from hipstraw_mm.evidence.excerpt_check import CheckResult, check_excerpt


class TestExcerptCheck:
    """Quotes, dashes and non-breaking spaces are unified, then casefold + collapse whitespace."""

    def test_exact_match_passes(self):
        page = "Acme Corp provides enterprise solutions for procurement teams."
        result = check_excerpt(
            excerpt="Acme Corp provides enterprise solutions",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"
        assert result.reason is None

    def test_case_difference_passes(self):
        page = "ACME CORP provides enterprise solutions."
        result = check_excerpt(
            excerpt="acme corp provides enterprise solutions",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"

    def test_linebreak_difference_passes(self):
        page = "Acme Corp\nprovides enterprise\nsolutions."
        result = check_excerpt(
            excerpt="Acme Corp provides enterprise solutions",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"

    def test_paraphrase_fails(self):
        page = "Acme Corp provides enterprise solutions for procurement teams."
        result = check_excerpt(
            excerpt="Acme Corp offers business tools for procurement",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "fail"
        assert result.reason == "excerpt_not_found"

    def test_straight_quotes_match_curly_quotes_on_page(self):
        page = "Our motto is “pay only what you owe” and we’re proud of it."
        result = check_excerpt(
            excerpt='Our motto is "pay only what you owe" and we\'re proud',
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"

    def test_curly_quotes_in_excerpt_match_straight_quotes_on_page(self):
        page = 'He said "hello" to the team.'
        result = check_excerpt(
            excerpt="He said “hello” to the team",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"

    def test_en_and_em_dashes_match_hyphens(self):
        page = "We employ 51–200 people — mostly in Atlanta."
        result = check_excerpt(
            excerpt="We employ 51-200 people - mostly in Atlanta",
            page_text=page,
            claim_value="51-200",
        )
        assert result.status == "pass"

    def test_non_breaking_space_matches_normal_space(self):
        page = "Headquartered in Atlanta, GA since 2015."
        result = check_excerpt(
            excerpt="Headquartered in Atlanta, GA",
            page_text=page,
            claim_value="Atlanta, GA",
        )
        assert result.status == "pass"

    def test_paraphrase_with_curly_quotes_still_fails(self):
        page = "Our motto is “pay only what you owe”."
        result = check_excerpt(
            excerpt='Our motto is "only pay what you owe"',
            page_text=page,
            claim_value=None,
        )
        assert result.status == "fail"
        assert result.reason == "excerpt_not_found"

    def test_value_not_in_excerpt_fails(self):
        page = "The company is based in Atlanta, GA with 120 employees."
        result = check_excerpt(
            excerpt="The company is based in Atlanta, GA",
            page_text=page,
            claim_value="120",
        )
        assert result.status == "fail"
        assert result.reason == "value_not_in_excerpt"

    def test_value_in_excerpt_passes(self):
        page = "The company has 120 employees in its Atlanta office."
        result = check_excerpt(
            excerpt="The company has 120 employees",
            page_text=page,
            claim_value="120",
        )
        assert result.status == "pass"

    def test_excerpt_over_300_chars_fails(self):
        page = "A" * 400
        result = check_excerpt(
            excerpt="A" * 301,
            page_text=page,
            claim_value=None,
        )
        assert result.status == "fail"
        assert result.reason == "excerpt_too_long"

    def test_excerpt_exactly_300_chars_passes(self):
        text = "B" * 300
        page = text + " more text"
        result = check_excerpt(
            excerpt=text,
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"

    def test_email_in_excerpt_fails(self):
        page = "Contact us at info@acme.com for more details."
        result = check_excerpt(
            excerpt="Contact us at info@acme.com for more",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "fail"
        assert result.reason == "contains_contact_data"

    def test_phone_in_excerpt_fails(self):
        page = "Call us at (404) 555-1234 today."
        result = check_excerpt(
            excerpt="Call us at (404) 555-1234 today",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "fail"
        assert result.reason == "contains_contact_data"

    def test_person_name_in_excerpt_passes(self):
        """FR-018: person names inside excerpts are allowed."""
        page = "CEO Jane Roe said the company is expanding its Atlanta office."
        result = check_excerpt(
            excerpt="CEO Jane Roe said the company is expanding",
            page_text=page,
            claim_value=None,
        )
        assert result.status == "pass"


class TestHeadquartersStateNames:
    """Added at the T051 review (2026-10-07): for a headquarters claim, a US state's two-letter code and
    its full name are equal when checking that the value appears in the excerpt (FR-007). In the
    first live run, Addison Health Systems' claim "Addison, TX" failed against "Addison, Texas"."""

    PAGE = (
        "Addison Health Systems is located in the heart of Addison, Texas. "
        "Addison is one of the Dallas area's most popular suburbs."
    )
    EXCERPT = "Addison Health Systems is located in the heart of Addison, Texas."

    def test_a_code_in_the_claim_matches_the_full_name_in_the_excerpt(self):
        result = check_excerpt(self.EXCERPT, self.PAGE, "Addison, TX", claim_field="hq")
        assert result.status == "pass"

    def test_a_full_name_in_the_claim_matches_the_code_in_the_excerpt(self):
        page = "Visit us at 10 Main Street, Addison, TX 75001."
        result = check_excerpt("10 Main Street, Addison, TX 75001.", page, "Addison, Texas", claim_field="hq")
        assert result.status == "pass"

    def test_multi_word_state_names(self):
        page = "Our headquarters is in Jersey City, New Jersey, near the PATH station."
        excerpt = "Our headquarters is in Jersey City, New Jersey, near the PATH station."
        assert check_excerpt(excerpt, page, "Jersey City, NJ", claim_field="hq").status == "pass"
        page_ny = "Headquarters: New York, NY."
        assert (
            check_excerpt("Headquarters: New York, NY.", page_ny, "New York, New York", claim_field="hq").status
            == "pass"
        )

    def test_a_different_state_still_fails(self):
        page = "We are based in Addison, Tennessee."
        result = check_excerpt("We are based in Addison, Tennessee.", page, "Addison, TX", claim_field="hq")
        assert result == CheckResult("fail", "value_not_in_excerpt")

    def test_a_different_city_still_fails(self):
        result = check_excerpt(self.EXCERPT, self.PAGE, "Dallas, TX", claim_field="hq")
        assert result == CheckResult("fail", "value_not_in_excerpt")

    def test_only_headquarters_claims_get_the_equivalence(self):
        assert check_excerpt(self.EXCERPT, self.PAGE, "Addison, TX", claim_field="parent").status == "fail"
        assert check_excerpt(self.EXCERPT, self.PAGE, "Addison, TX").status == "fail"
