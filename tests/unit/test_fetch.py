"""T013: Fetch adapter tests using replayed responses (research R3, FR-002, FR-008)."""

import json

import pytest

from hipstraw_mm.adapters.fetch import Fetcher, html_to_text_and_links
from hipstraw_mm.adapters.replay import ReplayStore, match_key_hash

BASE = "https://acme.test/"
ALLOW_ALL = {"status": 200, "text": "User-agent: *\nAllow: /", "headers": {"content-type": "text/plain"}}


def _html(body: str) -> dict:
    return {"status": 200, "text": f"<html><body>{body}</body></html>", "headers": {"content-type": "text/html"}}


def _redirect(location: str, status: int = 301) -> dict:
    return {"status": status, "text": "", "headers": {"content-type": "text/html", "location": location}}


@pytest.fixture
def fetch_fixtures(tmp_path):
    """A replay directory with pre-recorded fetch responses."""
    scenario = tmp_path / "fetch_test"
    fetch_dir = scenario / "fetch"
    fetch_dir.mkdir(parents=True)

    def _record(url: str, response: dict):
        record = {"matchKey": url, "request": {"url": url}, "response": response}
        (fetch_dir / f"{match_key_hash(url)}.json").write_text(json.dumps(record))

    for host in [
        "allowed.test",
        "acme.test",
        "www.acme.test",
        "app.acme.test",
        "moved.test",
        "other.test",
        "shop.test",
        "jump.test",
        "rel.test",
    ]:
        _record(f"https://{host}/robots.txt", ALLOW_ALL)

    _record(
        "https://blocked.test/robots.txt",
        {"status": 200, "text": "User-agent: *\nDisallow: /private", "headers": {"content-type": "text/plain"}},
    )

    _record(
        "https://allowed.test/page",
        {
            "status": 200,
            "text": (
                "<html><head><title>Acme</title></head><body><p>Hello world</p>"
                "<script>bad();</script><style>.x{}</style>"
                '<a href="https://other.test/about">About</a></body></html>'
            ),
            "headers": {"content-type": "text/html"},
        },
    )
    _record("https://blocked.test/private/data", _html("secret"))
    _record(
        "https://allowed.test/doc.pdf",
        {"status": 200, "text": "%PDF-1.4", "headers": {"content-type": "application/pdf"}},
    )
    _record(
        "https://allowed.test/huge",
        {"status": 200, "text": "x" * 3_000_000, "headers": {"content-type": "text/html"}},
    )

    # Redirect scenarios
    _record("https://acme.test/", _redirect("https://www.acme.test/"))
    _record("https://www.acme.test/", _html("<p>Acme Test Co</p>"))
    _record("https://acme.test/go-app", _redirect("https://app.acme.test/home", status=302))
    _record("https://app.acme.test/home", _html("<p>Acme app</p>"))
    _record("https://moved.test/", _redirect("https://other.test/"))
    _record("https://other.test/", _html("<p>Other company</p>"))
    _record("https://shop.test/", _redirect("https://notshop.test/"))
    _record("https://jump.test/", _redirect("https://www.linkedin.com/company/jump"))
    _record("https://rel.test/", _redirect("/home"))
    _record("https://rel.test/home", _html("<p>Rel home</p>"))

    return scenario


@pytest.fixture
def make_fetcher(fetch_fixtures):
    def _make() -> Fetcher:
        return Fetcher(
            replay_store=ReplayStore(fetch_fixtures, mode="replay"),
            denylist_domains=["linkedin.com", "glassdoor.com"],
            user_agent="TestBot/1.0",
            timeout_seconds=15,
            max_bytes=2_000_000,
        )

    return _make


class TestFetcher:
    def test_robots_disallowed(self, make_fetcher):
        result = make_fetcher().fetch("https://blocked.test/private/data")
        assert result.fail_reason == "robots_disallowed"

    def test_denylisted_domain_no_request(self, make_fetcher):
        # No recording exists for linkedin.com, so any request would raise ReplayMissingError.
        result = make_fetcher().fetch("https://linkedin.com/company/acme")
        assert result.fail_reason == "denylisted"

    def test_non_html_skipped(self, make_fetcher):
        result = make_fetcher().fetch("https://allowed.test/doc.pdf")
        assert result.fail_reason == "not_html"

    def test_oversized_rejected(self, make_fetcher):
        result = make_fetcher().fetch("https://allowed.test/huge")
        assert result.fail_reason == "too_large"

    def test_html_to_text_drops_script_and_style(self, make_fetcher):
        result = make_fetcher().fetch("https://allowed.test/page")
        assert result.text is not None
        assert "Hello world" in result.text
        assert "bad()" not in result.text
        assert ".x{}" not in result.text

    def test_outbound_links_returned(self, make_fetcher):
        result = make_fetcher().fetch("https://allowed.test/page")
        assert result.links is not None
        assert len(result.links) >= 1
        link = result.links[0]
        assert "href" in link
        assert "linkId" in link
        assert "anchorText" in link
        assert link["href"] == "https://other.test/about"


