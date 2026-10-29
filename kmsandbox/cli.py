from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .dashboard import render_dashboard
from .scanner import scan


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="knowledge-sandbox", description="Generate a knowledge-base inventory dashboard.")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Run the read-only Knowledge Sandbox API.")
    serve.add_argument("config", help="YAML configuration file")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    build = sub.add_parser("build", help="Build a portable HTML dashboard.")
    build.add_argument("config", help="YAML configuration file")
    build.add_argument("--output", help="Output directory override")
    build.add_argument("--filename", default="knowledge_sandbox.html")
    if raw_argv and raw_argv[0] not in {"build", "serve", "-h", "--help"}:
        raw_argv = ["build", *raw_argv]
    args = parser.parse_args(raw_argv)
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.config), host=args.host, port=args.port)
        return 0
    try:
        config = load_config(args.config)
        directories = [Path(item) if Path(item).is_absolute() else config.config_dir / item for item in config.directories]
        inventory = scan(directories, config.exclude_patterns)
        output_dir = Path(args.output).resolve() if args.output else (config.config_dir / config.output).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / args.filename
        output.write_text(render_dashboard(inventory, config.title, product_name=config.product_name, product_tagline=config.product_tagline, introduction=config.introduction, primary_color=config.primary_color, accent_color=config.accent_color, footer_html=config.footer_html), encoding="utf-8")
        print(f"Built {output} ({inventory['summary']['assets']} assets, {inventory['summary']['ontologies']} ontologies)")
        return 0
    except ValueError as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
