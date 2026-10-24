#!/usr/bin/env python3
"""Qualify a complete existing Moss/two-Nexus product on isolated cold copies."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request

spec = importlib.util.spec_from_file_location('cohost_copy_boundary', Path(__file__).with_name('cohost-checkpoint-boot.py'))
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)


def qualify(profile):
    boundary.verify_boundary(profile)
    evidence = Path(profile['evidence'])
    evidence.mkdir(mode=0o700)
    report = {'networkNamespace':os.readlink('/proc/self/ns/net'), 'mountBindingsVerified':True,
              'nativeHistoryRecoveryAccepted':False, 'domainJoinAccepted':False,
              'newAgentRequested':False, 'children':[]}
    children = []
    try:
        for child in profile['children']:
            if boundary.digest(child['executable']) != child['executableSha256']:
                raise ValueError('Product executable checksum mismatch: '+child['name'])
            if 'entry' in child and boundary.digest(child['entry']) != child['entrySha256']:
                raise ValueError('Product application entry checksum mismatch')
            environment = json.loads(Path(child['environmentFile']).read_text())
            with (evidence/(child['name']+'.stdout.log')).open('xb') as out, (evidence/(child['name']+'.stderr.log')).open('xb') as err:
                process = subprocess.Popen([child['executable'],*child['arguments']], env=environment,
                                           cwd=child['cwd'], stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            children.append((child['name'],process))
            attempts, failures, deadline = 0, [], time.monotonic()+45
            while True:
                if any(running.poll() is not None for _,running in children):
                    raise RuntimeError('A product component exited before readiness')
                attempts += 1
                try:
                    if child['kind'] == 'nexus':
                        result = subprocess.run([profile['node'],profile['probe']['path'],child['probeProfile']],
                                                capture_output=True,text=True,timeout=12)
                        if result.returncode:
                            raise RuntimeError(result.stderr[-1200:])
                        ready = json.loads(result.stdout)
                    else:
                        with urllib.request.urlopen(profile['mossReadyUrl'],timeout=3) as response:
                            ready = json.loads(response.read())
                            if response.status != 200 or ready.get('ready') is not True or ready.get('instance_id') != profile['instanceId']:
                                raise RuntimeError('Moss is not ready under the preserved instance identity')
                    break
                except (OSError,ValueError,RuntimeError) as error:
                    failures.append(str(error))
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Product component readiness exceeded 45 seconds: '+child['name']) from error
                    time.sleep(.25)
            report['children'].append({'name':child['name'],'attempts':attempts,'startupFailures':failures,'readiness':ready})
        report['afterMossNativeReadiness'] = []
        for child in profile['children']:
            if child['kind'] == 'nexus':
                probe = subprocess.run([profile['node'],profile['probe']['path'],child['probeProfile']],
                                       capture_output=True,text=True,timeout=12)
                if probe.returncode:
                    raise RuntimeError('Native process baseline changed after Moss startup: '+probe.stderr[-1200:])
                report['afterMossNativeReadiness'].append({'name':child['name'],'readiness':json.loads(probe.stdout)})
        db = sqlite3.connect('file:'+profile['database']+'?mode=ro',uri=True)
        try:
            counts = {table:db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                      for table in ('sessions','session_attempts','session_events')}
            if counts != profile['expectedRows']:
                raise RuntimeError('Existing Moss row counts changed during startup')
            report['mossRows'] = counts
        finally:
            db.close()
        report['productStartupAccepted'] = True
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        report['cleanup'] = []
        for name,process in reversed(children):
            forced = False
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5); forced = True
            report['cleanup'].append({'name':name,'exit':process.returncode,'forced':forced})
        (evidence/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    print(json.dumps(qualify(json.loads(Path(sys.argv[1]).read_text())),indent=2))
