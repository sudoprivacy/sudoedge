"""Run the shared actual-process regressions through the appliance adapter."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT/'scripts/sudostack.lock.json').read_text())
STACK = Path(os.environ['SUDOSTACK_DEPLOY_ROOT']).resolve()
TEST = STACK/LOCK['testPath']
assert hashlib.sha256(TEST.read_bytes()).hexdigest() == LOCK['testSha256'], 'Shared test source differs from the locked producer'
spec = importlib.util.spec_from_file_location('shared_cohost_tests', TEST)
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


class EdgeCohostTests(shared.CohostTests):
    def test_checkpoint_entry_and_both_locked_dependencies(self):
        command = [sys.executable, str(ROOT/'scripts/stack-action.py'), 'checkpoint', '--help']
        actual = subprocess.run(command, env={**self.environment,'SUDOSTACK_DEPLOY_ROOT':str(STACK)}, capture_output=True,text=True,timeout=15)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertIn('Cold checkpoint', actual.stdout)
        fake = self.root/'changed-stack/tools/deploy'
        fake.mkdir(parents=True)
        (fake/'cohost.py').write_bytes((STACK/LOCK['path']).read_bytes())
        (fake/'checkpoint.py').write_text('raise RuntimeError("must not execute")')
        changed = subprocess.run(command, env={**self.environment,'SUDOSTACK_DEPLOY_ROOT':str(fake.parents[1])},capture_output=True,text=True,timeout=15)
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn('does not match the pinned source',changed.stderr)
        self.assertNotIn('must not execute',changed.stderr)

    def test_tampered_shared_action_is_rejected_before_execution(self):
        fake = self.root/'changed-stack/tools/deploy'
        fake.mkdir(parents=True)
        (fake/'cohost.py').write_text('raise RuntimeError("must not execute")')
        result = subprocess.run([os.sys.executable,str(ROOT/'scripts/stack-action.py'),'--help'],
                                env={**self.environment,'SUDOSTACK_DEPLOY_ROOT':str(fake.parents[1])},
                                capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('does not match the pinned source',result.stderr)
        self.assertNotIn('must not execute',result.stderr)

    def invoke(self, command='install', **overrides):
        values = {'binary':str(self.binary), 'sha256':self.sha, 'source':shared.COMMIT,
                  'unit':'test-cohost', 'bind':'127.0.0.1:22141', 'zone':'test-zone',
                  'root':str(self.root/'state'), 'config':str(self.root/'config'),
                  'install-root':str(self.root/'versions')}
        values.update(overrides)
        names = {'sha256':'SHA256', 'source':'SOURCE', 'bind':'BIND_ADDR', 'zone':'CLUSTER',
                 'root':'ROOT', 'config':'CONFIG_HOME', 'install-root':'INSTALL_ROOT'}
        environment = {**self.environment, 'SUDOSTACK_DEPLOY_ROOT':str(STACK),
                       'SUDOEDGE_DEPLOY_COMMAND':command,
                       **{'SUDOEDGE_COHOST_'+target:values[key] for key,target in names.items()}}
        return subprocess.run(['bash',str(ROOT/'scripts/install-cohost.sh'),values['binary'],values['unit']],
                              env=environment,capture_output=True,text=True,timeout=15)


checkpoint_test = STACK/LOCK['checkpointTestPath']
assert hashlib.sha256(checkpoint_test.read_bytes()).hexdigest() == LOCK['checkpointTestSha256']
sys.path.insert(0, str(checkpoint_test.parent))
checkpoint_spec = importlib.util.spec_from_file_location('shared_checkpoint_tests', checkpoint_test)
checkpoint_shared = importlib.util.module_from_spec(checkpoint_spec)
checkpoint_spec.loader.exec_module(checkpoint_shared)


class EdgeCheckpointTests(checkpoint_shared.CheckpointTests):
    pass


if __name__ == '__main__':
    unittest.main()
