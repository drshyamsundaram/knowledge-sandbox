"""Read-only HTTP API for a configured local Knowledge Sandbox."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import rdflib
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .config import SandboxConfig, load_config
from .scanner import FORMATS, scan

MAX_QUERY_ROWS = 500
FORBIDDEN_SPARQL = ("CONSTRUCT", "DESCRIBE", "INSERT", "DELETE", "LOAD", "CLEAR", "CREATE", "DROP", "MOVE", "COPY", "ADD", "SERVICE")


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    asset_id: str | None = None
    scope: Literal["asset", "combined"] = "asset"


def _safe_query(query: str) -> None:
    upper = query.upper()
    if not upper.lstrip().startswith(("SELECT", "ASK", "PREFIX", "BASE")) or any(word in upper for word in FORBIDDEN_SPARQL):
        raise HTTPException(400, "Only read-only SELECT or ASK queries are allowed.")


def _graph_for_asset(asset: dict) -> rdflib.Graph:
    graph = rdflib.Graph()
    graph.parse(asset["path"], format=FORMATS[asset["extension"]])
    return graph


def create_app(config_path: str) -> FastAPI:
    config: SandboxConfig = load_config(config_path)
    directories = [Path(item) if Path(item).is_absolute() else config.config_dir / item for item in config.directories]
    state = {"inventory": scan(directories, config.exclude_patterns)}
    app = FastAPI(title=f"{config.product_name} API", version="0.1.0", description="Read-only knowledge-base inventory and SPARQL API.")

    def asset_or_404(asset_id: str) -> dict:
        asset = next((x for x in state["inventory"]["assets"] if x["id"] == asset_id), None)
        if not asset:
            raise HTTPException(404, "Unknown knowledge asset id.")
        return asset

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "generatedAt": state["inventory"]["generatedAt"], "summary": state["inventory"]["summary"]}

    @app.get("/api/assets")
    def assets(kind: Literal["all", "Ontology", "Document"] = "all", search: str = "") -> list[dict]:
        term = search.lower()
        return [x for x in state["inventory"]["assets"] if (kind == "all" or x["kind"] == kind) and term in str(x).lower()]

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str) -> dict:
        return asset_or_404(asset_id)

    @app.get("/api/ontologies")
    def ontologies() -> list[dict]:
        return [x for x in state["inventory"]["assets"] if x["kind"] == "Ontology"]

    @app.get("/api/ontologies/{asset_id}/schema")
    def ontology_schema(asset_id: str) -> dict:
        item = asset_or_404(asset_id)
        if item["kind"] != "Ontology":
            raise HTTPException(400, "This asset is not an ontology.")
        return item["profile"]

    @app.post("/api/query")
    def query(request: QueryRequest, limit: int = Query(default=100, ge=1, le=MAX_QUERY_ROWS)) -> dict:
        _safe_query(request.query)
        ontology_assets = [x for x in state["inventory"]["assets"] if x["kind"] == "Ontology" and x["profile"]["status"] == "ready"]
        if request.scope == "asset":
            if not request.asset_id:
                raise HTTPException(400, "asset_id is required when scope is 'asset'.")
            target = asset_or_404(request.asset_id)
            if target["kind"] != "Ontology":
                raise HTTPException(400, "Queries can only target ontology assets.")
            graph = _graph_for_asset(target)
        else:
            graph = rdflib.Graph()
            for item in ontology_assets:
                graph += _graph_for_asset(item)
        try:
            result = graph.query(request.query)
        except Exception as error:
            raise HTTPException(400, f"SPARQL query could not be evaluated: {error}") from error
        if result.type == "ASK":
            return {"type": "ASK", "boolean": bool(result.askAnswer), "limit": limit}
        columns = [str(column) for column in result.vars]
        rows = [{columns[index]: str(value) if value is not None else None for index, value in enumerate(row)} for row in list(result)[:limit]]
        return {"type": "SELECT", "columns": columns, "rows": rows, "limit": limit, "truncated": len(rows) == limit}

    @app.post("/api/rescan")
    def rescan() -> dict:
        state["inventory"] = scan(directories, config.exclude_patterns)
        return {"status": "rescanned", "generatedAt": state["inventory"]["generatedAt"], "summary": state["inventory"]["summary"]}

    return app
