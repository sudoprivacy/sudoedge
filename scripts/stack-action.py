#!/usr/bin/env python3
"""Execute the exact-pinned shared action; appliance code supplies only options."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def verified_shared():
    lock = json.loads(Path(__file__).with_name('sudostack.lock.json').read_text(encoding='utf-8'))
    source = os.environ.get('SUDOSTACK_DEPLOY_ROOT')
    if not source:
        raise ValueError('Set SUDOSTACK_DEPLOY_ROOT to the verified pinned sudostack checkout or offline action bundle')
    root = Path(source).resolve(strict=True)
    # Check the shared dependency too: checkpoint imports existing placement
    # helpers rather than carrying another private-publishing implementation.
    actions = {}
    for path_key, hash_key in [('path', 'sha256'), ('checkpointPath', 'checkpointSha256'),
                               ('configurationPath', 'configurationSha256'),('selectionPath','selectionSha256'),
                               ('productQualificationPath','productQualificationSha256'),
                               ('deviceOperationPath','deviceOperationSha256')]:
        relative = Path(lock[path_key])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid shared action lock path')
        action = root / relative
        if action.is_symlink() or not action.resolve(strict=True).is_relative_to(root):
            raise ValueError('Shared action escapes its installation')
        if hashlib.sha256(action.read_bytes()).hexdigest() != lock[hash_key]:
            raise ValueError('Shared deploy action does not match the pinned source; no action executed')
        actions[path_key] = action
    return root, actions


def main():
    arguments = sys.argv[1:]
    selected = 'path'
    choices = {'checkpoint':'checkpointPath','configuration':'configurationPath','selection':'selectionPath',
               'product':'productQualificationPath','operation':'deviceOperationPath'}
    if arguments and arguments[0] in choices:
        selected = choices[arguments[0]]
        arguments = arguments[1:]
    _, actions = verified_shared()
    # Hash the executable content, not a version marker supplied by the bundle.
    # The trusted repository lock associates these bytes with the producer commit.
    return subprocess.run([sys.executable, str(actions[selected]), *arguments], check=False).returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
