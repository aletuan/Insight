"""
Chrome bookmark HTML importer.

Usage:
    python -m scripts.import_bookmarks path/to/bookmarks.html
"""
import asyncio
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models import Item, SourceType


class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self._current_href = None
        self._current_add_date = None
        self._in_a = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attr_dict = dict(attrs)
            self._current_href = attr_dict.get("href")
            self._current_add_date = attr_dict.get("add_date")
            self._in_a = True

    def handle_data(self, data):
        if self._in_a and self._current_href:
            add_date = int(self._current_add_date) if self._current_add_date else None
            self.bookmarks.append({
                "url": self._current_href,
                "title": data.strip(),
                "add_date": add_date,
            })

    def handle_endtag(self, tag):
        if tag.lower() == "a":
            self._in_a = False
            self._current_href = None
            self._current_add_date = None


def parse_bookmarks_html(path: Path) -> list[dict]:
    parser = BookmarkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.bookmarks


async def import_to_db(bookmarks: list[dict]):
    async with async_session() as session:
        for bm in bookmarks:
            created_at = (
                datetime.fromtimestamp(bm["add_date"], tz=timezone.utc)
                if bm["add_date"]
                else None
            )
            values = {
                "url": bm["url"],
                "title": bm["title"],
                "source": SourceType.chrome,
            }
            if created_at:
                values["created_at"] = created_at
            stmt = (
                insert(Item)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["url"])
            )
            await session.execute(stmt)
        await session.commit()
        print(f"Imported {len(bookmarks)} bookmarks")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.import_bookmarks <bookmarks.html>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    bookmarks = parse_bookmarks_html(path)
    print(f"Parsed {len(bookmarks)} bookmarks")
    asyncio.run(import_to_db(bookmarks))


if __name__ == "__main__":
    main()
