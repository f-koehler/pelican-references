from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Any

from pelican import ArticlesGenerator, PagesGenerator, signals
from pelican.contents import Article, Page
import pelican.generators

LOGGER = logging.getLogger(__name__)

BibliographyData = dict[str, Any]

REGEX_CITATION = re.compile(r"\[\s*\@([\w\d]+)\s*\]", re.MULTILINE)


def guess_bibformat(extension: str) -> str:
    if extension.lower().lstrip(".") == "bib":
        return "biblatex"
    elif extension.lower().lstrip(".") == "json":
        return "csljson"
    else:
        raise RuntimeError(
            f"Failed to guess bibliography format for extension: {extension}"
        )


class Citation:
    def __init__(self, start: int, end: int, citekeys: list[str]):
        self.start = start
        self.end = end
        self.citekeys = citekeys

    def __str__(self) -> str:
        return str({"start": self.start, "end": self.end, "citekeys": self.citekeys})


def get_bibliography(content: Article | Page) -> BibliographyData | None:
    if "bibliography" not in content.metadata:
        return None

    path = Path(content.source_path).parent / content.metadata["bibliography"]
    if not path.exists():
        LOGGER.error(f"bibliography file does not exist: {path}")
        return None

    if "bibliographyformat" in content.metadata:
        bibformat = content.metadata["bibliographyformat"].lower()
    else:
        bibformat = guess_bibformat(path.suffix)

    with open(path) as fptr:
        data = fptr.read()

    if bibformat != "csljson":
        data = (
            subprocess.check_output(
                [
                    "pandoc",
                    f"--from={bibformat}",
                    "--to=csljson",
                    "--output=-",
                ],
                input=data.encode(),
            )
            .decode()
            .strip()
        )

    return json.loads(data)


def find_citations(content: Article | Page) -> list[Citation]:
    matches: list[re.Match] = list(REGEX_CITATION.finditer(content._content))
    citations: list[Citation] = []

    for match in matches:
        citations.append(
            Citation(
                match.start(),
                match.end(),
                [citekey.strip().lstrip("@") for citekey in match.group(1).split(",")],
            )
        )

    return citations


def generate_reference_numbers(citations: list[Citation]) -> dict[str, int]:
    counter = 1
    mapping: dict[str, int] = {}
    for citation in citations:
        for citekey in citation.citekeys:
            if citekey in mapping:
                continue

            mapping[citekey] = counter
            counter += 1

    return mapping


def replace_citations(
    content: Article | Page,
    citations: list[Citation],
    reference_numbers: dict[str, int],
):
    for citation in reversed(citations):
        replacement = (
            "<sup>["
            + ",".join(
                [
                    '<a href="#reference'
                    + str(reference_numbers[key])
                    + '">'
                    + str(reference_numbers[key])
                    + "</a>"
                    for key in citation.citekeys
                ]
            )
            + "]</sup>"
        )
        content._content = (
            content._content[: citation.start]
            + replacement
            + content._content[citation.end :]
        )


def process_content(content: Article | Page):
    if "bibliography" not in content.metadata:
        return

    bibliography = get_bibliography(content)
    if not bibliography:
        return

    citations = find_citations(content)
    if not citations:
        LOGGER.warn(f"no citations in article: {content.source_path}")
        return

    reference_numbers = generate_reference_numbers(citations)

    replace_citations(content, citations, reference_numbers)


class ReferencesProcessor:
    def __init__(self, generators: list[pelican.generators.Generator]):
        self.generators: list[ArticlesGenerator | PagesGenerator] = [
            generator
            for generator in generators
            if isinstance(generator, ArticlesGenerator)
            or isinstance(generator, PagesGenerator)
        ]

    def process(self):
        for generator in self.generators:
            if isinstance(generator, ArticlesGenerator):
                articles: list[Article] = (
                    generator.articles
                    + generator.translations
                    + generator.drafts
                    + generator.drafts_translations
                )

                for article in articles:
                    process_content(article)

            elif isinstance(generator, PagesGenerator):
                pages: list[Page] = (
                    generator.pages
                    + generator.translations
                    + generator.draft_pages
                    + generator.draft_translations
                )

                for page in pages:
                    process_content(page)


def add_references(generators: list[pelican.generators.Generator]):
    processor = ReferencesProcessor(generators)
    processor.process()


def register():
    signals.all_generators_finalized.connect(add_references)
