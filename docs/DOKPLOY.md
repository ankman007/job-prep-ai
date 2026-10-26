# Deploying on Dokploy

This guide deploys the full stack as a single Dokploy **Compose** application using `docker-compose.dokploy.yml`. The stack is FastAPI, the Celery worker, Next.js, Postgres, Redis and nginx in front. It is set up the same way as `ecommerce-store` on the same server, at **https://job-prep-ai.ankit-poudel.com.np**.

```
Cloudflare (HTTPS) -> Traefik (Dokploy) -> nginx :80 -+-> /       -> frontend :3000 (Next.js)
                                                      +-> /api/*  -> backend  :8000 (FastAPI, /api stripped)
                                       backend -> Postgres, Redis <- worker (Celery, calls Gemini)
```

The frontend is built with `NEXT_PUBLIC_API_BASE_URL=/api`, so the browser calls the API on its own origin. You don't need CORS setup, and you don't need to rebuild the frontend when the domain changes.

## 1. Prerequisites

- The Dokploy server that already runs `ecommerce-store` (`202.79.47.147`). The stack needs roughly 2 GB of RAM, more if RAG is enabled later, because the backend image ships CPU torch.
- This repository reachable by Dokploy (GitHub provider, `ankman007/job-prep-ai`).
- A Gemini API key.

## 2. Create the application

1. In Dokploy, open the project (or create one), then **Create Service → Compose**.
2. **General → Provider:** GitHub, repo `job-prep-ai`, branch `main`.
3. **Compose Path:** `./docker-compose.dokploy.yml`
4. **Environment:** paste `.env.dokploy.example` and replace every `replace-with-...` value (section 4). Dokploy writes them to `.env` next to the compose file.

Don't add anything under **Advanced → Ports**. Traefik already listens on 80/443.

## 3. Domain

The Cloudflare DNS record already exists: `A job-prep-ai → 202.79.47.147`, **Proxied**.

1. **Cloudflare → SSL/TLS → Overview:** **Full (strict)** (zone-wide, already set if ecommerce-store works).
2. **Dokploy → Domains → Create Domain:**
   - Host `job-prep-ai.ankit-poudel.com.np`
   - Service **`nginx`**, container port **`80`**, path `/`
   - HTTPS **on**, certificate **Let's Encrypt**

   Use `nginx`, not `frontend` or `backend`: nginx is what puts both on one origin.
3. If the browser shows **Cloudflare error 526** right after adding the domain, Let's Encrypt hasn't issued the certificate yet. Set the DNS record to **DNS only** (grey cloud), wait a couple of minutes, then switch it back to **Proxied**.

**If ecommerce-store is served through the Cloudflare Tunnel** (its `docs/DOKPLOY.md`, section 10), do the same here:
- Delete the `A` record and add a tunnel Public Hostname `job-prep-ai` → HTTP `dokploy-traefik:80`.
- In the Dokploy domain, set HTTPS **off** and certificate **None**.

## 4. Environment values

| Variable | Value |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `GEMINI_API_KEY` | your key from Google AI Studio |
| `POSTGRES_PASSWORD` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` (URL-safe, because it goes into `DATABASE_URL`) |
| `POSTGRES_USER`, `POSTGRES_DB` | keep `jobprep` unless you have a reason not to |
| `CORS_ORIGINS` | `https://job-prep-ai.ankit-poudel.com.np` |

The compose file builds `DATABASE_URL` and `REDIS_URL` itself. If a required variable is missing, the deploy stops with `set ... in the Environment tab`.

## 5. Deploy

Click **Deploy**. Dokploy builds the three images and starts the stack:
- **backend:** about 2-3 GB, because of torch.
- **frontend:** Next.js standalone.
- **nginx:** proxy config only.

nginx starts only when the backend's `/health/` and the frontend both respond. The backend creates the database tables on its first start.

Check it:

```bash
curl https://job-prep-ai.ankit-poudel.com.np/api/health/   # {"status":"ok"}
```

Then sign up in the browser and generate a cheatsheet. Generation runs in the **worker**, so if it hangs, look at the worker logs.

| Symptom | Where to look / fix |
|---|---|
| Deploy fails with `container ...-backend-1 is unhealthy` | **Logs → backend**. `DATABASE_URL is not set` / `SECRET_KEY` errors mean a missing Environment value. |
| `password authentication failed for user` | Postgres kept the password from the **first** deploy. **No real users yet:** add `DB_VOLUME_VERSION=2` (one higher than before; the default is 1) and redeploy for a fresh database. **Real users:** put the original password back, or change it in the db container terminal: `psql -U jobprep -d jobprep -c "ALTER USER jobprep PASSWORD '<new>';"` |
| Generation never finishes / task fails | **Logs → worker**. A Gemini error usually means a wrong `GEMINI_API_KEY` or quota. |
| 413 on upload | The resume is over 10 MB (`client_max_body_size` in `deploy/nginx/default.conf`). |
| Cloudflare 522 | The server isn't reachable on 80/443. See ecommerce-store `docs/DOKPLOY.md` section 10 (Cloudflare Tunnel). |

## 6. Data and backups

Postgres and Redis live in named volumes (`..._pgdata_<DB_VOLUME_VERSION>`, `redis_data`), and redeploys keep them. Set up **Volume Backups** in Dokploy for the Postgres volume. Redis only holds Celery task state, which expires after an hour.

## 7. Not production-hardened yet

These items are tracked in `docs/ROADMAP.md`. Fix them before inviting real users:
- Reset tokens are logged.
- Token lookup scans with bcrypt.
- There is no upload type check or rate limiting.
- There are no migrations (tables come from `create_all`).

The Postgres port is **not** published by this compose file, unlike the local `docker-compose.yml`.

The old `.github/workflows/ping-health.yml` still pings the previous Render deployment every 5 minutes. Dokploy doesn't sleep, so delete that workflow once Render is retired.
