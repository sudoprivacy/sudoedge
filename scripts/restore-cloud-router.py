"""Restore the RAM-backed cloud channel from the existing Moss/Nexus Vault."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
from urllib.parse import urlsplit


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_json(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > 65536
            or (os.name == 'posix' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077))):
        raise ValueError('Use a bounded private controller configuration file')
    return json.loads(path.read_text(encoding='utf-8'))


def configuration():
    path = Path.home()/'.config/sudoedge/cloud-route.json'
    if not path.exists():
        return None
    value = private_json(path)
    if (set(value) != {'schemaVersion', 'moss', 'secret', 'upstream'} or value['schemaVersion'] != 1
            or set(value['moss']) != {'origin', 'organizationId', 'credentialFile'}
            or set(value['secret']) != {'namespace', 'key'}
            or set(value['upstream']) != {'baseUrl', 'models'}):
        raise ValueError('Invalid cloud route configuration')
    upstream = value['upstream']
    url = urlsplit(upstream['baseUrl'])
    if (url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment
            or not isinstance(upstream['models'], list) or not upstream['models']
            or any(not isinstance(model, str) or not model.strip() or ',' in model or len(model) > 200
                   for model in upstream['models'])):
        raise ValueError('Specify an HTTPS upstream and explicit model identifiers')
    return value


def controller(value):
    """Load the exact shared implementation checked by the appliance source lock."""
    adapter = load_module('edge_shared_actions', Path(__file__).with_name('stack-action.py'))
    _, actions = adapter.verified_shared()
    shared = load_module('edge_moss_control', actions['mossControlPath'])
    client = shared.MossControl(value['moss']['origin'])
    credentials = private_json(value['moss']['credentialFile'])
    for attempt in range(30):
        try:
            client.login(credentials, value['moss']['organizationId'])
            return client
        except shared.MossControlError as error:
            if not error.retryable or attempt == 29:
                raise
            time.sleep(2)


def restore():
    value = configuration()
    if value is None:
        return
    client = controller(value)
    key = client.secret(value['secret']['namespace'], value['secret']['key'])
    cloud = {'baseUrl': value['upstream']['baseUrl'], 'models': ','.join(value['upstream']['models']), 'key': key}
    # Pass the upstream key directly in memory; never put it in argv, env or a file.
    configure = load_module('edge_configure_router', Path(__file__).with_name('configure-router.py'))
    configure.configure(cloud)
    print('Cloud Router channel restored from Moss Vault')


if __name__ == '__main__':
    try:
        restore()
    except Exception:
        # Unexpected provider errors may include private request/response content.
        print('Cloud Router restoration failed; inspect controller readiness, secret reference and shared source pin', file=sys.stderr)
        raise SystemExit(1)
