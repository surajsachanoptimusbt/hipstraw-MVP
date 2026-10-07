"""T078: the website load outcome and the name-domain check (FR-008, FR-016, research R4).

Revised after the first live run (2026-10-07): only a website that does not exist (HTTP 404 or 410,
or a host name that does not resolve) fails the existence check. A website that exists but cannot be
read, including one blocked by robots.txt, is `unreadable`, which Review turns into needs
verification.
"""

from __future__ import annotations

import pytest

from hipstraw_mm.evidence.existence import find_existence, name_matches_domain, website_status


class TestWebsiteStatus:
    def test_a_2xx_page_resolves(self):
        assert website_status(None, 200) == "resolves"

    @pytest.mark.parametrize(
        ("fail_reason", "http_status"),
        [("http_error", 404), ("http_error", 410), ("dns_error", None)],
    )
    def test_a_website_that_does_not_exist_fails(self, fail_reason, http_status):
        assert website_status(fail_reason, http_status) == "fails"

    @pytest.mark.parametrize(
        ("fail_reason", "http_status"),
        [
            ("robots_disallowed", None),
            ("http_error", 401),
            ("http_error", 403),
            ("http_error", 429),
            ("http_error", 500),
            ("http_error", 503),
            ("http_error", 400),
            ("network_error", None),
            ("redirect_off_site", 301),
            ("too_many_redirects", 302),
            ("not_html", 200),
            ("too_large", 200),
        ],
    )
    def test_a_website_that_exists_but_cannot_be_read_is_unreadable(self, fail_reason, http_status):
        assert website_status(fail_reason, http_status) == "unreadable"


class TestNameMatchesDomain:
    @pytest.mark.parametrize(
        ("name", "domain"),
        [
            ("Alpha Ledger", "alpha-ledger.test"),
            ("Accountable HQ", "www.accountablehq.com"),
            ("ADEO Healthcare Software", "adeohs.com"),
            ("6DOS", "6dos.co"),
            ("The Home Depot", "homedepot.com"),
            ("ACV Auctions", "www.acvauctions.com"),
            ("Alpha Ledger, Inc.", "go.alpha-ledger.test"),
        ],
    )
    def test_matching_names(self, name, domain):
        assert name_matches_domain(name, domain) is True

    @pytest.mark.parametrize(
        ("name", "domain"),
        [
            ("Addison Health Systems", "www.writepad.com"),
            ("Larch Health Systems", "quillpad.test"),
            ("Sorrel Analytics", "tallyhub.test"),
        ],
    )
    def test_mismatched_names(self, name, domain):
        assert name_matches_domain(name, domain) is False


class TestFindExistence:
    """Added at the T051 review (FR-016): the homepage first, then the website's own about or contact
    pages already fetched in the run, in fetch order. No page is fetched for this."""

    HOME = ("https://brightform.test/", "BrightForm\nBrightForm builds intake forms for clinics.")
    ABOUT = ("https://brightform.test/About-Us", "About BrightForm\nBrightForm is built by Teasel Systems, Inc.")
    CONTACT = ("https://brightform.test/contact", "Contact\nWrite to Teasel Systems at our New York office.")
    CAREERS = ("https://brightform.test/careers", "Careers\nTeasel Systems is hiring.")

    def test_the_homepage_is_used_when_it_names_the_company(self):
        home = ("https://teasel.test/", "Teasel Systems\nTeasel Systems builds intake forms.")
        assert find_existence([home, self.ABOUT], "Teasel Systems") == ("https://teasel.test/", "Teasel Systems")

    def test_an_about_page_is_used_when_the_homepage_does_not_name_the_company(self):
        url, excerpt = find_existence([self.HOME, self.CAREERS, self.ABOUT], "Teasel Systems")
        assert url == "https://brightform.test/About-Us"
        assert excerpt == "BrightForm is built by Teasel Systems, Inc."

    def test_about_and_contact_pages_are_searched_in_fetch_order(self):
        url, _ = find_existence([self.HOME, self.CONTACT, self.ABOUT], "Teasel Systems")
        assert url == "https://brightform.test/contact"

    def test_other_pages_do_not_count(self):
        assert find_existence([self.HOME, self.CAREERS], "Teasel Systems") == ("https://brightform.test/", "")
