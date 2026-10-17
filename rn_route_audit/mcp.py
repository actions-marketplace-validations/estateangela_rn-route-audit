"""An MCP server over stdio, so an AI coding agent can ask about routes.

The question an agent keeps getting wrong on an unfamiliar codebase is
"which file renders the screen the user is describing". It guesses from
file names. This hands it the answer.

Implemented directly against JSON-RPC rather than through the MCP SDK to
keep the package dependency-free, which is also what lets the GitHub Action
run with no install step.

**Everything that is not a protocol message goes to stderr.** stdout is the
transport; a single stray print corrupts the stream and the client
disconnects with no useful error.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .lookup import lookup as text_lookup
from .parser import Route, audit, enrich, load_i18n

#: Versions whose shapes this server handles. The client's own version is
#: echoed back when recognised, which is what the spec asks for.
SUPPORTED = ("2024-11-05", "2025-03-26", "2025-06-18")
DEFAULT_VERSION = "2024-11-05"


def log(*a: Any) -> None:
    print(*a, file=sys.stderr, flush=True)


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    run: Callable[[dict], str]

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.schema}


class Server:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.routes: list[Route] = []
        self.i18n: dict[str, str] = {}
        self.tools = {t.name: t for t in self._tools()}

    # ---------------------------------------------------------------- data

    def load(self) -> None:
        self.routes = audit(self.cfg)
        if self.cfg.i18n_files:
            self.routes = enrich(self.cfg, self.routes)
            self.i18n = load_i18n(self.cfg)
        log(f"rn-route-audit: {len(self.routes)} routes from {self.cfg.app_path}")

    # --------------------------------------------------------------- tools

    def _tools(self) -> list[Tool]:
        return [
            Tool(
                name="find_screen_by_text",
                description=(
                    "Given text that appears on screen, return the routes that "
                    "render it and the component file for each. Use this when a "
                    "request names a screen by what the user sees rather than by "
                    "route or file name. Matching ignores spacing, punctuation "
                    "and case, so interpolated copy still matches."),
                schema={"type": "object", "required": ["text"], "properties": {
                    "text": {"type": "string",
                             "description": "Words seen on the screen."},
                    "limit": {"type": "integer", "default": 10}}},
                run=self._find_by_text),
            Tool(
                name="get_route",
                description=(
                    "Look up one route by name. Returns the component file, "
                    "whether it is reachable, and the condition guarding it when "
                    "it is mounted behind a feature flag."),
                schema={"type": "object", "required": ["route"], "properties": {
                    "route": {"type": "string",
                              "description": "Exact route name, e.g. Main/Home."}}},
                run=self._get_route),
            Tool(
                name="list_routes",
                description=(
                    "List routes, optionally filtered. Use status='conditional' "
                    "to find screens that are only reachable behind a feature "
                    "flag, which usually need their own test cases."),
                schema={"type": "object", "properties": {
                    "status": {"type": "string",
                               "enum": ["mounted", "conditional",
                                        "unresolved", "unmounted"]},
                    "group": {"type": "string"},
                    "contains": {"type": "string",
                                 "description": "Substring of the route name."},
                    "limit": {"type": "integer", "default": 50}}},
                run=self._list_routes),
        ]

    def _find_by_text(self, args: dict) -> str:
        text = (args.get("text") or "").strip()
        if not text:
            return "Provide the text you see on the screen."
        if not self.i18n:
            return ("No translation files are loaded, so text lookup is not "
                    "available. Start the server with --i18n.")
        ms = text_lookup(text, self.routes, self.i18n,
                         limit=int(args.get("limit", 10)))
        if not ms:
            return f"No screen contains: {text}"
        out = [f"{len(ms)} match(es) for: {text}", ""]
        for m in ms:
            r = m.route
            out.append(f"{r.route}  [{m.tier} match]")
            out.append(f"  file      {r.file or '(unresolved)'}")
            out.append(f"  status    {r.status}"
                       + (f"  (condition: {r.condition})" if r.condition else ""))
            out.append(f"  matched   {m.key} = {m.text}")
            out.append("")
        return "\n".join(out).rstrip()

    def _get_route(self, args: dict) -> str:
        name = (args.get("route") or "").strip()
        hit = next((r for r in self.routes if r.route == name), None)
        if hit is None:
            near = [r.route for r in self.routes if name.lower() in r.route.lower()][:5]
            return (f"No route named {name}."
                    + (f" Did you mean: {', '.join(near)}" if near else ""))
        out = [f"{hit.route}",
               f"  status     {hit.status}",
               f"  file       {hit.file or '(unresolved)'}",
               f"  component  {hit.component or '-'}",
               f"  navigator  {hit.navigator or '-'}"]
        if hit.condition:
            out.append(f"  condition  {hit.condition}   "
                       f"<- unreachable while this is false")
        if hit.screen_title:
            out.append(f"  title      {hit.screen_title}")
        if hit.sample_texts:
            out.append(f"  on screen  {' / '.join(hit.sample_texts)}")
        return "\n".join(out)

    def _list_routes(self, args: dict) -> str:
        rs = self.routes
        if args.get("status"):
            rs = [r for r in rs if r.status == args["status"]]
        if args.get("group"):
            rs = [r for r in rs if r.group == args["group"]]
        if args.get("contains"):
            needle = args["contains"].lower()
            rs = [r for r in rs if needle in r.route.lower()]
        limit = int(args.get("limit", 50))
        head = f"{len(rs)} route(s)"
        rows = [f"  {r.route}  [{r.status}]"
                + (f"  {r.condition}" if r.condition else "")
                + (f"  -> {r.file}" if r.file else "")
                for r in rs[:limit]]
        if len(rs) > limit:
            rows.append(f"  …and {len(rs) - limit} more")
        return "\n".join([head, ""] + rows) if rs else "No routes match."

    # ------------------------------------------------------------ protocol

    def handle(self, msg: dict) -> dict | None:
        mid, method = msg.get("id"), msg.get("method")
        # A notification has no id and must never be answered.
        if mid is None:
            return None
        try:
            if method == "initialize":
                want = (msg.get("params") or {}).get("protocolVersion")
                return _ok(mid, {
                    "protocolVersion": want if want in SUPPORTED else DEFAULT_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rn-route-audit", "version": "1.1.0"},
                })
            if method == "ping":
                return _ok(mid, {})
            if method == "tools/list":
                return _ok(mid, {"tools": [t.as_dict() for t in self.tools.values()]})
            if method == "tools/call":
                params = msg.get("params") or {}
                tool = self.tools.get(params.get("name"))
                if tool is None:
                    return _err(mid, -32602, f"unknown tool: {params.get('name')}")
                try:
                    text = tool.run(params.get("arguments") or {})
                    return _ok(mid, {"content": [{"type": "text", "text": text}]})
                except Exception as e:                      # tool failure, not
                    return _ok(mid, {"content": [{"type": "text",  # protocol failure
                                                  "text": f"error: {e}"}],
                                     "isError": True})
            return _err(mid, -32601, f"method not found: {method}")
        except Exception as e:
            return _err(mid, -32603, f"internal error: {e}")

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        self.load()
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write(stdout, _err(None, -32700, "parse error"))
                continue
            reply = self.handle(msg)
            if reply is not None:
                _write(stdout, reply)


def _ok(mid, result) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _write(stream, msg: dict) -> None:
    # ensure_ascii=True on purpose. The transport is newline-delimited JSON,
    # and U+2028/U+2029 are line terminators to anything that splits text the
    # way JavaScript or Python's splitlines() does. One of those in a
    # translated string turns a single reply into two malformed lines, and
    # the client just disconnects. Escaping everything non-ASCII makes that
    # impossible and costs nothing: JSON escapes are read back identically.
    stream.write(json.dumps(msg, ensure_ascii=True) + "\n")
    stream.flush()
