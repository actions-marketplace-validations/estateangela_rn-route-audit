"""Command line interface.

    rn-route-audit audit  --app ./my-app --i18n locale/en.json
    rn-route-audit lookup --app ./my-app --i18n locale/en.json "Welcome back"

Standard library only, so it runs on a bare CI runner with no install step.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from .config import Config
from .diff import diff_audits, load as load_audit, to_markdown
from .lookup import lookup, normalize
from .page import write as write_page
from .parser import CONDITIONAL, MOUNTED, UNMOUNTED, UNRESOLVED, audit, enrich, load_i18n

CSV_COLUMNS = ["route", "const", "group", "status", "condition", "screen_title",
               "sample_texts", "component", "file", "navigator", "text_keys", "detail"]

# U+2028/U+2029 are JavaScript line terminators and Python's splitlines()
# treats them as newlines, yet json.dumps leaves them raw. Anything that
# embeds this JSON in a page or reads it line by line breaks on them.
_JS_UNSAFE = {"\u2028": "\\u2028", "\u2029": "\\u2029"}


def dump_json(data, **kwargs) -> str:
    out = json.dumps(data, ensure_ascii=False, **kwargs)
    for bad, good in _JS_UNSAFE.items():
        out = out.replace(bad, good)
    return out


def _config(args) -> Config:
    return Config(app_path=Path(args.app).expanduser().resolve(),
                  src_dir=args.src_dir,
                  router_file=args.router_file,
                  i18n_files=list(args.i18n or []),
                  alias=args.alias)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--app", required=True, help="path to the app repository")
    p.add_argument("--src-dir", default="src", help="source root (default: src)")
    p.add_argument("--router-file", default="router/path.tsx",
                   help="route constants file, relative to --src-dir")
    p.add_argument("--i18n", action="append", metavar="FILE",
                   help="translation JSON, relative to --app (repeatable)")
    p.add_argument("--alias", default="~/",
                   help="import alias pointing at --src-dir (default: ~/)")


def cmd_audit(args) -> int:
    cfg = _config(args)
    routes = audit(cfg)
    if cfg.i18n_files:
        routes = enrich(cfg, routes)

    counts = Counter(r.status for r in routes)
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "routes.json").write_text(
        dump_json([r.as_dict() for r in routes], indent=2) + "\n", encoding="utf-8")
    with (out_dir / "routes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in routes:
            w.writerow(r.as_dict())

    print(f"{len(routes)} routes")
    for status in (MOUNTED, CONDITIONAL, UNRESOLVED, UNMOUNTED):
        print(f"  {status:<12} {counts.get(status, 0)}")
    print(f"written: {out_dir / 'routes.json'}")
    print(f"         {out_dir / 'routes.csv'}")

    if args.html:
        html = write_page(routes, args.html, title=args.page_title)
        print(f"page:    {html}")

    d = None
    if args.baseline:
        base = Path(args.baseline).expanduser()
        if base.is_file():
            d = diff_audits(load_audit(base), [r.as_dict() for r in routes])
            print(f"\nvs baseline: {d.changed} change(s) "
                  f"(added {len(d.added)}, removed {len(d.removed)}, "
                  f"renamed {len(d.renamed)}, reachability "
                  f"{len(d.status_changed)})")
            if args.comment_file:
                Path(args.comment_file).expanduser().write_text(
                    to_markdown(d), encoding="utf-8")
                print(f"comment: {args.comment_file}")
        else:
            # A missing baseline is normal on the first run; failing the job
            # over it would make the action unusable until a baseline exists.
            print(f"\nbaseline not found, skipping diff: {base}")

    if args.summary_file:
        # key=value lines, ready to append to $GITHUB_OUTPUT. Produced here
        # rather than in the action's shell: a nested heredoc inside a YAML
        # block scalar cannot have its terminator indented, which silently
        # breaks the step.
        lines = [f"json={out_dir / 'routes.json'}",
                 f"csv={out_dir / 'routes.csv'}",
                 f"total={len(routes)}"]
        lines += [f"{s}={counts.get(s, 0)}"
                  for s in (MOUNTED, CONDITIONAL, UNRESOLVED, UNMOUNTED)]
        lines.append(f"changed={d.changed if d else 0}")
        lines.append(f"has-changes={'true' if d and d.changed else 'false'}")
        lines.append(f"added={len(d.added) if d else 0}")
        lines.append(f"removed={len(d.removed) if d else 0}")
        lines.append(f"renamed={len(d.renamed) if d else 0}")
        if args.comment_file:
            lines.append(f"comment={args.comment_file}")
        if args.html:
            lines.append(f"html={args.html}")
        Path(args.summary_file).expanduser().write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    if args.fail_on_unmounted and counts.get(UNMOUNTED, 0):
        print(f"error: {counts[UNMOUNTED]} unmounted route(s)", file=sys.stderr)
        return 1
    if args.fail_on_unresolved and counts.get(UNRESOLVED, 0):
        print(f"error: {counts[UNRESOLVED]} unresolved route(s)", file=sys.stderr)
        return 1
    return 0


def cmd_lookup(args) -> int:
    cfg = _config(args)
    if not cfg.i18n_files:
        print("error: lookup needs at least one --i18n file", file=sys.stderr)
        return 2
    routes = enrich(cfg, audit(cfg))
    matches = lookup(args.text, routes, load_i18n(cfg), limit=args.limit)

    if args.json:
        print(dump_json([{"tier": m.tier, "key": m.key, "text": m.text,
                          "route": m.route.route, "status": m.route.status,
                          "file": m.route.file} for m in matches], indent=2))
        return 0 if matches else 1

    if not matches:
        print(f"no screen contains: {args.text}")
        print(f"  (normalized form searched: {normalize(args.text)!r})")
        return 1
    last = None
    for m in matches:
        if m.tier != last:
            print(f"\n[{m.tier}]")
            last = m.tier
        print(f"  {m.route.route}")
        print(f"    key   {m.key}")
        print(f"    text  {m.text}")
        print(f"    file  {m.route.file or '-'}  ({m.route.status})")
    return 0


def cmd_diff(args) -> int:
    d = diff_audits(load_audit(args.base), load_audit(args.head))
    if args.json:
        print(dump_json(d.as_dict(), indent=2))
    else:
        print(to_markdown(d), end="")
    if args.comment_file:
        Path(args.comment_file).expanduser().write_text(
            to_markdown(d), encoding="utf-8")
    return 1 if (args.exit_code and d.changed) else 0


def cmd_mcp(args) -> int:
    from .mcp import Server
    Server(_config(args)).serve()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rn-route-audit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    a = sub.add_parser("audit", help="build the route table")
    _common(a)
    a.add_argument("--out", default="rn-route-audit-out", help="output directory")
    a.add_argument("--html", metavar="FILE",
                   help="also write a self-contained searchable HTML page")
    a.add_argument("--page-title", default="Screens",
                   help="heading shown on the HTML page")
    a.add_argument("--baseline", metavar="FILE",
                   help="a previous routes.json to diff against")
    a.add_argument("--comment-file", metavar="FILE",
                   help="write the diff as markdown (for a PR comment)")
    a.add_argument("--summary-file", metavar="FILE",
                   help="write key=value counts (for $GITHUB_OUTPUT)")
    a.add_argument("--fail-on-unmounted", action="store_true",
                   help="exit non-zero if any route constant is never mounted")
    a.add_argument("--fail-on-unresolved", action="store_true",
                   help="exit non-zero if any component cannot be traced to a file")
    a.set_defaults(func=cmd_audit)

    l = sub.add_parser("lookup", help="find the route that shows a piece of text")
    _common(l)
    l.add_argument("text", help="text seen on screen")
    l.add_argument("--limit", type=int, default=20)
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_lookup)

    f = sub.add_parser("diff", help="compare two audit results")
    f.add_argument("base", help="routes.json from the base revision")
    f.add_argument("head", help="routes.json from the new revision")
    f.add_argument("--json", action="store_true")
    f.add_argument("--comment-file", metavar="FILE",
                   help="also write the markdown to this file")
    f.add_argument("--exit-code", action="store_true",
                   help="exit 1 when anything changed")
    f.set_defaults(func=cmd_diff)

    m = sub.add_parser("mcp", help="run an MCP server over stdio")
    _common(m)
    m.set_defaults(func=cmd_mcp)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
