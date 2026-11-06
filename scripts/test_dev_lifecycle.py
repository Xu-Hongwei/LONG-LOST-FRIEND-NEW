"""Windows integration check using temporary database, state, logs and loopback ports."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def main():
    if os.name != 'nt':
        raise SystemExit('This lifecycle check requires Windows PowerShell.')
    with tempfile.TemporaryDirectory(prefix='campus_lifecycle_') as temporary:
        workspace = Path(temporary)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('CAMPUS_', 'LLM_ROUTER_', 'DASHSCOPE_', 'DEEPSEEK_', 'ARK_'))}
        ports = set()
        while len(ports) < 3:
            ports.add(free_port())
        backend, frontend, preview = ports
        env.update(CAMPUS_DB_PATH=str(workspace / 'test.db'), CAMPUS_RUNTIME_DIR=str(workspace / 'runtime'),
                   CAMPUS_BACKEND_PORT=str(backend), CAMPUS_FRONTEND_PORT=str(frontend), CAMPUS_PREVIEW_PORT=str(preview))
        state_file = workspace / 'runtime' / 'dev-processes.json'

        def run(script, *args, success=True):
            command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                       str(ROOT / 'scripts' / script), *args]
            # Background descendants can inherit pipe handles after PowerShell exits.
            # Files avoid waiting for those descendants to close captured pipes.
            with tempfile.TemporaryFile() as output:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=output,
                                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=100)
                output.seek(0)
                captured = output.read()
            if (result.returncode == 0) != success:
                raise AssertionError(captured.decode('utf-8', errors='replace'))
            return result

        def start(*args, success=True):
            return run('start-dev.ps1', '-NoLocalConfig', '-Python', sys.executable, *args, success=success)

        def state():
            return json.loads(state_file.read_text(encoding='utf-8-sig')) if state_file.exists() else []

        def health(port):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=5) as response:
                return json.load(response)

        original_records = None
        try:
            start()
            original_records = state()
            assert len(original_records) == 2 and (workspace / 'test.db').exists()
            assert health(backend)['instance_id'] == health(frontend)['instance_id']
            start(success=False)
            assert state() == original_records
            run('stop-dev.ps1', '-WhatIf')
            assert state() == original_records and health(frontend)['ok']
            changed = [dict(record) for record in original_records]
            changed[0]['start_ticks'] = '0'
            state_file.write_text(json.dumps(changed), encoding='utf-8')
            run('stop-dev.ps1', success=False)
            assert health(backend)['ok']
            state_file.write_text(json.dumps(original_records), encoding='utf-8')
            run('stop-dev.ps1')
            original_records = None
            assert state() == []
            print('PASS: ready checks, API proxy, duplicate start, WhatIf and identity mismatch protection', flush=True)

            with socket.socket() as unrelated:
                unrelated.bind(('127.0.0.1', backend))
                unrelated.listen()
                start(success=False)
                run('stop-dev.ps1')
                assert unrelated.getsockname()[1] == backend and state() == []
            print('PASS: occupied unrelated port is not stopped', flush=True)

            previous_node_options = env.get('NODE_OPTIONS')
            env['NODE_OPTIONS'] = '--campus-invalid-flag'
            start(success=False)
            assert state() == []
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', backend))
            if previous_node_options is None:
                env.pop('NODE_OPTIONS')
            else:
                env['NODE_OPTIONS'] = previous_node_options
            print('PASS: frontend startup failure rolls back the newly started backend', flush=True)

            env['CAMPUS_FRONTEND_PORT'] = 'not-a-port'
            start(success=False)
            assert state() == []
            env['CAMPUS_FRONTEND_PORT'] = str(frontend)
            start('-Preview')
            original_records = state()
            assert health(backend)['instance_id'] == health(preview)['instance_id']
            run('stop-dev.ps1')
            original_records = None
            print('PASS: invalid configuration rejected; production preview API proxy works', flush=True)
        finally:
            if original_records:
                state_file.write_text(json.dumps(original_records), encoding='utf-8')
            run('stop-dev.ps1')
        print('Lifecycle checks passed; temporary services and data removed.')


if __name__ == '__main__':
    main()
