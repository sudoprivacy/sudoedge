"""Exercise the real Edge adapter against a verified installed Stack package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(package, expected, commit):
    if platform.system() != 'Linux':
        raise ValueError('This device entry acceptance runs on Linux')
    descriptor = package / 'bundle.json'
    if descriptor.is_symlink() or sha(descriptor) != expected:
        raise ValueError('Package descriptor differs from the trusted receipt')
    data = json.loads(descriptor.read_text())
    if data.get('kind') != 'device-actions' or data.get('sourceCommit') != commit:
        raise ValueError('Package source/profile differs from the selected producer')
    client = package / 'cos_bundle.py'
    if client.is_symlink() or sha(client) != data['files']['cos_bundle.py']['sha256']:
        raise ValueError('Shared package client differs from the trusted descriptor')
    bundle = data['bundle']
    if Path(bundle).name != bundle:
        raise ValueError('Expected a flat archive filename')
    with tempfile.TemporaryDirectory(prefix='edge-installed-actions-') as directory:
        root = Path(directory)
        home = root / 'home'
        home.mkdir()
        environment = {name: value for name, value in os.environ.items() if name in ('PATH', 'LANG', 'LC_ALL')}
        environment['HOME'] = str(home)
        installed = root / 'installed'
        command = [sys.executable, str(client), 'unpack', '--descriptor', str(descriptor),
                   '--archive', str(package / bundle), '--destination', str(installed)]
        for _ in range(2):
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
        environment['SUDOSTACK_DEPLOY_ROOT'] = str(installed)
        for action in ('', 'checkpoint', 'configuration', 'selection', 'product', 'operation'):
            invocation = [sys.executable, str(ROOT / 'scripts/stack-action.py')]
            if action:
                invocation.append(action)
            result = subprocess.run([*invocation, '--help'], cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (action, result.stderr)
            assert 'usage:' in result.stdout
        selected = installed / 'tools/deploy/selection.py'
        selected.write_bytes(selected.read_bytes() + b'\nraise RuntimeError("must not execute changed action")\n')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/stack-action.py'), 'operation', '--help'],
                                cwd=root, env=environment, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0
        assert 'does not match the pinned source' in result.stderr
        assert 'must not execute changed action' not in result.stderr
    print(json.dumps({'status': 'PASS', 'sourceCommit': commit, 'descriptorSha256': expected,
                      'installedAdapterEntries': 6, 'verifiedReuse': True, 'changedSourceRefused': True,
                      'productServicesChanged': False, 'deployExecuted': False, 'domainJoinAccepted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-dir', type=Path, required=True)
    parser.add_argument('--descriptor-sha256', required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    run(args.package_dir.resolve(strict=True), args.descriptor_sha256, args.source_commit)
