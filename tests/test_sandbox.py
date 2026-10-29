from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def test_scan_profiles_bundled_knowledge_assets():
    from kmsandbox.scanner import scan
    inventory = scan([ROOT / "examples"], ["dist"])
    assert inventory["summary"]["ontologies"] == 3
    assert inventory["summary"]["classes"] >= 2
    assert {".ttl", ".owl", ".jsonld"}.issubset(inventory["summary"]["formats"])
    markdown = next(item for item in inventory["assets"] if item["extension"] == ".md")
    csv_asset = next(item for item in inventory["assets"] if item["extension"] == ".csv")
    assert markdown["assetType"] == "Markdown" and markdown["details"]["headings"] == 2
    assert csv_asset["assetType"] == "CSV data" and csv_asset["details"]["columns"] == 3


def test_scan_identifies_pdf_and_image_metadata(tmp_path):
    from PIL import Image
    from pypdf import PdfWriter
    from kmsandbox.scanner import scan
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (32, 16), "navy").save(image_path)
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter(); writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as file:
        writer.write(file)
    inventory = scan([tmp_path], [])
    image_asset = next(x for x in inventory["assets"] if x["extension"] == ".png")
    pdf_asset = next(x for x in inventory["assets"] if x["extension"] == ".pdf")
    assert image_asset["assetType"] == "Image" and image_asset["details"]["width"] == 32
    assert pdf_asset["assetType"] == "PDF" and pdf_asset["details"]["pages"] == 1


def test_dashboard_is_self_contained():
    from kmsandbox.dashboard import render_dashboard
    from kmsandbox.scanner import scan
    result = render_dashboard(scan([ROOT / "examples"], []), "Test Sandbox", product_name="My Product", primary_color="#123456")
    assert "My Product" in result
    assert "#123456" in result
    assert "Clinical study" in result
    assert "__DATA__" not in result


def test_api_is_registered_and_query_guard_is_read_only():
    from fastapi import HTTPException
    from kmsandbox.api import _safe_query, create_app
    app = create_app(str(ROOT / "sandbox.yaml"))
    paths = {route.path for route in app.routes}
    assert {"/api/health", "/api/assets", "/api/query", "/api/rescan"}.issubset(paths)
    _safe_query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
    with pytest.raises(HTTPException):
        _safe_query("DELETE WHERE { ?s ?p ?o }")
