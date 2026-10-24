"""The native checker must refuse execution in the real host network namespace."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class BoundaryTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux') and os.getuid() != 0, 'Unprivileged Linux required')
    def test_missing_os_isolation_refuses_before_any_candidate_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root/'profile.json'
            profile.write_text(json.dumps({'hostNetworkNamespace':os.readlink('/proc/self/ns/net'),
                                          'candidate':{'path':'must-never-execute'}, 'evidence':str(root/'evidence')}))
            for worker in ['cohost-checkpoint-boot.py','product-checkpoint-boot.py']:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name(worker)), str(profile)],
                                        capture_output=True,text=True,timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('separate network namespace is required', result.stderr)
                self.assertFalse((root/'evidence').exists())


if __name__ == '__main__':
    unittest.main()
