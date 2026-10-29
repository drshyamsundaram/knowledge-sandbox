from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class SandboxConfig:
    directories: list[str]
    title: str = "Knowledge Management Sandbox"
    output: str = "./dist"
    exclude_patterns: list[str] = field(default_factory=lambda: [".git", "node_modules", "__pycache__", "dist"])
    product_name: str = "Knowledge Sandbox"
    product_tagline: str = "Knowledge Management · local directory scan"
    introduction: str = "A portable knowledge inventory for configured folders."
    primary_color: str = "#63e6be"
    accent_color: str = "#b39cff"
    footer_html: str = ""
    config_dir: Path = field(default_factory=lambda: Path("."))


def load_config(path_text: str) -> SandboxConfig:
    path = Path(path_text)
    if not path.exists():
        raise ValueError(f"Configuration file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sandbox = raw.get("sandbox", raw)
    directories = sandbox.get("directories", [])
    if isinstance(directories, str):
        directories = [directories]
    if not isinstance(directories, list) or not directories:
        raise ValueError("Set sandbox.directories to one or more folders to scan.")
    template = sandbox.get("template", {}) or {}
    return SandboxConfig(directories=directories, title=sandbox.get("title", "Knowledge Management Sandbox"),
                         output=sandbox.get("output", "./dist"), exclude_patterns=sandbox.get("exclude_patterns", [".git", "node_modules", "__pycache__", "dist"]),
                         product_name=template.get("product_name", "Knowledge Sandbox"),
                         product_tagline=template.get("product_tagline", "Knowledge Management · local directory scan"),
                         introduction=template.get("introduction", "A portable knowledge inventory for configured folders."),
                         primary_color=template.get("primary_color", "#63e6be"), accent_color=template.get("accent_color", "#b39cff"),
                         footer_html=template.get("footer_html", ""),
                         config_dir=path.parent.resolve())
