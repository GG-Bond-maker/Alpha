"""Run a bounded local browser check; stop only the processes created here."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'docs' / 'review' / '2026-10-27' / 'screenshots'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_json(url):
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.load(response)
        except (OSError, ValueError):
            time.sleep(0.1)
    raise RuntimeError(f'Local process did not become ready: {url}')


def main():
    output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    expected_date = sys.argv[2] if len(sys.argv) > 2 else ''
    output.mkdir(parents=True, exist_ok=True)
    browser_path = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    if not browser_path.exists():
        browser_path = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    port, browser_port = free_port(), free_port()
    processes = []
    with tempfile.TemporaryDirectory(prefix='alpha-browser-', ignore_cleanup_errors=True) as profile, (output / 'server.log').open('w', encoding='utf-8') as log:
        try:
            processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
            wait_json(f'http://127.0.0.1:{port}/api/health')
            processes.append(subprocess.Popen([str(browser_path), '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--window-size=1440,1000', '--force-device-scale-factor=1', f'--remote-debugging-port={browser_port}', f'--user-data-dir={profile}', 'about:blank'], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
            wait_json(f'http://127.0.0.1:{browser_port}/json/version')
            request = urllib.request.Request(f'http://127.0.0.1:{browser_port}/json/new?about:blank', method='PUT')
            with urllib.request.urlopen(request) as response:
                page = json.load(response)
            subprocess.run(['node', str(ROOT / 'scripts' / 'verify_browser.mjs'), page['webSocketDebuggerUrl'], f'http://127.0.0.1:{port}', str(output)], cwd=ROOT, check=True, timeout=150,
                           env={**os.environ, 'ALPHA_EXPECT_LATEST_DATE': expected_date})
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == '__main__':
    main()
