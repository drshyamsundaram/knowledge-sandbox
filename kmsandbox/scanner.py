from __future__ import annotations

from collections import Counter
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import csv
import zipfile
from xml.etree import ElementTree
import rdflib
from PIL import Image
from pypdf import PdfReader

FORMATS = {".ttl": "turtle", ".turtle": "turtle", ".owl": "xml", ".rdf": "xml", ".xml": "xml", ".jsonld": "json-ld", ".json": "json-ld", ".n3": "n3", ".nt": "nt", ".trig": "trig"}
FILE_TYPES = {
    ".pdf": ("PDF", "application/pdf"),
    ".docx": ("Word document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".doc": ("Word document", "application/msword"),
    ".xlsx": ("Excel workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".xls": ("Excel workbook", "application/vnd.ms-excel"),
    ".csv": ("CSV data", "text/csv"), ".tsv": ("TSV data", "text/tab-separated-values"),
    ".md": ("Markdown", "text/markdown"), ".markdown": ("Markdown", "text/markdown"),
    ".txt": ("Text", "text/plain"), ".rtf": ("Rich text", "application/rtf"),
    ".png": ("Image", "image/png"), ".jpg": ("Image", "image/jpeg"), ".jpeg": ("Image", "image/jpeg"),
    ".gif": ("Image", "image/gif"), ".webp": ("Image", "image/webp"), ".bmp": ("Image", "image/bmp"), ".tiff": ("Image", "image/tiff"), ".svg": ("Image", "image/svg+xml"),
    ".pptx": ("PowerPoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".zip": ("Archive", "application/zip"), ".7z": ("Archive", "application/x-7z-compressed"),
}


def _name(term: object) -> str:
    return str(term).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def profile(path: Path) -> dict:
    graph = rdflib.Graph()
    try:
        graph.parse(path, format=FORMATS[path.suffix.lower()])
        classes = set(graph.subjects(rdflib.RDF.type, rdflib.OWL.Class)) | set(graph.subjects(rdflib.RDF.type, rdflib.RDFS.Class))
        object_properties = set(graph.subjects(rdflib.RDF.type, rdflib.OWL.ObjectProperty))
        datatype_properties = set(graph.subjects(rdflib.RDF.type, rdflib.OWL.DatatypeProperty))
        labels = lambda node: str(next(iter(graph.objects(node, rdflib.RDFS.label)), _name(node)))
        predicate_counts = Counter(_name(predicate) for _, predicate, _ in graph)
        return {"status": "ready", "triples": len(graph), "classes": len(classes), "objectProperties": len(object_properties),
                "datatypeProperties": len(datatype_properties), "classSample": [labels(x) for x in sorted(classes, key=lambda x: labels(x).lower())[:10]],
                "predicateSample": [name for name, _ in predicate_counts.most_common(10)],
                "namespaces": [str(namespace) for _, namespace in graph.namespaces()][:12], "error": ""}
    except Exception as error:  # malformed assets remain visible for remediation
        return {"status": "attention", "triples": 0, "classes": 0, "objectProperties": 0, "datatypeProperties": 0,
                "classSample": [], "predicateSample": [], "namespaces": [], "error": str(error).splitlines()[0][:180]}


def _zip_xml_count(path: Path, member: str, tag: str) -> int | None:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read(member))
            return sum(1 for item in root.iter() if item.tag.endswith(tag))
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return None


def describe_file(path: Path, extension: str) -> tuple[str, str, dict]:
    """Classify non-RDF files and obtain inexpensive, non-content metadata."""
    asset_type, mime_type = FILE_TYPES.get(extension, ("Other file", "application/octet-stream"))
    details: dict = {}
    try:
        if extension == ".pdf":
            details["pages"] = len(PdfReader(str(path)).pages)
        elif extension in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}:
            with Image.open(path) as image:
                details.update({"width": image.width, "height": image.height, "colorMode": image.mode, "frames": getattr(image, "n_frames", 1)})
        elif extension == ".xlsx":
            with zipfile.ZipFile(path) as archive:
                workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
                details["sheets"] = [item.attrib.get("name", "Untitled") for item in workbook.iter() if item.tag.endswith("sheet")]
        elif extension == ".docx":
            paragraphs = _zip_xml_count(path, "word/document.xml", "p")
            if paragraphs is not None:
                details["paragraphs"] = paragraphs
        elif extension == ".pptx":
            with zipfile.ZipFile(path) as archive:
                details["slides"] = len([name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")])
        elif extension in {".md", ".markdown"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            details["headings"] = sum(1 for line in text.splitlines() if line.lstrip().startswith("#"))
            details["lines"] = len(text.splitlines())
        elif extension in {".csv", ".tsv"}:
            delimiter = "\t" if extension == ".tsv" else ","
            with path.open(encoding="utf-8", errors="ignore", newline="") as file:
                reader = csv.reader(file, delimiter=delimiter)
                first = next(reader, [])
                details["columns"] = len(first)
                details["columnNames"] = first[:12]
        elif extension == ".zip":
            with zipfile.ZipFile(path) as archive:
                details["items"] = len(archive.infolist())
    except Exception as error:  # file remains discoverable when a preview cannot be read
        details["inspectionNote"] = str(error).splitlines()[0][:160]
    return asset_type, mime_type, details


def scan(directories: Iterable[Path], excludes: Iterable[str]) -> dict:
    excludes = set(excludes)
    assets, notices = [], []
    roots = [Path(item).resolve() for item in directories]
    for root in roots:
        if not root.is_dir():
            notices.append(f"Skipped missing directory: {root}")
            continue
        for path in root.rglob("*"):
            if not path.is_file() or any(part in excludes for part in path.parts):
                continue
            stat = path.stat(); ext = path.suffix.lower() or "[none]"; ontology = ext in FORMATS
            relative = str(path.relative_to(root))
            asset_type, mime_type, details = ("Ontology", "application/rdf+xml", {}) if ontology else describe_file(path, ext)
            assets.append({"id": sha256(f"{root}:{relative}".encode()).hexdigest()[:16], "path": str(path), "relativePath": relative, "root": str(root), "extension": ext,
                           "kind": "Ontology" if ontology else "Document", "assetType": asset_type, "mimeType": mime_type, "details": details, "size": stat.st_size,
                           "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                           "profile": profile(path) if ontology else None})
    assets.sort(key=lambda x: (x["kind"] != "Ontology", x["relativePath"].lower()))
    ontologies = [x for x in assets if x["profile"]]
    return {"generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "roots": [str(x) for x in roots], "notices": notices, "assets": assets,
            "summary": {"assets": len(assets), "ontologies": len(ontologies), "triples": sum(x["profile"]["triples"] for x in ontologies),
                        "classes": sum(x["profile"]["classes"] for x in ontologies), "formats": dict(Counter(x["extension"] for x in ontologies))}}
