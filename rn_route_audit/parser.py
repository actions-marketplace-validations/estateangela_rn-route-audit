"""Parse React Navigation declarations out of TypeScript/JavaScript source.

The parser is deliberately regex-and-scanner based rather than a real TS
parser: it only needs a handful of constructs, and this keeps the tool
dependency-free. The cases that actually broke naive regexes are covered
by tests in ``tests/test_parser.py`` -- read them before changing anything
here.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

#: A route whose screen is mounted unconditionally and whose component exists.
MOUNTED = "mounted"
#: Mounted, but wrapped in a condition (feature flag, permission check...).
#: ``navigation.navigate()`` fails when that condition is false.
CONDITIONAL = "conditional"
#: Declared as a route constant, but no screen mounts it anywhere.
UNMOUNTED = "unmounted"
#: Mounted, but the component expression could not be traced to a file.
UNRESOLVED = "unresolved"


#: How a screen declaration was written. Measured prevalence across four
#: real projects (BlueWallet, Rocket.Chat, react-navigation, one private app):
#: literal names and the v7 static API dominate; named constants are rare.
JSX_CONSTANT = "jsx-constant"
JSX_LITERAL = "jsx-literal"
STATIC_API = "static-api"


@dataclass
class ScreenDecl:
    """One screen declaration found in the source."""

    key: str                 #: route name, or the constant's identifier
    component_expr: str      #: component identifier, "" when not an identifier
    file: str                #: file the declaration lives in
    style: str
    condition: str = ""
    from_constant: bool = False


@dataclass
class Route:
    route: str
    const: str
    group: str = ""
    status: str = UNMOUNTED
    navigator: str = ""
    component: str = ""
    file: str = ""
    condition: str = ""
    style: str = ""
    screen_title: str = ""
    sample_texts: list[str] = field(default_factory=list)
    text_keys: list[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["sample_texts"] = " / ".join(self.sample_texts)
        d["text_keys"] = " | ".join(self.text_keys)
        return d


def load_route_constants(cfg: Config) -> tuple[dict[str, str], dict[str, str]]:
    """Read ``export const Name = 'RouteName'`` plus the comment above it.

    Line comments are treated as group headings, which is how most projects
    visually organise a long list of route constants.
    """
    const2route: dict[str, str] = {}
    const2group: dict[str, str] = {}
    group = ""
    decl = re.compile(r"^export\s+const\s+(\w+)\s*[:=]")
    value = re.compile(r"""=\s*['"`](.+?)['"`]""")

    for line in cfg.router_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("//"):
            group = s.lstrip("/").strip()
            continue
        m = decl.match(s)
        if not m:
            continue
        v = value.search(s)
        if not v:
            continue
        const2route[m.group(1)] = v.group(1)
        const2group[m.group(1)] = group
    return const2route, const2group


def iter_screen_tags(text: str):
    """Yield ``(attributes, start_offset)`` for every ``<*Screen ...>`` tag.

    Two things this gets right that a naive regex does not:

    * The optional namespace prefix. Screens are written both as ``<Screen>``
      (destructured) and ``<Tab.Screen>`` / ``<BottomTab.Screen>``. ``\\w``
      does not match the dot, so ``<(\\w*Screen)`` silently skips every
      namespaced tag -- and those screens then look unmounted.
    * Brace depth instead of ``[^>]*``. An attribute like
      ``options={({route}) => ...}`` contains ``>`` inside an arrow function,
      which truncates the match and drops the real attributes.
    """
    for m in re.finditer(r"<(?:\w+\.)?(\w*Screen)\b", text):
        i, depth, n = m.end(), 0, len(text)
        while i < n:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                yield text[m.end():i], m.start()
                break
            i += 1


def enclosing_condition(text: str, pos: int) -> str:
    """Condition of the innermost ``{cond && (...)}`` block containing ``pos``.

    Looking back a fixed number of lines for the last ``&&`` is wrong: a
    conditional block that already closed above the screen gets attributed to
    it, so an unconditionally mounted screen is reported as feature-flagged.
    Here each candidate block is accepted only if its opening brace is still
    unclosed at ``pos``.
    """
    best = ""
    for m in re.finditer(r"\{\s*([^{}\n]{1,80}?)\s*&&\s*\(", text):
        if m.start() >= pos:
            break
        if _closing_brace(text, m.start()) > pos:
            best = m.group(1).strip()      # innermost wins
    return best


