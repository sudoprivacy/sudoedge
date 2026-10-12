"""Protect idempotent new-api provisioning and full-token retrieval."""
import importlib.util
import json
import os
import socket
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch


class RouterConfigTest(unittest.TestCase):
    def test_repeated_provisioning_preserves_cloud_and_retrieves_full_key(self):
        state = {'ready': False, 'setup_count': 0, 'key_reads': 0, 'setup_disconnects': 0,
                 'metadata': {'cloud-model': {'context_window': 12345}}, 'ratios': {'cloud-model': 2},
                 'groups': {'default': 1, 'custom': 2}, 'usable': {'custom': 'Existing group'},
                 'channels': [{'id': 1, 'name': 'sudorouter-cloud', 'key': 'cloud-secret', 'status': 1,
                               'group': 'default', 'models': 'qwen3-30b,cloud-model'}],
                 'tokens': [{'id': 1, 'name': 'sudocode', 'status': 1, 'group': 'default'}]}

        class Router(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def do_PUT(self):
                self.respond()

            def do_DELETE(self):
                self.respond()

            def log_message(self, *_args):
                pass

            def respond(self):
                size = int(self.headers.get('Content-Length', '0'))
                body = json.loads(self.rfile.read(size)) if size else None
                path = self.path.split('?')[0]
                data = None
                if path == '/api/setup':
                    if self.command == 'GET' and state['setup_disconnects'] < 2:
                        state['setup_disconnects'] += 1
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    if body:
                        state['ready'] = True
                        state['setup_count'] += 1
                    data = {'status': state['ready'], 'root_init': state['ready']}
                elif path == '/api/user/login':
                    data = {'access_token': 'admin-session', 'user': {'id': 1}}
                else:
                    if self.headers.get('Authorization') != 'Bearer admin-session':
                        self.send_error(401)
                        return
                    if path == '/api/option/':
                        if body and body['key'] == 'ModelMetadata':
                            state['metadata'] = json.loads(body['value'])
                        if body and body['key'] == 'ModelRatio':
                            state['ratios'] = json.loads(body['value'])
                        if body and body['key'] == 'GroupRatio':
                            state['groups'] = json.loads(body['value'])
                        if body and body['key'] == 'UserUsableGroups':
                            state['usable'] = json.loads(body['value'])
                        data = [{'key': 'ModelMetadata', 'value': json.dumps(state['metadata'])},
                                {'key': 'ModelRatio', 'value': json.dumps(state['ratios'])},
                                {'key': 'GroupRatio', 'value': json.dumps(state['groups'])},
                                {'key': 'UserUsableGroups', 'value': json.dumps(state['usable'])}]
                    elif path == '/api/channel/':
                        if self.command == 'POST':
                            state['channels'].append({'id': 2, **body['channel']})
                        elif self.command == 'PUT':
                            if 'status' in body:
                                self.send_error(400)
                                return
                            state['channels'] = [{**c, **body} if c['id'] == body['id'] else c for c in state['channels']]
                        data = {'items': state['channels']}
                    elif path == '/api/channel/2/status':
                        state['channels'][1]['status'] = body['status']
                    elif path == '/api/token/':
                        if body:
                            if self.command == 'PUT':
                                state['tokens'] = [{**c, **body} if c['id'] == body['id'] else c for c in state['tokens']]
                            else:
                                state['tokens'].append({'id': max([c['id'] for c in state['tokens']] + [1])+1,
                                                        **body, 'status': 1, 'key': 'mask********key'})
                        data = {'items': state['tokens']}
                    elif path.startswith('/api/token/') and path.endswith('/key') and self.command == 'POST':
                        state['key_reads'] += 1
                        data = {'key': 'full-private-key-'+path.split('/')[3]}
                    elif path.startswith('/api/token/') and self.command == 'DELETE':
                        state['tokens'] = [c for c in state['tokens'] if str(c['id']) != path.split('/')[3]]
                    else:
                        self.send_error(404)
                        return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'data': data}).encode())

        server = HTTPServer(('127.0.0.1', 0), Router)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            spec = importlib.util.spec_from_file_location('configure_router', Path(__file__).resolve().parents[1] / 'scripts/configure-router.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as directory:
                env = {'ROUTER_URL': f'http://127.0.0.1:{server.server_port}', 'GPUSTACK_KEY': 'gpu-key',
                       'ADMIN_PW': 'test-password', 'SUDOEDGE_CONFIG_HOME': directory}
                with patch.dict(os.environ, env), patch.object(module.time, 'sleep') as sleep:
                    path = Path(directory) / 'sudocode.json'
                    path.write_text(json.dumps({'auth_modes': {'api-key': {'nexus': {'endpoint': 'nexus:///model'}}}}))
                    module.configure()
                    module.configure()
                    self.assertEqual(sleep.call_count, 2)
                config = json.loads((Path(directory) / 'sudocode.json').read_text())
                self.assertEqual(config['auth_modes']['api-key']['sudorouter']['apiKey'], 'sk-full-private-key-2')
                self.assertEqual(config['auth_modes']['api-key']['sudoedge-external']['apiKey'], 'sk-full-private-key-3')
                self.assertEqual(config['auth_modes']['api-key']['nexus'], {'endpoint': 'nexus:///model'})
                self.assertEqual(config['models']['qwen3-local']['contextWindow'], 65536)
                self.assertEqual(state['setup_count'], 1)
                self.assertEqual(state['setup_disconnects'], 2)
                self.assertEqual([(t['name'], t['group'], t['cross_group_retry']) for t in state['tokens']],
                                 [('sudocode-local', 'local', False), ('sudocode-cloud', 'external', False)])
                self.assertEqual(state['key_reads'], 4)
                self.assertEqual(len(state['channels']), 2)
                self.assertEqual(state['channels'][0]['key'], 'cloud-secret')
                self.assertEqual(state['channels'][0]['status'], 1)
                self.assertEqual([c['group'] for c in state['channels']], ['external', 'local'])
                self.assertEqual(state['groups'], {'default': 1, 'custom': 2, 'local': 1, 'external': 1})
                self.assertEqual(state['usable']['custom'], 'Existing group')
                self.assertEqual(state['metadata']['cloud-model']['context_window'], 12345)
                self.assertTrue(state['metadata']['qwen3-30b']['tool_calling_supported'])
                self.assertEqual(state['ratios'], {'cloud-model': 2, 'qwen3-30b': 0})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_persistent_setup_reset_stops_before_any_mutating_request(self):
        spec = importlib.util.spec_from_file_location('configure_router', Path(__file__).resolve().parents[1] / 'scripts/configure-router.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        client = MagicMock()
        client.open.side_effect = ConnectionResetError('Synthetic startup connection reset')
        env = {'ROUTER_URL': 'http://127.0.0.1:1', 'GPUSTACK_KEY': 'gpu-key', 'ADMIN_PW': 'test-password'}
        with patch.dict(os.environ, env), patch.object(module.urllib.request, 'build_opener', return_value=client), patch.object(module.time, 'sleep') as sleep:
            with self.assertRaises(ConnectionResetError):
                module.configure()
        self.assertEqual(client.open.call_count, 30)
        self.assertEqual(sleep.call_count, 29)
        self.assertTrue(all(call.args[0].get_method() == 'GET' and call.args[0].full_url.endswith('/api/setup') for call in client.open.call_args_list))


if __name__ == '__main__':
    unittest.main()
