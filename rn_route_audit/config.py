"""Project layout configuration.

Every path that the parser needs lives here, so it can be pointed at any
React Navigation project instead of one specific app.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Where things live in the project under audit."""

    app_path: Path
    #: Source root, relative to ``app_path``.
    src_dir: str = "src"
    #: Optional file declaring route names as ``export const Foo = 'Bar'``,
    #: relative to ``src_dir``. Most projects do not have one -- it is only
    #: used to resolve ``name={Constant}`` to its string value and to pick up
    #: group headings, never as the source of the route list.
    router_file: str = "router/path.tsx"
    #: Translation files (flat or nested JSON), relative to ``app_path``.
    #: Used to turn i18n keys found in screens into human-readable text.
    i18n_files: list[str] = field(default_factory=list)
    #: Import alias that points at ``src_dir`` (e.g. ``~/`` or ``@/``).
    alias: str = "~/"
    #: Extensions tried when resolving an import to a file on disk.
    extensions: tuple[str, ...] = (".tsx", ".ts", ".jsx", ".js")

    @property
    def src(self) -> Path:
        return self.app_path / self.src_dir

    @property
    def router_path(self) -> Path:
        return self.src / self.router_file

    @property
    def has_router_file(self) -> bool:
        return self.router_path.is_file()

    def validate(self) -> None:
        if not self.app_path.is_dir():
            raise FileNotFoundError(f"app path not found: {self.app_path}")
        if not self.src.is_dir():
            raise FileNotFoundError(
                f"source dir not found: {self.src} (set --src-dir)")
        # The router file is optional on purpose: requiring it made the tool
        # produce nothing on every project that writes route names inline.
