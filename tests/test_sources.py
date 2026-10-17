"""Tests for the three ways a React Navigation screen gets declared.

Measured prevalence across four real projects (BlueWallet,
Rocket.Chat.ReactNative, react-navigation's own example app and one private
production app): inline literal
names and the v7 static API account for almost everything, named constants
for one project out of four. Treating a route-constants file as required
produced an empty table -- or a hard error -- on three of the four, which is
why screen declarations are the source of truth here and the constants file
is optional enrichment.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from rn_route_audit.config import Config
from rn_route_audit.parser import (JSX_CONSTANT, JSX_LITERAL, MOUNTED, STATIC_API,
                                   UNRESOLVED, audit, find_static_screens)

FIXTURES = Path(__file__).parent / "fixtures"


def routes_for(name: str, **kw) -> dict:
    kw.setdefault("router_file", "__none__.tsx")
    cfg = Config(app_path=FIXTURES / name, **kw)
    return {r.route: r for r in audit(cfg)}


class LiteralNames(unittest.TestCase):
    """``<Stack.Screen name="Home" …>`` with no constants file anywhere."""

    @classmethod
    def setUpClass(cls):
        cls.routes = routes_for("literal-app")

    def test_routes_are_found_without_a_constants_file(self):
        self.assertEqual(set(self.routes), {"Home", "Settings", "Detail"})

    def test_style_is_recorded(self):
        self.assertEqual(self.routes["Home"].style, JSX_LITERAL)

    def test_component_resolves_through_relative_import(self):
        self.assertEqual(self.routes["Home"].file, "src/screens/Home.tsx")
        self.assertEqual(self.routes["Home"].status, MOUNTED)

    def test_inline_arrow_component_is_unresolved_not_guessed(self):
        self.assertEqual(self.routes["Detail"].status, UNRESOLVED)


class StaticApi(unittest.TestCase):
    """``createNativeStackNavigator({ screens: { … } })`` -- no JSX at all."""

    @classmethod
    def setUpClass(cls):
        cls.routes = routes_for("static-app")

    def test_routes_are_found(self):
        self.assertEqual(set(self.routes), {"Feed", "Profile", "Settings"})

    def test_style_is_recorded(self):
        self.assertEqual(self.routes["Feed"].style, STATIC_API)

    def test_shorthand_entry(self):
        """``screens: { Feed }`` -- key and component are the same identifier."""
        self.assertEqual(self.routes["Feed"].component, "Feed")
        self.assertEqual(self.routes["Feed"].status, MOUNTED)

    def test_object_entry_with_screen_key(self):
        """``screens: { Profile: { screen: Profile, options } }``."""
        self.assertEqual(self.routes["Profile"].component, "Profile")
        self.assertEqual(self.routes["Profile"].status, MOUNTED)

    def test_plain_entry(self):
        self.assertEqual(self.routes["Settings"].component, "Settings")

    def test_screens_block_parsing_is_brace_aware(self):
        src = """
        const N = createStackNavigator({
          screenOptions: { headerShown: false },
          screens: {
            A: ScreenA,
            B: { screen: ScreenB, options: { title: 'x, y' } },
            C,
          },
        })
        """
        decls = find_static_screens(src, "f.tsx")
        self.assertEqual([d.key for d in decls], ["A", "B", "C"])
        self.assertEqual([d.component_expr for d in decls],
                         ["ScreenA", "ScreenB", "C"])


class NamedConstants(unittest.TestCase):
    """The original pattern: ``name={HomePath}`` plus a constants file."""

    @classmethod
    def setUpClass(cls):
        cls.routes = routes_for("sample-app", i18n_files=["locale/en.json"],
                                router_file="router/path.tsx")

    def test_constant_resolves_to_its_string_value(self):
        self.assertIn("Main/Home", self.routes)
        self.assertEqual(self.routes["Main/Home"].const, "HomePath")
        self.assertEqual(self.routes["Main/Home"].style, JSX_CONSTANT)

    def test_group_comes_from_the_constants_file(self):
        self.assertEqual(self.routes["Main/Home"].group, "Main")


class UnknownConstant(unittest.TestCase):
    def test_constant_outside_the_router_file_is_reported_not_dropped(self):
        """A ``name={Const}`` whose constant lives elsewhere must still appear.

        One audited app mounts 12 parent navigators this way; requiring the
        constant to exist in the router file hid all of them.
        """
        routes = routes_for("sample-app", router_file="__none__.tsx")
        self.assertIn("HomePath", routes)        # falls back to the identifier
        self.assertIn("route name unknown", routes["HomePath"].detail)


if __name__ == "__main__":
    unittest.main()
