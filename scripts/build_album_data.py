#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MIXTAPE_PATH = ROOT / "output" / "mameli_mixtape_first50_artists_with_tags.json"
TAG_BROWSE_PATH = ROOT / "output" / "mameli_mixtape_tags_browse.md"
ALBUM_DATA_PATH = ROOT / "src" / "data" / "album-list.json"
APPLE_SCRIPT = (
    Path("/Users/filippomameli/.codex/skills/apple-music-album-linker/scripts")
    / "find_apple_music_album.py"
)

MUST_HEAR_URL = "https://www.albumoftheyear.org/must-hear/"
NEW_RELEASES_URL = "https://www.albumoftheyear.org/releases/"
MAX_MUST_HEAR = 5

ROW_EXTRACTION_JS = r"""
() => {
  const parseCount = (value) => {
    const text = (value || "")
      .replace(/[()]/g, "")
      .replace(/,/g, "")
      .trim()
      .toLowerCase();
    if (!text) return null;
    if (text.endsWith("k")) {
      return Math.round(parseFloat(text.slice(0, -1)) * 1000);
    }
    const count = Number(text);
    return Number.isFinite(count) ? count : null;
  };

  return Array.from(document.querySelectorAll("div.albumBlock"))
    .map((row, index) => {
      const albumAnchor = row.querySelector('a[href*="/album/"] .albumTitle');
      const albumLink = albumAnchor?.closest('a[href*="/album/"]');
      const ratingRows = Array.from(row.querySelectorAll(".ratingRow")).map((ratingRow) => {
        const labels = Array.from(ratingRow.querySelectorAll(".ratingText")).map((node) =>
          node.textContent.trim().toLowerCase()
        );
        return {
          label: labels[0] || null,
          score: Number(ratingRow.querySelector(".rating")?.textContent?.trim() || Number.NaN),
          count: parseCount(labels[1] || ""),
        };
      });

      const critic = ratingRows.find((entry) => entry.label === "critic score") || null;
      const user = ratingRows.find((entry) => entry.label === "user score") || null;

      return {
        source_rank: index + 1,
        artist:
          row.querySelector('a[href*="/artist/"] .artistTitle')?.textContent?.trim() ||
          row.querySelector(".artistTitle")?.textContent?.trim() ||
          null,
        album: albumAnchor?.textContent?.trim() || null,
        aoty_url: albumLink?.href || null,
        critic_score: Number.isFinite(critic?.score) ? critic.score : null,
        critic_count: critic?.count ?? null,
        user_score: Number.isFinite(user?.score) ? user.score : null,
        user_count: user?.count ?? null,
      };
    })
    .filter((row) => row.album && row.aoty_url);
}
""".strip()

ALBUM_DETAIL_JS = r"""
() => {
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim() || null;
  const normalizeTitle = (value) =>
    clean(value?.replace(/\s+- Reviews - Album of The Year$/, ""));

  const heading = document.querySelector("h1");
  const headingContainer = heading?.parentElement || null;
  const artistFromHeading = headingContainer
    ?.querySelector('a[href*="/artist/"]')
    ?.textContent;
  const titleText = normalizeTitle(document.title);
  const titleParts = titleText ? titleText.split(" - ") : [];

  const genreContainer = Array.from(document.querySelectorAll('a[href*="/genre/"]'))
    .map((link) => link.closest("div"))
    .find((container) => /\/\s*genre/i.test(container?.textContent || ""));

  let genreTags = [];
  if (genreContainer) {
    genreTags = Array.from(genreContainer.querySelectorAll('a[href*="/genre/"]'))
      .map((link) => clean(link.textContent))
      .filter(Boolean);
  }

  if (!genreTags.length) {
    genreTags = Array.from(document.querySelectorAll('a[href*="/genre/"]'))
      .map((link) => ({
        text: clean(link.textContent),
        top: link.getBoundingClientRect().top,
      }))
      .filter((entry) => entry.text && entry.top > 200 && entry.top < 1400)
      .map((entry) => entry.text);
  }

  return {
    title: document.title,
    artist: clean(artistFromHeading) || clean(titleParts[0]) || null,
    album:
      clean(heading?.textContent) ||
      clean(titleParts.slice(1).join(" - ")) ||
      null,
    apple_music:
      document.querySelector('a[href*="music.apple.com"], a[href*="geo.music.apple.com"]')
        ?.href || null,
    genre_tags: [...new Set(genreTags)],
  };
}
""".strip()


