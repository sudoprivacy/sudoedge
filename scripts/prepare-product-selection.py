#!/usr/bin/env python3
"""Prepare exact native unit-file selections for this existing Edge product.

This does not stop a service or install a unit. It preserves native unit/drop-in
configuration, replacing only the explicitly selected executable/application
entry and optional working directory. The shared Stack action owns activation.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


def service_assignments(text, key):
    section = None
    matches = []
    for number,line in enumerate(text.splitlines(keepends=True)):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped
        elif section == '[Service]' and line.startswith(key+'='):
            matches.append((number,line[len(key)+1:].strip()))
    if len(matches) != 1:
        raise ValueError('Expected exactly one native Service '+key+' assignment')
    return matches[0]


def prepare(profile, destination):
    expected = {'schemaVersion','exclusiveConfigurationOwner','checkpoint','versions'}
    if set(profile) != expected or profile['schemaVersion'] != 1 or profile['exclusiveConfigurationOwner'] is not True:
        raise ValueError('Use a versioned product profile with one exclusive configuration owner')
    spec = importlib.util.spec_from_file_location('edge_shared_actions',Path(__file__).with_name('stack-action.py'))
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    root, actions = adapter.verified_shared()
    sys.path.insert(0,str(actions['path'].parent))
    import checkpoint
    import selection
    from cohost import digest, private_directory, publish, quoted, unit_path

    destination = checkpoint.owned_path(str(destination))
    if destination.exists():
        raise ValueError('Use a new private selection-preparation directory')
    names = {unit['name'] for unit in profile['checkpoint']['units']}
    versions = profile['versions']
    if len(versions) != len(names) or {item['unit'] for item in versions} != names:
        raise ValueError('Prepare exactly the declared existing product services')
    # Reuse the common ownership/service/pin gate before preparing any bytes.
    checkpoint.inspect(profile['checkpoint'],destination)
    pins = {item['path']:item['sha256'] for item in profile['checkpoint']['pins']}
    prepared = []
    for version in versions:
        if set(version) - {'unit','binary','sha256','source','entry','workingDirectory'} or not re.fullmatch('[a-f0-9]{40}',version['source']):
            raise ValueError('Expected a source-bound product version')
        unit = version['unit']
        raw = checkpoint.control('show',unit,'--property=FragmentPath,DropInPaths,MainPID')
        properties = dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        path = checkpoint.owned_path(properties['FragmentPath'])
        if pins.get(str(path)) != digest(path):
            raise ValueError('Native unit file must be in the pinned checkpoint')
        for dropin in shlex.split(properties.get('DropInPaths','')):
            extra = checkpoint.owned_path(dropin)
            if pins.get(str(extra)) != digest(extra):
                raise ValueError('Every native drop-in must remain pinned')
            if re.search(r'^\s*ExecStart\s*=',extra.read_text(),re.M):
                raise ValueError('A drop-in overrides ExecStart; explicit native adaptation is required')
        text = path.read_text()
        index, command = service_assignments(text,'ExecStart')
        arguments = shlex.split(command)
        pid = int(properties['MainPID'])
        actual = (Path('/proc')/str(pid)/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        if arguments != actual or any(any(char in value for char in '\n\r\0%$') for value in arguments):
            raise ValueError('Native ExecStart requires expansion or differs from the actual process')
        binary = checkpoint.owned_path(version['binary'])
        if digest(binary) != version['sha256']:
            raise ValueError('Product candidate executable changed')
        arguments[0] = str(binary)
        files = []
        if version.get('entry'):
            entry = version['entry']
            if set(entry) != {'before','path','sha256'} or len(arguments)<2:
                raise ValueError('Product application entry does not match the existing process')
            launched_entry = Path(arguments[1])
            if not launched_entry.is_absolute():
                launched_entry = (Path('/proc')/str(pid)/'cwd').resolve()/launched_entry
            if checkpoint.owned_path(str(launched_entry)) != checkpoint.owned_path(entry['before']):
                raise ValueError('Product application entry does not match the existing process working directory')
            if pins.get(entry['before']) != digest(checkpoint.owned_path(entry['before'])):
                raise ValueError('Original application entry must be checkpointed and pinned')
            after = checkpoint.owned_path(entry['path'])
            if digest(after) != entry['sha256']:
                raise ValueError('New product application entry changed')
            arguments[1] = str(after)
            files.append({'path':str(after),'sha256':entry['sha256']})
        lines = text.splitlines(keepends=True)
        if any('$' in value for value in arguments):
            raise ValueError('Product arguments must not require systemd environment expansion')
        lines[index] = 'ExecStart='+' '.join(quoted(value) for value in arguments)+'\n'
        if version.get('workingDirectory'):
            position, old = service_assignments(text,'WorkingDirectory')
            if '%' in old.replace('%%','') or Path(old.replace('%%','%')) != (Path('/proc')/str(pid)/'cwd').resolve():
                raise ValueError('Native working directory differs from the running service')
            directory = checkpoint.owned_path(version['workingDirectory'])
            if not directory.is_dir():
                raise ValueError('New application directory is missing')
            if '$' in str(directory):
                raise ValueError('Working directory must not require expansion')
            lines[position] = 'WorkingDirectory='+unit_path(str(directory))+'\n'
        payload = ''.join(lines).encode()
        prepared.append({'unit':unit,'path':path,'payload':payload,'version':version,'argumentFiles':files})
    private_directory(destination.parent)
    destination.mkdir(mode=0o700)
    unit_directory = destination/'units'
    unit_directory.mkdir(mode=0o700)
    plan = {'schemaVersion':1,'checkpoint':profile['checkpoint'],'selections':[],'candidates':[]}
    for item in prepared:
        output = unit_directory/item['unit']
        publish(output,item['payload'],0o600)
        plan['selections'].append({'path':str(item['path']),'expectedSha256':pins[str(item['path'])],
                                   'prepared':str(output),'sha256':digest(output)})
        version = item['version']
        plan['candidates'].append({'name':item['unit'],'binary':version['binary'],'sha256':version['sha256'],
                                   'argumentFiles':item['argumentFiles']})
    verification = subprocess.run(['systemd-analyze','verify','--man=no',*[item['prepared'] for item in plan['selections']]],
                                  capture_output=True,text=True,timeout=30)
    if verification.returncode:
        raise ValueError('Native systemd rejected the prepared product units: '+verification.stderr)
    inspection = selection.select(plan,destination/'activation',False)
    publish(destination/'plan.json',(json.dumps(plan,indent=2)+'\n').encode(),0o600)
    report = {'status':'prepared-only','servicesChanged':False,'inspection':inspection,
              'versions':versions,'planSha256':digest(destination/'plan.json'),
              'nativeUnitVerification':{'exit':verification.returncode,'stderr':verification.stderr}}
    publish(destination/'preparation.json',(json.dumps(report,indent=2)+'\n').encode(),0o600)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',type=Path)
    parser.add_argument('destination',type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(json.loads(args.profile.read_text()),args.destination),indent=2))
