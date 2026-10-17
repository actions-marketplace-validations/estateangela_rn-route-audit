"""Tests for the MCP server.

The failures that matter here are protocol-level: a reply on two lines, a
notification that gets answered, a stray print on stdout. All of them look
to the user like "the server did not start" with nothing in any log.
"""
from __future__ import annotations

import io
import json
import unittest
from pathlib import Path

from rn_route_audit.config import Config
from rn_route_audit.mcp import Server

FIXTURE = Path(__file__).parent / "fixtures" / "sample-app"


def run(messages: list[dict]) -> tuple[list[dict], str]:
    cfg = Config(app_path=FIXTURE, i18n_files=["locale/en.json"],
                 router_file="router/path.tsx")
    out = io.StringIO()
    stdin = io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n")
    Server(cfg).serve(stdin=stdin, stdout=out)
    raw = out.getvalue()
    return [json.loads(l) for l in raw.split("\n") if l.strip()], raw


def call(tool: str, **args) -> str:
    msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": tool, "arguments": args}}])
    return msgs[0]["result"]["content"][0]["text"]


class Transport(unittest.TestCase):
    def test_replies_are_one_line_each(self):
        """Translations contain U+2028, which json.dumps leaves raw and which
        splits a line for anything that terminates lines the way JavaScript
        does. One of those turns a reply into two malformed lines."""
        msgs, raw = run([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "get_route", "arguments": {"route": "Main/Notice"}}}])
        self.assertEqual(len(raw.strip().split("\n")), 1)
        self.assertEqual(len(msgs), 1)

    def test_output_is_pure_ascii(self):
        _, raw = run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "get_route",
                                  "arguments": {"route": "Main/Notice"}}}])
        self.assertTrue(raw.isascii())
        self.assertNotIn("\u2028", raw)

    def test_notifications_get_no_reply(self):
        """A reply to a notification is a protocol violation."""
        msgs, _ = run([{"jsonrpc": "2.0", "method": "notifications/initialized"},
                       {"jsonrpc": "2.0", "id": 9, "method": "ping"}])
        self.assertEqual([m["id"] for m in msgs], [9])

    def test_malformed_json_does_not_kill_the_server(self):
        cfg = Config(app_path=FIXTURE, router_file="router/path.tsx")
        out = io.StringIO()
        Server(cfg).serve(stdin=io.StringIO('not json\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n'),
                          stdout=out)
        msgs = [json.loads(l) for l in out.getvalue().split("\n") if l.strip()]
        self.assertEqual(msgs[0]["error"]["code"], -32700)
        self.assertEqual(msgs[1]["id"], 2)


class Handshake(unittest.TestCase):
    def test_echoes_a_supported_protocol_version(self):
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"}}])
        self.assertEqual(msgs[0]["result"]["protocolVersion"], "2025-06-18")

    def test_falls_back_for_an_unknown_version(self):
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "1999-01-01"}}])
        self.assertEqual(msgs[0]["result"]["protocolVersion"], "2024-11-05")

    def test_declares_the_tools_capability(self):
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {}}])
        self.assertIn("tools", msgs[0]["result"]["capabilities"])

    def test_unknown_method(self):
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "nope/nope"}])
        self.assertEqual(msgs[0]["error"]["code"], -32601)


class Tools(unittest.TestCase):
    def test_every_tool_declares_a_schema(self):
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        for t in msgs[0]["result"]["tools"]:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertTrue(t["description"])

    def test_find_screen_by_text_tolerates_messy_input(self):
        out = call("find_screen_by_text", text="welcome   back!!")
        self.assertIn("Main/Home", out)
        self.assertIn("HomeScreen.tsx", out)

    def test_get_route_reports_the_guarding_condition(self):
        out = call("get_route", route="Main/Notice")
        self.assertIn("conditional", out)
        self.assertIn("flags.noticeEnabled", out)

    def test_get_route_suggests_near_misses(self):
        out = call("get_route", route="Main/Hom")
        self.assertIn("Did you mean", out)
        self.assertIn("Main/Home", out)

    def test_list_routes_filters_by_status(self):
        out = call("list_routes", status="conditional")
        self.assertIn("Main/Notice", out)
        self.assertNotIn("Main/Home ", out)

    def test_unknown_tool_is_a_protocol_error(self):
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "nope", "arguments": {}}}])
        self.assertEqual(msgs[0]["error"]["code"], -32602)

    def test_tool_failure_is_reported_in_content_not_as_a_protocol_error(self):
        """A tool that raises must not look like a broken server."""
        msgs, _ = run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "list_routes",
                                   "arguments": {"limit": "not-a-number"}}}])
        self.assertNotIn("error", msgs[0])
        self.assertTrue(msgs[0]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