def normalize_tag(tag: str) -> str:
    normalized = tag.lower().strip()
    normalized = normalized.replace("\u2010", "-").replace("\u2011", "-")
    normalized = normalized.replace("\u2012", "-").replace("\u2013", "-")
    normalized = normalized.replace("\u2014", "-").replace("\u2015", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("r&b", "rnb").replace("r and b", "rnb")
    normalized = normalized.replace("hip hop", "hip-hop").replace("hiphop", "hip-hop")
    normalized = normalized.replace("/", " ").replace("_", " ")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -")
    return normalized


def parse_cli_result(output: str) -> Any:
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "### Result":
            continue
        payload_lines: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate.startswith("### "):
                break
            payload_lines.append(candidate)
        payload = "\n".join(payload_lines).strip()
        if not payload:
            return None
        return json.loads(payload)
    raise RuntimeError(f"Could not parse Playwright output:\n{output}")


def run_command(args: list[str], *, timeout: int = 120) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        details = result.stdout or result.stderr
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{details}")
    return result.stdout


def run_playwright(args: list[str], *, timeout: int = 120) -> str:
    return run_command(["playwright-cli", *args], timeout=timeout)


def eval_playwright(js: str, *, timeout: int = 120) -> Any:
    output = run_playwright(["eval", js], timeout=timeout)
    return parse_cli_result(output)


def open_browser() -> None:
    run_playwright(["open", "about:blank", "--headed"], timeout=120)


def close_browser() -> None:
    try:
        run_playwright(["close"], timeout=30)
    except RuntimeError:
        pass


def goto(url: str) -> None:
    run_playwright(["goto", url], timeout=120)


def wait_for_page_ready() -> None:
    time.sleep(1.0)


def title_is_blocked() -> bool:
    title = eval_playwright("() => document.title", timeout=30)
    return isinstance(title, str) and title.strip() == "Just a moment..."


def ensure_page(url: str, *, allow_retry: bool = True) -> None:
    goto(url)
    wait_for_page_ready()
    if allow_retry and title_is_blocked():
        time.sleep(3.0)
        goto(url)
        wait_for_page_ready()


def load_mixtape_rows() -> list[dict[str, Any]]:
    return json.loads(MIXTAPE_PATH.read_text())


def build_tag_profile(rows: list[dict[str, Any]]) -> tuple[Counter[str], Counter[str]]:
    frequency = Counter()
    weighted = Counter()

    for row in rows:
        scrobbles = int(row.get("scrobbles", 0))
        tags = [normalize_tag(tag) for tag in row.get("tags", []) if normalize_tag(tag)]
        for tag in set(tags):
            frequency[tag] += 1
        for rank, tag in enumerate(tags[:5]):
            weighted[tag] += (5 - rank) * scrobbles

    return frequency, weighted


def write_tag_browse(rows: list[dict[str, Any]], frequency: Counter[str], weighted: Counter[str]) -> None:
    TAG_BROWSE_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Mameli Mixtape Tags",
        "",
        f"Total artists processed: {len(rows)}",
        "",
        "## Top Tags by Artist Frequency",
        "",
        "| Tag | Artists |",
        "| --- | ---: |",
    ]
    for tag, count in frequency.most_common():
        lines.append(f"| {tag} | {count} |")

    lines.extend(
        [
            "",
            "## Top Tags by Scrobble-Weighted Preference",
            "",
            "| Tag | Weighted score |",
            "| --- | ---: |",
        ]
    )
    for tag, score in weighted.most_common():
        lines.append(f"| {tag} | {score} |")

    TAG_BROWSE_PATH.write_text("\n".join(lines) + "\n")


def extract_album_rows(url: str) -> list[dict[str, Any]]:
    ensure_page(url)
    rows = eval_playwright(ROW_EXTRACTION_JS, timeout=60)
    if not isinstance(rows, list):
        raise RuntimeError(f"Unexpected row payload for {url}: {rows!r}")
    return rows


