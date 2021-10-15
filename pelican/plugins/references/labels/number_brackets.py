from __future__ import annotations

from pybtex.style import FormattedBibliography, FormattedEntry
from pybtex.style.labels import BaseLabelStyle


class LabelStyle(BaseLabelStyle):
    def format_labels(self, sorted_entries: FormattedEntry):
        for number, _ in enumerate(sorted_entries):
            yield f"[{number+1}]"

    def inline_label(
        self,
        citekeys: list[str],
        bibliography: FormattedBibliography,
    ) -> str:
        stripped_labels: list[str] = []
        indices: list[int] = []

        for citekey in citekeys:
            for index, entry in enumerate(bibliography.entries):
                if entry.key == citekey:
                    stripped_labels.append(entry.label.lstrip("[").rstrip("]"))
                    indices.append(index)
                    break
            else:
                raise KeyError(citekey)
        links = [
            f'<a href="#reference{index+1}">{label}</a>'
            for index, label in zip(indices, stripped_labels)
        ]
        return "<sup>[" + ", ".join(links) + "]</sup>"
