# Maoty Weekly Album Update Guide

Use this workflow when refreshing the Maoty album list and homepage.

This process is intended to run every Friday.

## Goal

Update the website with the latest Album of the Year picks, keep the newest qualifying albums at the top of the site list, and regenerate the supporting outputs used by the homepage.

## Source pages

- Must Hear: `https://www.albumoftheyear.org/must-hear/`
- New Releases: `https://www.albumoftheyear.org/releases/`

## Browser requirements

- Scrape AOTY by driving the dedicated Hermes Chrome profile **directly over
  CDP** via `scripts/aoty_cdp.py`. Do NOT use playwright or playwright-cli.
- Dedicated Chrome profile: `~/.hermes/chrome-debug-default` (profile `Default`).
- CDP endpoint: `http://127.0.0.1:9222`. Make sure the dedicated Chrome is
  running with remote debugging (LaunchAgent `com.hermes.chrome-debug-default`);
  if the CDP endpoint is unreachable, start it with
  `launchctl kickstart -k gui/$(id -u)/com.hermes.chrome-debug-default` and wait
  for `http://127.0.0.1:9222/json/version` to respond. (`scripts/aoty_cdp.py`
  already does this check and kickstart automatically.)
- Readiness is proven by a successful `http://127.0.0.1:9222/json/version`
  response.
- The AOTY login (`rememberMe` cookie) and any Cloudflare clearance live in the
  dedicated Chrome profile itself. Log in manually in that visible Chrome window
  if the session is no longer authenticated.
- `scripts/aoty_cdp.py` opens a dedicated tab for the run, navigates it, and
  evaluates JS via `Runtime.evaluate`; the tab is closed when the run finishes.
- Read the live DOM from the loaded page. Do not rely on search snippets.
- Do NOT launch a separate persistent Playwright profile for AOTY; the old
  `.playwright/aoty-profile` is deprecated and must not be recreated.
- `python3` needs the `websocket-client` package:
  `python3 -m pip install --user websocket-client`.

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
- `cover_url`
- `genre_tags`
- `score`
- `score_type`
- `review_count`
- `apple_music`
- `aoty_url`
- `source`
- `source_rank`

Album page rules:

- Cover art:
  - prefer `meta[property="og:image"]`
  - fallback to `meta[name="twitter:image"]` or the main album image
- Apple Music link:
  - use the first link matching `music.apple.com` or `geo.music.apple.com`
- Genre tags:
  - use the top genre links in the main metadata block
  - selector pattern: `a[href*="/genre/"]`
  - ignore footer or sidebar genre links
  - if AOTY has no genre tags, keep the album with an empty `genre_tags` array, count it in the report, and continue
- If the page title is `Just a moment...`, retry once in the same session after a short wait.

## Apple Music fallback

If the album page has no Apple Music link, use the local skill script:

```bash
python3 "$HOME/.codex/skills/apple-music-album-linker/scripts/find_apple_music_album.py" --artist "ARTIST" --album "ALBUM" --json
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
- `cover_url`
- `genre_tags`
- `score`
- `score_type`
- `apple_music`
- `aoty_url`
- `source`
- `review_count`
- `taste_label`
- `source_rank`

`apple_music` and `genre_tags` are optional when AOTY and the permitted fallback cannot provide them. Record and report their absence, but never block the refresh solely for either field.

## Taste label rules

The taste label is editorial and must not be computed by script.

After scraping and enriching the albums, assign exactly one of these labels to each album by editorial judgment using the existing mixtape tag ingestion as taste context:

- `It's a match`
- `Just for you`
- `Maybe you'll like it`

Base the decision primarily on genre and scene alignment with the mixtape tag profile in `output/mameli_mixtape_tags_browse.md`.

Strong recurring preference signals currently include:

- `indie`
- `indie rock`
- `hip-hop`
- `rap`
- `rnb`
- `singer-songwriter`
- `electronic`
- `pop`
- `neo-soul` as a secondary positive signal

Use the first 3 album genre tags plus general artist fit to decide the label.
Do not label from score alone.
High score does not imply stronger taste fit.

Rubric:

- `It's a match`
  - Use when the album sits clearly inside one or more core lanes from the mixtape profile.
  - Typical examples: indie rock, singer-songwriter, hip-hop, rap, rnb, electronic, neo-soul records that feel directly compatible with the recurring listening taste.
  - This should be reserved for the clearest fits, not just albums that look good or well reviewed.

- `Just for you`
  - Use when the album still feels like a real recommendation for this taste, but the overlap is less direct or more mixed.
  - Good for albums with one strong matching signal plus one or two less central traits.
  - This is the middle label for "likely interesting" albums that are not obvious slam-dunks.

