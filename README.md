# Claude Token Tracker

A lightweight macOS menu bar app that shows your remaining Minimax API quota at a glance.

## How it works

The app makes a minimal API call to Minimax and reads the rate-limit headers
(`X-RateLimit-Remaining`, `X-RateLimit-Limit`, `X-RateLimit-Reset`) returned in
every response. It refreshes automatically on a configurable interval.

## Requirements

- macOS (Catalina 10.15 or later)
- Python 3.8+

## Setup

```bash
# 1. Install dependencies (one-time)
pip3 install -r requirements.txt

# 2. Launch the menu bar app
python3 app.py
```

The app appears in your menu bar as **⚡ —**. Click it to open the menu, then go
to **Settings…** to enter your API key.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| API Key | _(empty)_ | Your Minimax API key |
| Region | Global | `Global` (`api.minimax.io`) or `China` (`api.minimaxi.com`) |
| Refresh | 5 min | How often to auto-refresh |

Config is stored at `~/.minimax-tracker.json` (not committed to git).

## Menu bar display

```
⚡ 4,523 rem
─────────────────
Remaining:   4,523
Limit:       5,000
Resets:      in 23 min

Last updated: 2:14 PM
Refresh Now
─────────────────
Settings…
Quit
```

## Auto-start on login (optional)

Add a Login Item in **System Settings → General → Login Items** pointing to a
small shell script that runs `python3 /path/to/MinimaxCalculator/app.py`.
