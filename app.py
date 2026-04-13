"""
Minimax Token Tracker — macOS Menu Bar App
Displays remaining API quota from Minimax rate-limit headers.
"""

import json
import os
import threading
from datetime import datetime, timezone

import requests
import rumps

CONFIG_PATH = os.path.expanduser("~/.minimax-tracker.json")

REGIONS = {
    "Global": "https://api.minimax.io",
    "China":  "https://api.minimaxi.com",
}

DEFAULT_CONFIG = {
    "api_key": "",
    "region": "Global",
    "model": "MiniMax-M2.7",
    "refresh_minutes": 5,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            # fill in any missing keys from defaults
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def time_until(reset_ts):
    """Return a human-readable 'in X min' string from a Unix timestamp."""
    try:
        reset_ts = int(reset_ts)
        now = int(datetime.now(timezone.utc).timestamp())
        diff = reset_ts - now
        if diff <= 0:
            return "now"
        if diff < 60:
            return f"in {diff}s"
        return f"in {diff // 60}m"
    except Exception:
        return "—"


class MinimaxTrackerApp(rumps.App):
    def __init__(self):
        super().__init__("⚡ —", quit_button=None)

        self.config = load_config()
        self._timer_obj = None

        # --- menu items ---
        self.lbl_remaining = rumps.MenuItem("Remaining:  —")
        self.lbl_limit     = rumps.MenuItem("Limit:         —")
        self.lbl_resets    = rumps.MenuItem("Resets:       —")
        self.lbl_updated   = rumps.MenuItem("Last updated: —")
        self.btn_refresh   = rumps.MenuItem("Refresh Now", callback=self.on_refresh)
        self.btn_settings  = rumps.MenuItem("Settings…",   callback=self.on_settings)
        self.btn_quit      = rumps.MenuItem("Quit",         callback=rumps.quit_application)

        # disable info labels (they're display-only)
        self.lbl_remaining.set_callback(None)
        self.lbl_limit.set_callback(None)
        self.lbl_resets.set_callback(None)
        self.lbl_updated.set_callback(None)

        self.menu = [
            self.lbl_remaining,
            self.lbl_limit,
            self.lbl_resets,
            None,
            self.lbl_updated,
            self.btn_refresh,
            None,
            self.btn_settings,
            self.btn_quit,
        ]

        self._apply_timer()

        # initial fetch (non-blocking)
        if self.config["api_key"]:
            threading.Thread(target=self._do_fetch, daemon=True).start()

    # ------------------------------------------------------------------
    # Timer management
    # ------------------------------------------------------------------

    def _apply_timer(self):
        """Set (or reset) the periodic refresh timer."""
        interval = max(1, int(self.config.get("refresh_minutes", 5))) * 60
        if self._timer_obj:
            self._timer_obj.stop()
        self._timer_obj = rumps.Timer(self._timer_tick, interval)
        self._timer_obj.start()

    def _timer_tick(self, _sender):
        if self.config["api_key"]:
            threading.Thread(target=self._do_fetch, daemon=True).start()

    # ------------------------------------------------------------------
    # Fetch logic
    # ------------------------------------------------------------------

    def _do_fetch(self):
        api_key = self.config["api_key"].strip()
        base    = REGIONS.get(self.config.get("region", "Global"), REGIONS["Global"])

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }

        # Minimal chat completion — 1 token output, just to get rate-limit headers.
        payload = {
            "model": self.config.get("model", "MiniMax-M2.7"),
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }

        try:
            resp = requests.post(
                f"{base}/v1/text/chatcompletion_v2",
                headers=headers,
                json=payload,
                timeout=15,
            )
        except requests.RequestException as exc:
            rumps.notification(
                "Minimax Tracker",
                "Network error",
                str(exc),
                sound=False,
            )
            self.title = "⚡ err"
            return

        remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("x-ratelimit-remaining")
        limit     = resp.headers.get("X-RateLimit-Limit")     or resp.headers.get("x-ratelimit-limit")
        reset_ts  = resp.headers.get("X-RateLimit-Reset")     or resp.headers.get("x-ratelimit-reset")

        if resp.status_code == 401 or resp.status_code == 403:
            self.title = "⚡ auth err"
            rumps.notification(
                "Minimax Tracker",
                "Auth error",
                "Check your API key in Settings.",
                sound=False,
            )
            return

        now_str = datetime.now().strftime("%-I:%M %p")

        if remaining is not None:
            self.title = f"⚡ {int(remaining):,} rem"
            self.lbl_remaining.title = f"Remaining:  {int(remaining):,}"
            self.lbl_limit.title     = f"Limit:         {int(limit):,}" if limit else "Limit:         —"
            self.lbl_resets.title    = f"Resets:       {time_until(reset_ts)}" if reset_ts else "Resets:       —"
        else:
            # headers absent — show HTTP status as a hint
            body = {}
            try:
                body = resp.json()
            except Exception:
                pass
            status_msg = body.get("base_resp", {}).get("status_msg", f"HTTP {resp.status_code}")
            self.title = "⚡ —"
            self.lbl_remaining.title = f"Remaining:  — ({status_msg})"
            self.lbl_limit.title     = "Limit:         —"
            self.lbl_resets.title    = "Resets:       —"

        self.lbl_updated.title = f"Last updated: {now_str}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @rumps.clicked("Refresh Now")
    def on_refresh(self, _):
        if not self.config["api_key"]:
            rumps.alert("No API key set", "Open Settings and enter your Minimax API key.")
            return
        threading.Thread(target=self._do_fetch, daemon=True).start()

    @rumps.clicked("Settings…")
    def on_settings(self, _):
        # --- API Key ---
        win_key = rumps.Window(
            message="Enter your Minimax API key:",
            title="Minimax Tracker — Settings",
            default_text=self.config["api_key"],
            ok="Next",
            cancel="Cancel",
            dimensions=(400, 24),
        )
        win_key.default_text = self.config["api_key"]
        r = win_key.run()
        if not r.clicked:
            return
        api_key = r.text.strip()

        # --- Model ---
        win_model = rumps.Window(
            message="Model name (e.g. MiniMax-M2.7, abab6.5s-chat):",
            title="Minimax Tracker — Settings",
            default_text=self.config.get("model", "MiniMax-M2.7"),
            ok="Next",
            cancel="Cancel",
            dimensions=(400, 24),
        )
        r1b = win_model.run()
        if not r1b.clicked:
            return
        model = r1b.text.strip() or "MiniMax-M2.7"

        # --- Region ---
        region_options = list(REGIONS.keys())
        current_region = self.config.get("region", "Global")
        region_hint = " / ".join(
            f"[{opt}]" if opt == current_region else opt
            for opt in region_options
        )
        win_region = rumps.Window(
            message=f"Region ({region_hint}):",
            title="Minimax Tracker — Settings",
            default_text=current_region,
            ok="Next",
            cancel="Cancel",
            dimensions=(400, 24),
        )
        r2 = win_region.run()
        if not r2.clicked:
            return
        region = r2.text.strip()
        if region not in REGIONS:
            region = "Global"

        # --- Refresh interval ---
        win_interval = rumps.Window(
            message="Refresh every N minutes (e.g. 5):",
            title="Minimax Tracker — Settings",
            default_text=str(self.config.get("refresh_minutes", 5)),
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 24),
        )
        r3 = win_interval.run()
        if not r3.clicked:
            return
        try:
            minutes = max(1, int(r3.text.strip()))
        except ValueError:
            minutes = 5

        self.config["api_key"]         = api_key
        self.config["model"]           = model
        self.config["region"]          = region
        self.config["refresh_minutes"] = minutes
        save_config(self.config)
        self._apply_timer()

        if api_key:
            threading.Thread(target=self._do_fetch, daemon=True).start()


if __name__ == "__main__":
    MinimaxTrackerApp().run()
