# Static hosting and hourly refresh

Use an existing HTTPS web server with a virtual host. The Python process runs only during a refresh. No MariaDB, container, or always-running application worker is needed.

Keep the source, `.venv`, SQLite cache and session outside the webroot. The only served path should be the `current/` symlink under the publication directory. The following paths and hostname are examples, not existing infrastructure.

Example cron entry for the account that owns the private cache (use absolute paths):

```cron
17 * * * * flock -n /var/lib/hydro/refresh.lock /opt/hydro/.venv/bin/python /opt/hydro/deploy/refresh.py --data-dir /var/lib/hydro/account --publish-dir /var/lib/hydro/snapshots >> /var/lib/hydro/refresh.log 2>&1
```

Provision `/var/lib/hydro` for that service account and authenticate once interactively with `sync.py`. The importer needs writable private files. The web-server account needs read/traverse access only to `snapshots/current/` and its parents, not to `account/`. Monitor refresh exit codes and arrange log rotation. A successful hourly run does not mean Hydro has already released the latest hour.

Add this protected location to an **existing TLS-enabled** Nginx virtual host for your chosen hostname:

```nginx
server_name hydro.example.com;
root /var/lib/hydro/snapshots/current;
index index.html;

auth_basic "Private electricity usage";
auth_basic_user_file /etc/nginx/hydro.htpasswd;

location / {
    try_files $uri $uri/ =404;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

This is a location/server fragment, not a complete TLS configuration. Create the password file locally, keep it outside the served directory, and redirect HTTP to HTTPS. Check the server configuration before reloading it. Verify an unauthenticated request to both `/` and `/data.json` receives `401`, and an authenticated request can load the graph. Protect consumption snapshots as private data.

`refresh.py` uses sibling directories and an atomic symlink replacement on the same filesystem. Do not replace `current` with a real directory. Use `--skip-sync` with a synthetic cache to test your publication path before enabling a timer. Session expiry leaves the last complete snapshot available; perform a new interactive sign-in to resume updates.