def _closing_brace(text: str, open_idx: int) -> int:
    """Index of the ``}`` matching the ``{`` at ``open_idx`` (or ``len(text)``)."""
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def find_router_maps(cfg: Config) -> dict[str, tuple[str, str]]:
    """Find ``SomeRouterMap.set(RouteConst, Component)`` registrations.

    Projects that register screens dynamically pass
    ``component={SomeRouterMap.get(RouteConst)}``, so the component name is
    never written next to the screen and has to be looked up here.
    """
    out: dict[str, tuple[str, str]] = {}
    pattern = re.compile(r"(\w*RouterMap)\.set\(\s*(\w+)\s*,\s*(\w+)\s*\)")
    for f in _source_files(cfg):
        for m in pattern.finditer(_read(f)):
            out[m.group(2)] = (_rel(cfg, f), m.group(3))
    return out


def resolve_component(cfg: Config, file_rel: str, component: str) -> tuple[str, str]:
    """Trace a component name to the file that defines it.

    Returns ``(relative_path, detail)``; path is empty when unresolved.
    """
    text = _read(cfg.app_path / file_rel)
    spec = _import_spec(text, component)
    if spec is None:
        if re.search(rf"(function|const|class)\s+{re.escape(component)}\b", text):
            return file_rel, "defined in same file"
        return "", "no import found"

    if spec.startswith(cfg.alias):
        base = cfg.src / spec[len(cfg.alias):]
    elif spec.startswith("."):
        base = (cfg.app_path / file_rel).parent / spec
    else:
        return "", f"external package: {spec}"

    # An import spec may already carry its extension; appending another one
    # produces paths like ``Screen.tsx.tsx`` that never exist.
    candidates = [base] if base.suffix in cfg.extensions else []
    for ext in cfg.extensions:
        candidates.append(Path(str(base) + ext))
    for ext in cfg.extensions:
        candidates.append(base / f"index{ext}")

    for p in candidates:
        if p.is_file():
            return _rel(cfg, p), "ok"
    return "", f"file not found for import: {spec}"


def _import_spec(text: str, component: str) -> str | None:
    """Module specifier of the import that brings ``component`` into scope."""
    name = re.escape(component)
    pattern = (
        rf"import\s+(?:"
        rf"\{{[^}}]*\b{name}\b[^}}]*\}}"        # named import
        rf"|{name}(?:\s*,\s*\{{[^}}]*\}})?"     # default, maybe with named
        rf")\s+from\s+['\"](.+?)['\"]"
    )
    m = re.search(pattern, text)
    return m.group(1) if m else None


def find_static_screens(text: str, file_rel: str) -> list[ScreenDecl]:
    """Parse React Navigation v7 static API declarations.

        createNativeStackNavigator({
          screens: { Home: HomeScreen, Detail: { screen: DetailScreen } },
        })

    There is no JSX and no ``name=`` attribute here, so a scanner looking for
    ``<Screen>`` finds nothing at all -- Rocket.Chat declares all 147 of its
    screens this way. The object key is the route name.
    """
    out: list[ScreenDecl] = []
    for m in re.finditer(r"create\w*Navigator\s*\(\s*\{", text):
        sm = re.compile(r"\bscreens\s*:\s*\{").search(text, m.end(), m.end() + 6000)
        if not sm:
            continue
        block = text[sm.end() - 1:_closing_brace(text, sm.end() - 1) + 1]
        for key, value in _top_level_entries(block):
            comp = value
            # `{ screen: Component, options: ... }` form
            inner = re.search(r"\bscreen\s*:\s*(\w+)", value)
            if inner:
                comp = inner.group(1)
            if not re.fullmatch(r"\w+", comp or ""):
                comp = ""
            out.append(ScreenDecl(key=key, component_expr=comp, file=file_rel,
                                  style=STATIC_API))
    return out


