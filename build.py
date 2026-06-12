#!/usr/bin/env python3
"""
build.py — Static generator for a personal publications site.

Reads:   publications.toml   (data — where you add/edit papers)
         templates/*.html    (templates)
         assets/*            (CSS etc.)
Writes:  dist/               (the finished site for GitHub Pages)

Run:     python3 build.py
No dependencies — Python 3.11+ stdlib only (tomllib).

The output is plain static HTML with Highwire `citation_*` meta tags,
JSON-LD, Open Graph, a BibTeX cite block, a CSS-only topic filter, and a
sitemap — so Google Scholar and search engines can index it well.
"""

import html
import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
TPL = ROOT / "templates"

# Topic key -> human label. Order defines the filter-tab order.
TOPICS = [
    ("inequality", "Inequality"),
    ("hierarchy", "Hierarchy"),
    ("number-theory", "Number theory"),
    ("ml-ai", "Machine learning"),
    ("information", "Information & cognition"),
    ("software", "Software engineering"),
]
TOPIC_LABELS = dict(TOPICS)


def fill(template: str, mapping: dict) -> str:
    """Replace {{KEY}} with values. Simple, no templating engine."""
    out = template
    for key, value in mapping.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def meta_tag(name: str, content: str, attr: str = "name") -> str:
    if not content:
        return ""
    return f'<meta {attr}="{name}" content="{html.escape(content, quote=True)}">'


def strip_html(text: str) -> str:
    """Plain text from a (possibly HTML) abstract — for meta descriptions / JSON-LD."""
    t = re.sub(r"<[^>]+>", "", text or "")
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def author_list(pub: dict, site: dict) -> list:
    """Authors for this paper: the per-paper `authors`, else the site author."""
    return pub.get("authors") or [site["author"]]


def cite_author(name: str) -> str:
    """Normalise to 'Surname, First' for Scholar; leave already-comma'd names as-is."""
    return name if "," in name else surname_first(name)


def citation_meta(pub: dict, site: dict, landing_url: str) -> str:
    """Highwire Press citation_* meta tags for Google Scholar."""
    authors = author_list(pub, site)
    is_solo = authors == [site["author"]]
    tags = [meta_tag("citation_title", pub["title"])]
    tags += [meta_tag("citation_author", cite_author(a)) for a in authors]
    if is_solo:
        tags.append(meta_tag("citation_author_orcid", site.get("orcid", "")))
    tags += [
        meta_tag("citation_publication_date", pub.get("date", "")),
        meta_tag("citation_online_date", pub.get("date", "")),
        meta_tag("citation_technical_report_institution", site.get("affiliation", "")),
        meta_tag("citation_abstract_html_url", landing_url),
        meta_tag("citation_pdf_url", pub.get("pdf_url", "")),
        meta_tag("citation_doi", pub.get("doi", "")),
        meta_tag("citation_arxiv_id", pub.get("arxiv_id", "")),
        meta_tag("citation_keywords", "; ".join(pub.get("keywords", []))),
        meta_tag("citation_language", pub.get("language", "en")),
    ]
    return "\n".join(t for t in tags if t)


def og_meta(title: str, description: str, url: str, kind: str, site: dict) -> str:
    """Open Graph + Twitter card tags for nice link previews."""
    desc = description[:300]
    tags = [
        meta_tag("og:title", title, attr="property"),
        meta_tag("og:description", desc, attr="property"),
        meta_tag("og:type", kind, attr="property"),
        meta_tag("og:url", url, attr="property"),
        meta_tag("og:site_name", site["title"], attr="property"),
        meta_tag("twitter:card", "summary"),
        meta_tag("twitter:title", title),
        meta_tag("twitter:description", desc),
    ]
    return "\n".join(t for t in tags if t)


def jsonld(obj: dict) -> str:
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(obj, ensure_ascii=False, indent=2)
        + "\n</script>"
    )


def jsonld_article(pub: dict, site: dict, landing_url: str) -> str:
    obj = {
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle",
        "headline": pub["title"],
        "name": pub["title"],
        "author": [{"@type": "Person", "name": a} for a in author_list(pub, site)],
        "url": landing_url,
    }
    if pub.get("date"):
        obj["datePublished"] = str(pub["date"]).replace("/", "-")
    if not is_placeholder(pub.get("doi", "")):
        obj["identifier"] = "https://doi.org/" + pub["doi"]
    if not is_placeholder(pub.get("pdf_url", "")):
        obj["sameAs"] = pub["pdf_url"]
    abs = strip_html(pub.get("abstract", ""))
    if abs:
        obj["abstract"] = abs
    if pub.get("keywords"):
        obj["keywords"] = pub["keywords"]
    return jsonld(obj)


