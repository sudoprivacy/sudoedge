#!/usr/bin/env python3
"""Execute the exact-pinned shared action; appliance code supplies only options."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    lock = json.loads(Path(__file__).with_name('sudostack.lock.json').read_text(encoding='utf-8'))
    source = os.environ.get('SUDOSTACK_DEPLOY_ROOT')
    if not source:
        raise ValueError('Set SUDOSTACK_DEPLOY_ROOT to the verified pinned sudostack checkout or offline action bundle')
    root = Path(source).resolve(strict=True)
    relative = Path(lock['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid shared action lock path')
    action = root / relative
    if action.is_symlink() or not action.resolve(strict=True).is_relative_to(root):
        raise ValueError('Shared action escapes its installation')
    if hashlib.sha256(action.read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('Shared deploy action does not match the pinned source; no action executed')
    # Hash the executable content, not a version marker supplied by the bundle.
    # The trusted repository lock associates these bytes with the producer commit.
    return subprocess.run([sys.executable, str(action), *sys.argv[1:]], check=False).returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
