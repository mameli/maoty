# Album of the Year Extraction Guide

Use this workflow when extracting album lists from Album of the Year with Playwright.

## Required output fields

For each album, collect:

- `artist`
- `album`
- `score`
- `score_type`
- `apple_music`
- `genre_tags`
- `aoty_url`

## Browser requirements

- Use `playwright-cli` with a real headed Chromium session.
- Reuse the same browser session if the user has already signed in or passed Cloudflare.
- Prefer reading the live DOM from the loaded page instead of relying on search snippets.

Example:

```bash
playwright-cli open https://www.albumoftheyear.org/ --headed
playwright-cli goto https://www.albumoftheyear.org/must-hear/
playwright-cli snapshot
```

## Must Hear page

Source page:

- `https://www.albumoftheyear.org/must-hear/`

Rules:

- No filter is needed.
- Extract the first albums in page order.
- Use the score shown on the row:
  - if `critic score` is present, use it
  - otherwise use `user score`

## New Releases page

Source page:

- `https://www.albumoftheyear.org/releases/`

Rules:

- Filter to albums with:
  - `critic score >= 80`
  - `review count > 5`
- Ignore albums that only show a user score.
- Use the critic score and critic review count from the release row.

## Album page enrichment

After collecting the row data, open each album page and extract:

- Apple Music link:
  - first matching link with `music.apple.com` or `geo.music.apple.com`
- Genre tags:
  - use the top genre links near the album metadata block
  - selector pattern: `a[href*="/genre/"]`
  - ignore footer/sidebar genre links by keeping only links near the top of the page

Practical Playwright check:

```bash
playwright-cli eval '() => ({
  apple: document.querySelector("a[href*=\"music.apple.com\"], a[href*=\"geo.music.apple.com\"]")?.href || null,
  genres: [...document.querySelectorAll("a[href*=\"/genre/\"]")]
    .map(a => ({ text: a.textContent.trim(), top: a.getBoundingClientRect().top }))
    .filter(x => x.text && x.top > 200 && x.top < 1200)
    .map(x => x.text)
})'
```

## Row extraction notes

- Album rows usually contain:
  - artist link: `a[href*="/artist/"]`
  - album link: `a[href*="/album/"]`
  - score block with either `critic score` or `user score`
- Keep page order.
- Do not deduplicate by artist.
- Deduplicate by album URL if the same card is matched twice during DOM scanning.

## Validation

Before returning results:

- confirm the album page title is not `Just a moment...`
- confirm the Apple Music link is non-empty
- confirm genre tags are taken from the main metadata section, not the footer
- on `new releases`, confirm the critic review count is strictly greater than `5`

## Fallback

If an album page is temporarily blocked:

- retry in the same Playwright session
- if the page still shows Cloudflare, wait briefly and retry once
- only fall back to other lookup methods if the live album page cannot be read

