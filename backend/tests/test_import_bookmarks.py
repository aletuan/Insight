from pathlib import Path

from scripts.import_bookmarks import parse_bookmarks_html


def test_parse_bookmarks_html():
    html_path = Path(__file__).parent / "fixtures" / "bookmarks_sample.html"
    bookmarks = parse_bookmarks_html(html_path)
    assert len(bookmarks) == 3
    assert bookmarks[0]["url"] == "https://example.com/article1"
    assert bookmarks[0]["title"] == "Article One"
    assert bookmarks[2]["url"] == "https://example.com/nested"


def test_parse_bookmarks_extracts_timestamp():
    html_path = Path(__file__).parent / "fixtures" / "bookmarks_sample.html"
    bookmarks = parse_bookmarks_html(html_path)
    assert bookmarks[0]["add_date"] == 1710000000