- `Maybe you'll like it`
  - Use when the album is adjacent, exploratory, or harder to map to the core profile.
  - Default here for records driven by peripheral traits such as art pop, psychedelia, experimental detours, niche regional styles, or other tags that are only weakly represented in the mixtape profile.
  - Example: a record tagged `Art Pop`, `Neo-Psychedelia`, and `Hindustani Classical Music` should usually land here unless there is unusually strong outside context for a better fit.

Decision guidance:

- Prefer the stricter label when unsure.
- If only one tag overlaps with the taste profile and the rest are peripheral, avoid `It's a match`.
- If the album feels more "interesting detour" than "natural extension," use `Maybe you'll like it`.
- Use `Just for you` only when the record feels genuinely recommended, not merely plausible.

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

- cover art
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
bun run albums
```

This command must:

- drive the dedicated Hermes Chrome profile directly over CDP
  (`http://127.0.0.1:9222`) via `scripts/aoty_cdp.py`
- scrape the current Friday album batch from AOTY
- enrich each album page with Apple Music and genre tags
- update `src/data/album-list.json`

Do not treat the mixtape tag browse output as part of the weekly refresh.

After running `bun run albums`, review the albums it reports as needing a
`taste_label` and fill the field in before publishing. `bun run albums` also
accepts `--dry-run`, which scrapes and reports without writing
`src/data/album-list.json` — use it to inspect an off-schedule run without
producing churn.

Then publish with the script that owns the deterministic tail:

```bash
scripts/publish.sh
```

It validates every `taste_label` (and rejects duplicate `aoty_url` values),
runs `bun run build`, stages only `src/data/album-list.json`, commits, pushes
with one retry on a transient network failure, and prints a JSON report. Use
`scripts/publish.sh --dry-run` to validate and build without committing.

## Validation checklist

Before considering the update complete, confirm:

- Must Hear contributed exactly 5 albums
- every New Releases album has `critic score >= 80`
- every New Releases album has `review_count > 5`
- missing Apple Music links after fallback are counted and do not block the refresh
- missing genre tags are counted and do not block the refresh
- every album has one valid `taste_label`
- newly scraped albums were inserted at the top of `src/data/album-list.json`
- no album is duplicated by `aoty_url`
- the homepage builds successfully

## Automation

The weekly refresh runs as a scheduled job. The repository owns the
deterministic steps; the scheduled agent owns only editorial judgment and
relaying the report.

Agent workflow:

1. `bun run albums` — scrape, filter, enrich and merge. This preserves
   existing `taste_label` values and leaves `taste_label` null on genuinely
   new albums.
2. Assign one valid `taste_label` to each album the run reports as needing one.
3. `scripts/publish.sh` — validates labels, builds, commits and pushes, and
   emits the report as JSON.

`scripts/publish.sh` replaces the previous prose instructions for staging,
commit messages, push retry and the `ssh -T git@github.com` diagnostic. Those
rules live in the script so a run cannot skip or misreport them.

The refresh re-stamps `batch_date` with today's date and re-ranks the current
top batch, so an off-schedule run produces churn. Inspect with
`bun run albums --dry-run` instead of running the real refresh out of schedule.

Reuse the existing mixtape tag ingestion. Do not refresh the Last.fm tag export
unless that is a separate explicit task.

### Report fields

`bun run albums` prints every count the report needs, so the agent relays them
rather than recomputing them. Batch-scoped keys describe this run's selected
albums; `file_`-prefixed keys describe the whole dataset.

| Key | Meaning |
| --- | --- |
| `must_hear_scraped` | Must Hear albums taken (target: 5) |
| `new_releases_qualified` | New Releases rows passing critic ≥ 80 and review count > 5 |
| `batch_size` | Albums in this Friday batch |
| `batch_new_albums` | Batch albums not previously in the dataset |
| `batch_refreshed_albums` | Batch albums already known and re-dated into the top batch |
| `apple_fallback_lookups` | Apple Music fallback lookups attempted |
| `albums_needing_taste_label` | Batch albums still missing a label |
| `batch_missing_apple_music_links` | Batch albums left without an Apple Music link |
| `batch_missing_genre_tags` | Batch albums left without genre tags |
| `file_missing_apple_music_links` | Whole-dataset albums without an Apple Music link |
| `file_missing_genre_tags` | Whole-dataset albums without genre tags |
| `total_albums` | Dataset size after merge |
| `off_friday` | True when the run did not happen on a Friday |
| `dry_run` | True when nothing was written |

An optional Apple Music link or genre tag gap is reportable, never a blocker. A
blocker in Cloudflare, browser interaction, authentication or git push must be
reported explicitly instead of guessed.
