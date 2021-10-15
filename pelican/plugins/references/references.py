from __future__ import annotations

import io
import logging
from pathlib import Path
import re
import subprocess

from bs4 import BeautifulSoup
from pybtex.plugin import find_plugin, register_plugin
from pybtex.style import FormattedBibliography

from pelican import ArticlesGenerator, PagesGenerator, signals
from pelican.contents import Article, Page
import pelican.generators
from pelican.plugins.references.labels import number_brackets

register_plugin("pybtex.style.labels", "number_brackets", number_brackets.LabelStyle)

LOGGER = logging.getLogger(__name__)

REGEX_CITATION = re.compile(r"\[@([\w\d]+)\]", re.MULTILINE)


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


def format_bibliography(
    bibliography: str,
    citations: list[str],
    bibliography_style: str = "unsrt",
    label_style: str = "number_brackets",
    name_style: str = "plain",
    sorting_style: str = "none",
) -> FormattedBibliography:
    from pybtex.database.input.bibtex import Parser
    from pybtex.plugin import find_plugin
    from pybtex.style.formatting import BaseStyle

    bib_data = Parser(wanted_entries=citations).parse_string(bibliography)

    style: BaseStyle = find_plugin("pybtex.style.formatting", bibliography_style)(
        label_style=label_style,
        sorting_style=sorting_style,
        name_style=name_style,
    )

    return style.format_bibliography(bib_data, citations)


def render_bibliography(formatted_bibliography: FormattedBibliography) -> str:
    from pybtex.backends.html import Backend

    backend = Backend()
    html = backend.write_to_file(formatted_bibliography, io.StringIO())

    # add ids for each reference
    soup = BeautifulSoup(html, "html.parser")
    for index, tag in enumerate(soup.find_all("dt")):
        tag["id"] = f"reference{index+1}"

    return str(soup)


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
            ),
        )

    return citations


def inline_label_fallback(
    citekeys: list[str],
    bibliography: FormattedBibliography,
) -> str:
    labels: list[str] = []
    indices: list[int] = []

    for citekey in citekeys:
        for index, entry in enumerate(bibliography.entries):
            if entry.key == citekey:
                labels.append(entry.label)
                indices.append(index)
                break
        else:
            raise KeyError(citekey)
    links = [
        f'<a href="#reference{index+1}">{label}</a>'
        for index, label in zip(indices, labels)
    ]
    return "<sup>" + ", ".join(links) + "</sup>"


def replace_citations(
    content: Article | Page,
    citations: list[Citation],
    formatted_bibliography: FormattedBibliography,
    label_style: str = "number_brackets",
):
    label_plugin = find_plugin("pybtex.style.labels", label_style)()
    for citation in reversed(citations):
        try:
            label = label_plugin.inline_label(citation.citekeys, formatted_bibliography)
        except AttributeError:
            label = inline_label_fallback(citation.citekeys, formatted_bibliography)
        content._content = (
            content._content[: citation.start]
            + label
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
        LOGGER.warning(f"no citations in article: {content.source_path}")
        return

    citekeys = []
    for citation in citations:
        for citekey in citation.citekeys:
            if citekey not in citekeys:
                citekeys.append(citekey)

    formatted_bib = format_bibliography(bibliography, citekeys)
    rendered_bib = render_bibliography(formatted_bib)

    replace_citations(content, citations, formatted_bib)

    content._content += rendered_bib


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
