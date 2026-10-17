"""Tests for the self-contained HTML page.

The page is the part non-programmers use, so the failure that matters is
the silent one: a page that loads, looks right, and whose search box does
nothing because the embedded data broke the script.
"""
from __future__ import annotations

import re
import unittest

from rn_route_audit.page import build
from rn_route_audit.parser import MOUNTED, Route


def routes():
    return [
        Route(route="Main/Home", const="HomePath", status=MOUNTED,
              component="HomeScreen", file="src/Home.tsx",
              screen_title="Home", sample_texts=["Welcome back", "Confirm"]),
        Route(route="Main/Notice", const="NoticePath", status=MOUNTED,
              component="NoticeScreen", file="src/Notice.tsx",
              screen_title="Notice",
              sample_texts=["First line\u2028second line"]),
    ]


class SelfContained(unittest.TestCase):
    def test_no_external_resources(self):
        """Designers open this from a download, often offline."""
        page = build(routes())
        self.assertNotIn('src="http', page)
        self.assertNotIn('href="http', page)

    def test_data_is_embedded(self):
        page = build(routes())
        self.assertIn("Welcome back", page)
        self.assertIn("Main/Home", page)


class EmbeddedJson(unittest.TestCase):
    def test_line_separator_is_escaped(self):
        """U+2028 is a JavaScript line terminator that json.dumps leaves raw.
        It breaks the script with a syntax error and the page renders empty."""
        page = build(routes())
        data = [l for l in page.split("\n") if l.startswith("var ROUTES")]
        self.assertEqual(len(data), 1)
        self.assertNotIn("\u2028", data[0])
        self.assertIn("\\u2028", data[0])

    def test_script_tag_cannot_be_closed_early(self):
        rs = routes()
        rs[0].sample_texts = ["</script><script>alert(1)</script>"]
        page = build(rs)
        self.assertNotIn("</script><script>alert", page)

    def test_data_stays_on_one_line(self):
        page = build(routes())
        line = [l for l in page.split("\n") if l.startswith("var ROUTES")][0]
        self.assertTrue(line.rstrip().endswith(";"))

    def test_title_is_escaped(self):
        page = build(routes(), title='x" onload="alert(1)')
        self.assertNotIn('onload="alert(1)"', page)


class Content(unittest.TestCase):
    def test_subtitle_defaults_to_a_count_and_timestamp(self):
        """Without a freshness line nobody can tell a current page from a
        year-old one."""
        page = build(routes())
        self.assertIn("2 screens", page)
        self.assertIn("UTC", page)

    def test_custom_title(self):
        self.assertIn("Acme screens", build(routes(), title="Acme screens"))


if __name__ == "__main__":
    unittest.main()
