"""FreeCAD 1.1.3 probe for whole-object and future subelement source links.

Run with ``freecad/`` on ``sys.path`` using FreeCAD or FreeCADCmd.  Kept outside
unittest discovery because native property serialization is the behavior tested.
"""

import os
import tempfile

import FreeCAD as App
import Part


def run():
    handle, path = tempfile.mkstemp(prefix="steel_structures_plate_link_", suffix=".FCStd")
    os.close(handle)
    doc = None
    reopened = None
    try:
        doc = App.newDocument("PlateLinkProbe")
        source = doc.addObject("Part::Feature", "Source")
        source.Shape = Part.makeBox(10, 10, 1)
        whole = doc.addObject("Part::FeaturePython", "WholeLink")
        whole.addProperty("App::PropertyLink", "SourceObject")
        whole.SourceObject = source
        sub = doc.addObject("Part::FeaturePython", "SubLink")
        sub.addProperty("App::PropertyLinkSub", "SourceObject")
        sub.SourceObject = (source, ["Face1"])
        whole_sub = doc.addObject("Part::FeaturePython", "WholeLinkSub")
        whole_sub.addProperty("App::PropertyLinkSub", "SourceObject")
        whole_sub.SourceObject = (source, [])
        doc.recompute()
        print("BEFORE", whole.SourceObject.Name, sub.SourceObject[1], whole_sub.SourceObject[1], flush=True)
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        doc = None
        reopened = App.openDocument(path)
        assert reopened.WholeLink.SourceObject.Name == "Source"
        assert reopened.SubLink.SourceObject[0].Name == "Source"
        assert tuple(reopened.SubLink.SourceObject[1]) == ("Face1",)
        assert reopened.WholeLinkSub.SourceObject[0].Name == "Source"
        assert tuple(reopened.WholeLinkSub.SourceObject[1]) == ()
        print("AFTER OK", flush=True)
    finally:
        for candidate in (reopened, doc):
            if candidate is not None:
                App.closeDocument(candidate.Name)
        os.remove(path)


if __name__ == "__main__":
    run()
