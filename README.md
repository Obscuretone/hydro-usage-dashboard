# Hydro usage dashboard

A small, self-hosted Hydro-Québec dashboard: one scrollable graph of hourly electricity usage and optional current weather estimates. Includes 7-day, 30-day and full-history views, missing-data gaps, and statistics for the visible readings.

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

## Optional current outdoor weather

Create a private `weather-config.json` in the refresh data directory (excluded from Git), containing `latitude`, `longitude` and a city-level `label`. City coordinates are sufficient; no exact address is needed. The weather request goes to Open-Meteo. Snapshots include the city label and temperature timeseries, but exclude coordinates.

```json
{"latitude": 40.0, "longitude": -70.0, "label": "Example city"}
```

Normal refresh collects weather as well as energy. For a separate 15-minute weather schedule, use the same command with `--weather-only`; it never contacts Hydro or advances the energy sync timestamp. Both modes serialize publication using the same file lock. `--publish-only` reads existing caches without network requests. See [deployment notes](deploy/README.md).

Open-Meteo current conditions are model estimates at 15-minute intervals; historical hourly values are also model data. The current estimate's timestamp is shown independently of retrieval time. Weather outages retain cached readings with an overdue warning. History starts with up to 92 past days, accumulates thereafter, and retains up to 370 days; future hourly forecasts are excluded. Attribution: [Open-Meteo](https://open-meteo.com/) ([API documentation](https://open-meteo.com/en/docs)).

## Reading the graph

- Usage is delayed hourly energy in **kWh**, not per-second power. It cannot identify an appliance by itself.
- The dotted orange line shows hourly weather estimates from Open-Meteo, with a separate current-temperature timestamp. Hydro's daily mean is omitted from the graph. Weather estimates are not indoor or on-site sensor readings.
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
