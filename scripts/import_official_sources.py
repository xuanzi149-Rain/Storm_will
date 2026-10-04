"""Fetch curated public university guides into the local RAG corpus.

Run from the project root after reviewing data/official_urls.json. Only pages
from the university's own HTTPS domain are accepted. This is a corpus refresh,
not a live crawler used during user queries.
"""

import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.services.schools import beijing_schools

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "official_urls.json"
MANIFEST = ROOT / "data" / "sources.json"
DOCS = ROOT / "data" / "sample_docs"
REPORT = ROOT / "data" / "import_report.json"
COVERAGE = ROOT / "data" / "coverage.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UniversityRAGCorpus/1.0)"}
SELECTORS = (
    "#vsb_content", "#vsb_content_2", ".v_news_content",
    ".wp_articlecontent", ".article-txt", "article", ".article",
    ".news_content", ".content_main", ".content", "main",
)


def domain_allowed(url, domain):
    parsed = urlparse(url)
    return parsed.scheme == "https" and (
        parsed.hostname == domain or parsed.hostname.endswith("." + domain)
    )


def extract_html(raw, encoding, selector=None):
    soup = BeautifulSoup(raw, "html.parser", from_encoding=encoding)
    for node in soup(["script", "style", "noscript", "svg", "input", "button"]):
        node.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    candidates = [soup.select_one(selector)] if selector else []
    candidates += [soup.select_one(item) for item in SELECTORS]
    candidates = [node for node in candidates if node is not None]
    # Prefer a substantial article; the full body is a last resort for atypical sites.
    chosen = next((node for node in candidates if len(node.get_text(" ", strip=True)) >= 180), None)
    if chosen is None:
        chosen = soup.body or soup
        for node in chosen.select("nav, header, footer, aside"):
            node.decompose()
    for img in chosen.find_all("img"):
        alt = img.get("alt", "").strip()
        if alt and len(alt) > 4:
            img.replace_with("\n" + alt + "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in chosen.get_text("\n").splitlines()]
    lines = [line for line in lines if line]
    return title, "\n".join(lines)


def fetch(entry):
    school, slug, url, domain = (entry[key] for key in ("school", "slug", "url", "domain"))
    if school not in beijing_schools():
        raise ValueError(f"Unknown school: {school}")
    if not domain_allowed(url, domain):
        raise ValueError(f"URL outside official domain: {url}")
    response = requests.get(url, headers=HEADERS, timeout=35, allow_redirects=True)
    response.raise_for_status()
    if not domain_allowed(response.url, domain):
        raise ValueError(f"Redirect outside official domain: {response.url}")
    if len(response.content) > 12_000_000:
        raise ValueError("Document larger than 12 MB")
    is_pdf = response.content[:4] == b"%PDF"
    if is_pdf:
        reader = PdfReader(io.BytesIO(response.content))
        visible = "".join(page.extract_text() or "" for page in reader.pages)
        if len(visible.strip()) < 120:
            raise ValueError("PDF has insufficient extractable text; OCR needed")
        filename = f"{school}__{slug}.pdf"
        content = response.content
        char_count = len(visible)
        title = entry.get("title", slug)
    else:
        response.encoding = response.apparent_encoding
        title, body = extract_html(response.content, response.encoding, entry.get("selector"))
        if len(body) < 180:
            raise ValueError(f"HTML body too short ({len(body)} characters)")
        if any(bad in title.lower() for bad in ("404", "登录", "访问受限", "access denied")):
            raise ValueError(f"Likely login/error page: {title}")
        filename = f"{school}__{slug}.txt"
        content = (
            f"学校：{school}\n标题：{entry.get('title') or title}\n"
            f"官方来源：{response.url}\n抓取日期：{date.today().isoformat()}\n\n{body}\n"
        ).encode("utf-8")
        char_count = len(body)
    return filename, content, {
        "authority": "official", "school": school, "url": response.url,
        "title": entry.get("title") or title, "retrieved_at": date.today().isoformat(),
    }, char_count


def main():
    entries = json.loads(CATALOG.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, item): item for item in entries}
        for job in as_completed(jobs):
            item = jobs[job]
            try:
                filename, content, metadata, chars = job.result()
                (DOCS / filename).write_bytes(content)
                manifest[filename] = metadata
                results.append({"file": filename, "school": metadata["school"], "chars": chars})
                print(f"OK {metadata['school']} {filename} ({chars} chars)")
            except Exception as exc:
                errors.append({"school": item["school"], "url": item["url"], "error": str(exc)})
                print(f"SKIP {item['school']} {item['url']}: {exc}")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps({"imported": sorted(results, key=lambda x: x["file"]), "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage = {}
    for filename, metadata in manifest.items():
        if metadata.get("authority") == "official" and (DOCS / filename).exists():
            coverage.setdefault(metadata["school"], []).append(filename)
    schools = beijing_schools()
    COVERAGE.write_text(json.dumps({
        "as_of": date.today().isoformat(),
        "school_total": len(schools),
        "schools_with_official_files": len(coverage),
        "official_file_total": sum(map(len, coverage.values())),
        "covered": {school: sorted(files) for school, files in sorted(coverage.items())},
        "without_official_files": [school for school in schools if school not in coverage],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(results)} sources from {len({x['school'] for x in results})} schools; {len(errors)} skipped")


if __name__ == "__main__":
    main()
