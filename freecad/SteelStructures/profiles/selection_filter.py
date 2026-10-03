"""Filtered catalog choices, preserving the catalog's normal ordering."""
from .. import profile_catalog


class ProfileChoices:
    def __init__(self, predicate):
        self.predicate = predicate
        self._profiles = tuple(p for p in profile_catalog.profiles().values()
                               if predicate(p.definition))

    def categories(self):
        return [c for c in profile_catalog.categories()
                if any(p.category == c for p in self._profiles)]

    def series_for_category(self, category):
        return [s for s in profile_catalog.series_for_category(category)
                if self.designations(category, s)]

    def designations(self, category=None, series=None):
        return [p.designation for p in self._profiles
                if (category is None or p.category == category)
                and (series is None or p.series == series)]

    def selection(self, current, preferred=None):
        choices = self.designations()
        for value in (current, preferred):
            if value in choices:
                return value
        return next(iter(choices), None)
