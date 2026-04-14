"""
Minimax Token Tracker — macOS Menu Bar App
Verifies your API key and provides quick access to the Minimax dashboard.
Note: The Minimax API does not expose remaining quota in response headers
for the M2.7 plan, so balance must be checked on the web dashboard.
"""

import json
import os
import subprocess
import threading
from datetime import datetime

import requests
import rumps

CONFIG_PATH   = os.path.expanduser("~/.minimax-tracker.json")
DASHBOARD_URL = "https://platform.minimax.io"

REGIONS = {
    "Global": "https://api.minimax.io",
    "China":  "https://api.minimaxi.com",
}

DEFAULT_CONFIG = {
    "api_key":         "",
    "region":          "Global",
    "model":           "MiniMax-M2.7",
    "refresh_minutes": 5,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


class MinimaxTrackerApp(rumps.App):
    def __init__(self):
        super().__init__("⚡ —", quit_button=None)

        self.config = load_config()
        self._timer_obj = None

        # --- display-only labels ---
        self.lbl_status  = rumps.MenuItem("Status:    —")
        self.lbl_model   = rumps.MenuItem("Model:     —")
        self.lbl_tokens  = rumps.MenuItem("Last call: —")
        self.lbl_updated = rumps.MenuItem("Updated:   —")

        for lbl in (self.lbl_status, self.lbl_model, self.lbl_tokens, self.lbl_updated):
            lbl.set_callback(None)

        self.btn_refresh   = rumps.MenuItem("Refresh Now",       callback=self.on_refresh)
        self.btn_dashboard = rumps.MenuItem("Open Dashboard →",  callback=self.on_open_dashboard)
        self.btn_settings  = rumps.MenuItem("Settings…",         callback=self.on_settings)
        self.btn_quit      = rumps.MenuItem("Quit",               callback=rumps.quit_application)

        self.menu = [
            self.lbl_status,
            self.lbl_model,
            self.lbl_tokens,
            None,
            self.lbl_updated,
            self.btn_refresh,
            self.btn_dashboard,
            None,
            self.btn_settings,
            self.btn_quit,
        ]

        self._apply_timer()

        if self.config["api_key"]:
            threading.Thread(target=self._do_fetch, daemon=True).start()

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def _apply_timer(self):
        interval = max(1, int(self.config.get("refresh_minutes", 5))) * 60
        if self._timer_obj:
            self._timer_obj.stop()
        self._timer_obj = rumps.Timer(self._timer_tick, interval)
        self._timer_obj.start()

    def _timer_tick(self, _sender):
        if self.config["api_key"]:
            threading.Thread(target=self._do_fetch, daemon=True).start()

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _do_fetch(self):
        api_key = self.config["api_key"].strip()
        base    = REGIONS.get(self.config.get("region", "Global"), REGIONS["Global"])
        model   = self.config.get("model", "MiniMax-M2.7")

        req_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }

        payload = {
            "model":     model,
            "messages":  [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }

        try:
            resp = requests.post(
                f"{base}/v1/text/chatcompletion_v2",
                headers=req_headers,
                json=payload,
                timeout=15,
            )
        except requests.RequestException as exc:
            self.title = "⚡ err"
            self.lbl_status.title  = f"Status:    Error — {exc}"
            self.lbl_model.title   = f"Model:     {model}"
            self.lbl_tokens.title  = "Last call: —"
            self.lbl_updated.title = f"Updated:   {datetime.now().strftime('%-I:%M %p')}"
            return

        now_str = datetime.now().strftime("%-I:%M %p")

        if resp.status_code in (401, 403):
            self.title = "⚡ auth err"
            self.lbl_status.title  = "Status:    Auth error — check API key"
            self.lbl_model.title   = f"Model:     {model}"
            self.lbl_tokens.title  = "Last call: —"
            self.lbl_updated.title = f"Updated:   {now_str}"
            return

        # Parse usage from response body
        total_tokens = None
        try:
            body = resp.json()
            usage = body.get("usage", {})
            total_tokens  = usage.get("total_tokens")
            prompt_tokens = usage.get("prompt_tokens")
            comp_tokens   = usage.get("completion_tokens")
        except Exception:
            pass

        if resp.status_code == 200:
            self.title = "⚡ OK"
            self.lbl_status.title = "Status:    Connected ✓"
        else:
            self.title = f"⚡ {resp.status_code}"
            self.lbl_status.title = f"Status:    HTTP {resp.status_code}"

        self.lbl_model.title = f"Model:     {model}"

        if total_tokens is not None:
            self.lbl_tokens.title = (
                f"Last call: {total_tokens} tokens"
                f"  ({prompt_tokens}↑ {comp_tokens}↓)"
            )
        else:
            self.lbl_tokens.title = "Last call: —"

        self.lbl_updated.title = f"Updated:   {now_str}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @rumps.clicked("Refresh Now")
    def on_refresh(self, _):
        if not self.config["api_key"]:
            rumps.alert("No API key", "Open Settings and enter your Minimax API key.")
            return
        threading.Thread(target=self._do_fetch, daemon=True).start()

    @rumps.clicked("Open Dashboard →")
    def on_open_dashboard(self, _):
        subprocess.run(["open", DASHBOARD_URL])

    @rumps.clicked("Settings…")
    def on_settings(self, _):
        # API Key
        r = rumps.Window(
            message="Enter your Minimax API key:",
            title="Minimax Tracker — Settings",
            default_text=self.config["api_key"],
            ok="Next", cancel="Cancel", dimensions=(400, 24),
        ).run()
        if not r.clicked:
            return
        api_key = r.text.strip()

        # Model
        r2 = rumps.Window(
            message="Model name (e.g. MiniMax-M2.7):",
            title="Minimax Tracker — Settings",
            default_text=self.config.get("model", "MiniMax-M2.7"),
            ok="Next", cancel="Cancel", dimensions=(400, 24),
        ).run()
        if not r2.clicked:
            return
        model = r2.text.strip() or "MiniMax-M2.7"

        # Region
        current_region = self.config.get("region", "Global")
        region_hint = " / ".join(
            f"[{opt}]" if opt == current_region else opt
            for opt in REGIONS
        )
        r3 = rumps.Window(
            message=f"Region ({region_hint}):",
            title="Minimax Tracker — Settings",
            default_text=current_region,
            ok="Next", cancel="Cancel", dimensions=(400, 24),
        ).run()
        if not r3.clicked:
            return
        region = r3.text.strip() if r3.text.strip() in REGIONS else "Global"

        # Refresh interval
        r4 = rumps.Window(
            message="Auto-refresh every N minutes (e.g. 5):",
            title="Minimax Tracker — Settings",
            default_text=str(self.config.get("refresh_minutes", 5)),
            ok="Save", cancel="Cancel", dimensions=(400, 24),
        ).run()
        if not r4.clicked:
            return
        try:
            minutes = max(1, int(r4.text.strip()))
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
