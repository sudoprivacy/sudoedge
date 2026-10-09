"""Exercise installer activation checks against real Linux process bytes."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(Path('/proc/self/exe').exists(), 'Linux process filesystem required')
class CohostInstallTest(unittest.TestCase):
    def run_install(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            commands = home / 'commands'
            commands.mkdir()
            binary = home / 'source-cohost'
            shutil.copy2(shutil.which('sleep'), binary)
            install_root = home / 'installed'
            install_root.mkdir()
            (commands / 'systemctl').write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys
root = Path(os.environ['HOME'])
mode = os.environ['TEST_ACTIVATION_MODE']
args = sys.argv[1:]
if 'enable' in args:
    if mode == 'missing':
        (root / 'pid').write_text('0')
    elif not (root / 'pid').exists():
        child = subprocess.Popen([str(root / 'installed/nexusd-cohost'), '3600'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (root / 'pid').write_text(str(child.pid))
elif 'show' in args:
    print((root / 'pid').read_text())
''')
            (commands / 'systemctl').chmod(0o755)
            previous = None
            if mode in ['override', 'old-running']:
                previous_binary = home / 'override-cohost'
                shutil.copy2(shutil.which('tail'), previous_binary)
                if mode == 'old-running':
                    previous_binary = install_root / 'nexusd-cohost'
                    shutil.copy2(shutil.which('tail'), previous_binary)
                previous = subprocess.Popen([str(previous_binary), '-f', '/dev/null'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                (home / 'pid').write_text(str(previous.pid))
            env = {**os.environ, 'HOME': directory, 'PATH': str(commands) + os.pathsep + os.environ['PATH'], 'SUDOEDGE_COHOST_INSTALL_ROOT': str(install_root), 'TEST_ACTIVATION_MODE': mode}
            try:
                result = subprocess.run(['bash', str(ROOT / 'scripts/install-cohost.sh'), str(binary)], env=env, text=True, capture_output=True, timeout=15)
                self.assertEqual((install_root / 'nexusd-cohost').read_bytes(), binary.read_bytes())
                if mode == 'correct':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('Installed sudoedge-cohost.service', result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('Installed sudoedge-cohost.service', result.stdout)
                    self.assertIn('no running main process' if mode == 'missing' else 'did not activate the requested binary', result.stderr)
                if previous:
                    self.assertIsNone(previous.poll(), 'staging must preserve the old running process')
            finally:
                if previous:
                    previous.terminate()
                    previous.wait(timeout=5)
                elif (home / 'pid').exists():
                    pid = int((home / 'pid').read_text())
                    if pid > 0:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass

    def test_fresh_install_verifies_the_running_binary(self):
        self.run_install('correct')

    def test_execstart_override_cannot_report_upgrade_success(self):
        self.run_install('override')

    def test_active_old_binary_is_preserved_and_requires_activation(self):
        self.run_install('old-running')

    def test_missing_main_process_cannot_report_success(self):
        self.run_install('missing')


if __name__ == '__main__':
    unittest.main()