def _top_level_entries(block: str) -> list[tuple[str, str]]:
    """``{ A: x, B: { ... }, C }`` -> ``[("A", "x"), ("B", "{...}"), ("C", "C")]``."""
    assert block.startswith("{")
    body = block[1:-1] if block.endswith("}") else block[1:]
    entries, depth, buf = [], 0, ""
    for ch in body:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            entries.append(buf)
            buf = ""
        else:
            buf += ch
    entries.append(buf)

    out = []
    for e in entries:
        e = e.strip()
        if not e or e.startswith("//") or e.startswith("..."):
            continue
        if ":" in e and (e.index(":") < (e.index("{") if "{" in e else len(e))):
            k, v = e.split(":", 1)
            k, v = k.strip().strip("'\"`"), v.strip()
        else:
            k = v = e.strip().strip("'\"`")   # shorthand `{ SelectServerView }`
        if re.fullmatch(r"\w+", k):
            out.append((k, v))
    return out


def find_jsx_screens(text: str, file_rel: str) -> list[ScreenDecl]:
    """Parse JSX ``<Screen name=... component=... />`` declarations."""
    name_const = re.compile(r"name=\{(\w+)\}")
    name_literal = re.compile(r"""name=['"]([^'"]+)['"]""")
    comp_ident = re.compile(r"component=\{(\w+)\}")
    comp_mapget = re.compile(r"component=\{(\w+)\.get\(")

    out: list[ScreenDecl] = []
    for attrs, offset in iter_screen_tags(text):
        mc, ml = name_const.search(attrs), name_literal.search(attrs)
        if mc:
            key, style, from_const = mc.group(1), JSX_CONSTANT, True
        elif ml:
            key, style, from_const = ml.group(1), JSX_LITERAL, False
        else:
            continue
        ident = comp_ident.search(attrs)
        comp = ident.group(1) if ident else ""
        if not comp and comp_mapget.search(attrs):
            comp = ""        # resolved later via RouterMap.set()
        out.append(ScreenDecl(key=key, component_expr=comp, file=file_rel,
                              style=style, from_constant=from_const,
                              condition=enclosing_condition(text, offset)))
    return out


def audit(cfg: Config) -> list[Route]:
    """Build the route table.

    Screen declarations are the source of truth, not the route-constants
    file. Measured across four real projects, inline names (``name="Home"``)
    and the v7 static API account for the overwhelming majority of
    declarations; only one of the four used named constants. Treating the
    constants file as required produced an empty table -- or an error -- on
    three of them.
    """
    cfg.validate()
    const2route: dict[str, str] = {}
    const2group: dict[str, str] = {}
    if cfg.has_router_file:
        const2route, const2group = load_route_constants(cfg)
    router_maps = find_router_maps(cfg)

    decls: list[ScreenDecl] = []
    for f in _source_files(cfg):
        text = _read(f)
        rel = _rel(cfg, f)
        decls += find_jsx_screens(text, rel)
        decls += find_static_screens(text, rel)

    # route name -> declarations. A constant resolves through the router file
    # when it is available; otherwise the identifier itself is the best label
    # we have, and that is recorded so output is not silently misleading.
    grouped: dict[str, list[tuple[ScreenDecl, bool]]] = defaultdict(list)
    for d in decls:
        if d.from_constant:
            name = const2route.get(d.key)
            grouped[name or d.key].append((d, name is None))
        else:
            grouped[d.key].append((d, False))

    routes: list[Route] = []
    for name, items in grouped.items():
        resolved: list[tuple[ScreenDecl, str, str]] = []
        for d, unresolved_const in items:
            comp, path, detail = d.component_expr, "", ""
            if not comp and d.style == JSX_CONSTANT and d.key in router_maps:
                src_file, comp = router_maps[d.key]
                path, detail = resolve_component(cfg, src_file, comp)
            elif comp:
                path, detail = resolve_component(cfg, d.file, comp)
            else:
                detail = "component expression not understood"
            if unresolved_const:
                detail = (detail + "; " if detail else "") + \
                    f"route name unknown, showing constant {d.key}"
            resolved.append((d, path, detail))

        with_file = [r for r in resolved if r[1]]
        pick = with_file[0] if with_file else resolved[0]
        d, path, detail = pick
        if not with_file:
            status = UNRESOLVED
        elif all(r[0].condition for r in with_file):
            status = CONDITIONAL
        else:
            status = MOUNTED

        const = d.key if d.from_constant else ""
        routes.append(Route(route=name, const=const,
                            group=const2group.get(d.key, "") if d.from_constant else "",
                            status=status, navigator=d.file,
                            component=d.component_expr or (
                                router_maps.get(d.key, ("", ""))[1]
                                if d.from_constant else ""),
                            file=path, condition=d.condition,
                            style=d.style, detail=detail))

    # Constants declared but never mounted are only knowable when the
    # router file exists.
    mounted_consts = {d.key for d in decls if d.from_constant}
    for const, name in const2route.items():
        if const in mounted_consts or name in grouped:
            continue
        routes.append(Route(route=name, const=const, group=const2group.get(const, ""),
                            status=UNMOUNTED, style=JSX_CONSTANT,
                            detail="declared as a route constant but never mounted"))

    routes.sort(key=lambda r: (r.group, r.route))
    return routes


