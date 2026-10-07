"""Check deployment model limits and ACP config using a local HTTP catalog."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class ModelConfigTest(unittest.TestCase):
    def test_launcher_uses_catalog_and_preserves_other_configuration(self):
        class Catalog(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'data': [
                    {'id': 'qwen3-30b', 'context_window': 65536, 'max_output_tokens': 4096},
                    {'id': 'cloud', 'context_window': 99999, 'max_output_tokens': 1000},
                ]}).encode())

            def log_message(self, *_args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Catalog)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'sudocode.json'
                config = {
                    'auth_modes': {'proxy': {'box': {'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'apiKey': 'test'}}},
                    'models': {'cloud': {'alias': 'keep-existing'}},
                    'permission': {'mode': 'default'},
                }
                path.write_text(json.dumps(config))
                with patch.dict(os.environ, {'SUDO_CODE_CONFIG_HOME': directory, 'SUDOEDGE_SCODE_BIN': '/test/scode'}), patch('os.execv') as execute:
                    module('scode-with-catalog').launch()
                actual = json.loads(path.read_text())
                self.assertEqual(actual['models']['qwen3-30b']['contextWindow'], 65536)
                self.assertEqual(actual['models']['qwen3-30b']['maxOutputTokens'], 4096)
                self.assertEqual(actual['models']['cloud'], config['models']['cloud'])
                self.assertEqual(actual['auth_modes'], config['auth_modes'])
                self.assertEqual(actual['permission'], config['permission'])
                self.assertEqual(execute.call_args.args[0], '/test/scode')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_invalid_limits_do_not_contact_router(self):
        with patch.dict(os.environ, {'MODEL_MAX_LEN': '4096', 'MODEL_MAX_OUTPUT_TOKENS': '4096'}), patch('urllib.request.urlopen') as request:
            with self.assertRaises(ValueError):
                module('configure-router').configure()
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
