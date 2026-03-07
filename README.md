# maoty

Small workspace for utility scripts and scrape outputs.

## Last.fm scrape summary

This repo includes a script to scrape a public Last.fm user artist library and fetch the top genre tags shown on each artist page:

- Script: `scripts/scrape_lastfm_library.py`
- Latest export:
  - `output/mameli_mixtape_first50_artists_with_tags.csv`
  - `output/mameli_mixtape_first50_artists_with_tags.json`

The current export contains the first 50 artists from `https://www.last.fm/user/mameli_mixtape/library/artists` plus their Last.fm tags.

## Notes

- Page 1 of the library is publicly accessible.
- Page 2 and beyond redirect to Last.fm login when scraped anonymously, so larger exports require an authenticated session.
- The script supports limiting the scrape with `--max-pages` and `--max-artists`.
