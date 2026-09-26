# VinOT portal

Public site of the server: landing page, news and promotions (edited in Sanity), and the player
area (create account with e-mail confirmation, log in, account details, new characters, password
change and reset).

- `app/`: FastAPI + Jinja, no JavaScript build. Pixel art lives in `app/static/px` and is drawn by
  `tools/pixelart.py` (same shield and palette as the Cockpit logo).
- `cms/`: Sanity Studio with the content types (site settings, landing page, posts). Same setup as
  the Manchete CMS.

It shares only the database with the game and the Cockpit. Accounts are written the way Canary
expects (`passwordType = "sha1"`, the e-mail is the login), so the game client logs in with them.
An account only exists in `accounts` after its e-mail is confirmed; pending sign-ups wait in
`portal_tokens` (hashed token, expires in 24 h).

## Running

On the server it is the `portal` service in `docker/docker-compose.yml`, bound to
`127.0.0.1:8091` and published through Cloudflare Tunnel:

```bash
cp portal/portal.env.example docker/portal.env && chmod 600 docker/portal.env   # fill it in
cd docker && docker compose up -d --build portal
```

Tunnel (the VM's cloudflared runs from `/etc/cloudflared/config.yml`): add, above the final 404 rule,

```yaml
  - hostname: vinot.barbosamaria.online
    service: http://127.0.0.1:8091
```

then `cloudflared tunnel route dns <tunnel> vinot.barbosamaria.online` and
`sudo systemctl restart cloudflared`.

Locally: `pip install -r requirements.txt` and
`MYSQL_HOST=127.0.0.1 PORTAL_DEV=1 uvicorn app.main:app --port 8091`. With `PORTAL_DEV=1` and no
SMTP, the confirmation and reset links are shown on the page and written to the log.

## Content (Sanity)

```bash
cd portal/cms && npm install
export SANITY_STUDIO_PROJECT_ID=<id>      # PowerShell: $env:SANITY_STUDIO_PROJECT_ID="<id>"
npx sanity login
npm run seed      # first time only: default settings, landing and a welcome post
npm run deploy    # publishes the Studio at https://vinot.sanity.studio
```

The portal reads published content from Sanity's CDN (no token, cached 60 s). Without
`SANITY_PROJECT_ID` it falls back to the built-in texts in `app/cms.py`.

## Security

Sign-ups start **closed** (`PORTAL_SIGNUPS=closed`). Open or close them instantly, no restart:

```sql
INSERT INTO server_config (config, value) VALUES ('portal_signups', 'open')   -- or 'closed'
  ON DUPLICATE KEY UPDATE value = VALUES(value);
```

Log in, account pages and news keep working while sign-ups are closed. Turn on Turnstile before
opening them on the public address (the portal logs a warning otherwise).

- Signed session cookie (`Secure` when `PORTAL_BASE_URL` is https), `SameSite=Lax`, CSRF token on
  every form, sessions end when the password changes.
- Rate limits: log in 5 failures per e-mail and 10 per IP in 10 min; 5 sign-ups per IP per hour
  and `PORTAL_SIGNUPS_PER_HOUR` overall; e-mail sends 5 per IP per hour. Honeypot field and
  optional Turnstile captcha on sign-up.
- Strict Content-Security-Policy and security headers; the container runs read-only as `nobody`
  with all capabilities dropped.
- Canary stores SHA-1 without salt, which the game requires. The portal compensates with a
  password policy and rate limits; the hash format can only change together with the game.
- Optional least-privilege database user (start the portal once with the normal user first, so
  `portal_tokens` exists):

```sql
CREATE USER 'portal'@'%' IDENTIFIED BY '<senha>';
GRANT SELECT ON `otservbr-global`.* TO 'portal'@'%';
GRANT INSERT ON `otservbr-global`.`accounts` TO 'portal'@'%';
GRANT UPDATE (`password`) ON `otservbr-global`.`accounts` TO 'portal'@'%';
GRANT INSERT ON `otservbr-global`.`players` TO 'portal'@'%';
GRANT INSERT, DELETE, UPDATE ON `otservbr-global`.`portal_tokens` TO 'portal'@'%';
```
