"""Prepare reproducible PDF workloads locally; pip install pypdfium2 beautifulsoup4.

Uses only the PDFs listed in the supplied Drive folder HTML, not unrelated local PDFs.
Records hashes and original page indices; full workloads include every page.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium
from bs4 import BeautifulSoup

p = argparse.ArgumentParser()
p.add_argument("--source", required=True)
p.add_argument("--folder-html", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
html = BeautifulSoup(Path(a.folder_html).read_text(), "html.parser")
files = {}
for element in html.select("[data-id]"):
    name = element.get_text(" ", strip=True)
    if name.endswith(".pdf") and (Path(a.source) / name).exists():
        files[name] = element["data-id"]
assert files, "No matching documents"
manifest, samples = [], []
composite = pdfium.PdfDocument.new()
full = []
for number, (name, drive_id) in enumerate(sorted(files.items())):
    path = Path(a.source) / name
    record = dict(name=name, drive_id=drive_id, bytes=path.stat().st_size,
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    try:
        doc = pdfium.PdfDocument(str(path))
        n = len(doc)
        record["pages"] = n
        # Spread six pages across the document; include all pages of short documents.
        indices = sorted(set(round(i * (n-1) / 5) for i in range(6)))
        record["sample_pages_1based"] = [i+1 for i in indices]
        composite.import_pages(doc, indices)
        for i in indices:
            samples.append(dict(document=name, page=i+1))
        for start in range(0, n, 25):
            chunk = pdfium.PdfDocument.new()
            chunk.import_pages(doc, list(range(start, min(start+25, n))))
            filename = f"full/{number:02d}-{start:04d}.pdf"
            (out / "full").mkdir(exist_ok=True)
            chunk.save(str(out / filename))
            chunk.close()
            full.append(dict(file=filename, document=name, start_page=start+1,
                             pages=min(25, n-start)))
        doc.close()
    except Exception as exc:
        record["error"] = repr(exc)
    manifest.append(record)
composite.save(str(out / "sample.pdf"))
for size in [1, 5, 10, 25, 50, 100]:
    tasks = []
    for start in range(0, len(samples), size):
        chunk = pdfium.PdfDocument.new()
        chunk.import_pages(composite, list(range(start, min(start+size, len(samples)))))
        filename = f"sample-{size}/{start:04d}.pdf"
        (out / f"sample-{size}").mkdir(exist_ok=True)
        chunk.save(str(out / filename))
        chunk.close()
        tasks.append(dict(file=filename, pages=min(size, len(samples)-start),
                          provenance=samples[start:start+size]))
    (out / f"sample-{size}.json").write_text(json.dumps(tasks, indent=2))
composite.close()
(out / "full.json").write_text(json.dumps(full, indent=2))
(out / "corpus.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(dict(documents=len(manifest), pages=sum(x.get("pages",0) for x in manifest),
                      sample_pages=len(samples), full_chunks=len(full),
                      errors=[x for x in manifest if "error" in x]), indent=2))
