"""C6-H contact and depth remain independent across intent persistence."""

import json
import unittest

from freecad.SteelStructures.connections import (
    CONNECTION_INTENT_SCHEMA_VERSION, ConnectionIntent, GussetChordContact,
    GussetFitSpec, dumps, loads,
)
from freecad.SteelStructures.trusses.connections import intent_from_data


class GussetSchemaC6HTests(unittest.TestCase):
    def test_independent_fields_roundtrip(self):
        original = ConnectionIntent(
            "N:connection", "N", gusset=GussetFitSpec(
                plate_thickness=10., chord_contact=GussetChordContact.TRUSS_EXTERIOR,
                transverse_placement="N:gap:NearA"))
        restored = loads(dumps(original))
        self.assertEqual(restored.gusset.chord_contact,
                         GussetChordContact.TRUSS_EXTERIOR)
        self.assertEqual(restored.gusset.transverse_placement, "N:gap:NearA")
        self.assertEqual(restored.schema_version, CONNECTION_INTENT_SCHEMA_VERSION)

    def test_published_schema_and_local_c6_migrate_without_conflating_contact(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                data = {"schema_version": version, "intent_key": "N:connection",
                        "node_key": "N", "gusset": {"plate_thickness": 10.,
                        "attachment_mode": "Inner", "side": "FaceA"}}
                for migrated in (loads(json.dumps(data)), intent_from_data("N", data)):
                    self.assertEqual(migrated.gusset.chord_contact,
                                     GussetChordContact.AUTO)
                    self.assertEqual(migrated.gusset.transverse_placement, "")
                    self.assertEqual(migrated.gusset.attachment_mode.value, "Inner")
                    self.assertEqual(migrated.gusset.side.value, "FaceA")

    def test_bad_contact_or_non_string_placement_is_rejected(self):
        with self.assertRaises(ValueError):
            GussetFitSpec(chord_contact="SectionVoid")
        with self.assertRaises(ValueError):
            GussetFitSpec(transverse_placement=3)


if __name__ == "__main__":
    unittest.main()
