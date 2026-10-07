#!/usr/bin/env python3
"""Launch scode with explicit model limits from the configured Router catalog.

The ARM64 0.2.20 ACP path does not warm discovery before its first request.
Keep the Router as the source of model limits while that path is upgraded.
stdout is reserved for ACP; this launcher emits no protocol output.
"""
import json
import os
from pathlib import Path
import sys
import urllib.request


def launch() -> None:
    binary = os.environ['SUDOEDGE_SCODE_BIN']
    home = Path(os.environ['SUDO_CODE_CONFIG_HOME'])
    path = home / 'sudocode.json'
    config = json.loads(path.read_text())
    providers = config.get('auth_modes', {}).get('proxy', {})
    if len(providers) != 1:
        raise ValueError('Expected one Moss proxy provider')
    provider_name, connection = next(iter(providers.items()))
    headers = {'Authorization': 'Bearer ' + connection['apiKey']} if connection.get('apiKey') else {}
    url = connection['baseUrl'].rstrip('/') + '/models'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
        catalog = json.load(response)
    models = config.setdefault('models', {})
    for item in catalog.get('data', []):
        model = item.get('id')
        if model != os.environ.get('SUDOEDGE_LOCAL_MODEL', 'qwen3-30b'):
            continue
        context = item.get('context_window')
        output = item.get('max_output_tokens')
        if not isinstance(model, str) or type(context) is not int or type(output) is not int:
            continue
        if not 0 < output < context:
            raise ValueError('Router advertised inconsistent model limits')
        models[model] = {
            'alias': model,
            'name': model,
            'maxOutputTokens': output,
            'contextWindow': context,
            'providers': {'proxy': {'provider': provider_name, 'model': model, 'api': 'openai-completions'}},
        }
    temporary = path.with_suffix('.next')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
        json.dump(config, stream)
    temporary.replace(path)
    os.execv(binary, [binary, *sys.argv[1:]])


if __name__ == '__main__':
    launch()
