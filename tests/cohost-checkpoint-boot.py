#!/usr/bin/env python3
"""Boot a producer-pinned cohost on a cold checkpoint inside a reviewed OS sandbox.

This does not provision a domain or Agent. Refuse ordinary host execution before
starting a process, including when a private network/mount mapping was omitted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_boundary(profile):
    if os.getuid() == 0:
        raise ValueError('Run the checker as the original unprivileged device user')
    if os.readlink('/proc/self/ns/net') == profile['hostNetworkNamespace']:
        raise ValueError('A separate network namespace is required; host execution refused')
    if os.readlink('/proc/self/ns/mnt') == profile['hostMountNamespace']:
        raise ValueError('A separate mount namespace is required')
    mounts = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        mount = re.sub(r'\\([0-7]{3})', lambda value:chr(int(value[1],8)), fields[4])
        mounts.append((mount, fields[5].split(',')))
    for path in profile['readOnlyPaths']:
        matching = [(mount,options) for mount,options in mounts
                    if path == mount or path.startswith(mount.rstrip('/')+'/')]
        if not matching or 'ro' not in max(matching, key=lambda item:len(item[0]))[1]:
            raise ValueError('Host path is not mounted read-only: '+path)
    for binding in profile['bindings']:
        original, copy = Path(binding['original']), Path(binding['copy'])
        if original.resolve() == copy.resolve():
            raise ValueError('Expected two distinct mount paths')
        left, right = original.stat(), copy.stat()
        if (left.st_dev, left.st_ino) != (right.st_dev, right.st_ino):
            raise ValueError('The cold-copy mount is not installed at '+str(original))
    for name in ['candidate', 'probe']:
        if digest(profile[name]['path']) != profile[name]['sha256']:
            raise ValueError('Qualification input checksum mismatch: '+name)


def qualify(profile):
    verify_boundary(profile)
    evidence = Path(profile['evidence'])
    evidence.mkdir(mode=0o700, exist_ok=True)
    report = {'networkNamespace':os.readlink('/proc/self/ns/net'), 'mountBindingsVerified':True,
              'candidate':profile['candidate'], 'newAgentCreated':False,
              'nativeHistoryRecoveryAccepted':False, 'domainJoinAccepted':False}
    with (evidence/'cohost.stdout.log').open('xb') as out, (evidence/'cohost.stderr.log').open('xb') as err:
        process = subprocess.Popen([profile['candidate']['path'], '--bind-addr', profile['bind']],
                                   stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            deadline = time.monotonic()+45
            failures = []
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Candidate exited before authenticated native readiness: '+str(process.returncode))
                probe = subprocess.run([profile['node'], profile['probe']['path'], profile['profilePath']],
                                       capture_output=True, text=True, timeout=12)
                if probe.returncode == 0:
                    report['nativeReadiness'] = json.loads(probe.stdout)
                    break
                failures.append({'exit':probe.returncode, 'stderr':probe.stderr[-1200:]})
                if time.monotonic() >= deadline:
                    raise RuntimeError('Authenticated native readiness did not pass within 45 seconds')
                time.sleep(0.25)
            report['probeAttempts'] = len(failures)+1
            report['startupProbeFailures'] = failures
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    report['forcedFixtureCleanup'] = True
            report['candidateExitAfterCleanup'] = process.returncode
            (evidence/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    options = parser.parse_args()
    profile = json.loads(options.profile.read_text())
    profile['profilePath'] = str(options.profile.resolve())
    print(json.dumps(qualify(profile), indent=2))
