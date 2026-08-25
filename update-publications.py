#!/usr/bin/env python3
"""Generate the website publication list from two BibTeX files.

BIB_IN_PREP points to the BibTeX file work in preparation (not used here)
BIB_SUBMITTED points to the BibTeX file for submitted work 
BIB_PUBLISHED points to the BibTeX file for published or accepted work.
"""

from __future__ import annotations

import html
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

try:
    import bibtexparser
    from bibtexparser.bparser import BibTexParser
    from bibtexparser.customization import author, convert_to_unicode
except ImportError:
    sys.exit(
        "Missing Python package 'bibtexparser'. Install it with:\n"
        "  python3 -m pip install 'bibtexparser<2'"
    )


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "_includes" / "publications.html"
INDEX = ROOT / "index.md"
INDEX_CONTENT = """---
layout: default
title: Home
---

{% include publications.html %}

{% include nsf-acknowledgement.html %}
"""


def source_path(variable: str) -> Path:
    value = os.environ.get(variable, "").strip()
    if not value:
        sys.exit(f"{variable} is not set. It must contain the path to a BibTeX file.")

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()

    if not path.is_file():
        sys.exit(f"{variable} does not point to a readable file: {path}")

    return path


def customize(record: dict[str, str]) -> dict[str, object]:
    """Decode LaTeX accents and normalize BibTeX author names."""
    decoded = convert_to_unicode(record)
    if decoded.get("author"):
        decoded = author(decoded)
    return decoded


def read_bibtex(path: Path) -> list[dict[str, object]]:
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    parser.customization = customize

    try:
        with path.open("r", encoding="utf-8-sig") as bib_file:
            return bibtexparser.load(bib_file, parser=parser).entries
    except Exception as exc:
        sys.exit(f"Could not parse {path}: {exc}")


def clean(value: object) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.replace("--", "–").replace("~", " ")


def initial_for(token: str) -> str:
    token = token.strip("{} ")
    if not token:
        return ""
    if token[0].islower():
        return token

    pieces = [piece for piece in token.split("-") if piece]
    return "-".join(f"{piece[0].upper()}." for piece in pieces)


def abbreviated_name(person: str) -> str:
    person = clean(person)
    if "," not in person:
        return person

    family, given = (part.strip() for part in person.split(",", 1))
    initials = " ".join(
        initial
        for initial in (initial_for(token) for token in given.split())
        if initial
    )
    return f"{initials} {family}".strip()


def authors_for(entry: dict[str, object]) -> str:
    people = entry.get("author") or entry.get("editor") or []
    if isinstance(people, str):
        people = re.split(r"\s+and\s+", people)
    return ", ".join(abbreviated_name(str(person)) for person in people)


def sort_key(entry: dict[str, object]) -> tuple[int, str, str]:
    year_match = re.search(r"\d{4}", clean(entry.get("year")))
    year = int(year_match.group()) if year_match else -1
    return (-year, authors_for(entry).casefold(), clean(entry.get("title")).casefold())


def venue_for(entry: dict[str, object], submitted: bool) -> str:
    if submitted:
        venue = clean(entry.get("note")) or "Preprint"
        if venue[-1] not in ".?!":
            venue += "."
        return venue

    parts: list[str] = []
    primary = (
        clean(entry.get("journal"))
        or clean(entry.get("booktitle"))
        or clean(entry.get("school"))
        or clean(entry.get("institution"))
        or clean(entry.get("publisher"))
    )
    if primary:
        parts.append(primary)

    if entry.get("volume"):
        parts.append(f"vol. {clean(entry['volume'])}")
    if entry.get("number"):
        parts.append(f"no. {clean(entry['number'])}")
    if entry.get("pages"):
        parts.append(f"pp. {clean(entry['pages'])}")

    publisher = clean(entry.get("publisher"))
    if publisher and publisher != primary:
        parts.append(publisher)
    if entry.get("address"):
        parts.append(clean(entry["address"]))
    if entry.get("note"):
        parts.append(clean(entry["note"]))

    venue = " ".join(part for part in parts if part).strip()
    if venue and venue[-1] not in ".?!":
        venue += "."
    return venue


