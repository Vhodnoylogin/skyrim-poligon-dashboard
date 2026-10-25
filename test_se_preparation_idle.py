import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
import polygon

class SEPreparationIdleTests(unittest.TestCase):
    def test_both_editions_and_loaders_block_preparation(self):
        p=polygon.Polygon.__new__(polygon.Polygon);p.executor=Mock()
        for name in ('SkyrimSE.exe','skse64_loader.exe','SkyrimVR.exe','sksevr_loader.exe','vrcompositor.exe'):
            with self.subTest(name=name), patch.dict(sys.modules, {'skyrim_autotest':SimpleNamespace(native=SimpleNamespace(processes=lambda:[{'name':name}]))}):
                self.assertFalse(p.environment_idle())
        with patch.dict(sys.modules, {'skyrim_autotest':SimpleNamespace(native=SimpleNamespace(processes=lambda:[{'name':'explorer.exe'}]))}):
            self.assertTrue(p.environment_idle())

if __name__=='__main__':unittest.main()
