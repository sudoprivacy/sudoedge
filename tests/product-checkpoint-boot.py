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
        dependency = profile.get('loopbackDependency')
        if dependency:
            lock = json.loads(Path(__file__).resolve().parents[1].joinpath('scripts/sudostack.lock.json').read_text())
            if boundary.digest(dependency['path']) != lock['qualificationEndpointSha256']:
                raise ValueError('Shared qualification endpoint differs from the pinned Stack producer')
            with (evidence/'dependency.stdout.log').open('xb') as out, (evidence/'dependency.stderr.log').open('xb') as err:
                process = subprocess.Popen([sys.executable,dependency['path'],'namespace','--socket',dependency['socket'],
                                            '--port',str(dependency['port']),'--host-network-namespace',profile['hostNetworkNamespace']],
                                           stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            children.append(('loopback-dependency',process))
            deadline = time.monotonic()+10
            while True:
                if process.poll() is not None:
                    raise RuntimeError('The isolated real dependency endpoint exited before readiness')
                records = (evidence/'dependency.stdout.log').read_text().splitlines()
                if records and json.loads(records[0]).get('ready') is True:
                    report['loopbackDependency'] = json.loads(records[0])
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('The isolated dependency endpoint did not become ready')
                time.sleep(.05)
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
        if profile.get('mossProductProbe'):
            product = profile['mossProductProbe']
            if boundary.digest(product['path']) != product['sha256']:
                raise ValueError('Moss producer recovery probe checksum mismatch')
            moss = next(child for child in profile['children'] if child['kind'] == 'moss')
            recovery = subprocess.run([profile['node'],product['path'],product['config'],str(evidence/'product-recovery'),
                                       '--resume-existing',product['sessionId']],
                                      env=json.loads(Path(moss['environmentFile']).read_text()),
                                      capture_output=True,text=True,timeout=240)
            (evidence/'recovery.stdout.log').write_text(recovery.stdout)
            (evidence/'recovery.stderr.log').write_text(recovery.stderr)
            if recovery.returncode:
                raise RuntimeError('Existing product recovery failed; see private probe evidence')
            report['existingProductRecovery'] = json.loads(recovery.stdout)
            execution = next(child for child in profile['children'] if child['name'] == 'execution')
            live = subprocess.run([profile['node'],profile['probe']['path'],execution['probeProfile'],'--live-agent'],
                                  capture_output=True,text=True,timeout=12)
            (evidence/'live-execution.stdout.log').write_text(live.stdout)
            (evidence/'live-execution.stderr.log').write_text(live.stderr)
            if live.returncode:
                raise RuntimeError('Existing Agent live identity probe failed: '+live.stderr[-1200:])
            report['existingExecutionObserved'] = json.loads(live.stdout)
            db = sqlite3.connect('file:'+profile['database']+'?mode=ro',uri=True)
            try:
                counts = {table:db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                          for table in ('sessions','session_attempts','session_events')}
                if counts['sessions'] != profile['expectedRows']['sessions'] or counts['session_attempts'] != profile['expectedRows']['session_attempts']+1:
                    raise RuntimeError('Recovery must reuse the logical session and create one execution attempt')
                report['mossRowsAfterRecovery'] = counts
            finally:
                db.close()
        report['productStartupAccepted'] = True
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        cleanup_failure = None
        if profile.get('mossProductProbe') and any(item['name'] == 'moss' for item in report['children']):
            product = profile['mossProductProbe']
            moss = next(child for child in profile['children'] if child['kind'] == 'moss')
            try:
                cleanup = subprocess.run([profile['node'],product['path'],product['config'],str(evidence/'execution-cleanup'),
                                          '--terminate-existing',product['sessionId']],
                                         env=json.loads(Path(moss['environmentFile']).read_text()),
                                         capture_output=True,text=True,timeout=240)
                (evidence/'execution-cleanup.stdout.log').write_text(cleanup.stdout)
                (evidence/'execution-cleanup.stderr.log').write_text(cleanup.stderr)
                if cleanup.returncode:
                    raise RuntimeError('Native product execution cleanup failed; retain the private evidence')
                report['executionCleanup'] = json.loads(cleanup.stdout)
            except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
                cleanup_failure = str(error)
                report['executionCleanupError'] = cleanup_failure
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
        if cleanup_failure and 'error' not in report:
            raise RuntimeError(cleanup_failure)
    return report


if __name__ == '__main__':
    print(json.dumps(qualify(json.loads(Path(sys.argv[1]).read_text())),indent=2))
