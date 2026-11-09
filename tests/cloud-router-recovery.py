"""Exercise the Edge boot adapter through the real shared Moss HTTP boundary."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class CloudRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.received = []
        self.organization = 'edge-org'
        self.secret = {'value': 'synthetic-upstream-key', 'status': 'enabled', 'version': 1}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_unused):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.received.append((self.path, body))
                self.reply({'access_token': 'synthetic-access-token', 'organization': {'id': outer.organization}})

            def do_GET(self):
                outer.received.append((self.path, self.headers.get('Authorization')))
                self.reply({'success': True, 'data': outer.secret})

            def reply(self, value):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        credentials = self.home/'controller-login.json'
        credentials.write_text(json.dumps({'username': 'admin', 'password': 'synthetic-login-password'}))
        credentials.chmod(0o600)
        self.config = {
            'schemaVersion': 1,
            'moss': {'origin': f'http://127.0.0.1:{self.server.server_port}', 'organizationId': 'edge-org',
                     'credentialFile': str(credentials)},
            'secret': {'namespace': 'system:sudoedge-router', 'key': 'api-key'},
            'upstream': {'baseUrl': 'https://router.example.invalid', 'models': ['cloud-model']},
        }
        self.path = self.home/'.config/sudoedge/cloud-route.json'
        self.path.parent.mkdir(parents=True)
        self.save()
        self.restore = module('restore-cloud-router')
        self.home_patch = patch.object(Path, 'home', return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def save(self):
        self.path.write_text(json.dumps(self.config))
        self.path.chmod(0o600)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_boot_reads_vault_and_passes_key_only_in_memory(self):
        consumer = module('configure-router')
        actual_loader = self.restore.load_module
        def load(name, path):
            return consumer if name == 'edge_configure_router' else actual_loader(name, path)
        before = dict(os.environ)
        with patch.object(self.restore, 'load_module', side_effect=load), patch.object(consumer, 'configure') as configure:
            self.restore.restore()
        configure.assert_called_once_with({'baseUrl': 'https://router.example.invalid',
                                          'models': 'cloud-model', 'key': 'synthetic-upstream-key'})
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(self.received[1], ('/api/v1/secrets/system%3Asudoedge-router/api-key',
                                            'Bearer synthetic-access-token'))
        self.assertNotIn('synthetic-upstream-key', self.path.read_text())

    def test_disabled_secret_wrong_org_and_changed_library_stop_before_router_mutation(self):
        for failure in ['disabled', 'wrong-org', 'changed-library']:
            self.secret['status'] = 'disabled' if failure == 'disabled' else 'enabled'
            self.organization = 'another-org' if failure == 'wrong-org' else 'edge-org'
            with self.subTest(failure=failure), patch.object(self.restore, 'load_module', wraps=self.restore.load_module) as load:
                if failure == 'changed-library':
                    with patch.dict(os.environ, {'SUDOSTACK_DEPLOY_ROOT': str(self.home)}):
                        with self.assertRaises((OSError, ValueError)):
                            self.restore.restore()
                else:
                    with self.assertRaises(RuntimeError):
                        self.restore.restore()
                self.assertFalse(any(call.args[0] == 'edge_configure_router' for call in load.call_args_list))

    def test_missing_profile_preserves_local_only_installation(self):
        self.path.unlink()
        self.restore.restore()
        self.assertEqual(self.received, [])

    def test_insecure_upstream_or_world_readable_login_refused(self):
        self.config['upstream']['baseUrl'] = 'http://router.example.invalid'
        self.save()
        with self.assertRaises(ValueError):
            self.restore.restore()
        self.assertEqual(self.received, [])
        if os.name == 'posix':
            self.config['upstream']['baseUrl'] = 'https://router.example.invalid'
            self.save()
            Path(self.config['moss']['credentialFile']).chmod(0o644)
            with self.assertRaises(ValueError):
                self.restore.restore()
            self.assertEqual(self.received, [])

    @unittest.skipIf(os.name == 'nt', 'Actual appliance shell runs on Linux')
    def test_cloud_failure_still_refreshes_local_client_and_mount_then_reports_failure(self):
        bin_dir = self.home/'bin'; bin_dir.mkdir()
        repo = self.home/'repo'; (repo/'scripts').mkdir(parents=True)
        calls = self.home/'calls'
        (repo/'scripts/configure.sh').write_text('printf "local\\n" >> "$CALLS"\n')
        python = bin_dir/'python3'
        python.write_text('#!/bin/sh\ncase "$1" in\n-c) printf "synthetic-gpu-key";;\n'
                          '*restore-cloud-router.py) printf "cloud\\n" >> "$CALLS"; exit 42;;\n'
                          '*sync-moss-router.py) printf "sync\\n" >> "$CALLS";;\nesac\n')
        python.chmod(0o700)
        command = bin_dir/'sudoedge'
        command.write_text('#!/bin/sh\nprintf "mount\\n" >> "$CALLS"\n')
        command.chmod(0o700)
        mount_config = self.home/'mount.json';mount_config.write_text('{}')
        result = subprocess.run(['bash', str(ROOT/'scripts/reconfigure-on-boot.sh'), str(repo)],
            env={**os.environ, 'PATH': str(bin_dir)+os.pathsep+os.environ['PATH'], 'CALLS': str(calls),
                 'GPUSTACK_KEY_FILE': 'unused-fixture-path', 'SUDOEDGE_MODEL_MOUNT_CONFIG': str(mount_config)},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(calls.read_text().splitlines(), ['local', 'cloud', 'sync', 'mount'])


if __name__ == '__main__':
    unittest.main()
