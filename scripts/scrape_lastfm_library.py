#!/usr/bin/env python3

import argparse
import csv
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from threading import local
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE_URL = "https://www.last.fm"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

THREAD_LOCAL = local()

ROW_RE = re.compile(
    r'<tr\b[^>]*class="[^"]*chartlist-row[^"]*"[^>]*>(.*?)</tr>',
    re.S,
)
NAME_URL_RE = re.compile(
    r'<td\b[^>]*class="[^"]*chartlist-name[^"]*"[^>]*>.*?<a\b[^>]*href="(?P<url>/music/[^"]+)"[^>]*>(?P<name>.*?)</a>',
    re.S,
)
COUNT_RE = re.compile(
    r'<span class="chartlist-count-bar-value">\s*([\d,]+)\s*<span class="stat-name">scrobbles',
    re.S,
)
PAGE_RE = re.compile(r'href="\?page=(\d+)"')
TAG_SECTION_RE = re.compile(
    r'<section\s+class="\s*catalogue-tags\s*".*?</section>',
    re.S,
)
TAG_RE = re.compile(
    r'<li[^>]*class="tag"[^>]*>\s*<a[^>]*href="/tag/[^"]+"[^>]*>(.*?)</a>',
    re.S,
)
TEALIUM_TAG_RE = re.compile(r'&#34;tag&#34;:\s*&#34;([^&#]+)&#34;')


@dataclass
class ArtistRecord:
    artist: str
    artist_url: str
    scrobbles: int
    tags: list[str]


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    return html.unescape(text).strip()


def make_opener():
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9,it;q=0.8"),
    ]
    with opener.open(Request(f"{BASE_URL}/"), timeout=30) as response:
        response.read()
    return opener


def get_opener():
    opener = getattr(THREAD_LOCAL, "opener", None)
    if opener is None:
        opener = make_opener()
        THREAD_LOCAL.opener = opener
    return opener


def fetch(url: str, retries: int = 4, timeout: int = 30) -> str:
    last_error = None
    for attempt in range(retries):
        try:
            opener = get_opener()
            with opener.open(Request(url), timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if hasattr(THREAD_LOCAL, "opener"):
                del THREAD_LOCAL.opener
            if attempt < retries - 1:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def parse_total_pages(page_html: str) -> int:
    page_numbers = [int(match) for match in PAGE_RE.findall(page_html)]
    return max(page_numbers) if page_numbers else 1


def parse_library_page(page_html: str) -> list[ArtistRecord]:
    artists: list[ArtistRecord] = []
    for row_html in ROW_RE.findall(page_html):
        name_match = NAME_URL_RE.search(row_html)
        if not name_match:
            continue
        count_match = COUNT_RE.search(row_html)
        name = clean_text(name_match.group("name"))
        artist_url = html.unescape(name_match.group("url"))
        scrobbles = int((count_match.group(1) if count_match else "0").replace(",", ""))
        artists.append(
            ArtistRecord(
                artist=name,
                artist_url=urljoin(BASE_URL, artist_url),
                scrobbles=scrobbles,
                tags=[],
            )
        )
    return artists


def parse_tags(artist_html: str) -> list[str]:
    section_match = TAG_SECTION_RE.search(artist_html)
    tags: list[str] = []
    if section_match:
        tags = [clean_text(tag) for tag in TAG_RE.findall(section_match.group(0))]
    if not tags:
        tealium_match = TEALIUM_TAG_RE.search(artist_html)
        if tealium_match:
            raw_tags = html.unescape(tealium_match.group(1))
            tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    seen = set()
    deduped = []
    for tag in tags:
        if tag not in seen:
            deduped.append(tag)
            seen.add(tag)
    return deduped


def scrape_library(
    library_url: str,
    max_pages: int | None = None,
    max_artists: int | None = None,
) -> dict[str, ArtistRecord]:
    first_page = fetch(library_url)
    total_pages = parse_total_pages(first_page)
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)
    print(f"Found {total_pages} library pages", file=sys.stderr)

    artists: dict[str, ArtistRecord] = {}
    for page in range(1, total_pages + 1):
        page_html = first_page if page == 1 else fetch(f"{library_url}?page={page}")
        page_artists = parse_library_page(page_html)
        for artist in page_artists:
            artists.setdefault(artist.artist_url, artist)
            if max_artists is not None and len(artists) >= max_artists:
                break
        print(
            f"Parsed page {page}/{total_pages} ({len(artists)} unique artists)",
            file=sys.stderr,
        )
        if max_artists is not None and len(artists) >= max_artists:
            break
    return artists


