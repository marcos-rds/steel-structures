"""Run the real Task View layout regression in an isolated GUI process."""
import json
import os
from pathlib import Path
import sys
import traceback
import unittest


if os.environ.get('SS_DUOPITCH_ROOT'):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore,QtWidgets
    root=Path(os.environ['SS_DUOPITCH_ROOT'])
    out=Path(os.environ['SS_DUOPITCH_OUT'])
    sys.path.insert(0,str(root))
    import freecad
    freecad.__path__.insert(0,str(root/'freecad'))
    def launch():
        errors=[]
        previous_hook=sys.excepthook
        sys.excepthook=lambda kind,error,trace:errors.append(''.join(traceback.format_exception(kind,error,trace)))
        try:
            import freecad.SteelStructures.init_gui
            Gui.activateWorkbench('SteelStructuresWorkbench')
            Gui.getMainWindow().show()
            Gui.Control.showTaskView()
            qss=os.environ.get('SS_TRUSS_EDITOR_QSS')
            if qss:
                path=Path(qss)
                QtCore.QDir.addSearchPath('qss',str(path.parent))
                QtWidgets.QApplication.instance().setStyleSheet(path.read_text(encoding='utf-8'))
            from tests.test_truss_reference_layout import ReferenceLayoutTests
            suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceLayoutTests)
            result=unittest.TextTestRunner(verbosity=2).run(suite)
            record=dict(ok=result.wasSuccessful() and not errors,tests=result.testsRun,
                        failures=[(str(test),trace) for test,trace in result.failures],
                        errors=[(str(test),trace) for test,trace in result.errors],qt_errors=errors,
                        dpi=QtWidgets.QApplication.primaryScreen().logicalDotsPerInch(),
                        device_pixel_ratio=QtWidgets.QApplication.primaryScreen().devicePixelRatio())
        except Exception: record=dict(ok=False,error=traceback.format_exc())
        finally: sys.excepthook=previous_hook
        (out/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        QtCore.QTimer.singleShot(0,QtWidgets.QApplication.quit)
    QtCore.QTimer.singleShot(500,launch)
