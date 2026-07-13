# Migrate dm-grab-extractor to the Hetzner box

Plug-and-play runbook (DM Dispatch 031). Goal: kill Render free-tier cold
starts and the Render Cloudflare-edge `error code: 502`, and stop paying the
per-request latency of a sleeping instance. The extractor becomes a container
on the Hetzner box, reached only through the existing Cloudflare tunnel.

**Prerequisite:** the tunnel is already up — `cloudflared` installed and the
`n8n-dmlogic` tunnel showing **Active** (roadmap item 1). This shares that
tunnel; it does not create a new one.

## 1. Docker on the box (once)
```
curl -fsSL https://get.docker.com | sh
```

## 2. Get the code + set the token
```
git clone https://github.com/Monodrama311/dm-grab-extractor.git
cd dm-grab-extractor
cp .env.example .env
# edit .env: INTERNAL_TOKEN must EQUAL the dmlogic-web Worker secret
# EXTRACTOR_TOKEN (value relayed to you separately — not stored in this repo).
nano .env
```

## 3. Build + run
```
docker compose up -d --build
# first build compiles the bgutil Node provider — a few minutes.
docker compose ps          # healthy?
curl -s http://127.0.0.1:8000/health
# expect: {"ok":true,"service_version":"5.1", ... "pot_provider_ready":true ...}
```

## 4. Route the tunnel to it
In Cloudflare → Zero Trust → Networks → Tunnels → `n8n-dmlogic` → Public
Hostname → **Add**:
- Subdomain `grab-extractor`, Domain `dmlogic.ca`
- Service `HTTP` → `localhost:8000`

**Do NOT put an interactive Access policy on this hostname.** The caller is the
Worker doing a server-to-server `fetch`, which cannot complete a Google login.
The endpoint stays gated the same way Render was: the `INTERNAL_TOKEN` /
`X-Internal-Token` shared secret. (If you want a second layer, use a Cloudflare
Access **Service Token** and send it from the Worker — optional, later.)
Interactive Access is for the human-facing services (n8n, Uptime Kuma).

Verify token-gating from anywhere:
```
curl -s -o /dev/null -w "%{http_code}\n" https://grab-extractor.dmlogic.ca/extract   # 403 without token
curl -s https://grab-extractor.dmlogic.ca/health                                     # {"ok":true,...}
```

## 5. Point the Worker at the tunnel
In `dmlogic-web/wrangler.jsonc`, change the `EXTRACTOR_URL` var:
```
"EXTRACTOR_URL": "https://grab-extractor.dmlogic.ca"
```
Then `npx wrangler deploy`. Keep Render running as a read-only backup for a
week or two, then delete the Render service.

## 6. Real end-to-end test (no fake lead)
Use the same AB Clinic public film as before:
```
curl -s -X POST https://dmlogic.ca/api/grab \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=WAu69V64gxA"}'
```
`{"ok":true,...,"data":{...formats...}}` → Grab recovers to Live automatically
(the Worker writes a fresh `health:grab` success and status.json flips).

## ⚠️ Honest caveat — this may not fully un-break Grab
Migration definitively removes two Render-specific failures: free-tier cold
start and the Render edge 502. But per DM Dispatch 024, one earlier diagnosis
was that **YouTube's bot-check blocks datacenter egress IPs** — and Hetzner is
also a datacenter IP. If step 6 comes back with a YouTube "confirm you're not a
bot" / no-formats error even though `/health` is green and the token matches,
the remaining fix is a residential/ISP proxy for the extractor's egress — a
separate, later decision. In that case Grab stays honestly **Limited/Offline**;
do not fake it green.
