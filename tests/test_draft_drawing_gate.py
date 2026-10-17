"""Keep native/cleanup failures from becoming a successful GUI gate."""
import ast
from pathlib import Path
import re
import unittest


class DrawingGateSafetyTests(unittest.TestCase):
    def test_native_failure_signatures_are_rejected(self):
        path=Path(__file__).resolve().parents[1]/'scripts/run_draft_drawing_gate.py'
        tree=ast.parse(path.read_text(encoding='utf8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='fatal_log_lines')
        namespace=dict(re=re)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
        classify=namespace['fatal_log_lines']
        for line in ('Traceback (most recent call last):',
                     'Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.',
                     'The error message is: Access violation',
                     'Unhandled Base::Exception caught in GUIApplication::notify.'):
            self.assertEqual(classify(line),[line])
        self.assertEqual(classify('QString::arg: Argument missing'),[])

    def test_result_includes_cleanup_before_publication(self):
        source=(Path(__file__).resolve().parents[1]/'tests/manual_draft_drawing.py').read_text(encoding='utf8')
        self.assertLess(source.index("result['cleanup_errors']=cleanup_errors"),
                        source.index("(out/'result.json').write_text"))
        self.assertIn("result['ok']=False",source)
