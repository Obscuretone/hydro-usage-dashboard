# Private static hosting and hourly refresh

Use an existing MariaDB server and HTTPS virtual host. Python runs only during refresh; no persistent application worker is needed. All paths, domains and usernames below are examples.

## Database and enrollment

Create a dedicated service account and MariaDB schema. As the database administrator, adapt these example statements to the account running the importer:

```sql
CREATE DATABASE hydro_dashboard CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 'hydro-dashboard'@'localhost' IDENTIFIED VIA unix_socket;
GRANT SELECT, INSERT, UPDATE ON hydro_dashboard.* TO 'hydro-dashboard'@'localhost';
```

Apply `deploy/schema.sql` to that schema as administrator. Run importer and refresh as the matching OS account. Use `HYDRO_DB_NAME`, `HYDRO_DB_USER`, and `HYDRO_DB_SOCKET` for other names. For password authentication, use `HYDRO_DB_PASSWORD_FILE` outside the webroot, readable only by the service account. `HYDRO_DB_HOST`/`HYDRO_DB_PORT` support local loopback TCP; this example does not configure encrypted remote database access.

Keep source, environment, session and refresh status outside the webroot:

```sh
/opt/hydro/.venv/bin/python /opt/hydro/sync.py --auth-client mobile --days 90 --data-dir /var/lib/hydro/account
/opt/hydro/.venv/bin/python /opt/hydro/deploy/refresh.py --data-dir /var/lib/hydro/account --publish-dir /var/lib/hydro/snapshots --publish-only
```

Provision these directories for the service account. Sessions are mode 0600. Exported directories are 0750 and files 0640: grant the web server read/traverse access only to snapshots and their parents, using a shared group or inherited ACL. Never grant it access to `account/` or database credentials. Verify access as the actual web-server user before enabling the virtual host.

Example cron, using a non-overlap lock:

```cron
17 * * * * flock -n /var/lib/hydro/refresh.lock /opt/hydro/.venv/bin/python /opt/hydro/deploy/refresh.py --data-dir /var/lib/hydro/account --publish-dir /var/lib/hydro/snapshots >> /var/lib/hydro/refresh.log 2>&1
```

To refresh configured weather every 15 minutes without contacting Hydro, add:

```cron
*/15 * * * * /opt/hydro/.venv/bin/python /opt/hydro/deploy/refresh.py --data-dir /var/lib/hydro/account --publish-dir /var/lib/hydro/snapshots --weather-only >> /var/lib/hydro/weather.log 2>&1
```

The internal shared lock serializes weather and energy publication. Weather uses a bounded HTTPS request, caches estimates in the private data directory, and adds no persistent worker. A weather outage does not advance its timestamps or prevent energy publication.

Monitor exit status and rotate logs. Snapshot publication uses a same-filesystem atomic symlink switch, retains three snapshots, and preserves the served snapshot if export fails. Keep `current` as a symlink. Failed sync publishes cached readings with its failure state and does not advance the last-success timestamp. Reconnect interactively on exit 20; scheduled jobs never solicit email codes.

## Shared NTKA / OIDC login

Register a dedicated confidential OIDC client in your identity service with exact callback `https://hydro.example.com/oauth2/callback`. Grant only the intended owner access; disable guest grants and public enrollment for this app. Use your existing trusted identity provider; do not put Hydro account credentials in the proxy.

Run OAuth2 Proxy bound only to `127.0.0.1:8797`, with a small systemd memory cap and these illustrative settings:

```toml
provider = "oidc"
oidc_issuer_url = "https://login.example.com"
client_id = "REPLACE_WITH_REGISTERED_CLIENT_ID"
redirect_url = "https://hydro.example.com/oauth2/callback"
http_address = "127.0.0.1:8797"
upstreams = ["static://202"]
scope = "openid profile email"
code_challenge_method = "S256"
cookie_name = "__Host-hydro_identity"
cookie_secure = true
cookie_httponly = true
cookie_samesite = "lax"
cookie_expire = "5m"
reverse_proxy = true
skip_provider_button = true
```

Provide the client secret, random cookie secret, and explicit owner email allowlist through protected files or systemd `LoadCredential`. Use OAuth2 Proxy's `--client-secret-file`, `--cookie-secret-file`, and `--authenticated-emails-file` options. Keep issuer, audience, signature and nonce validation enabled. The provider should issue verified email claims; review claim semantics for passkey-only identities rather than broadly weakening validation. An authenticated provider account alone must not grant access to the dashboard.

Inside an existing TLS-enabled Nginx server:

```nginx
server_name hydro.example.com;
root /var/lib/hydro/snapshots/current;
index index.html;
add_header Cache-Control "no-store" always;
add_header X-Content-Type-Options "nosniff" always;

location = /_hydro_session {
    internal;
    proxy_pass http://127.0.0.1:8797/oauth2/auth;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Authorization "";
    proxy_set_header Host hydro.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Original-URL https://hydro.example.com$request_uri;
}
location ~ ^/oauth2/(start|callback|sign_out)$ {
    proxy_pass http://127.0.0.1:8797;
    proxy_set_header Host hydro.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host hydro.example.com;
    proxy_set_header X-Auth-Request-Redirect https://hydro.example.com/;
}
location = /data.json {
    auth_request /_hydro_session;
    try_files $uri =404;
}
location / {
    auth_request /_hydro_session;
    error_page 401 = @hydro_signin;
    try_files $uri $uri/ =404;
}
location @hydro_signin {
    return 302 /oauth2/start?rd=%2F;
}
```

This is a fragment, not a complete TLS configuration. Redirect HTTP to HTTPS, check Nginx configuration before reload, and keep OAuth2 Proxy inaccessible externally. Verify anonymous `/` redirects to login, `/data.json` returns 401, fake identity headers do not bypass authentication, unentitled users are denied, and the owner callback loads the graph. Consumption files and all assets require the same access control.
