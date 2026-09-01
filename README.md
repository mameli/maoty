# maoty

`maoty` is a small Astro site that surfaces albums worth tracking. The homepage is built from generated JSON data and is refreshed from external music sources like Last.fm and Album of the Year.

## What is in this repo

- Astro frontend in `src/pages/index.astro`
- Generated album dataset in `src/data/album-list.json`
- Album aggregation script in `scripts/build_album_data.py`
- Last.fm library scraper in `scripts/scrape_lastfm_library.py`

## Local development

Install dependencies with Bun:

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

The site reads album entries from `src/data/album-list.json`.

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

- `python3` with the `websocket-client` package (`python3 -m pip install --user websocket-client`)
- the dedicated Hermes Chrome profile running with remote debugging (CDP endpoint `http://127.0.0.1:9222`, LaunchAgent `com.hermes.chrome-debug-default`)
- the Apple Music helper script at `$HOME/.codex/skills/apple-music-album-linker/scripts/find_apple_music_album.py`
- the Last.fm export file at `output/mameli_mixtape_first50_artists_with_tags.json`

If any of those are missing, `scripts/build_album_data.py` will fail early.

### AOTY scraping lane (direct CDP)

`scripts/build_album_data.py` drives AOTY through `scripts/aoty_cdp.py`, which
speaks the Chrome DevTools Protocol directly — no playwright, no playwright-cli,
no separate browser profile in this repo.

- Chrome user-data-dir: `~/.hermes/chrome-debug-default` (dedicated Hermes profile)
- CDP endpoint: `http://127.0.0.1:9222`
- LaunchAgent label: `com.hermes.chrome-debug-default`
- The AOTY login (rememberMe cookie) and any Cloudflare clearance live in that Chrome profile.

`scripts/aoty_cdp.py` opens its own tab via `/json/new` (PUT), attaches a
session, navigates, and evaluates the extraction JS via `Runtime.evaluate`.
When the run finishes, that tab is closed again. If the CDP endpoint is
unreachable, the helper restarts the LaunchAgent with
`launchctl kickstart -k gui/$(id -u)/com.hermes.chrome-debug-default` and polls
`/json/version` for readiness.

First-run flow (already done on this machine):

1. Make sure the dedicated Chrome is running (LaunchAgent above; the endpoint is
   reachable when `curl http://127.0.0.1:9222/json/version` answers).
2. Log into Album of the Year once, manually, in that visible Chrome window
   (cookie persistence happens in the profile itself).
3. Run `bun run albums`.

Notes:

- Do not launch a separate persistent Playwright profile for AOTY; the old
  `.playwright/aoty-profile` is deprecated and must not be recreated.
- If Album of the Year starts returning `Just a moment...`, refresh that site in
  the dedicated Chrome window manually (passing the challenge updates the
  profile's clearance cookie) before rerunning the build.

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

The scraper writes both CSV and JSON outputs to the `output/` directory.

## Troubleshooting

- If the album build hangs or fails to attach, check that the dedicated Chrome CDP endpoint answers: `curl http://127.0.0.1:9222/json/version`. If not, restart it with `launchctl kickstart -k gui/$(id -u)/com.hermes.chrome-debug-default`.
- Stale album data can be fixed by deleting `src/data/album-list.json` and rerunning `bun run albums`.
