from __future__ import annotations

import enum
import json
import logging
from pathlib import Path
import subprocess
from typing import Any

from pelican import ArticlesGenerator, PagesGenerator, signals
from pelican.contents import Article, Page

LOGGER = logging.getLogger(__name__)

BibliographyData = dict[str, Any]


@enum.unique
class BibliographyFormat(enum.Enum):
    BIBLATEX = "biblatex"
    BIBTEX = "bibtex"
    CSLJSON = "csljson"

    @staticmethod
    def guess(extension: str) -> BibliographyFormat:
        if extension.lower().lstrip(".") == "bib":
            return BibliographyFormat.BIBLATEX
        elif extension.lower().lstrip(".") == "json":
            return BibliographyFormat.CSLJSON
        else:
            raise RuntimeError(
                f"Failed to guess bibliography format for extension: {extension}"
            )


def get_bibliography(self, content: Article | Page) -> BibliographyData | None:
    if "Bibliography" not in content.metadata:
        return None

    path = Path(content.metadata)
    if not path.exists():
        LOGGER.error(f"bibliography file does not exist: {path}")
        return None

    if "BibliographyFormat" in content.metadata:
        bibformat = BibliographyFormat(content.metadata["BibliographyFormat"].lower())
    else:
        bibformat = BibliographyFormat.guess(path.suffix)

    with open(path) as fptr:
        data = fptr.read()

    if bibformat != BibliographyFormat.CSLJSON:
        data = (
            subprocess.check_output(
                [
                    "pandoc",
                    f"--from={bibformat}",
                    f"--to={BibliographyFormat.CSLJSON}",
                    "--output=-",
                ],
                input=data.encode(),
            )
            .decode()
            .strip()
        )

    return json.loads(data)


def process_content(self, content: Article | Page):
    if "Bibliography" not in content.metadata:
        return


class ReferencesProcessor:
    def __init__(self, generators: list[ArticlesGenerator | PagesGenerator]):
        self.generators = [
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


def add_references():
    pass


def register():
    signals.all_generators_finalized.connect(add_references)