def jsonld_person(site: dict) -> str:
    same = [u for u in (
        f"https://orcid.org/{site.get('orcid','')}" if site.get("orcid") else "",
        site.get("scholar", ""),
        site.get("github", ""),
        site.get("arxiv", ""),
    ) if u]
    obj = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": site["author"],
        "affiliation": site.get("affiliation", ""),
        "url": site["base_url"].rstrip("/") + "/",
        "description": site.get("tagline", ""),
    }
    if same:
        obj["sameAs"] = same
    return jsonld(obj)


def surname_first(name: str) -> str:
    """'Kristian Sestak' -> 'Sestak, Kristian' (the format Scholar wants)."""
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def date_key(date: str) -> tuple:
    """'YYYY/MM/DD' or 'YYYY' -> sortable (y, m, d). Missing parts sort last within a year."""
    parts = (date or "").replace("-", "/").split("/")
    nums = []
    for p in parts[:3]:
        nums.append(int(p) if p.isdigit() else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def year_of(pub: dict) -> str:
    return str(date_key(pub.get("date", ""))[0] or "")


def is_placeholder(value: str) -> bool:
    return not value or value.startswith("REPLACE")


def doi_link(doi: str) -> str:
    if is_placeholder(doi):
        return ""
    return f'<a href="https://doi.org/{doi}">DOI: {doi}</a>'


def links_block(pub: dict) -> str:
    items = []
    pdf = pub.get("pdf_url", "")
    if not is_placeholder(pdf):
        items.append(f'<a href="{html.escape(pdf, quote=True)}"><strong>Full text (PDF)</strong></a>')
    d = doi_link(pub.get("doi", ""))
    if d:
        items.append(d)
    code = pub.get("code_url", "")
    if not is_placeholder(code):
        items.append(f'<a href="{html.escape(code, quote=True)}">Code &amp; data (GitHub)</a>')
    arxiv = pub.get("arxiv_id", "")
    if not is_placeholder(arxiv):
        items.append(f'<a href="https://arxiv.org/abs/{arxiv}">arXiv:{arxiv}</a>')
    return " ".join(items)


def bibtex(pub: dict, site: dict) -> str:
    """A BibTeX entry generated from the publication data."""
    if pub.get("preprint"):
        entry = "misc"
    elif "In:" in (pub.get("codes") or ""):
        entry = "inproceedings"
    else:
        entry = "article"
    key = re.sub(r"[^a-zA-Z0-9]", "", author_list(pub, site)[0].split(",")[0]) + (year_of(pub) or "")
    fields = [
        ("title", "{" + pub["title"] + "}"),
        ("author", " and ".join(cite_author(a) for a in author_list(pub, site))),
    ]
    if year_of(pub):
        fields.append(("year", year_of(pub)))
    codes = pub.get("codes") or ""
    if entry == "inproceedings" and codes:
        fields.append(("booktitle", "{" + strip_html(codes) + "}"))
    elif entry == "article" and codes:
        fields.append(("journal", "{" + strip_html(codes) + "}"))
    if pub.get("preprint"):
        fields.append(("note", "{Preprint}"))
    if not is_placeholder(pub.get("doi", "")):
        fields.append(("doi", pub["doi"]))
        fields.append(("url", "https://doi.org/" + pub["doi"]))
    elif not is_placeholder(pub.get("arxiv_id", "")):
        fields.append(("url", "https://arxiv.org/abs/" + pub["arxiv_id"]))
    # title/journal/booktitle already carry their own braces; wrap the rest.
    body = ",\n".join(
        f"  {k} = {v}" if v.startswith("{") else f"  {k} = {{{v}}}"
        for k, v in fields
    )
    return f"@{entry}{{{key},\n{body}\n}}"


def cite_block(pub: dict, site: dict) -> str:
    bib = html.escape(bibtex(pub, site))
    return (
        '  <details class="cite">\n'
        '    <summary>Cite (BibTeX)</summary>\n'
        f'    <pre>{bib}</pre>\n'
        '  </details>'
    )


def versions_block(pub: dict) -> str:
    versions = pub.get("versions", [])
    if not versions:
        return ""
    rows = []
    for v in sorted(versions, key=lambda x: date_key(x.get("date", "")), reverse=True):
        links = []
        if not is_placeholder(v.get("pdf_url", "")):
            links.append(f'<a href="{html.escape(v["pdf_url"], quote=True)}">PDF</a>')
        if not is_placeholder(v.get("doi", "")):
            links.append(f'<a href="https://doi.org/{v["doi"]}">DOI</a>')
        meta = " · ".join([html.escape(str(v.get("date", "")))] + links)
        rows.append(f'    <li><span class="v-label">{html.escape(v.get("label", ""))}</span><br>{meta}</li>')
    return (
        '  <div class="versions">\n'
        f'  <h2>Versions ({len(versions)})</h2>\n'
        '  <ul>\n' + "\n".join(rows) + "\n  </ul>\n  </div>"
    )


def keywords_block(pub: dict) -> str:
    kws = pub.get("keywords", [])
    if not kws:
        return ""
    spans = "".join(f"<span>{html.escape(k)}</span>" for k in kws)
    return f'  <div class="keywords"><strong>Keywords:</strong> {spans}</div>'


def display_authors(pub: dict, site: dict) -> str:
    """Human-readable byline. Adds affiliation only for the solo site author."""
    authors = author_list(pub, site)
    if authors == [site["author"]]:
        return f"{html.escape(site['author'])} ({html.escape(site['affiliation'])})"
    return html.escape(", ".join(authors))


def meta_line(pub: dict, site: dict) -> str:
    parts = [display_authors(pub, site)]
    second = []
    if pub.get("date"):
        second.append(html.escape(str(pub["date"])))
    if pub.get("preprint"):
        second.append("preprint")
    if pub.get("codes"):
        second.append(html.escape(pub["codes"]))
    if second:
        parts.append(" · ".join(second))
    return "<br>".join(parts)


def header_links(site: dict) -> str:
    links = []
    if site.get("orcid"):
        links.append(f'<a href="https://orcid.org/{site["orcid"]}">ORCID</a>')
    if site.get("scholar"):
        links.append(f'<a href="{html.escape(site["scholar"], quote=True)}">Google&nbsp;Scholar</a>')
    if site.get("github"):
        links.append(f'<a href="{html.escape(site["github"], quote=True)}">GitHub</a>')
    if site.get("arxiv"):
        links.append(f'<a href="{html.escape(site["arxiv"], quote=True)}">arXiv</a>')
    return " · ".join(links)


def filter_controls(present: list) -> tuple:
    """Return (radios+tabs HTML, generated CSS) for the CSS-only topic filter."""
    keys = ["all"] + [k for k, _ in TOPICS if k in present]
    radios = "".join(
        f'<input type="radio" name="topic" id="f-{k}" class="filter"{" checked" if k=="all" else ""}>\n'
        for k in keys
    )
    labels = "".join(
        f'<label for="f-{k}">{html.escape("All" if k=="all" else TOPIC_LABELS[k])}</label>'
        for k in keys
    )
    tabs = radios + f'  <nav class="tabs">{labels}</nav>'
    css_rules = ["#f-all:checked ~ .pub-list .pub{display:block}"]
    for k in keys:
        if k == "all":
            continue
        css_rules.append(f"#f-{k}:checked ~ .pub-list .pub{{display:none}}")
        css_rules.append(f"#f-{k}:checked ~ .pub-list .pub.topic-{k}{{display:block}}")
    for k in keys:
        css_rules.append(f"#f-{k}:checked ~ .tabs label[for=f-{k}]{{background:var(--accent);color:#fff;border-color:var(--accent)}}")
    return tabs, "\n".join(css_rules)


def build():
    data = tomllib.loads((ROOT / "publications.toml").read_text(encoding="utf-8"))
    site = data["site"]
    pubs = data.get("publication", [])
    base = site["base_url"].rstrip("/")

    # newest first — sort by date regardless of order in the .toml
    pubs.sort(key=lambda p: date_key(p.get("date", "")), reverse=True)

    # clean dist
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "p").mkdir(parents=True)
    shutil.copytree(ROOT / "assets", DIST / "assets")

    pub_tpl = (TPL / "publication.html").read_text(encoding="utf-8")
    idx_tpl = (TPL / "index.html").read_text(encoding="utf-8")

    warnings = []
    cards = []
    urls = [base + "/"]

    for pub in pubs:
        pid = pub["id"]
        landing_url = f"{base}/p/{pid}.html"
        urls.append(landing_url)
        abstract_txt = strip_html(pub.get("abstract", ""))

        if is_placeholder(pub.get("pdf_url", "")):
            warnings.append(f"  [!] '{pid}': missing citation_pdf_url — Scholar won't index the full text.")
        if is_placeholder(pub.get("doi", "")):
            warnings.append(f"  [!] '{pid}': missing DOI.")

        page = fill(pub_tpl, {
            "LANG": pub.get("language", "en"),
            "CITATION_META": citation_meta(pub, site, landing_url),
            "OG_META": og_meta(pub["title"], abstract_txt, landing_url, "article", site),
            "JSONLD": jsonld_article(pub, site, landing_url),
            "TITLE": html.escape(pub["title"]),
            "META_LINE": meta_line(pub, site),
            "LINKS": links_block(pub),
            "ABSTRACT": pub.get("abstract", "").strip(),
            "VERSIONS_BLOCK": versions_block(pub),
            "CITE_BLOCK": cite_block(pub, site),
            "KEYWORDS_BLOCK": keywords_block(pub),
            "AUTHOR": html.escape(site["author"]),
            "ORCID": html.escape(site.get("orcid", "")),
        })
        (DIST / "p" / f"{pid}.html").write_text(page, encoding="utf-8")

        # index card
        meta_bits = []
        if pub.get("date"):
            meta_bits.append(html.escape(str(pub["date"])))
        if pub.get("preprint"):
            meta_bits.append('<span class="badge">preprint</span>')
        if not is_placeholder(pub.get("arxiv_id", "")):
            meta_bits.append(f"arXiv:{pub['arxiv_id']}")
        if pub.get("versions"):
            meta_bits.append(f"{len(pub['versions'])} versions")
        idx_links = []
        if not is_placeholder(pub.get("pdf_url", "")):
            idx_links.append(f'<a href="{html.escape(pub["pdf_url"], quote=True)}">PDF</a>')
        if not is_placeholder(pub.get("doi", "")):
            idx_links.append(f'<a href="https://doi.org/{pub["doi"]}">DOI</a>')
        if not is_placeholder(pub.get("code_url", "")):
            idx_links.append(f'<a href="{html.escape(pub["code_url"], quote=True)}">Code</a>')

        topic = pub.get("topic", "other")
        cards.append(
            f'    <article class="pub topic-{html.escape(topic)}">\n'
            f'      <h3><a href="p/{pid}.html">{html.escape(pub["title"])}</a></h3>\n'
            f'      <p class="m">{html.escape(", ".join(author_list(pub, site)))} · {" · ".join(meta_bits)}</p>\n'
            f'      <p class="excerpt">{pub.get("abstract", "").strip()}</p>\n'
            f'      <p class="pub-links">{" ".join(idx_links)}</p>\n'
            '    </article>'
        )

    present = {p.get("topic") for p in pubs}
    tabs, filter_css = filter_controls(present)

    index = fill(idx_tpl, {
        "SITE_TITLE": html.escape(site["title"]),
        "SITE_DESCRIPTION": html.escape(site["description"]),
        "OG_META": og_meta(site["title"], site["description"], base + "/", "website", site),
        "JSONLD": jsonld_person(site),
        "FILTER_CSS": filter_css,
        "AUTHOR": html.escape(site["author"]),
        "TAGLINE": html.escape(site.get("tagline", "")),
        "AFFILIATION": html.escape(site["affiliation"]),
        "HEADER_LINKS": header_links(site),
        "FILTER_TABS": tabs,
        "PUBLICATIONS": "\n".join(cards),
        "COUNT": len(pubs),
    })
    (DIST / "index.html").write_text(index, encoding="utf-8")

    # sitemap.xml + robots.txt
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"  <url><loc>{html.escape(u)}</loc></url>")
    sm.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8"
    )

    print(f"✓ Built {len(pubs)} publications -> {DIST}")
    print(f"  + sitemap.xml ({len(urls)} URLs), robots.txt, JSON-LD, OpenGraph, BibTeX, topic filter")
    if warnings:
        print("\nWarnings (the site was still generated):")
        print("\n".join(warnings))
    if "USERNAME" in base:
        print("\n  [!] base_url in publications.toml still contains 'USERNAME' — fill in your GitHub username.")


if __name__ == "__main__":
    sys.exit(build())
