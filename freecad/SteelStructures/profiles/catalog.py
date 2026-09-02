# SPDX-License-Identifier: LGPL-2.1-or-later
"""Discovery, indexing and queries for schema-v2 profile catalogs."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .effective_properties import resolve_effective_section_properties
from .models import ProfileRef
from .validation import CatalogValidationError, ProfileNotFoundError, validate_catalog_payload


def canonicalize_designation(value: str) -> str:
    """Normalize equivalent inch marks to the catalog's stable spelling."""
    return str(value).replace("″", '"')


def normalize_search_text(value: str) -> str:
    """Normalize commercial designations for tolerant substring matching."""
    return "".join(canonicalize_designation(value).casefold().replace(",", ".").split())


class ProfileLibrary:
    """In-memory, reloadable collection of one or more schema-v2 catalogs."""

    def __init__(self, catalogs_dir: Path):
        self.catalogs_dir = Path(catalogs_dir)
        self._loaded = False
        self._clear()

    def _clear(self):
        self._catalogs = {}
        self._categories = []
        self._series = []
        self._profiles = []
        self._categories_by_key = {}
        self._series_by_key = {}
        self._profiles_by_ref = {}
        self._series_by_category = defaultdict(list)
        self._profiles_by_series = defaultdict(list)
        self._search_text = {}

    def _ensure_loaded(self):
        if not self._loaded:
            self.reload()

    def reload(self):
        """Discard all indices, re-read every JSON file and validate again."""
        self._clear()
        # Development fixtures are intentionally isolated from sourced catalogs,
        # but are part of the installed library and therefore survive restarts.
        paths = sorted(self.catalogs_dir.glob("*.json"), key=lambda path: path.name)
        paths.extend(sorted((self.catalogs_dir / "dev").glob("*.json"), key=lambda path: path.name))
        for path in paths:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise CatalogValidationError(f"{path.name}: não foi possível ler o catálogo: {exc}") from exc
            metadata, categories, series, profiles = validate_catalog_payload(payload, path)
            try:
                profiles = tuple(
                    resolve_effective_section_properties(profile) for profile in profiles
                )
            except (TypeError, ValueError) as exc:
                raise CatalogValidationError(
                    f"{path.name} [{metadata.id}]: propriedade efetiva inválida: {exc}"
                ) from exc
            duplicate_ref = next(
                (profile.ref for profile in profiles if profile.ref in self._profiles_by_ref),
                None,
            )
            if duplicate_ref is not None:
                raise CatalogValidationError(
                    f"{path.name} [{metadata.id}]: ProfileRef duplicada: {duplicate_ref!r}"
                )
            if metadata.id in self._catalogs:
                raise CatalogValidationError(f"{path.name} [{metadata.id}]: catalog.id duplicado")
            self._catalogs[metadata.id] = metadata
            self._categories.extend(categories)
            self._series.extend(series)
            for item in categories:
                self._categories_by_key[(item.catalog_id, item.id)] = item
            for item in series:
                self._series_by_key[(item.catalog_id, item.id)] = item
                self._series_by_category[(item.catalog_id, item.category_id)].append(item)
            for profile in profiles:
                self._profiles.append(profile)
                self._profiles_by_ref[profile.ref] = profile
                self._profiles_by_series[(profile.ref.catalog_id, profile.series_id)].append(profile)
                terms = (profile.designation,) + profile.aliases
                self._search_text[profile.ref] = tuple(normalize_search_text(term) for term in terms)
        self._loaded = True
        return self

    def list_catalogs(self):
        self._ensure_loaded()
        return tuple(self._catalogs.values())

    def list_categories(self):
        self._ensure_loaded()
        return tuple(self._categories)

    def list_series(self, category_id=None):
        self._ensure_loaded()
        if category_id is None:
            return tuple(self._series)
        return tuple(item for item in self._series if item.category_id == category_id)

    def list_profiles(self, category_id=None, series_id=None):
        self._ensure_loaded()
        return tuple(
            profile for profile in self._profiles
            if (category_id is None or profile.category_id == category_id)
            and (series_id is None or profile.series_id == series_id)
        )

    def get(self, ref: ProfileRef):
        self._ensure_loaded()
        if not isinstance(ref, ProfileRef):
            raise TypeError("ref deve ser ProfileRef")
        try:
            return self._profiles_by_ref[ref]
        except KeyError as exc:
            raise ProfileNotFoundError(f"Perfil não encontrado: {ref!r}") from exc

    def search(self, text, category_id=None, series_id=None):
        self._ensure_loaded()
        needle = normalize_search_text(text)
        if not needle:
            return self.list_profiles(category_id, series_id)
        return tuple(
            profile for profile in self.list_profiles(category_id, series_id)
            if any(needle in term for term in self._search_text[profile.ref])
        )
