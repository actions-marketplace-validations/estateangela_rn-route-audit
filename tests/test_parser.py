"""Regression tests for the parsing cases that actually broke in practice.

Each test names the mistake it guards against. The fixture app under
``tests/fixtures/sample-app`` is small on purpose: every file in it exists
to exercise one of these.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from rn_route_audit.config import Config
from rn_route_audit.lookup import lookup, normalize
from rn_route_audit.parser import (CONDITIONAL, MOUNTED, UNMOUNTED, UNRESOLVED,
                                   audit, enrich, iter_screen_tags, load_i18n)

FIXTURE = Path(__file__).parent / "fixtures" / "sample-app"


def build() -> tuple[Config, dict]:
    cfg = Config(app_path=FIXTURE, i18n_files=["locale/en.json"])
    routes = enrich(cfg, audit(cfg))
    return cfg, {r.route: r for r in routes}


class ScreenTagScanning(unittest.TestCase):
    def test_namespaced_tag_is_found(self):
        """``\\w`` does not match ``.``, so ``<(\\w*Screen)`` skips
        ``<Tab.Screen>`` and those screens look unmounted."""
        tags = list(iter_screen_tags("<Tab.Screen name={A} component={B} />"))
        self.assertEqual(len(tags), 1)
        self.assertIn("name={A}", tags[0][0])

    def test_plain_tag_is_found(self):
        tags = list(iter_screen_tags("<Screen name={A} />"))
        self.assertEqual(len(tags), 1)

    def test_arrow_function_does_not_truncate_attributes(self):
        """``options={({route}) => ...}`` contains ``>``; matching ``[^>]*``
        cuts the tag short and loses ``component``."""
        src = "<Screen options={({ route }) => ({ t: route.name })} component={X} />"
        attrs, _ = next(iter_screen_tags(src))
        self.assertIn("component={X}", attrs)

    def test_offset_is_returned_for_condition_lookup(self):
        _, offset = next(iter_screen_tags("abc\n<Screen name={A} />"))
        self.assertEqual(offset, 4)


class RouteStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.routes = build()

    def test_namespaced_screen_is_mounted_not_unmounted(self):
        self.assertEqual(self.routes["Main/Home"].status, MOUNTED)

    def test_component_behind_arrow_options_still_resolves(self):
        self.assertEqual(self.routes["Main/Home"].component, "HomeScreen")
        self.assertTrue(self.routes["Main/Home"].file.endswith("HomeScreen.tsx"))

    def test_import_that_already_has_extension(self):
        """``from '~/container/DetailScreen.tsx'`` must not become
        ``DetailScreen.tsx.tsx``."""
        r = self.routes["Main/Detail"]
        self.assertEqual(r.status, MOUNTED)
        self.assertEqual(r.file, "src/container/DetailScreen.tsx")

    def test_router_map_registration(self):
        """``component={WalletRouterMap.get(WalletPath)}`` names no component,
        so ``RouterMap.set()`` has to be parsed separately."""
        r = self.routes["Main/Wallet"]
        self.assertEqual(r.status, MOUNTED)
        self.assertEqual(r.component, "WalletScreen")

    def test_relative_import(self):
        self.assertEqual(self.routes["Auth/Login"].file,
                         "src/container/LoginScreen.tsx")

    def test_named_export(self):
        self.assertEqual(self.routes["Main/Notice"].component, "NoticeScreen")

    def test_conditional_mount_is_detected(self):
        r = self.routes["Main/Notice"]
        self.assertEqual(r.status, CONDITIONAL)
        self.assertEqual(r.condition, "flags.noticeEnabled")

    def test_condition_does_not_leak_to_later_screens(self):
        """A conditional block that already closed above a screen must not be
        attributed to it, or unconditional screens look feature-flagged."""
        self.assertEqual(self.routes["Main/Dynamic"].condition, "")

    def test_unmounted_constant(self):
        self.assertEqual(self.routes["Auth/SignUp"].status, UNMOUNTED)
        self.assertEqual(self.routes["Main/Legacy"].status, UNMOUNTED)

    def test_untraceable_component_is_unresolved_not_mounted(self):
        self.assertEqual(self.routes["Main/Dynamic"].status, UNRESOLVED)

    def test_group_comes_from_the_comment_above_the_constant(self):
        self.assertEqual(self.routes["Main/Home"].group, "Main")
        self.assertEqual(self.routes["Auth/Login"].group, "Auth")


class I18nEnrichment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.routes = build()

    def test_screen_title_from_header_title(self):
        self.assertEqual(self.routes["Main/Home"].screen_title, "Home")

    def test_sample_texts_are_collected_in_order(self):
        self.assertEqual(self.routes["Main/Home"].sample_texts,
                         ["Home", "Welcome back", "Confirm"])

    def test_keys_are_deduplicated(self):
        keys = self.routes["Main/Home"].text_keys
        self.assertEqual(len(keys), len(set(keys)))

    def test_line_separator_survives_in_text(self):
        """Real translation files contain U+2028."""
        self.assertTrue(any("\u2028" in t
                            for t in self.routes["Main/Notice"].sample_texts))


class JsonSafety(unittest.TestCase):
    def test_line_separators_are_escaped_in_output(self):
        """U+2028/U+2029 are JS line terminators and Python's splitlines()
        treats them as newlines, but json.dumps leaves them raw."""
        from rn_route_audit.cli import dump_json
        out = dump_json({"t": "a\u2028b\u2029c"})
        self.assertNotIn("\u2028", out)
        self.assertNotIn("\u2029", out)
        self.assertIn("\\u2028", out)
        self.assertEqual(json.loads(out)["t"], "a\u2028b\u2029c")
        self.assertEqual(len(out.splitlines()), 1)


class Lookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, routes = build()
        cls.routes = list(routes.values())
        cls.i18n = load_i18n(cls.cfg)

    def find(self, q):
        return lookup(q, self.routes, self.i18n)

    def test_exact_match_ranks_first(self):
        m = self.find("Welcome back")
        self.assertEqual(m[0].tier, "exact")
        self.assertEqual(m[0].route.route, "Main/Home")

    def test_substring_match(self):
        m = self.find("Welcome")
        self.assertTrue(m)
        self.assertEqual(m[0].tier, "contains")

    def test_normalized_match_ignores_punctuation_and_spacing(self):
        m = self.find("welcome   back!!")
        self.assertTrue(m)
        self.assertEqual(m[0].tier, "normalized")

    def test_no_match_returns_empty(self):
        self.assertEqual(self.find("this text is nowhere"), [])

    def test_normalize_handles_full_width_and_case(self):
        self.assertEqual(normalize("ＡＢ, c"), normalize("ab c"))


if __name__ == "__main__":
    unittest.main()