def load_i18n(cfg: Config) -> dict[str, str]:
    """Flatten the translation files into ``{dotted.key: text}``."""
    out: dict[str, str] = {}
    for rel in cfg.i18n_files:
        p = cfg.app_path / rel
        if not p.is_file():
            continue
        out.update(_flatten(json.loads(p.read_text(encoding="utf-8"))))
    return out


def extract_keys(text: str, i18n: dict[str, str]) -> list[str]:
    """Find translation keys used in a component, in either common style.

        t('settings.about')          // function call
        loc.settings.about           // property access on an i18n object

    The second style has no marker that says "this is a translation" -- it
    looks like any other property chain. Rather than guess which identifier
    is the i18n object (projects call it loc, i18n, strings, messages...),
    a dotted path counts only if it actually resolves to a known key. That
    makes false positives impossible and needs no configuration.
    """
    keys: list[str] = []

    def add(k: str) -> None:
        if k in i18n and k not in keys:
            keys.append(k)

    for k in re.findall(r"""\bt\(\s*['"]([A-Za-z0-9_.\-]+)['"]""", text):
        add(k)
    for head, rest in re.findall(r"\b(\w+)((?:\.\w+){1,3})\b", text):
        path = rest.lstrip(".")
        add(path)                      # loc.settings.about  -> settings.about
        add(f"{head}.{path}")          # or the whole chain is the key
    return keys


def enrich(cfg: Config, routes: list[Route], max_keys: int = 8,
           max_texts: int = 6) -> list[Route]:
    """Attach the screen title and sample on-screen text to each route.

    This is what makes reverse lookup ("I see this text, which route is it?")
    possible, and it is also the only part that needs the i18n files.
    """
    i18n = load_i18n(cfg)
    if not i18n:
        return routes
    title_re = re.compile(
        r"""title=\{?\s*(?:t\(\s*['"]([A-Za-z0-9_.\-]+)['"]|(\w+(?:\.\w+){1,3}))""")

    for r in routes:
        if not r.file:
            continue
        p = cfg.app_path / r.file
        if not p.is_file():
            continue
        text = _read(p)

        m = title_re.search(text)
        if m:
            for cand in (m.group(1), m.group(2)):
                if not cand:
                    continue
                for k in (cand, cand.split(".", 1)[-1]):
                    if k in i18n:
                        r.screen_title = i18n[k]
                        break
                if r.screen_title:
                    break

        keys = extract_keys(text, i18n)
        r.text_keys = keys[:max_keys]
        r.sample_texts = [i18n[k] for k in keys[:max_texts]]
    return routes


def _source_files(cfg: Config):
    seen = set()
    for ext in cfg.extensions:
        for f in sorted(cfg.src.rglob(f"*{ext}")):
            if f not in seen:
                seen.add(f)
                yield f


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _rel(cfg: Config, p: Path) -> str:
    return str(p.resolve().relative_to(cfg.app_path.resolve()))


def _flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = str(v)
    return out
