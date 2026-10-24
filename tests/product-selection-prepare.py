import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
STACK = Path(os.environ['SUDOSTACK_DEPLOY_ROOT']).resolve()
LOCK = json.loads((ROOT/'scripts/sudostack.lock.json').read_text())
shared = STACK/LOCK['checkpointTestPath']
assert hashlib.sha256(shared.read_bytes()).hexdigest() == LOCK['checkpointTestSha256']
sys.path.insert(0,str(shared.parent))
import test_checkpoint
from cohost import digest, quoted, unit_path

spec = importlib.util.spec_from_file_location('edge_product_preparer',ROOT/'scripts/prepare-product-selection.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


@unittest.skipUnless(platform.system() == 'Linux','Linux real executable and native unit inspection')
class ProductPreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_checkpoint.CheckpointTests()
        self.fixture.setUp()
        self.home = self.fixture.home
        self.units = self.home/'units'
        self.units.mkdir(mode=0o700)
        self.old_app = self.home/'old-app.py'
        self.old_app.write_text('import time;time.sleep(600)\n')
        self.new_root = self.home/'versioned app%path'
        self.new_root.mkdir(mode=0o700)
        self.new_app = self.new_root/'new-app.py'
        self.new_app.write_text(self.old_app.read_text())
        self.binary = self.home/'new-python'
        shutil.copy2(Path(sys.executable).resolve(),self.binary)
        self.binary.chmod(0o700)
        plan = copy.deepcopy(self.fixture.plan)
        plan['paths'].update(units=str(self.units),oldEntry=str(self.old_app))
        plan['pins'].append({'path':str(self.old_app),'sha256':digest(self.old_app)})
        self.versions = []
        for index,unit in enumerate(plan['units']):
            child = self.fixture.children[unit['name']]
            child.terminate(); child.wait(timeout=5)
            self.fixture.children[unit['name']] = subprocess.Popen([sys.executable,self.old_app.name],cwd=self.home,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            path = self.units/unit['name']
            path.write_text('[Unit]\nDescription=Preserve this native unit\n[Service]\nType=simple\nWorkingDirectory='+unit_path(str(self.home))+
                            '\nEnvironment=UNCHANGED=value\nExecStart='+quoted(sys.executable)+' '+quoted(self.old_app.name)+'\n[Install]\nWantedBy=default.target\n')
            plan['pins'].append({'path':str(path),'sha256':digest(path)})
            version = {'unit':unit['name'],'binary':str(self.binary),'sha256':digest(self.binary),'source':'a'*40}
            if index == 0:
                version.update(entry={'before':str(self.old_app),'path':str(self.new_app),'sha256':digest(self.new_app)},workingDirectory=str(self.new_root))
            self.versions.append(version)
        self.profile = {'schemaVersion':1,'exclusiveConfigurationOwner':True,'checkpoint':plan,'versions':self.versions}
        self.original_dispatch = self.fixture.dispatch
        self.dropin = None
        def dispatch(*args):
            if args[0]=='show' and 'FragmentPath' in args[-1]:
                return 'FragmentPath='+str(self.units/args[1])+'\nDropInPaths='+('' if self.dropin is None else str(self.dropin))+'\nMainPID='+str(self.fixture.children[args[1]].pid)
            return self.original_dispatch(*args)
        self.fixture.control.stop()
        from unittest.mock import patch
        self.fixture.control = patch.object(test_checkpoint.checkpoint,'control',dispatch)
        self.fixture.control.start()

    def tearDown(self):
        self.fixture.tearDown()

    def test_prepares_only_selected_native_fields_and_keeps_live_processes_and_original_units(self):
        before = {name:(self.units/name).read_bytes() for name in self.fixture.children}
        pids = {name:child.pid for name,child in self.fixture.children.items()}
        result = native.prepare(self.profile,self.home/'prepared')
        self.assertEqual(result['status'],'prepared-only')
        self.assertFalse(result['servicesChanged'])
        plan = json.loads((self.home/'prepared/plan.json').read_text())
        prepared = Path(plan['selections'][0]['prepared']).read_text()
        position,value = native.service_assignments(prepared,'ExecStart')
        # Token splitting does not perform systemd's %% -> % specifier pass.
        self.assertEqual(shlex.split(value),[str(self.binary),str(self.new_app).replace('%','%%')])
        self.assertIn('Environment=UNCHANGED=value\n',prepared)
        self.assertIn('[Install]\nWantedBy=default.target\n',prepared)
        self.assertEqual({name:(self.units/name).read_bytes() for name in before},before)
        self.assertEqual({name:child.pid for name,child in self.fixture.children.items()},pids)
        self.assertEqual(self.fixture.calls,[])
        self.assertEqual((self.home/'prepared/plan.json').stat().st_mode&0o777,0o600)

    def test_changed_candidate_refuses_before_creating_prepared_files(self):
        self.profile['versions'][1]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError,'candidate executable changed'):
            native.prepare(self.profile,self.home/'prepared')
        self.assertFalse((self.home/'prepared').exists())
        self.assertEqual(self.fixture.calls,[])

    def test_exec_start_dropin_is_not_silently_overwritten(self):
        self.dropin = self.units/'override.conf'
        self.dropin.write_text('[Service]\nExecStart=\n')
        self.profile['checkpoint']['pins'].append({'path':str(self.dropin),'sha256':digest(self.dropin)})
        with self.assertRaisesRegex(ValueError,'drop-in overrides ExecStart'):
            native.prepare(self.profile,self.home/'prepared')
        self.assertFalse((self.home/'prepared').exists())


if __name__ == '__main__':
    unittest.main()
