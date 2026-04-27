# mkrss

> Make RSS feeds from any webpage.

A self-hosted alternative to rsseverything.com. Point it at a page, define an extraction rule, and get a clean RSS feed your reader can subscribe to.

Live instance: <https://mkrss.local>

## Features

- **Two extraction modes**
  - **CSS selectors** — one named row per field (title, link, description, date, ...). Robust against minor markup changes, debuggable in browser devtools.
  - **rsseverything-style template** — paste the same `{%}` / `{*}` pattern you already use, no rewrite needed.
- **Follow item links** — any field can be marked as sourced from the *post page* instead of the listing card, so the feed includes full article bodies, not just the snippet from the index.
- **JS-rendered pages** — opt-in Playwright (Chromium) per feed for SPAs that don't render server-side.
- **Live preview** — HTMX preview pane re-fetches the source and shows what would be captured before you save. Iterate on selectors in seconds.
- **Per-feed refresh interval**, deduped by GUID, last 100 items retained.
- **Public RSS** at `/feeds/{slug}.xml`; password-gated editor for everything else.
- **Single SQLite file** for state. No external services.

## Stack

Python 3.12 · FastAPI · selectolax · feedgen · APScheduler · Playwright · HTMX · SQLite · Dokku

## Local dev

```bash
uv sync
uv run playwright install chromium

export EDITOR_PASSWORD=test
export SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export BASE_URL=http://localhost:8000
export DB_PATH=data/mkrss.sqlite3

uv run python scripts/seed.py            # optional: seed the AISI Blog example feed
uv run uvicorn mkrss.main:app --reload
```

Open <http://localhost:8000>, log in with `test`, edit the seeded feed and click **test extraction** to iterate on selectors.

```bash
uv run pytest -q                         # 22 tests
uvx ruff check .                         # lint
```

## Anatomy of a feed

```yaml
source_url: https://www.aisi.gov.uk/blog
item_selector: div.work-card-wrapper.w-dyn-item
fields:
  - { name: link,        from: item, selector: 'a[href*="/blog/"]',          attribute: href, transform: absolute_url }
  - { name: title,       from: item, selector: '[fs-list-field="title"]' }
  - { name: category,    from: item, selector: '[fs-list-field="category"]' }
  - { name: date,        from: item, selector: '[fs-list-field="date"]',     transform: parse_date }
  - { name: description, from: item, selector: '[fs-list-field="description"]' }
  - { name: body,        from: post, selector: 'article',                    transform: raw_html }
templates:
  title:       "{title}"
  link:        "{link}"
  description: "<p><strong>{category}</strong> &mdash; {date}</p><p>{description:raw}</p><hr>{body:raw}"
```

`from: post` triggers a follow-the-link fetch on each *new* item; existing items are deduped before the post-page hit, so a steady-state refresh costs one HTTP request.

Output templates support both named (`{title}`, `{body:raw}`) and positional (`{%1}`, `{%2}`) placeholders. Suffix any placeholder with `:raw` to skip HTML escaping.

## Deploy (Dokku)

```bash
dokku apps:create mkrss
dokku storage:ensure-directory mkrss
dokku storage:mount mkrss /var/lib/dokku/data/storage/mkrss:/app/data
dokku domains:set mkrss rss.example.com
dokku ports:set mkrss http:80:8000
dokku config:set mkrss \
  BASE_URL=https://rss.example.com \
  EDITOR_PASSWORD='<choose one>' \
  SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# add deploy key, push, then:
dokku letsencrypt:enable mkrss
```

DNS: point `rss.example.com` at the Dokku host before enabling Let's Encrypt.

CI in `.github/workflows/ci.yml` runs ruff, pytest, then deploys on push to `main`. Set repo secret `DOKKU_SSH_KEY` to a private key registered on Dokku via `dokku ssh-keys:add`.

## Environment variables

| Name | Required | Notes |
|---|---|---|
| `EDITOR_PASSWORD` | yes for editor | Single password. If unset, editor returns 404; public XML still serves. |
| `SESSION_SECRET` | yes | 32+ bytes, signs the editor session cookie. |
| `BASE_URL` | yes | e.g. `https://rss.example.com`. Used for the RSS `self` link. |
| `DB_PATH` | no | Defaults to `data/mkrss.sqlite3`. Use `/app/data/mkrss.sqlite3` on Dokku. |

## License

MIT.
