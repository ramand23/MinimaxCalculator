"""
Claude Token Tracker — macOS Menu Bar App
Shows remaining API token quota from Anthropic rate-limit headers.
"""

import json
import os
import threading
from datetime import datetime, timezone

import requests
import rumps

CONFIG_PATH = os.path.expanduser("~/.claude-tracker.json")
API_BASE    = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
# Cheapest model — used only to ping the API and get rate-limit headers
PING_MODEL  = "claude-haiku-4-5-20251001"

DEFAULT_CONFIG = {
    "api_key":         "",
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


def fmt_num(val):
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return "—"


def time_until(reset_str):
    """Parse ISO-8601 reset timestamp and return 'in Xm Ys'."""
    try:
        # e.g. "2024-01-15T10:30:00Z"
        reset_str = reset_str.rstrip("Z") + "+00:00"
        from datetime import timezone
        reset_dt = datetime.fromisoformat(reset_str)
        now_dt   = datetime.now(timezone.utc)
        diff     = int((reset_dt - now_dt).total_seconds())
        if diff <= 0:
            return "now"
        if diff < 60:
            return f"in {diff}s"
        m, s = divmod(diff, 60)
        return f"in {m}m {s:02d}s"
    except Exception:
        return "—"


class ClaudeTrackerApp(rumps.App):
    def __init__(self):
        super().__init__("⚡ —", quit_button=None)

        self.config     = load_config()
        self._timer_obj = None

        # display-only labels
        self.lbl_tok_rem  = rumps.MenuItem("Tokens left:    —")
        self.lbl_tok_lim  = rumps.MenuItem("Token limit:    —")
        self.lbl_req_rem  = rumps.MenuItem("Requests left:  —")
        self.lbl_resets   = rumps.MenuItem("Resets:         —")
        self.lbl_last_use = rumps.MenuItem("Last call:      —")
        self.lbl_updated  = rumps.MenuItem("Updated:        —")

        for lbl in (self.lbl_tok_rem, self.lbl_tok_lim,
                    self.lbl_req_rem, self.lbl_resets,
                    self.lbl_last_use, self.lbl_updated):
            lbl.set_callback(None)

        self.btn_refresh  = rumps.MenuItem("Refresh Now",  callback=self.on_refresh)
        self.btn_settings = rumps.MenuItem("Settings…",    callback=self.on_settings)
        self.btn_quit     = rumps.MenuItem("Quit",          callback=rumps.quit_application)

        self.menu = [
            self.lbl_tok_rem,
            self.lbl_tok_lim,
            self.lbl_req_rem,
            self.lbl_resets,
            None,
            self.lbl_last_use,
            self.lbl_updated,
            self.btn_refresh,
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
        now_str = datetime.now().strftime("%-I:%M %p")

        req_headers = {
            "x-api-key":         api_key,
            "anthropic-version": API_VERSION,
            "content-type":      "application/json",
        }

        payload = {
            "model":      PING_MODEL,
            "max_tokens": 1,
            "messages":   [{"role": "user", "content": "hi"}],
        }

        try:
            resp = requests.post(
                f"{API_BASE}/v1/messages",
                headers=req_headers,
                json=payload,
                timeout=15,
            )
        except requests.RequestException as exc:
            self.title = "⚡ err"
            self.lbl_tok_rem.title = f"Tokens left:    error — {exc}"
            self.lbl_updated.title = f"Updated:        {now_str}"
            return

        h = resp.headers

        tok_rem   = h.get("anthropic-ratelimit-tokens-remaining")
        tok_lim   = h.get("anthropic-ratelimit-tokens-limit")
        tok_reset = h.get("anthropic-ratelimit-tokens-reset")
        req_rem   = h.get("anthropic-ratelimit-requests-remaining")

        if resp.status_code == 401:
            self.title = "⚡ auth err"
            self.lbl_tok_rem.title  = "Tokens left:    Auth error — check API key"
            self.lbl_tok_lim.title  = "Token limit:    —"
            self.lbl_req_rem.title  = "Requests left:  —"
            self.lbl_resets.title   = "Resets:         —"
            self.lbl_last_use.title = "Last call:      —"
            self.lbl_updated.title  = f"Updated:        {now_str}"
            return

        # Per-call usage from response body
        call_tokens = None
        try:
            body        = resp.json()
            usage       = body.get("usage", {})
            in_tok      = usage.get("input_tokens",  0)
            out_tok     = usage.get("output_tokens", 0)
            call_tokens = in_tok + out_tok
        except Exception:
            pass

        if tok_rem is not None:
            self.title = f"⚡ {fmt_num(tok_rem)}"
        else:
            self.title = "⚡ OK" if resp.status_code == 200 else f"⚡ {resp.status_code}"

        self.lbl_tok_rem.title  = f"Tokens left:    {fmt_num(tok_rem)}"
        self.lbl_tok_lim.title  = f"Token limit:    {fmt_num(tok_lim)}"
        self.lbl_req_rem.title  = f"Requests left:  {fmt_num(req_rem)}"
        self.lbl_resets.title   = f"Resets:         {time_until(tok_reset) if tok_reset else '—'}"
        self.lbl_last_use.title = (
            f"Last call:      {call_tokens:,} tokens" if call_tokens is not None else "Last call:      —"
        )
        self.lbl_updated.title  = f"Updated:        {now_str}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @rumps.clicked("Refresh Now")
    def on_refresh(self, _):
        if not self.config["api_key"]:
            rumps.alert("No API key", "Open Settings and enter your Anthropic API key.")
            return
        threading.Thread(target=self._do_fetch, daemon=True).start()

    @rumps.clicked("Settings…")
    def on_settings(self, _):
        r = rumps.Window(
            message="Enter your Anthropic API key (starts with sk-ant-):",
            title="Claude Tracker — Settings",
            default_text=self.config["api_key"],
            ok="Next", cancel="Cancel", dimensions=(420, 24),
        ).run()
        if not r.clicked:
            return
        api_key = r.text.strip()

        r2 = rumps.Window(
            message="Auto-refresh every N minutes (e.g. 5):",
            title="Claude Tracker — Settings",
            default_text=str(self.config.get("refresh_minutes", 5)),
            ok="Save", cancel="Cancel", dimensions=(420, 24),
        ).run()
        if not r2.clicked:
            return
        try:
            minutes = max(1, int(r2.text.strip()))
        except ValueError:
            minutes = 5

        self.config["api_key"]         = api_key
        self.config["refresh_minutes"] = minutes
        save_config(self.config)
        self._apply_timer()

        if api_key:
            threading.Thread(target=self._do_fetch, daemon=True).start()


if __name__ == "__main__":
    ClaudeTrackerApp().run()
