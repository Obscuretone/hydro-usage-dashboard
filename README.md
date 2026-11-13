# Hydro usage dashboard

A small, self-hosted Hydro-Québec electricity dashboard: one scrollable graph of hourly consumption, with outside daily mean temperature alongside it. Includes 7-day, 30-day and full-history views, missing-data gaps, and statistics for the visible readings.

The browser serves static HTML, CSS, JavaScript and a generated JSON snapshot. An hourly one-shot Python importer refreshes a local SQLite cache and publishes a new snapshot. No database server, container, persistent Python web process, or JavaScript build step is required.

This repository contains source and deterministic synthetic test fixtures. It excludes account credentials, saved authentication sessions, household readings, generated snapshots, and private deployment configuration.

## Try it with synthetic data

Requires Python 3.12+ and a browser. Node.js is optional for frontend tests.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python make_demo.py
python -m http.server 8000 --bind 127.0.0.1 --directory site
```

Open <http://127.0.0.1:8000>. The generated demo represents an invented household; it does not connect to Hydro. Both `data/` and `site/` are ignored by Git.

## Connect your own account

```sh
python sync.py --data-dir data/account --days 90
python deploy/build_snapshot.py \
  --db data/account/hydro.sqlite \
  --assets deploy/assets \
  --out site
python -m http.server 8000 --bind 127.0.0.1 --directory site
```

The importer prompts for your login email and password, then an email MFA code if required. The password is not stored. A reusable authenticated session is stored in `data/account/session.json` with owner-only permissions; treat that file like a password. The SQLite cache is also owner-only. Neither belongs in Git or a webroot. Use a separate data directory for each account. Multiple contracts require an interactive selection; unattended refresh is intended for a single-contract account.

For scheduled refresh after the first interactive login:

```sh
python deploy/refresh.py \
  --data-dir data/account \
  --publish-dir generated
```

Serve only `generated/current/`. The helper fetches the most recent three completed days, updates existing readings, and atomically switches the static snapshot. It retains three snapshots and leaves the current one intact if sync or export fails. `--skip-sync` builds from an existing cache. Sessions can expire or require MFA again; rerun `sync.py` interactively when that happens.

For remote use, put the static directory behind your existing HTTPS virtual host and authentication. The generated `data.json` contains personal consumption and billing metadata even though it excludes login credentials and contract identifiers. Protect **every file**, including `data.json`, with the same access controls. Do not enable GitHub Pages for real account data. See [deployment notes](deploy/README.md).

## What the graph means

- Usage is energy consumed during each hour, in **kWh**, with delayed readings. It is not a per-second power monitor and cannot identify an appliance by itself.
- The amber line is Hydro's **daily mean outside temperature**, repeated across that day. It is not hourly weather or the temperature in your basement.
- Labels use Toronto local time, regardless of the viewer's timezone. Missing usage or temperature is left empty; a valid zero is preserved.
- The upstream hourly response has unqualified local hour labels. The importer deliberately skips daylight-saving transition days rather than guessing repeated or missing hours. The current graph uses local hour labels and is intended for that importer, not for displaying both folds of an offset-aware CSV import.
- Source quality flags are preserved in the cache and snapshot. A reading is not proof that a day is complete or that Hydro has finalized its bill.
- `core.py` retains conservative analysis helpers from the original prototype. The graph does not use its experimental heating estimates or its date-limited 2026–27 ordinary Rate D calculation; these are not an authoritative bill calculator.

The integration uses the community [HydroQC API wrapper](https://github.com/hydroqc/hydroqc). This is an independent project, not an official Hydro-Québec application. Portal/API changes may require adapter updates. Credentials and MFA are entered locally, never through this static dashboard.

## Checks

```sh
pip install -r requirements-dev.txt
python -m pytest -q
node --test test_frontend.cjs
```

Tests cover cache isolation, invalid imports, daylight-saving gaps, synthetic data, mocked authentication and session refresh, temperature history retention, credential exclusion from snapshots, and frontend gap/statistics behavior. Authentication tests are mocked and make no Hydro requests.

## Files

- `core.py`: SQLite storage, validation, parsing and prototype analysis helpers.
- `sync.py`: interactive login and incremental HydroQC import.
- `make_demo.py`: deterministic synthetic cache and static demo generator.
- `deploy/build_snapshot.py`: selected-account cache to static JSON and assets.
- `deploy/refresh.py`: one-shot sync and atomic publication for scheduling.
- `deploy/assets/`: the browser interface and vendored Plotly bundle.

Plotly.js 3.1.0 is vendored under its [MIT license](deploy/assets/plotly.LICENSE); see [third-party notices](THIRD_PARTY_NOTICES.md).
