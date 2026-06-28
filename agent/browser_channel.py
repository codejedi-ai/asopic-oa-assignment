"""
BrowserChannel — an in-process browser "channel" that is opened at the start of a
mission and closed when the mission ends.

This replaces the MCP connection (a subprocess speaking JSON-RPC over stdio). It
reuses the same Playwright tool implementations from ``mcp_server`` but calls
them directly in-process — no subprocess, no serialization round-trip.

The browser is exposed as a SINGLE action tool: ``act(action)`` takes a JSON
action describing which link/element to act on, and the browser performs it.
After every action, tabs that are no longer in use are closed and their URLs are
saved for later reference (``~/.clio/data/saved_urls.json``).

    channel = BrowserChannel()
    await channel.start()                                   # open the channel
    result = await channel.act({"type": "navigate", "url": "/pallets/flask/releases"})
    state  = await channel.call_tool("get_page_state", {...})  # observations
    await channel.stop()                                    # close the channel
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
import mcp_server

SAVED_URLS_PATH = Path(config.DATA_DIR) / "saved_urls.json"
GITHUB_BASE = "https://github.com"


class BrowserChannel:
    """Direct, in-process channel to the Playwright browser."""

    def __init__(self):
        self._open = False
        self.saved_urls: List[str] = []

    async def start(self) -> None:
        await mcp_server.initialize_browser()
        self._open = True
        print("Browser channel opened.")

    # ----- single action tool -----------------------------------------------

    async def act(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one JSON browser action and tidy up unused tabs.

        action = {
            "type": "navigate" | "click",
            "url":      "<href or /relative>",   # for navigate
            "selector": "<css selector>",        # for click (preferred)
            "text":     "<visible text>",        # for click (fallback)
        }
        Returns {ok, action, closed_tabs, [error]}.
        """
        action = action or {}
        atype = action.get("type", "navigate")
        out: Dict[str, Any] = {"ok": False, "action": atype, "closed_tabs": []}

        try:
            if atype == "navigate":
                href = action.get("url", "")
                if not href:
                    out["error"] = "navigate action missing url"
                    return out
                full_url = href if href.startswith("http") else f"{GITHUB_BASE}{href}"
                await self.call_tool("navigate_to_url", {"url": full_url})
                out["ok"] = True
                out["url"] = full_url

            elif atype == "click":
                selector = action.get("selector") or ""
                text = action.get("text") or ""
                target = selector if len(selector) > 5 else f"text={text}"
                res = await self.call_tool("click_button", {"selector": target})
                if isinstance(res, dict) and res.get("status") == "error":
                    out["error"] = res.get("error", "click failed")
                    return out
                out["ok"] = True

            else:
                out["error"] = f"unknown action type: {atype}"
                return out

            # Let the page settle, then tidy up tabs.
            try:
                await self.call_tool("is_page_loaded", {"timeout_ms": 3000})
            except Exception:
                pass
            out["closed_tabs"] = await self._close_unused_tabs()
            return out

        except Exception as e:
            out["error"] = str(e)
            return out

    async def _close_unused_tabs(self) -> List[str]:
        """Close every tab except the active one, saving their URLs for reference."""
        ctx = getattr(mcp_server, "context", None)
        active = getattr(mcp_server, "page", None)
        closed: List[str] = []
        if ctx is None:
            return closed
        for p in list(getattr(ctx, "pages", [])):
            if p is active:
                continue
            try:
                url = p.url
                await p.close()
                if url and url not in ("about:blank",):
                    closed.append(url)
            except Exception:
                pass
        if closed:
            self.saved_urls.extend(closed)
            self._persist_saved_urls()
        return closed

    def _persist_saved_urls(self) -> None:
        try:
            SAVED_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SAVED_URLS_PATH.write_text(json.dumps(self.saved_urls, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[browser_channel] could not persist saved urls: {e}")

    # ----- low-level tool access (observations) -----------------------------

    async def call_tool(self, name: str, arguments: Dict[str, Any] = None) -> Any:
        """Invoke a browser tool in-process and return its parsed result.

        Mirrors the old MCPClient.call_tool: tools return their payload as a JSON
        string inside a text content block, which we parse back into a dict.
        """
        if arguments is None:
            arguments = {}
        result = await mcp_server.call_tool(name, arguments)
        if not result:
            return {}
        first = result[0]
        if getattr(first, "type", None) == "text":
            text = getattr(first, "text", "")
            try:
                return json.loads(text)
            except Exception:
                return text
        return result

    async def stop(self) -> None:
        await mcp_server.cleanup_browser()
        self._open = False
        print("Browser channel closed.")
