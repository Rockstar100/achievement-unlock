# Staging — client demo

## Live on Render (one click)

**[Deploy to Render →](https://render.com/deploy?repo=https://github.com/Tervigon-Collective/pet-trend-intelligence)**

You need a Render account linked to GitHub with access to **Tervigon-Collective**.

After deploy completes (~5 min):

| | |
|--|--|
| **URL** | `https://pet-trend-dashboard.onrender.com` (check Render dashboard for exact URL) |
| **Access** | Open URL directly — no login |

### What's included

- Full dashboard (India gold + Global watch)
- 1 GB persistent disk for pipeline data
- Daily auto-refresh at 02:30 UTC

### Manual refresh (Render Shell)

```bash
python scripts/run_render_pipeline.py
```

---

## Private GitHub

Repo: **Tervigon-Collective/pet-trend-intelligence** (private)

## Run locally

```bash
pip install -r requirements.txt
python scripts/serve_dashboard.py
```

Open http://127.0.0.1:8765
