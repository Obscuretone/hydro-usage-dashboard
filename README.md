# Hydro usage dashboard

A small, self-hosted Hydro-Québec dashboard: one scrollable graph of hourly electricity usage and daily mean outside temperature. Includes 7-day, 30-day and full-history views, missing-data gaps, and statistics for the visible readings.

The browser serves static files. An hourly one-shot Python importer updates MariaDB and atomically publishes a snapshot. It can share an existing database server and HTTPS virtual host; it needs no persistent Python worker or JavaScript build step.

This repository contains source and synthetic fixtures. Credentials, saved sessions, household readings, generated snapshots and private deployment configuration are excluded.

## Try synthetic data

Python 3.12+ is required; MariaDB and a Hydro account are unnecessary for the demo.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python make_demo.py
python -m http.server 8000 --bind 127.0.0.1 --directory site
```

Open <http://127.0.0.1:8000>. The graph labels this invented household as synthetic. The demo refuses to overwrite an account snapshot.

## Connect an account

First provision a dedicated MariaDB schema using [deployment notes](deploy/README.md). Set `HYDRO_DB_NAME`, `HYDRO_DB_USER` and `HYDRO_DB_SOCKET` as needed. Defaults are `hydro_dashboard`, `hydro-dashboard` and `/run/mysqld/mysqld.sock`. Local Unix-socket authentication avoids a database password; alternatively use an owner-only file named by `HYDRO_DB_PASSWORD_FILE`. TCP configuration is intended for local loopback only.

```sh
python sync.py --auth-client mobile --data-dir data/account --days 90
python deploy/refresh.py --data-dir data/account --publish-dir generated --publish-only
python -m http.server 8000 --bind 127.0.0.1 --directory generated/current
```

The importer prompts for login and an initial email verification code if required. It does not store the password. The default mobile client uses a separate owner-only `session-mobile.json`, persists rotated tokens atomically, and checks the saved owner, client and selected contract. Treat this file like a password. Keep it outside the webroot and Git. Use a dedicated schema/data directory per account; export rejects a database containing multiple contracts.

After enrollment, schedule this one-shot command hourly:

```sh
python deploy/refresh.py --data-dir data/account --publish-dir generated
```

Unattended refresh never attempts an interactive login. It returns code 20 when sign-in is required, preserving cached data and showing a warning. Run `sync.py` interactively again to reconnect. The mobile route is intended to avoid the web client's daily email intervention; session revocation and upstream changes remain possible. A successful initial refresh does not establish long-term reliability.

Serve only `generated/current/` behind HTTPS and authentication. Protect **every file**, including `data.json`, which contains private consumption and billing metadata. The NTKA/OIDC reverse-proxy example is in [deployment notes](deploy/README.md). Do not publish account snapshots through GitHub Pages.

## Reading the graph

- Usage is delayed hourly energy in **kWh**, not per-second power. It cannot identify an appliance by itself.
- Outside temperature is Hydro's **daily mean**, repeated across the day, not current weather or indoor temperature. No separate weather feed is enabled.
- Labels use Toronto time. Missing readings remain gaps; valid zeroes are retained.
- Hydro's unqualified local hour labels are ambiguous around daylight-saving changes. The importer skips those transition days rather than guessing.
- Last successful sync is distinct from snapshot generation. Sign-in, failed-refresh, overdue and stale-upstream states are visible.
- Quality flags are retained. Readings need not be finalized billing data.
- Prototype analysis helpers in `core.py`, including date-limited ordinary Rate D estimates, are experimental and are not used by the graph as an authoritative bill calculator.

This independent project uses the community [HydroQC wrapper](https://github.com/hydroqc/hydroqc). It is not an official Hydro-Québec application. Credentials are entered in the local importer, never the static website.

## Checks

```sh
pip install -r requirements-dev.txt
python -m pytest -q
node --test test_frontend.cjs
```

Most tests require no database and make no Hydro requests. Two optional MariaDB integration checks require a separately provisioned disposable schema beginning `hydro_test_`; set `HYDRO_TEST_DATABASE` and the connection variables. They reject other schema names and remove only their own fixture rows.

`core.py` contains parsing, MariaDB cache and analysis; `sync.py` handles account import; `make_demo.py` creates synthetic snapshots; `deploy/` contains schema, export, refresh and browser assets. Plotly.js 3.1.0 is vendored under its [MIT license](deploy/assets/plotly.LICENSE); see [third-party notices](THIRD_PARTY_NOTICES.md).
