#!/usr/bin/env python3
"""Render website publication lists from a BibTeX bibliography.

The script intentionally uses only the Python standard library so it can run in
GitHub Actions without installing dependencies. Existing HTML outside the
documented marker pairs is preserved verbatim.
"""

from __future__ import annotations

import argparse
import html
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HOME_START = "<!-- PUBLICATIONS:HOME:START -->"
HOME_END = "<!-- PUBLICATIONS:HOME:END -->"
ARCHIVE_START = "<!-- PUBLICATIONS:ARCHIVE:START -->"
ARCHIVE_END = "<!-- PUBLICATIONS:ARCHIVE:END -->"
AUTHOR_PATTERN = re.compile(r"\bAngela\s+Cortecchia\b|\bCortecchia\s*,\s*Angela\b", re.I)
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
KNOWN_VENUES = ("ACSOS-C", "ACSOS", "COORDINATION", "DS-RT", "CCNC", "DCOSS-IoT")
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass(frozen=True)
class Publication:
    """Normalised publication data used by the HTML renderer."""

    title: str
    authors: str
    venue: str
    year: int
    pages: str
    link: str | None
    link_label: str | None
    accepted: bool
    sort_date: tuple[int, int, int]


def find_matching_delimiter(text: str, start: int, opening: str) -> int:
    """Return the closing delimiter matching ``text[start]``."""

    closing = "}" if opening == "{" else ")"
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
        if quoted:
            continue
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced BibTeX entry")


def split_top_level(value: str) -> list[str]:
    """Split a BibTeX field list on commas outside braces and quotes."""

    parts: list[str] = []
    start = 0
    depth = 0
    quoted = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"' and depth == 0:
            quoted = not quoted
        elif not quoted:
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
            elif character == "," and depth == 0:
                parts.append(value[start:index])
                start = index + 1
    parts.append(value[start:])
    return parts


def unwrap(value: str) -> str:
    """Remove a single pair of BibTeX value delimiters."""

    value = value.strip()
    if len(value) >= 2 and ((value[0] == "{" and value[-1] == "}") or (value[0] == '"' and value[-1] == '"')):
        return value[1:-1].strip()
    return value


def parse_bibtex(source: str) -> list[dict[str, str]]:
    """Parse the regular BibTeX subset used by the curriculum repository."""

    entries: list[dict[str, str]] = []
    cursor = 0
    entry_pattern = re.compile(r"@(\w+)\s*([\{(])", re.I)
    while match := entry_pattern.search(source, cursor):
        entry_type, opening = match.group(1).lower(), match.group(2)
        end = find_matching_delimiter(source, match.end() - 1, opening)
        cursor = end + 1
        if entry_type in {"comment", "preamble", "string"}:
            continue
        body = source[match.end():end]
        chunks = split_top_level(body)
        if not chunks:
            continue
        fields: dict[str, str] = {"entry_type": entry_type, "key": chunks[0].strip()}
        for chunk in chunks[1:]:
            if "=" not in chunk:
                continue
            name, raw_value = chunk.split("=", 1)
            fields[name.strip().lower()] = unwrap(raw_value)
        entries.append(fields)
    return entries


def latex_to_text(value: str) -> str:
    """Convert the small set of LaTeX constructs used in display fields."""

    replacements = {
        r"\&": "&",
        r"\_": "_",
        r"\%": "%",
        r"\#": "#",
        r"{\LaTeX}": "LaTeX",
        r"\LaTeX": "LaTeX",
        r"{\'{o}}": "ó",
        r"\'{o}": "ó",
        r"{\'{O}}": "Ó",
        r"\'{O}": "Ó",
    }
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)
    value = re.sub(r"\\(?:textit|emph|textbf)\s*\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\[A-Za-z]+\s*", "", value)
    value = value.replace("{", "").replace("}", "").replace("~", " ")
    value = value.replace("--", "–")
    return " ".join(value.split())