def scrape_tags(artists: dict[str, ArtistRecord], workers: int) -> None:
    def fetch_artist_tags(record: ArtistRecord):
        artist_html = fetch(record.artist_url)
        return record.artist_url, parse_tags(artist_html)

    completed = 0
    total = len(artists)
    failed_urls: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_artist_tags, record): record.artist_url
            for record in artists.values()
        }
        for future in as_completed(future_map):
            artist_url = future_map[future]
            try:
                artist_url, tags = future.result()
                artists[artist_url].tags = tags
            except Exception as exc:  # noqa: BLE001
                failed_urls.append(artist_url)
                print(f"Tag fetch failed for {artist_url}: {exc}", file=sys.stderr)
            completed += 1
            if completed % 100 == 0 or completed == total:
                print(f"Fetched tags for {completed}/{total} artists", file=sys.stderr)

    if failed_urls:
        print(f"Retrying {len(failed_urls)} failed artist tag requests sequentially", file=sys.stderr)
        for artist_url in failed_urls:
            try:
                artist_html = fetch(artist_url)
                artists[artist_url].tags = parse_tags(artist_html)
            except Exception as exc:  # noqa: BLE001
                print(f"Sequential retry failed for {artist_url}: {exc}", file=sys.stderr)


def write_outputs(artists: dict[str, ArtistRecord], output_base: Path) -> tuple[Path, Path]:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_base.with_suffix(".csv")
    json_path = output_base.with_suffix(".json")

    records = sorted(artists.values(), key=lambda record: (-record.scrobbles, record.artist.lower()))

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["artist", "artist_url", "scrobbles", "tags"],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "artist": record.artist,
                    "artist_url": record.artist_url,
                    "scrobbles": record.scrobbles,
                    "tags": " | ".join(record.tags),
                }
            )

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(
            [
                {
                    "artist": record.artist,
                    "artist_url": record.artist_url,
                    "scrobbles": record.scrobbles,
                    "tags": record.tags,
                }
                for record in records
            ],
            json_file,
            ensure_ascii=False,
            indent=2,
        )

    return csv_path, json_path


def main():
    parser = argparse.ArgumentParser(
        description="Scrape artists from a public Last.fm library and fetch artist tags."
    )
    parser.add_argument("library_url", help="Last.fm library artist URL")
    parser.add_argument(
        "--output-base",
        default="output/lastfm_library_artists_with_tags",
        help="Output path without extension",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent artist tag requests",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum library pages to scrape",
    )
    parser.add_argument(
        "--max-artists",
        type=int,
        default=None,
        help="Maximum number of artists to include",
    )
    args = parser.parse_args()

    artists = scrape_library(
        args.library_url,
        max_pages=args.max_pages,
        max_artists=args.max_artists,
    )
    scrape_tags(artists, workers=max(args.workers, 1))
    csv_path, json_path = write_outputs(artists, Path(args.output_base))

    with_tags = sum(1 for artist in artists.values() if artist.tags)
    print(
        json.dumps(
            {
                "artists": len(artists),
                "artists_with_tags": with_tags,
                "csv": str(csv_path.resolve()),
                "json": str(json_path.resolve()),
            }
        )
    )


if __name__ == "__main__":
    main()
