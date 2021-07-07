from __future__ import annotations

from pelican import Pelican


class PelicanReferencesSettings:
    def __init__(self):
        self.citestyle: str = "numeric"
        self.bibstyle: str = "default"

    @staticmethod
    def from_settings(pelican: Pelican) -> PelicanReferencesSettings:
        obj = PelicanReferencesSettings()

        settings = pelican.settings.get("REFERENCES", None)

        if settings is None:
            return obj

        obj.citestyle = settings.get("citestyle", obj.citestyle)
        obj.bibstyle = settings.get("bibstyle", obj.bibstyle)

        return obj