def abbreviate_author(author: str) -> str:
    """Format one BibTeX author as initials followed by family name."""

    author = latex_to_text(author.strip())
    if "," in author:
        family, given = (part.strip() for part in author.split(",", 1))
    else:
        parts = author.split()
        if len(parts) == 1:
            return parts[0]
        given, family = " ".join(parts[:-1]), parts[-1]
    initials = " ".join(f"{part[0]}." for part in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", given) if part)
    return f"{initials} {family}".strip()


def format_authors(value: str) -> str:
    """Format a BibTeX author list for compact academic display."""

    authors = [abbreviate_author(author) for author in re.split(r"\s+and\s+", value, flags=re.I)]
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return " and ".join(authors)
    return ", ".join(authors[:-1]) + f", and {authors[-1]}"


def short_venue(fields: dict[str, str], year: int) -> str:
    """Prefer a concise venue name when a common acronym is available."""

    if fields.get("journal"):
        return latex_to_text(fields["journal"])
    booktitle = latex_to_text(fields.get("booktitle", ""))
    for acronym in KNOWN_VENUES:
        if re.search(rf"\b{re.escape(acronym)}\b", booktitle, re.I):
            if acronym == "ACSOS" and "companion" in booktitle.casefold():
                return f"ACSOS {year} Companion"
            return f"{acronym} {year}"
    return booktitle or latex_to_text(fields.get("publisher", ""))


def publication_date(fields: dict[str, str], year: int) -> tuple[int, int, int]:
    """Return the best publication date available without using index dates from other years."""

    explicit_date = fields.get("date", "")
    if match := re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", explicit_date):
        parsed = tuple(int(part) for part in match.groups())
        if parsed[0] == year:
            return parsed

    month_pattern = (
        r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
    )
    booktitle_match = re.search(
        rf"\b(?P<month>{month_pattern})\.?\s+(?P<day>\d{{1,2}})\b[^\n]{{0,24}}?\b(?P<year>\d{{4}})\b",
        fields.get("booktitle", ""),
        re.I,
    )
    if booktitle_match and int(booktitle_match.group("year")) == year:
        month = MONTHS[booktitle_match.group("month")[:3].casefold()]
        return year, month, int(booktitle_match.group("day"))

    timestamp_match = re.search(
        rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{month_pattern})\.?\s+(?P<year>\d{{4}})\b",
        fields.get("timestamp", ""),
        re.I,
    )
    if timestamp_match and int(timestamp_match.group("year")) == year:
        month = MONTHS[timestamp_match.group("month")[:3].casefold()]
        return year, month, int(timestamp_match.group("day"))
    return year, 0, 0


def normalise_publications(entries: Iterable[dict[str, str]]) -> list[Publication]:
    """Filter, normalise, and sort publications authored by Angela Cortecchia."""

    publications: list[Publication] = []
    for fields in entries:
        author_value = fields.get("author", "")
        if not AUTHOR_PATTERN.search(author_value):
            continue
        year_match = YEAR_PATTERN.search(fields.get("year", "") or fields.get("date", ""))
        if not year_match or not fields.get("title"):
            continue
        year = int(year_match.group(0))
        doi = latex_to_text(fields.get("doi", "")).strip()
        url = latex_to_text(fields.get("url", "")).strip()
        link: str | None = None
        link_label: str | None = None
        if doi and doi.upper() != "TBD":
            link = f"https://doi.org/{doi}"
            link_label = "DOI"
        elif url.startswith(("https://", "http://")) and "TBD" not in url.upper():
            link = url
            link_label = "Link"
        annote = fields.get("annote", "").strip().lower()
        publications.append(
            Publication(
                title=latex_to_text(fields["title"]),
                authors=format_authors(author_value),
                venue=short_venue(fields, year),
                year=year,
                pages=latex_to_text(fields.get("pages", "")),
                link=link,
                link_label=link_label,
                accepted=annote in {"notpub", "accepted", "forthcoming"},
                sort_date=publication_date(fields, year),
            )
        )
    return sorted(
        publications,
        key=lambda publication: (
            publication.year,
            not publication.accepted,
            publication.sort_date,
            publication.title.casefold(),
        ),
        reverse=True,
    )


