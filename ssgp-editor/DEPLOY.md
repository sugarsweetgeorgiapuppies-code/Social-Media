# Running SSGP Editor "always on, from any computer"

The app has to *run* somewhere (it uses FFmpeg + Python to process video — it
can't be a static GitHub Page). Once it's running on an always-on machine, you
open it from **any** computer's browser and point **n8n** at it.

Everything below uses **Docker**, so there's nothing to install by hand (FFmpeg,
fonts, Python, and all dependencies are bundled). One command brings it up and
keeps it up across reboots and crashes.

---

## Option A — Cheap always-on cloud server (recommended, best for n8n)

A small Linux server (VPS) for ~$6/month (DigitalOcean, Hetzner, Vultr, Linode).
It runs 24/7 and has its own web address.

**1. Create the server:** pick Ubuntu 22.04/24.04, the smallest "shared CPU"
plan is fine to start (2 GB RAM+). You'll get an IP like `203.0.113.10`.

**2. Connect to it** from your Mac's Terminal:
```
ssh root@YOUR_SERVER_IP
```

**3. Paste this once** (installs Docker, gets the app, starts it):
```
curl -fsSL https://get.docker.com | sh
git clone https://github.com/sugarsweetgeorgiapuppies-code/Social-Media.git
cd Social-Media && git checkout claude/ssgp-editor-video-tool-jm5uq7 && cd ssgp-editor
# (optional) enable AI Smart cut:
echo 'ANTHROPIC_API_KEY=sk-ant-your-key-here' > .env
docker compose up -d --build
```
Give it a few minutes the first time (it builds the image). When it's done:

- **Open the app** from any computer: `http://YOUR_SERVER_IP:8080`
- It stays running and **auto-restarts** on reboot (`restart: unless-stopped`).

**4. Update later** (whenever I push improvements):
```
cd ~/Social-Media/ssgp-editor && git pull && docker compose up -d --build
```

**5. Point n8n at it:** in your HTTP Request nodes use
`http://YOUR_SERVER_IP:8080/render` and `http://YOUR_SERVER_IP:8080/render/{{ $json.id }}`
(exactly like the README's n8n section, just with the server address).

> Want a real domain + HTTPS (e.g. `https://editor.yoursite.com`)? Add a
> reverse proxy like Caddy in front — ask me and I'll give you the 6-line config.

---

## Option B — Deploy straight from GitHub (least server work)

Platforms like **Railway** or **Render** build the Dockerfile for you and give
you a URL — no server commands.

1. Create an account, "New Project → Deploy from GitHub repo," pick this repo.
2. Set it to use the **Dockerfile** in `ssgp-editor/` (set root/working dir to
   `ssgp-editor`), branch `claude/ssgp-editor-video-tool-jm5uq7`.
3. Add env var `ANTHROPIC_API_KEY` (optional, for Smart cut).
4. Deploy → you get a public URL to use in the app and in n8n.

Cost scales with usage (roughly $5–20/mo). Easiest to set up; a bit pricier per
render than a fixed VPS. Note: give it a persistent disk for `/app/output` and
the model cache if the platform supports it.

---

## Option C — Keep it on your Mac + a secure public link (free)

Good if you have a computer at the store that stays on and awake. Adds a public
`https://…` link to the app running on your Mac, reachable from anywhere **while
that Mac is on**.

```
brew install cloudflared
# in one Terminal, run the app:
python run.py
# in a second Terminal, expose it:
cloudflared tunnel --url http://localhost:8080
```
Cloudflare prints a public `https://something.trycloudflare.com` URL — use that
in n8n. (For a permanent link instead of a random one, set up a named tunnel —
ask me.)

Downside: it only works while your Mac is on and awake, so for a hands-off n8n
pipeline, Option A is better.

---

## Run it with Docker locally (any computer, no Python setup)

You don't even need the cloud to escape the Python/venv setup — on any machine
with Docker Desktop:
```
git clone https://github.com/sugarsweetgeorgiapuppies-code/Social-Media.git
cd Social-Media && git checkout claude/ssgp-editor-video-tool-jm5uq7 && cd ssgp-editor
docker compose up -d --build
```
Open http://localhost:8080. Stop with `docker compose down`.

---

## Which should you pick?

- **You want it hands-off for n8n, cheapest long-term →** Option A (VPS).
- **You want the least terminal work and don't mind paying a bit more →** Option B.
- **You have an always-on computer and want free →** Option C.

Tell me which one and I'll walk you through it step by step (and wire n8n to it).
