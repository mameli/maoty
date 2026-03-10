# Maoty Weekly Album Update Guide

Use this workflow when refreshing the Maoty album list and homepage.

This process is intended to run every Friday.

## Goal

Update the website with the latest Album of the Year picks, keep the newest qualifying albums at the top of the site list, and regenerate the supporting outputs used by the homepage.

## Source pages

- Must Hear: `https://www.albumoftheyear.org/must-hear/`
- New Releases: `https://www.albumoftheyear.org/releases/`

## Browser requirements

- Use `playwright-cli` with the named session `aoty`.
- Use a persistent Chromium profile stored at `.playwright/aoty-profile`.
- Reuse the same signed-in session if Cloudflare has already been passed.
- If the `aoty` session is already open, attach to it instead of opening a fresh browser.
- Read the live DOM from the loaded page. Do not rely on search snippets.

Open or restore the browser with:

```bash
playwright-cli -s aoty open about:blank --headed --persistent --profile .playwright/aoty-profile
```

Sign in manually only when the saved profile is no longer authenticated.

## Friday collection rules

### Must Hear

- Take exactly the first 5 albums in page order.
- Do not filter before taking the first 5.
- Use the row score shown on the page:
  - use `critic score` if present
  - otherwise use `user score`

### New Releases

- Use only the currently loaded first page.
- Keep only rows with:
  - `critic score >= 80`
  - `critic review count > 5`
- Ignore releases that only show a user score.
- Use the critic score and critic review count from the row.

## Album enrichment rules

For every selected album, open the album page and collect:

- `artist`
- `album`
- `genre_tags`
- `score`
- `score_type`
- `review_count`
- `apple_music`
- `aoty_url`
- `source`
- `source_rank`

Album page rules:

- Apple Music link:
  - use the first link matching `music.apple.com` or `geo.music.apple.com`
- Genre tags:
  - use the top genre links in the main metadata block
  - selector pattern: `a[href*="/genre/"]`
  - ignore footer or sidebar genre links
- If the page title is `Just a moment...`, retry once in the same session after a short wait.

## Apple Music fallback

If the album page has no Apple Music link, use the local skill script:

```bash
python3 /Users/filippomameli/.codex/skills/apple-music-album-linker/scripts/find_apple_music_album.py --artist "ARTIST" --album "ALBUM" --json
```

Fallback rules:

- accept the result automatically when `match_quality` is `exact`
- if `match_quality` is `likely`, verify artist and album names before using the URL
- do not invent a link if the lookup fails

## Mixtape tag browse output

The mixtape tag extraction is a one-time ingestion and is already in place.

Use these existing files as the reference taste input:

- `output/mameli_mixtape_first50_artists_with_tags.json`
- `output/mameli_mixtape_tags_browse.md`

Weekly Friday album updates must reuse the existing mixtape tag data.
Do not re-scrape or rebuild the mixtape tag browse output unless the source Last.fm export itself is intentionally refreshed.

The existing tag browse file is tag-only and contains:

- total artists processed
- top tags by artist frequency
- top tags by scrobble-weighted preference

## Generated site data

The website album dataset lives at:

- `src/data/album-list.json`

Each album entry must contain:

- `artist`
- `album`
- `genre_tags`
- `score`
- `score_type`
- `apple_music`
- `aoty_url`
- `source`
- `review_count`
- `taste_label`
- `source_rank`

## Taste label rules

The taste label is editorial and must not be computed by script.

After scraping and enriching the albums, assign exactly one of these labels to each album by prompt-based judgment using the existing mixtape tag ingestion as taste context:

- `It's a match`
- `Just for you`
- `Maybe you'll like it`

Meaning:

- `It's a match`: the album is strongly aligned with the recurring favorite genres and overall taste profile
- `Just for you`: the album is a good match, even if not the clearest genre overlap
- `Maybe you'll like it`: the album is adjacent, experimental, or less aligned by genre but still plausibly interesting

Do not invent extra labels.
Do not derive this label from a numeric formula.
If an album already exists in `src/data/album-list.json`, preserve its existing `taste_label` unless there is a clear reason to revise it.

## Ordering rule for weekly updates

This refresh is cumulative.

- Keep the existing albums already present in `src/data/album-list.json`.
- Add newly scraped albums at the top of the list.
- Do not duplicate an album already present in the file.
- Deduplicate by `aoty_url`.
- Preserve the existing relative order of older albums already in the file.
- Within the newly scraped batch, keep this order:
  - qualifying New Releases first
  - then Must Hear
  - within each source, preserve source page order

If a scraped album already exists in `src/data/album-list.json`, update its fields in place and keep it in the new top batch for that Friday.

## Homepage update

The homepage reads from:

- `src/pages/index.astro`

The album cards on the homepage must show:

- artist
- album
- first 3 genre tags
- score
- taste label
- Apple Music link
- source label

Presentation rules:

- keep the layout minimal
- do not show any numeric taste score
- do not render the score inside a button or badge-shaped element
- keep cards visually consistent when titles wrap to one or two lines

## Commands

Primary refresh command:

```bash
npm run albums
```

This command must:

- reuse the `aoty` Playwright session and `.playwright/aoty-profile`
- scrape the current Friday album batch from AOTY
- enrich each album page with Apple Music and genre tags
- update `src/data/album-list.json`

Do not treat the mixtape tag browse output as part of the weekly refresh.

After running `npm run albums`, manually review any newly added albums and fill in `taste_label` before rebuilding the site if the field is missing.

After regenerating data, rebuild the site:

```bash
npm run build
```

## Validation checklist

Before considering the update complete, confirm:

- Must Hear contributed exactly 5 albums
- every New Releases album has `critic score >= 80`
- every New Releases album has `review_count > 5`
- every album has a non-empty Apple Music link
- every album has at least one main metadata genre tag
- every album has one valid `taste_label`
- newly scraped albums were inserted at the top of `src/data/album-list.json`
- no album is duplicated by `aoty_url`
- the homepage builds successfully

## Notes for future automation

If this workflow is automated later, the automation should run every Friday in this workspace and execute:

1. `npm run albums`
2. `npm run build`

The automation output should report:

- how many albums were scraped from Must Hear
- how many albums qualified from New Releases
- how many albums were inserted at the top
- whether any Apple Music fallback lookups were needed
- whether any new albums still needed a manual `taste_label`
- whether the build passed

The automation should reuse the existing mixtape tag ingestion and must not refresh the Last.fm tag export unless that becomes a separate explicit task.
