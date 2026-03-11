# maoty

`maoty` is a small Astro site that surfaces albums worth tracking. The homepage is built from generated JSON data and is intended to be refreshed from external music sources.

## What is in this repo

- Astro frontend in [src/pages/index.astro](/Users/mameli/Projects/maoty/src/pages/index.astro)
- Generated album dataset in [src/data/album-list.json](/Users/mameli/Projects/maoty/src/data/album-list.json)
- Album aggregation script in [scripts/build_album_data.py](/Users/mameli/Projects/maoty/scripts/build_album_data.py)
- Last.fm library scraper in [scripts/scrape_lastfm_library.py](/Users/mameli/Projects/maoty/scripts/scrape_lastfm_library.py)

## Local development

Install dependencies:

```bash
bun install
```

Start the Astro dev server:

```bash
bun run dev
```

Build the production site:

```bash
bun run build
```

Preview the production build:

```bash
bun run preview
```

## Data workflow

The site reads album entries from [src/data/album-list.json](/Users/mameli/Projects/maoty/src/data/album-list.json).

To refresh that file:

```bash
bun run albums
```

`scripts/build_album_data.py` currently does all of the following:

- reads the Last.fm export at `output/mameli_mixtape_first50_artists_with_tags.json`
- derives a tag profile summary and writes `output/mameli_mixtape_tags_browse.md`
- opens Album of the Year pages, collects album metadata, and merges the result into `src/data/album-list.json`

## External prerequisites for `bun run albums`

The album build is not fully self-contained. It expects:

- `python3`
- `playwright-cli` available on `PATH`
- a usable Playwright session/profile for Album of the Year scraping
- the Apple Music helper script at `/Users/filippomameli/.codex/skills/apple-music-album-linker/scripts/find_apple_music_album.py`
- the Last.fm export file at `output/mameli_mixtape_first50_artists_with_tags.json`

If any of those are missing, `scripts/build_album_data.py` will fail early.

## Last.fm scraper

Use the standalone scraper to create or refresh the Last.fm export:

```bash
python3 scripts/scrape_lastfm_library.py \
  "https://www.last.fm/user/<user>/library/artists" \
  --output-base output/lastfm_library_artists_with_tags
```

Useful flags:

- `--workers` controls concurrent artist tag requests
- `--max-pages` limits how many library pages are scraped
- `--max-artists` caps the total number of artists written

The scraper writes both CSV and JSON outputs.
