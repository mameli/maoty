#!/usr/bin/env python3
"""Minimal direct-CDP helper for AOTY scraping.

Drives the dedicated Hermes Chrome profile (LaunchAgent
``com.hermes.chrome-debug-default``) over the Chrome DevTools Protocol,
with no playwright/playwright-cli involvement. The AOTY session
(rememberMe cookie, Cloudflare clearance) lives in that Chrome profile.

Requirements:
- python3 with the ``websocket-client`` package (pip install --user
  websocket-client)
- Chrome reachable at the CDP endpoint; readiness is proven by a
  successful GET /json/version.

Public helpers mirror the needs of build_album_data.py:
- ensure_cdp_ready(): check /json/version, optionally kickstart the
  LaunchAgent and wait for readiness
- AotyCdp context manager: open a dedicated target (tab) in the
  dedicated profile, navigate it, and evaluate JS via Runtime.evaluate
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from websocket import create_connection

CDP_HTTP = "http://127.0.0.1:9222"
LAUNCHAGENT_LABEL = "com.hermes.chrome-debug-default"
NAVIGATE_TIMEOUT_S = 60
EVAL_TIMEOUT_S = 60


def _http_get_json(path: str, timeout: float = 5.0):
    with urllib.request.urlopen(f"{CDP_HTTP}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def cdp_is_ready() -> bool:
    try:
        _http_get_json("/json/version")
        return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_cdp_ready(*, kickstart: bool = True, wait_seconds: int = 30) -> bool:
    """Return True when the dedicated Chrome answers on the CDP endpoint.

    When ``kickstart`` is set and the endpoint is down, restart the
    LaunchAgent and poll /json/version until it answers.
    """
    if cdp_is_ready():
        return True
    if not kickstart:
        return False
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{subprocess.getoutput('id -u').strip()}/{LAUNCHAGENT_LABEL}"],
        check=False,
        capture_output=True,
    )
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if cdp_is_ready():
            return True
        time.sleep(1.0)
    return False


class AotyCdpError(RuntimeError):
    """Raised on CDP navigation/evaluation failures."""


class AotyCdp:
    """One dedicated CDP target (tab) in the dedicated Hermes Chrome profile."""

    def __init__(self) -> None:
        self._ws = None
        self._target_id: str | None = None
        self._created_tab = False

    def __enter__(self) -> "AotyCdp":
        if not ensure_cdp_ready():
            raise AotyCdpError(
                f"CDP endpoint not reachable at {CDP_HTTP} after kickstart attempt"
            )
        # A dedicated tab for this process, so we never disturb the user's tabs.
        # Chrome 111+ requires PUT for /json/new.
        request = urllib.request.Request(f"{CDP_HTTP}/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(request, timeout=5) as response:
            created = json.loads(response.read().decode("utf-8"))
        self._target_id = created["id"]
        self._created_tab = True
        self._connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._target_id and self._created_tab:
            try:
                urllib.request.urlopen(
                    f"{CDP_HTTP}/json/close/{self._target_id}", timeout=5
                ).read()
            except Exception:
                pass
        self._target_id = None

    # -- internals ---------------------------------------------------------

    def _connect(self) -> None:
        info = _http_get_json("/json/version")
        ws_url = info["webSocketDebuggerUrl"]
        # Browser-level socket; we address the target explicitly per command.
        # Chrome rejects WebSocket handshakes carrying an Origin header
        # (403) unless --remote-allow-origins is set, so suppress it.
        self._ws = create_connection(ws_url, timeout=EVAL_TIMEOUT_S, suppress_origin=True)

    def _send(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        if self._ws is None:
            raise AotyCdpError("WebSocket not connected")
        msg_id = uuid.uuid4().int & 0x7FFFFFFF
        payload = {"id": msg_id, "method": method, "params": params or {}}
        if self._target_id:
            payload["sessionId"] = self._session_id()
        self._ws.send(json.dumps(payload))
        deadline = time.time() + (timeout or EVAL_TIMEOUT_S)
        while time.time() < deadline:
            raw = self._ws.recv()
            message = json.loads(raw)
            if message.get("id") != msg_id:
                continue  # ignore events
            if "error" in message:
                raise AotyCdpError(f"{method} failed: {message['error']}")
            return message.get("result", {})
        raise AotyCdpError(f"{method} timed out")

    def _session_id(self) -> str:
        if not hasattr(self, "_sid"):
            result = self._ws_send_browser("Target.attachToTarget", {
                "targetId": self._target_id,
                "flatten": True,
            })
            self._sid = result["sessionId"]
        return self._sid

    def _ws_send_browser(self, method: str, params: dict) -> dict:
        """Send a browser-level command (no sessionId)."""
        ws = self._ws
        if ws is None:
            raise AotyCdpError("WebSocket not connected")
        msg_id = uuid.uuid4().int & 0x7FFFFFFF
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        deadline = time.time() + EVAL_TIMEOUT_S
        while time.time() < deadline:
            raw = ws.recv()
            message = json.loads(raw)
            if message.get("id") != msg_id:
                continue
            if "error" in message:
                raise AotyCdpError(f"{method} failed: {message['error']}")
            return message.get("result", {})
        raise AotyCdpError(f"{method} timed out")

    # -- public API --------------------------------------------------------

    def navigate(self, url: str) -> None:
        result = self._send("Page.navigate", {"url": url}, timeout=NAVIGATE_TIMEOUT_S)
        if result.get("errorText"):
            raise AotyCdpError(f"Navigation failed for {url}: {result['errorText']}")

    def wait_for_load(self, timeout_s: float = 30.0) -> None:
        """Wait until the target reaches document.readyState 'complete'."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                state = self.evaluate("() => document.readyState")
            except Exception:
                state = None
            if state == "complete":
                return
            time.sleep(0.5)
        raise AotyCdpError("Page load timed out")

    def evaluate(self, js: str, timeout: float | None = None):
        """Evaluate a JS function/expression in the page and return its value.

        Accepts both arrow-function style ("() => ...") used by the
        playwright-era extraction snippets and bare expressions.
        """
        expression = js.strip()
        if expression.startswith("()"):
            expression = f"({expression})()"
        params = {"expression": expression, "returnByValue": True, "awaitPromise": True}
        result = self._send("Runtime.evaluate", params, timeout=timeout or EVAL_TIMEOUT_S)
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            text = details.get("exception", {}).get("description") or details.get("text")
            raise AotyCdpError(f"Evaluation failed: {text}")
        return result.get("result", {}).get("value")
