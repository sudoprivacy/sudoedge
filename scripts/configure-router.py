"""Provision new-api through its supported setup, channel and token APIs."""
import http.cookiejar
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


def configure() -> None:
    base = os.environ.get('ROUTER_URL', 'http://127.0.0.1:3000').rstrip('/')
    model = os.environ.get('MODEL', 'qwen3-30b')
    context = int(os.environ.get('MODEL_MAX_LEN', '65536'))
    output = int(os.environ.get('MODEL_MAX_OUTPUT_TOKENS', '4096'))
    if not 0 < output < context:
        raise ValueError('Require 0 < MODEL_MAX_OUTPUT_TOKENS < MODEL_MAX_LEN')
    gpu_key = os.environ['GPUSTACK_KEY']
    gpu_url = os.environ.get('GPUSTACK_URL', 'http://127.0.0.1/v1-openai').rstrip('/')
    password = os.environ.get('ADMIN_PW')
    if not password:
        raise ValueError('Set ADMIN_PW or provide it through the boot credential file')
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    access_token = None

    def call(path, body=None, method=None):
        headers = {'Content-Type': 'application/json'}
        if access_token is not None:
            headers['Authorization'] = 'Bearer ' + access_token
        request = urllib.request.Request(base + path, headers=headers, method=method,
                                         data=json.dumps(body).encode() if body is not None else None)
        with client.open(request, timeout=20) as response:
            result = json.load(response)
        if not result.get('success'):
            raise RuntimeError(f"new-api {path}: {result.get('message', 'request failed')}")
        return result.get('data')

    for attempt in range(30):
        try:
            setup = call('/api/setup')
            break
        except (urllib.error.URLError, TimeoutError):
            if attempt == 29:
                raise
            time.sleep(2)
    if not setup['status']:
        if setup.get('root_init'):
            raise RuntimeError('Uninitialized Router already has a root user; inspect setup before provisioning')
        call('/api/setup', {'username': 'root', 'password': password, 'confirmPassword': password,
                            'SelfUseModeEnabled': True, 'DemoSiteEnabled': False})
    login = call('/api/user/login', {'username': 'root', 'password': password})
    access_token = login['access_token']
    call('/api/option/', {'key': 'SelfUseModeEnabled', 'value': 'true'}, 'PUT')
    options = call('/api/option/')
    raw = next((item['value'] for item in options if item['key'] == 'ModelMetadata'), '{}')
    metadata = json.loads(raw or '{}')
    metadata[model] = {**metadata.get(model, {}), 'context_window': context,
                       'max_output_tokens': output, 'tool_calling_supported': True,
                       'vision_supported': False}
    call('/api/option/', {'key': 'ModelMetadata', 'value': json.dumps(metadata)}, 'PUT')
    ratios = json.loads(next((item['value'] for item in options if item['key'] == 'ModelRatio'), '{}') or '{}')
    ratios[model] = 0
    call('/api/option/', {'key': 'ModelRatio', 'value': json.dumps(ratios)}, 'PUT')
    groups = json.loads(next((item['value'] for item in options if item['key'] == 'GroupRatio'), '{}') or '{}')
    groups.update({'local': 1, 'external': 1})
    call('/api/option/', {'key': 'GroupRatio', 'value': json.dumps(groups)}, 'PUT')
    usable = json.loads(next((item['value'] for item in options if item['key'] == 'UserUsableGroups'), '{}') or '{}')
    usable.update({'local': 'Local GPU models', 'external': 'Cloud models'})
    call('/api/option/', {'key': 'UserUsableGroups', 'value': json.dumps(usable)}, 'PUT')
    channels = call('/api/channel/?p=0&page_size=100')
    channels = channels['items'] if isinstance(channels, dict) else channels
    desired = [{'type': 8, 'name': 'gpustack-local', 'key': gpu_key,
                'base_url': gpu_url + '/chat/completions', 'models': model, 'status': 1,
                'group': 'local', 'param_override': json.dumps({'max_tokens': output})}]
    if os.environ.get('SUDOROUTER_KEY'):
        desired.append({'type': 1, 'name': 'sudorouter-cloud', 'key': os.environ['SUDOROUTER_KEY'],
                        'base_url': os.environ.get('SUDOROUTER_URL', 'https://hk.sudorouter.ai').rstrip('/'),
                        'models': os.environ['SUDOROUTER_MODELS'], 'status': 1, 'group': 'external'})
    else:
        for channel in channels:
            if channel['name'] == 'sudorouter-cloud':
                call('/api/channel/', {'id': channel['id'], 'group': 'external'}, 'PUT')
    for channel in desired:
        matches = [item for item in channels if item['name'] == channel['name']]
        if len(matches) > 1:
            raise RuntimeError(f"Duplicate Router channel: {channel['name']}")
        if matches:
            channel_id = matches[0]['id']
            update = {key: value for key, value in channel.items() if key != 'status'}
            call('/api/channel/', {**update, 'id': channel_id}, 'PUT')
            call(f'/api/channel/{channel_id}/status', {'status': channel['status']})
        else:
            call('/api/channel/', {'mode': 'single', 'channel': channel})
    tokens = call('/api/token/?p=0&page_size=100')
    tokens = tokens['items'] if isinstance(tokens, dict) else tokens
    def route_token(name, group):
        matches = [item for item in tokens if item['name'] == name and item['status'] == 1]
        if len(matches) > 1:
            raise RuntimeError(f'Multiple active {name} tokens')
        desired = {'name': name, 'expired_time': -1, 'unlimited_quota': True,
                   'model_limits_enabled': False, 'group': group, 'cross_group_retry': False}
        if matches:
            call('/api/token/', {**desired, 'id': matches[0]['id']}, 'PUT')
            token_id = matches[0]['id']
        else:
            call('/api/token/', desired)
            current = call('/api/token/?p=0&page_size=100')
            current = current['items'] if isinstance(current, dict) else current
            found = [item for item in current if item['name'] == name and item['status'] == 1]
            if len(found) != 1:
                raise RuntimeError(f'Expected one active {name} token after provisioning')
            token_id = found[0]['id']
        key = call(f'/api/token/{token_id}/key', {})['key']
        return key if key.startswith('sk-') else 'sk-' + key

    token = route_token('sudocode-local', 'local')
    is_cloud_configured = bool(os.environ.get('SUDOROUTER_KEY')) or any(
        item['name'] == 'sudorouter-cloud' for item in channels)
    cloud_token = route_token('sudocode-cloud', 'external') if is_cloud_configured else None
    home = Path(os.environ.get('SUDOEDGE_CONFIG_HOME', str(Path.home() / '.nexus/sudocode')))
    home.mkdir(parents=True, exist_ok=True)
    path = home / 'sudocode.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    providers = config.setdefault('auth_modes', {}).setdefault('api-key', {})
    providers.update({'sudorouter': {'baseUrl': base + '/v1', 'apiKey': token},
                      'gpustack': {'baseUrl': gpu_url, 'apiKey': gpu_key}})
    if cloud_token:
        providers['sudoedge-external'] = {'baseUrl': base + '/v1', 'apiKey': cloud_token}
    else:
        providers.pop('sudoedge-external', None)
    for alias, provider in [('qwen3-local', 'sudorouter'), ('qwen3-direct', 'gpustack')]:
        config.setdefault('models', {})[alias] = {
            'alias': alias, 'name': model, 'input': ['text'],
            'contextWindow': context, 'maxOutputTokens': output,
            'providers': {'api-key': {'provider': provider, 'model': model, 'api': 'openai-completions'}},
        }
    temporary = path.with_suffix('.next')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
        json.dump(config, stream, indent=2)
    temporary.replace(path)
    for item in tokens:
        if item['name'] == 'sudocode':
            call(f"/api/token/{item['id']}", method='DELETE')
    print(f'new-api configured: {model}, context={context}, output={output}; client credentials refreshed')


if __name__ == '__main__':
    configure()
