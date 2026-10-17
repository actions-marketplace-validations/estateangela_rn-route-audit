"""Compare two audit results and describe what changed.

Built for pull request comments: the interesting question on a PR is not
"what routes exist" but "which screens did this change add, remove, rename,
or hide behind a feature flag".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

#: Marker so a bot can find and update its own comment instead of posting
#: a new one on every push.
COMMENT_MARKER = "<!-- rn-route-audit -->"


@dataclass
class Diff:
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    renamed: list[dict] = field(default_factory=list)
    status_changed: list[dict] = field(default_factory=list)
    condition_changed: list[dict] = field(default_factory=list)
    base_total: int = 0
    head_total: int = 0

    @property
    def changed(self) -> int:
        return (len(self.added) + len(self.removed) + len(self.renamed)
                + len(self.status_changed) + len(self.condition_changed))

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["changed"] = self.changed
        return d


def _identity(r: dict) -> tuple[str, str] | None:
    """Something stable enough to recognise a renamed route.

    Route names change; the file and component they point at usually do not.
    Most projects have no route-constants file, so a constant cannot be used
    as the key here.
    """
    if r.get("file") and r.get("component"):
        return (r["file"], r["component"])
    return None


def diff_audits(base: list[dict], head: list[dict]) -> Diff:
    d = Diff(base_total=len(base), head_total=len(head))
    b_by_route = {r["route"]: r for r in base}
    h_by_route = {r["route"]: r for r in head}

    added_names = [n for n in h_by_route if n not in b_by_route]
    removed_names = [n for n in b_by_route if n not in h_by_route]

    # Pair an addition with a removal that points at the same screen: that is
    # a rename, not a delete plus a create. Reporting it as two changes would
    # hide the thing a reviewer most needs to know -- analytics breaks on a
    # renamed route.
    b_by_id = {}
    for n in removed_names:
        ident = _identity(b_by_route[n])
        if ident:
            b_by_id.setdefault(ident, []).append(n)

    paired_removed: set[str] = set()
    for n in list(added_names):
        ident = _identity(h_by_route[n])
        if ident and b_by_id.get(ident):
            old = b_by_id[ident].pop(0)
            paired_removed.add(old)
            added_names.remove(n)
            d.renamed.append({"from": old, "to": n,
                              "file": h_by_route[n].get("file", "")})

    d.added = [h_by_route[n] for n in sorted(added_names)]
    d.removed = [b_by_route[n] for n in sorted(removed_names)
                 if n not in paired_removed]
    d.renamed.sort(key=lambda r: r["to"])

    for n in sorted(set(b_by_route) & set(h_by_route)):
        b, h = b_by_route[n], h_by_route[n]
        if b.get("status") != h.get("status"):
            d.status_changed.append({"route": n, "from": b.get("status", ""),
                                     "to": h.get("status", ""),
                                     "condition": h.get("condition", "")})
        elif (b.get("condition") or "") != (h.get("condition") or ""):
            d.condition_changed.append({"route": n,
                                        "from": b.get("condition", ""),
                                        "to": h.get("condition", "")})
    return d


def to_markdown(d: Diff, limit: int = 15) -> str:
    """Render the diff as a pull request comment."""
    if not d.changed:
        return (f"{COMMENT_MARKER}\n"
                f"**No navigation changes.** {d.head_total} routes, unchanged.\n")

    def rows(items, fmt):
        out = [fmt(i) for i in items[:limit]]
        if len(items) > limit:
            out.append(f"- _…and {len(items) - limit} more_")
        return out

    lines = [COMMENT_MARKER, "### Navigation changes", ""]

    # Renames first: they silently break analytics and deep links.
    if d.renamed:
        lines.append("**Renamed** — anything referring to the old name breaks "
                     "(analytics, deep links, tests)")
        lines += rows(d.renamed,
                      lambda i: f"- `{i['from']}` → `{i['to']}`")
        lines.append("")
    if d.status_changed:
        lines.append("**Reachability changed**")
        lines += rows(d.status_changed, lambda i: (
            f"- `{i['route']}` — {i['from']} → **{i['to']}**"
            + (f" (`{i['condition']}`)" if i["condition"] else "")))
        lines.append("")
    if d.condition_changed:
        lines.append("**Mount condition changed**")
        lines += rows(d.condition_changed, lambda i: (
            f"- `{i['route']}` — `{i['from'] or '(none)'}` → "
            f"`{i['to'] or '(none)'}`"))
        lines.append("")
    if d.added:
        lines.append("**Added**")
        lines += rows(d.added, lambda i: (
            f"- `{i['route']}`" + (f" — {i['file']}" if i.get("file") else "")))
        lines.append("")
    if d.removed:
        lines.append("**Removed**")
        lines += rows(d.removed, lambda i: f"- `{i['route']}`")
        lines.append("")

    lines.append(f"<sub>{d.base_total} → {d.head_total} routes · "
                 f"{d.changed} change(s)</sub>")
    return "\n".join(lines) + "\n"


def load(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