def fetch_album_detail(url: str) -> dict[str, Any]:
    ensure_page(url)
    detail = eval_playwright(ALBUM_DETAIL_JS, timeout=60)
    if not isinstance(detail, dict):
        raise RuntimeError(f"Unexpected detail payload for {url}: {detail!r}")
    if detail.get("title") == "Just a moment...":
        raise RuntimeError(f"Album page blocked by Cloudflare: {url}")
    return detail


def lookup_apple_music(artist: str, album: str) -> str | None:
    if not artist or not album:
        return None

    output = run_command(
        [
            "python3",
            str(APPLE_SCRIPT),
            "--artist",
            artist,
            "--album",
            album,
            "--json",
        ],
        timeout=60,
    )
    payload = json.loads(output)
    match_quality = payload.get("match_quality")
    if match_quality == "exact":
        return payload.get("url")
    if match_quality == "likely":
        if normalize_tag(payload.get("artist", "")) == normalize_tag(artist) and normalize_tag(
            payload.get("album", "")
        ) == normalize_tag(album):
            return payload.get("url")
    return None


def choose_score(row: dict[str, Any], *, source: str) -> tuple[int, str, int | None]:
    if source == "must-hear":
        if row.get("critic_score") is not None:
            return int(row["critic_score"]), "critic score", row.get("critic_count")
        if row.get("user_score") is not None:
            return int(row["user_score"]), "user score", row.get("user_count")
        raise RuntimeError(f"Must Hear row has no score: {row}")

    if row.get("critic_score") is None:
        raise RuntimeError(f"New release row missing critic score: {row}")
    return int(row["critic_score"]), "critic score", row.get("critic_count")


def collect_albums() -> list[dict[str, Any]]:
    must_hear_rows = extract_album_rows(MUST_HEAR_URL)
    new_release_rows = extract_album_rows(NEW_RELEASES_URL)

    must_hear = must_hear_rows[:MAX_MUST_HEAR]
    new_releases = [
        row
        for row in new_release_rows
        if row.get("critic_score") is not None
        and int(row["critic_score"]) >= 80
        and int(row.get("critic_count") or 0) > 5
    ]

    selected: list[tuple[str, dict[str, Any]]] = [("must-hear", row) for row in must_hear]
    selected.extend(("new-releases", row) for row in new_releases)

    albums: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for source, row in selected:
        url = row["aoty_url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        score, score_type, review_count = choose_score(row, source=source)
        detail = fetch_album_detail(url)

        artist = detail.get("artist") or row.get("artist")
        album = detail.get("album") or row.get("album")
        genre_tags = [tag for tag in detail.get("genre_tags", []) if tag][:3]
        apple_music = detail.get("apple_music") or lookup_apple_music(artist, album)

        if not apple_music:
            raise RuntimeError(f"Missing Apple Music link for {artist} - {album}")
        if not genre_tags:
            raise RuntimeError(f"Missing genre tags for {artist} - {album}")

        albums.append(
            {
                "artist": artist,
                "album": album,
                "genre_tags": genre_tags,
                "score": score,
                "score_type": score_type,
                "apple_music": apple_music,
                "aoty_url": url,
                "source": source,
                "review_count": review_count,
                "source_rank": int(row["source_rank"]),
            }
        )

    albums.sort(
        key=lambda album: (
            -album["score"],
            0 if album["source"] == "must-hear" else 1,
            album["source_rank"],
        )
    )
    return albums


def write_album_data(albums: list[dict[str, Any]]) -> None:
    ALBUM_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALBUM_DATA_PATH.write_text(json.dumps(albums, indent=2) + "\n")


def main() -> int:
    if not MIXTAPE_PATH.exists():
        raise FileNotFoundError(f"Missing mixtape export: {MIXTAPE_PATH}")
    if not APPLE_SCRIPT.exists():
        raise FileNotFoundError(f"Missing Apple Music skill script: {APPLE_SCRIPT}")

    mixtape_rows = load_mixtape_rows()
    frequency, weighted = build_tag_profile(mixtape_rows)
    write_tag_browse(mixtape_rows, frequency, weighted)

    open_browser()
    try:
        albums = collect_albums()
    finally:
        close_browser()

    write_album_data(albums)
    print(f"Wrote {TAG_BROWSE_PATH}")
    print(f"Wrote {ALBUM_DATA_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001
        print(f"Error: {error}", file=sys.stderr)
        raise