def safe_link(value: object) -> str:
    url = clean(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if url.startswith("//"):
        return ""
    return url


def links_for(entry: dict[str, object]) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, url: str) -> None:
        if url and url not in seen:
            links.append((label, url))
            seen.add(url)

    eprint = clean(entry.get("arxiv") or entry.get("eprint"))
    archive = clean(entry.get("archiveprefix") or entry.get("eprinttype")).lower()
    if eprint and (entry.get("arxiv") or archive == "arxiv"):
        eprint = re.sub(r"^arxiv:\s*", "", eprint, flags=re.IGNORECASE)
        eprint = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", eprint)
        eprint = eprint.removesuffix(".pdf")
        add("arXiv", f"https://arxiv.org/abs/{eprint}")

    doi = clean(entry.get("doi"))
    if doi:
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
        add("doi", f"https://doi.org/{doi}")

    pdf = safe_link(entry.get("pdf") or entry.get("fulltext"))
    if pdf:
        add("pdf", pdf)

    url = safe_link(entry.get("url"))
    if url:
        lowered = url.lower()
        if "arxiv.org" in lowered:
            add("arXiv", url)
        elif "doi.org" in lowered:
            add("doi", url)
        else:
            add("url", url)

    return links


def render_entry(entry: dict[str, object], submitted: bool) -> str:
    entry_id = clean(entry.get("ID")) or "unknown"
    title = clean(entry.get("title")) or f"Untitled entry ({entry_id})"
    authors = authors_for(entry)
    year = clean(entry.get("year"))
    venue = venue_for(entry, submitted)
    abstract = clean(entry.get("abstract"))
    links = links_for(entry)

    pieces = ['  <article class="publication">', '    <div class="publication-line">']
    if authors:
        pieces.append(f'      <span class="paper-authors">{html.escape(authors)}</span>')
    if year:
        pieces.append(f'      <span class="paper-year">({html.escape(year)})</span>')
    pieces.append(f'      <span class="paper-title">{html.escape(title)}</span>')
    if venue:
        pieces.append(f'      <span class="paper-venue">{html.escape(venue)}</span>')
    pieces.append("    </div>")

    if links or abstract:
        pieces.append('    <div class="paper-links">')
        for label, url in links:
            pieces.append(
                f'      <a href="{html.escape(url, quote=True)}">[{html.escape(label)}]</a>'
            )
        if abstract:
            pieces.extend(
                [
                    '      <details class="publication-details">',
                    "        <summary>[abstract]</summary>",
                    f'        <div class="publication-abstract">{html.escape(abstract)}</div>',
                    "      </details>",
                ]
            )
        pieces.append("    </div>")

    pieces.append("  </article>")
    return "\n".join(pieces)


def render_section(
    entries: list[dict[str, object]],
    section_id: str,
    heading: str,
    submitted: bool,
) -> str:
    lines = [
        f'<section class="research-section" aria-labelledby="{section_id}-heading">',
        f'  <h2 id="{section_id}-heading" class="section-heading">{html.escape(heading)}</h2>',
        "",
    ]

    if entries:
        lines.append(
            "\n\n".join(
                render_entry(entry, submitted)
                for entry in sorted(entries, key=sort_key)
            )
        )
    else:
        lines.append('  <p class="no-publications">No entries.</p>')

    lines.append("</section>")
    return "\n".join(lines)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def main() -> None:
    submitted = read_bibtex(source_path("BIB_SUBMITTED"))
    published = read_bibtex(source_path("BIB_PUBLISHED"))

    content = "\n".join(
        [
            "<!-- Generated by update-publications.py; do not edit manually. -->",
            render_section(
                submitted,
                "preprints",
                "Research · submitted",
                submitted=True,
            ),
            "",
            render_section(
                published,
                "published",
                "Research · published / accepted",
                submitted=False,
            ),
            "",
        ]
    )
    atomic_write(OUTPUT, content)
    atomic_write(INDEX, INDEX_CONTENT)
    print(
        f"Updated {INDEX} and {OUTPUT} with {len(submitted)} preprint(s) "
        f"and {len(published)} published/accepted item(s)."
    )


if __name__ == "__main__":
    main()
