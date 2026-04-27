# mkrss

Make RSS feeds from any webpage. A self-hosted alternative to rsseverything.com.

Lives at <https://mkrss.local>.

## How it works

Add a source URL, define an extraction rule (CSS selectors, or rsseverything-style `{%}`/`{*}` template), and mkrss republishes matching items as a public RSS feed you can paste into Inoreader / Feedbin / your reader of choice.

- **CSS mode** (recommended): one row per field — title, link, description, date, etc.
- **Template mode**: paste the same `{%}`/`{*}` pattern you already use on rsseverything.
- **Browser render mode**: opt-in Playwright (Chromium) for JS-rendered SPAs.
- Feeds refresh every N minutes (per-feed, default 30) via APScheduler in-process.

## Local dev

```bash
uv sync
uv run playwright install chromium

export EDITOR_PASSWORD=test
export SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export BASE_URL=http://localhost:8000
export DB_PATH=data/mkrss.sqlite3

uv run python scripts/seed.py            # optional: insert AISI Blog example
uv run uvicorn mkrss.main:app --reload
```

Open <http://localhost:8000>, log in with `test`, edit the seeded feed and click **test extraction** to iterate on selectors.

## Tests

```bash
uv run pytest -q
```

## Deploy (Dokku)

```bash
dokku apps:create mkrss
dokku storage:ensure-directory mkrss
dokku storage:mount mkrss /var/lib/dokku/data/storage/mkrss:/app/data
dokku domains:set mkrss mkrss.local
dokku ports:set mkrss http:80:8000
dokku config:set mkrss \
  BASE_URL=https://mkrss.local \
  EDITOR_PASSWORD='<choose one>' \
  SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# add deploy key, push, then:
dokku letsencrypt:enable mkrss
```

DNS: point `mkrss.local` (CNAME or A) at the Dokku host before enabling Let's Encrypt.

## CI / GitHub Actions

`.github/workflows/ci.yml` lints with ruff, runs pytest, and on push to `main` deploys to Dokku via `ssh://dokku@*** The repo needs a `DOKKU_SSH_KEY` secret containing a private key authorised on the Dokku host (`dokku ssh-keys:add github-actions-mkrss <pubkey>`).

## Environment variables

| Name | Required | Notes |
|---|---|---|
| `EDITOR_PASSWORD` | yes for editor | Single password for the editor; if unset, editor returns 404 (public XML still serves). |
| `SESSION_SECRET` | yes | 32+ bytes, used to sign session cookies. |
| `BASE_URL` | yes | e.g. `https://mkrss.local`. Used for the RSS `self` link. |
| `DB_PATH` | no | Defaults to `data/mkrss.sqlite3` (use `/app/data/mkrss.sqlite3` on Dokku). |
