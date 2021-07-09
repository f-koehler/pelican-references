from __future__ import annotations

import io
import logging
from pathlib import Path
import re
import subprocess

import jinja2

from pelican import ArticlesGenerator, PagesGenerator, signals
from pelican.contents import Article, Page
import pelican.generators

LOGGER = logging.getLogger(__name__)

REGEX_CITATION = re.compile(r"\[\s*\@([\w\d]+)\s*\]", re.MULTILINE)

ENV_CITESTYLES = jinja2.Environment(
    loader=jinja2.PackageLoader("pelican.plugins.references", "citestyles"),
)


def read_bibliography(content: Article | Page) -> str:
    if "bibliography" not in content.metadata:
        return ""

    path = Path(content.source_path).parent / content.metadata["bibliography"]
    if not path.exists():
        LOGGER.error(f"bibliography file does not exist: {path}")
        return ""

    with open(path) as fptr:
        bibcontent = fptr.read()

    if path.suffix.lower().lstrip().strip() == "json":
        bibcontent = (
            subprocess.check_output(
                [
                    "pandoc",
                    "--from=csljson",
                    "--to=bibtex",
                    "--output=-",
                ],
                input=bibcontent.encode(),
            )
            .decode()
            .strip()
        )

    return bibcontent


def render_bibliography(
    bibliography: str,
    citations: list[str],
    bibliography_style: str = "unsrt",
    label_style: str = "number",
    name_style: str = "plain",
    sorting_style: str = "none",
):
    from pybtex.backends.html import Backend
    from pybtex.database.input.bibtex import Parser
    from pybtex.plugin import find_plugin
    from pybtex.style.formatting import BaseStyle

    bib_data = Parser(wanted_entries=citations).parse_string(bibliography)

    style: BaseStyle = find_plugin("pybtex.style.formatting", bibliography_style)(
        label_style=label_style, sorting_style=sorting_style, name_style=name_style
    )

    formatted_bibliography = style.format_bibliography(bib_data, citations)

    backend = Backend()
    return backend.write_to_file(formatted_bibliography, io.StringIO())


class Citation:
    def __init__(self, start: int, end: int, citekeys: list[str]):
        self.start = start
        self.end = end
        self.citekeys = citekeys

    def __str__(self) -> str:
        return str({"start": self.start, "end": self.end, "citekeys": self.citekeys})


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
    template = ENV_CITESTYLES.get_template("numeric/inline.html")

    for citation in reversed(citations):
        content._content = (
            content._content[: citation.start]
            + template.render(
                citation=citation, reference_numbers=reference_numbers
            ).strip()
            + content._content[citation.end :]
        )


def process_content(content: Article | Page):
    if "bibliography" not in content.metadata:
        return

    bibliography = read_bibliography(content)
    if not bibliography:
        return

    citations = find_citations(content)
    if not citations:
        LOGGER.warn(f"no citations in article: {content.source_path}")
        return

    citekeys = []
    for citation in citations:
        for citekey in citation.citekeys:
            if citekey not in citekeys:
                citekeys.append(citekey)

    reference_numbers = generate_reference_numbers(citations)

    replace_citations(content, citations, reference_numbers)

    rendered = render_bibliography(bibliography, citekeys)

    content._content += rendered


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
