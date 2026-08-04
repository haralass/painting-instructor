# Sharing Painting Instructor with friends

Everything in the repo is ready. What is left needs your Cloudflare account,
so only you can do it. Budget 20 minutes, once.

The shape of it: your Mac keeps running the app on `localhost`, a Cloudflare
Tunnel gives it a public HTTPS address without opening a port on your router,
and Cloudflare Access puts a password in front of that address so only your
friends get in. Free, no monthly cost, no server to rent.

**The trade:** your Mac has to be awake and online for anyone to use it. When
you close the lid, the site is down. That is the whole price.

---

## Before you start

You need a domain name. If you do not have one, Cloudflare sells them at cost
(~€10/year) — that is the only money involved, and you can skip it entirely by
using a free `trycloudflare.com` URL (see [Quick test](#quick-test-no-domain-no-account)
at the bottom) for a one-off demo.

```bash
brew install cloudflared
```

---

## 1. Cloudflare account and domain

1. Sign up at <https://dash.cloudflare.com/sign-up>.
2. Add your domain: **Websites → Add a site**, enter it, choose the **Free**
   plan.
3. Cloudflare gives you two nameservers. Set them at your domain registrar
   (where you bought the domain), replacing the existing ones.
4. Wait for the dashboard to show your domain as **Active**. Usually minutes,
   occasionally a few hours.

## 2. Log cloudflared in

```bash
cloudflared tunnel login
```

A browser opens. Pick your domain and authorise. This writes a certificate to
`~/.cloudflared/cert.pem`.

## 3. Create the tunnel

```bash
cloudflared tunnel create painting-instructor
```

It prints a **tunnel UUID** and writes credentials to
`~/.cloudflared/<UUID>.json`. Keep that UUID — the next step needs it.

## 4. Point two hostnames at the tunnel

Pick the hostname you want, e.g. `paint.yourdomain.com`. The frontend and the
API each need one, because the browser calls the API directly:

```bash
cloudflared tunnel route dns painting-instructor paint.yourdomain.com
cloudflared tunnel route dns painting-instructor api.paint.yourdomain.com
```

## 5. Fill in the config

Edit [`deploy/cloudflared/config.yml`](../deploy/cloudflared/config.yml) and
replace the two placeholders:

- `<TUNNEL-UUID>` → the UUID from step 3 (appears twice)
- `<YOUR-DOMAIN>` → `paint.yourdomain.com` (appears twice)

Then create `deploy/cloudflared/.env`:

```bash
PUBLIC_DOMAIN=paint.yourdomain.com
TUNNEL_NAME=painting-instructor
```

> `.env` and any `*.json` credentials in `deploy/cloudflared/` are gitignored.
> Never commit them.

## 6. Lock it down

**This is the step that keeps strangers out. Do not skip it.** Until you do,
anyone who guesses the URL can use your Mac's CPU.

> **One thing to know first:** Cloudflare Access has no "shared password"
> option. On the free plan its browser-facing login methods are a one-time
> code emailed to the visitor, or a social login (Google/GitHub). A single
> password everyone shares is not something Access offers — so the closest
> equivalent, and what these steps set up, is a short allow-list of your
> friends' email addresses. It is free for up to 50 users, it is fewer steps
> than a password, and you can remove one friend without telling the others
> anything. If you specifically want a literal shared password, see
> [Shared password instead](#shared-password-instead) below.

In the Cloudflare dashboard:

1. **Zero Trust** (left sidebar) → if prompted, choose the **Free** plan
   (50 users, no card required).
2. **Access → Applications → Add an application → Self-hosted**.
3. Application name: `Painting Instructor`.
   Session duration: `1 month` — so friends log in once, not every visit.
4. Add **two** public hostnames to the same application:
   - `paint.yourdomain.com`
   - `api.paint.yourdomain.com`

   Both. If you protect only the frontend, the API is still wide open and
   anyone can POST jobs to it.
5. **Next → Add policy**:
   - Policy name: `Friends`
   - Action: **Allow**
   - Include → **Emails** → add your own address and each friend's.
6. Save.

On their first visit each friend enters their email, Cloudflare sends a
6-digit code, and they are in for a month.

### Shared password instead

If you would rather hand out one password, Access cannot do it, but a
Cloudflare Worker in front of the app can — HTTP Basic Auth, still free:

1. **Workers & Pages → Create → Worker**, name it `paint-gate`.
2. Replace the code with:

   ```js
   const USER = "friends";
   const PASS = "pick-something-long";

   export default {
     async fetch(request, env, ctx) {
       const auth = request.headers.get("Authorization") || "";
       const expected = "Basic " + btoa(`${USER}:${PASS}`);
       if (auth !== expected) {
         return new Response("Authentication required", {
           status: 401,
           headers: { "WWW-Authenticate": 'Basic realm="Painting Instructor"' },
         });
       }
       return fetch(request);
     },
   };
   ```

3. Deploy, then **Settings → Domains & Routes → Add route** for both
   `paint.yourdomain.com/*` and `api.paint.yourdomain.com/*`.

Weaker than step 6 proper (one password for everyone, no way to revoke one
person, and the browser caches it), but it is genuinely one shared password.

## 7. Go live

```bash
./scripts/share.sh
```

It checks Redis, cloudflared and the tunnel, starts the API, the Celery
worker, a production build of the frontend, and the tunnel — then prints your
URL. Stop everything with `Ctrl+C`.

Send your friends `https://paint.yourdomain.com`. First visit, they enter
their email and the code Cloudflare sends them.

---

## Keeping the Mac awake

The site is up only while the Mac is on and this script is running.

```bash
# Stop it sleeping while the lid is open
sudo pmset -a disablesleep 1     # undo with: sudo pmset -a disablesleep 0
```

Also uncheck **System Settings → Displays → Prevent automatic sleeping…** as
you prefer. If you want it to survive a lid close, keep it plugged in and use
`caffeinate`:

```bash
caffeinate -s ./scripts/share.sh
```

## Your own projects

Projects are scoped per browser, using an id in `localStorage`. Anything you
made before this change has no owner and is therefore invisible to everyone —
deliberately, so sharing the box cannot expose your old work.

To adopt them, get your id from the browser console on the app:

```js
localStorage.getItem("painter_user_id")
```

Then:

```bash
.venv/bin/python scripts/claim_projects.py --user-id <that-uuid> --dry-run
.venv/bin/python scripts/claim_projects.py --user-id <that-uuid>
```

Each friend automatically gets their own id on first visit — they see only
their own paintings and critiques. This is separation, not authentication;
the actual lock on the door is the Access policy from step 6.

## Limits your friends will hit

Configurable as environment variables in `deploy/cloudflared/.env`:

| Variable | Default | What it does |
| --- | --- | --- |
| `MAX_UPLOAD_MB` | `25` | Largest photo accepted |
| `RATE_LIMIT_JOBS_PER_HOUR` | `20` | New lessons per IP per hour |
| `RATE_LIMIT_CRITIQUES_PER_HOUR` | `120` | Critiques per IP per hour |

One painting is analysed at a time. Someone who uploads while another lesson
is running sees *"you are number 2 in the queue"*, not a stuck spinner.

---

## Quick test (no domain, no account)

To show someone the app for ten minutes without any of the above:

```bash
./scripts/dev.sh                      # terminal 1
cloudflared tunnel --url http://localhost:3000   # terminal 2
```

It prints a random `https://<words>.trycloudflare.com` URL. **There is no
password on it** — anyone with the link gets in, so treat it as disposable and
kill it when you are done. The API will not be reachable from that URL either,
so the app will load but not analyse anything. It is a demo of the front page,
nothing more.

---

## When something is wrong

**Friends see a Cloudflare error page, not the app.**
`./scripts/share.sh` is not running, or the Mac is asleep.

**The app loads but every image is broken and nothing analyses.**
The API hostname is not reachable. Check you added `api.` in step 4 *and*
included it in the Access application in step 6 — and that `NEXT_PUBLIC_API_URL`
matches it (the script sets this for you).

**"Waiting to start" forever.**
The Celery worker died. Check the terminal running `share.sh`. Job status
lives in Redis, so a job queued before a restart stays queued forever — start
a fresh one.

**Local development broke after going live.**
It should not: `CORS_ORIGINS` adds the public domain to `localhost:3000`
rather than replacing it, and there is a test pinning that
(`tests/test_cors.py`). If localhost is genuinely broken, that is a bug worth
reporting.