def render_item(publication: Publication, indent: str) -> str:
    """Render one publication list item."""

    venue = html.escape(publication.venue)
    details = f"<em>{venue}</em>" if venue else ""
    if publication.pages:
        details += f", pp. {html.escape(publication.pages)}"
    if details:
        details += "."
    text = (
        f"{indent}<li><p><strong>{html.escape(publication.title)}</strong><br />"
        f"{html.escape(publication.authors)}. {details}</p>"
    )
    if publication.link and publication.link_label:
        text += f'<a href="{html.escape(publication.link, quote=True)}">{publication.link_label}</a>'
    elif publication.accepted:
        text += '<span class="status">Accepted</span>'
    return text + "</li>"


def render_group(year: int, publications: list[Publication], *, archive: bool) -> str:
    """Render one year group for the homepage or the archive."""

    if archive:
        lines = [
            f'      <section class="publication-archive" aria-labelledby="year-{year}">',
            '        <div class="publication-group">',
            f'          <h2 id="year-{year}">{year}</h2>',
            '          <ol class="publication-list">',
        ]
        lines.extend(render_item(publication, "            ") for publication in publications)
        lines.extend(["          </ol>", "        </div>", "      </section>"])
        return "\n".join(lines)
    lines = [
        '        <div class="publication-group">',
        f"          <h3>{year}</h3>",
        '          <ol class="publication-list">',
    ]
    lines.extend(render_item(publication, "            ") for publication in publications)
    lines.extend(["          </ol>", "        </div>"])
    return "\n".join(lines)


def replace_between(path: Path, start_marker: str, end_marker: str, content: str) -> None:
    """Replace generated content between a unique marker pair."""

    source = path.read_text(encoding="utf-8")
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise ValueError(f"Expected one marker pair in {path}")
    start = source.index(start_marker) + len(start_marker)
    end = source.index(end_marker, start)
    path.write_text(source[:start] + "\n" + content + "\n        " + source[end:], encoding="utf-8")


def main() -> None:
    """Render the homepage selection and the complete publication archive."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bib", type=Path, required=True, help="Source BibTeX file")
    parser.add_argument("--home", type=Path, required=True, help="Homepage HTML file")
    parser.add_argument("--archive", type=Path, required=True, help="Publication archive HTML file")
    parser.add_argument("--latest", type=int, default=5, help="Number of homepage publications")
    arguments = parser.parse_args()

    publications = normalise_publications(parse_bibtex(arguments.bib.read_text(encoding="utf-8")))
    if not publications:
        raise ValueError("The bibliography contains no publications by Angela Cortecchia")

    home_groups: dict[int, list[Publication]] = defaultdict(list)
    for publication in publications[: arguments.latest]:
        home_groups[publication.year].append(publication)
    home_html = "\n".join(
        ["        <!-- Generated by scripts/render_publications.py. Do not edit manually. -->"]
        + [render_group(year, home_groups[year], archive=False) for year in sorted(home_groups, reverse=True)]
    )

    archive_groups: dict[int, list[Publication]] = defaultdict(list)
    for publication in publications:
        archive_groups[publication.year].append(publication)
    archive_html = "\n\n".join(
        ["      <!-- Generated by scripts/render_publications.py. Do not edit manually. -->"]
        + [render_group(year, archive_groups[year], archive=True) for year in sorted(archive_groups, reverse=True)]
    )

    replace_between(arguments.home, HOME_START, HOME_END, home_html)
    replace_between(arguments.archive, ARCHIVE_START, ARCHIVE_END, archive_html)
    print(f"Rendered {len(publications)} publications; {min(arguments.latest, len(publications))} on the homepage.")


if __name__ == "__main__":
    main()
