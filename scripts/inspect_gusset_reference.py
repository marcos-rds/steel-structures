"""Read-only inspection of saved configurations and current pure outlines."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.connections import connection_participants


def inspect(path):
    with zipfile.ZipFile(path, "r") as archive:
        root = ET.fromstring(archive.read("Document.xml"))
    saved = {}
    for obj in root.findall("./ObjectData/Object"):
        props = {p.get("name"): p for p in obj.findall("./Properties/Property")}
        if all(key in props for key in ("SourceSignature", "ParentTruss", "NodeKey")):
            saved[(props["ParentTruss"][0].get("value"),
                   props["NodeKey"][0].get("value"))] = json.loads(
                       props["SourceSignature"][0].get("value"))
    for obj in root.findall("./ObjectData/Object"):
        props = {p.get("name"): p for p in obj.findall("./Properties/Property")}
        if "AppliedState" not in props:
            continue
        config = json.loads(props["AppliedState"][0].get("value"))["candidate"]["config"]
        candidate = build_candidate(config)
        outlines, diagnostics = preliminary_gusset_outlines(candidate)
        print(obj.get("name"), config["envelope_type"], config["topology_preset"])
        for outline in outlines:
            node = outline.spec.node_key
            print(json.dumps(dict(node=node,
                saved_points=saved.get((obj.get("name"), node), {}).get("points"),
                participants=[(p.role, p.end) for p in connection_participants(candidate, node)],
                points=outline.points, edges=[e.kind for e in outline.semantic_edges],
                thickness=outline.spec.plate_thickness, margin=outline.spec.edge_margin,
                overlap=outline.spec.member_overlap), ensure_ascii=True))
        for diagnostic in diagnostics:
            print(diagnostic)


if __name__ == "__main__":
    inspect(sys.argv[1])