class TestHtmlToText:
    """Lines break only at block elements, so inline tags never split a sentence (FR-007 false failures)."""

    def test_inline_tags_do_not_break_text(self):
        text, _ = html_to_text_and_links("<p><strong>Alpha Ledger</strong>: billing for <em>B2B</em> teams.</p>", BASE)
        assert text == "Alpha Ledger: billing for B2B teams."

    def test_link_followed_by_punctuation_stays_on_one_line(self):
        text, _ = html_to_text_and_links('<li>Made by <a href="/a">Alpha Ledger</a>, Inc. in Atlanta.</li>', BASE)
        assert text == "Made by Alpha Ledger, Inc. in Atlanta."

    def test_block_elements_start_new_lines(self):
        html = "<h1>Title</h1><p>One.</p><div>Two.</div><ul><li>Three.</li><li>Four.</li></ul>"
        text, _ = html_to_text_and_links(html, BASE)
        assert text.splitlines() == ["Title", "One.", "Two.", "Three.", "Four."]

    def test_br_and_table_cells_separate_lines(self):
        html = "<p>Line one<br>Line two</p><table><tr><td>Zeta Holdings LLC</td><td>Active</td></tr></table>"
        text, _ = html_to_text_and_links(html, BASE)
        assert text.splitlines() == ["Line one", "Line two", "Zeta Holdings LLC", "Active"]

    def test_source_line_breaks_inside_a_paragraph_are_spaces(self):
        text, _ = html_to_text_and_links("<p>Alpha Ledger is\n   headquartered in\nAtlanta, GA.</p>", BASE)
        assert text == "Alpha Ledger is headquartered in Atlanta, GA."

    def test_adjacent_inline_elements_keep_their_spacing(self):
        text, _ = html_to_text_and_links("<p><span>Alpha</span> <span>Ledger</span><span>,</span> Inc.</p>", BASE)
        assert text == "Alpha Ledger, Inc."


class TestRedirectRule:
    """FR-008: the website check follows redirects only within the same company key or its subdomains."""

    def test_redirect_to_www_is_followed(self, make_fetcher):
        result = make_fetcher().fetch("https://acme.test/", same_company_only=True)
        assert result.fail_reason is None
        assert result.status == 200
        assert result.final_url == "https://www.acme.test/"
        assert result.redirect_chain == ["https://acme.test/"]
        assert "Acme Test Co" in result.text

    def test_redirect_to_subdomain_is_followed(self, make_fetcher):
        result = make_fetcher().fetch("https://acme.test/go-app", same_company_only=True)
        assert result.fail_reason is None
        assert result.final_url == "https://app.acme.test/home"

    def test_redirect_to_other_company_stops(self, make_fetcher):
        result = make_fetcher().fetch("https://moved.test/", same_company_only=True)
        assert result.fail_reason == "redirect_off_site"
        assert result.status == 301
        assert result.final_url == "https://other.test/"
        assert result.text is None

    def test_redirect_to_lookalike_host_stops(self, make_fetcher):
        # notshop.test ends with "shop.test" but is a different company.
        result = make_fetcher().fetch("https://shop.test/", same_company_only=True)
        assert result.fail_reason == "redirect_off_site"

    def test_redirect_to_other_company_allowed_for_ordinary_pages(self, make_fetcher):
        result = make_fetcher().fetch("https://moved.test/")
        assert result.fail_reason is None
        assert result.final_url == "https://other.test/"

    def test_redirect_into_denylisted_domain_is_blocked(self, make_fetcher):
        result = make_fetcher().fetch("https://jump.test/")
        assert result.fail_reason == "denylisted"

    def test_relative_location_is_resolved(self, make_fetcher):
        result = make_fetcher().fetch("https://rel.test/", same_company_only=True)
        assert result.fail_reason is None
        assert result.final_url == "https://rel.test/home"
