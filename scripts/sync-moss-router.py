"""Refresh local Moss's Router credential after RAM-backed Router provisioning."""
import json
import importlib.util
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


def sync() -> None:
    spec = importlib.util.spec_from_file_location('edge_cloud_restore', Path(__file__).with_name('restore-cloud-router.py'))
    restore = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(restore)
    cloud = restore.configuration()
    credential_file = os.environ.get('MOSS_BOOTSTRAP_CREDENTIAL_FILE')
    if not cloud and not credential_file:
        return
    if cloud:
        client = restore.controller(cloud)
        router = json.loads((Path.home()/'.nexus/sudocode/sudocode.json').read_text())['auth_modes']['api-key']
        settings = client.request('/api/v1/settings/system?scope=organization')
        providers = settings['modelProviders']
        for provider_id, router_id in [('box-gpu', 'sudorouter'), ('box-cloud', 'sudoedge-external')]:
            route = router.get(router_id)
            if route is None:
                continue
            provider = next((item for item in providers if item['id'] == provider_id), None)
            if provider is None:
                raise RuntimeError('Provision the Moss route provider before enabling credential refresh')
            provider.update(baseUrl=route['baseUrl'], apiKey=route['apiKey'])
        client.request('/api/v1/settings/system?scope=organization', {'modelProviders': providers}, 'PATCH')
        print('Moss Router credentials refreshed')
        return
    credentials = json.loads(Path(credential_file).read_text())
    base = os.environ.get('MOSS_BASE_URL', 'http://127.0.0.1:43127').rstrip('/')

    def call(path, body=None, token=None, method=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    for attempt in range(30):
        try:
            token = call('/api/v1/auth/login', {'grant_type': 'password', **credentials})['access_token']
            break
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == 29:
                raise
            time.sleep(2)
        except urllib.error.URLError:
            if attempt == 29:
                raise
            time.sleep(2)
    router = json.loads((Path.home() / '.nexus/sudocode/sudocode.json').read_text())['auth_modes']['api-key']['sudorouter']
    settings = call('/api/v1/settings/system', token=token)
    provider_id = os.environ.get('MOSS_MODEL_PROVIDER_ID', 'box-gpu')
    providers = settings['modelProviders']
    provider = next((p for p in providers if p['id'] == provider_id), None)
    if provider is None:
        raise RuntimeError('Local Moss provider is missing; provision it before enabling credential refresh')
    provider.update(baseUrl=router['baseUrl'], apiKey=router['apiKey'])
    call('/api/v1/settings/system', {'modelProviders': providers}, token, 'PATCH')
    print('  Moss local Router credential refreshed')


if __name__ == '__main__':
    sync()
