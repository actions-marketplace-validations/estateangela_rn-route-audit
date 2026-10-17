"""Tests for the pull request diff."""
from __future__ import annotations

import unittest

from rn_route_audit.diff import COMMENT_MARKER, diff_audits, to_markdown


def r(route, component="C", file="src/C.tsx", status="mounted", condition=""):
    return {"route": route, "component": component, "file": file,
            "status": status, "condition": condition}


class RenameDetection(unittest.TestCase):
    def test_same_screen_new_name_is_one_rename(self):
        """Reporting a rename as remove+add buries the thing reviewers need:
        the old name keeps appearing in analytics and deep links."""
        d = diff_audits([r("Old")], [r("New")])
        self.assertEqual(len(d.renamed), 1)
        self.assertEqual(d.renamed[0]["from"], "Old")
        self.assertEqual(d.renamed[0]["to"], "New")
        self.assertEqual(d.added, [])
        self.assertEqual(d.removed, [])

    def test_different_screen_is_add_and_remove(self):
        d = diff_audits([r("Old", "A", "src/A.tsx")],
                        [r("New", "B", "src/B.tsx")])
        self.assertEqual(d.renamed, [])
        self.assertEqual(len(d.added), 1)
        self.assertEqual(len(d.removed), 1)

    def test_unresolved_routes_are_not_paired(self):
        """Without a file and component there is nothing to match on, so a
        guess would be wrong more often than right."""
        d = diff_audits([r("Old", "", "", "unresolved")],
                        [r("New", "", "", "unresolved")])
        self.assertEqual(d.renamed, [])
        self.assertEqual(len(d.added), 1)
        self.assertEqual(len(d.removed), 1)


class ReachabilityChanges(unittest.TestCase):
    def test_becoming_conditional_is_reported(self):
        d = diff_audits([r("A")], [r("A", status="conditional",
                                     condition="flags.beta")])
        self.assertEqual(len(d.status_changed), 1)
        self.assertEqual(d.status_changed[0]["to"], "conditional")
        self.assertEqual(d.status_changed[0]["condition"], "flags.beta")

    def test_condition_edited_without_status_change(self):
        d = diff_audits([r("A", status="conditional", condition="old")],
                        [r("A", status="conditional", condition="new")])
        self.assertEqual(len(d.condition_changed), 1)
        self.assertEqual(d.status_changed, [])

    def test_no_change(self):
        d = diff_audits([r("A")], [r("A")])
        self.assertEqual(d.changed, 0)


class Markdown(unittest.TestCase):
    def test_marker_is_present_so_the_comment_can_be_updated(self):
        self.assertIn(COMMENT_MARKER, to_markdown(diff_audits([r("A")], [r("A")])))

    def test_no_change_says_so(self):
        md = to_markdown(diff_audits([r("A")], [r("A")]))
        self.assertIn("No navigation changes", md)

    def test_renames_come_first(self):
        d = diff_audits([r("Old"), r("Z", "Z", "src/Z.tsx")],
                        [r("New"), r("Z", "Z", "src/Z.tsx", "conditional", "f")])
        md = to_markdown(d)
        self.assertLess(md.index("Renamed"), md.index("Reachability"))

    def test_long_lists_are_truncated(self):
        base = []
        head = [r(f"R{i}", f"C{i}", f"src/C{i}.tsx") for i in range(30)]
        md = to_markdown(diff_audits(base, head), limit=5)
        self.assertIn("and 25 more", md)


if __name__ == "__main__":
    unittest.main()
