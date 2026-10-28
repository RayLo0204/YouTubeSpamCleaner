"""Native launcher: one local instance, an ephemeral loopback port, browser UI."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from .web import create_app


def default_root(demo=False):
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    return base / 'YouTubeSpamCleaner' / ('demo' if demo else 'data')


def instance_lock(root):
    handle = (root / 'instance.lock').open('a+b')
    # Windows byte locks can reject reads before locking() is reached.
    # Inspect the length without reading the byte held by the first instance.
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    try:
        if sys.platform == 'win32':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main():
    parser = argparse.ArgumentParser(description='YouTube Spam Cleaner — local browser application')
    parser.add_argument('--demo', action='store_true', help='Use isolated offline sample data; no Google requests')
    parser.add_argument('--no-browser', action='store_true', help='Start without opening a browser')
    parser.add_argument('--data-dir', type=Path, help='Override the local data directory')
    args = parser.parse_args()
    root = (args.data_dir or default_root(args.demo)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = instance_lock(root)
    if lock is None:
        try:
            if not args.no_browser:
                webbrowser.open(json.loads((root / 'session.json').read_text())['url'])
        except (OSError, ValueError, KeyError):
            pass
        return 0
    handler = RotatingFileHandler(root / 'application.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.WARNING, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    token = secrets.token_urlsafe(32)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Binding port zero avoids taking over another application's fixed port.
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    holder = {}
    app = create_app(root, token=token, demo=args.demo, shutdown=lambda: setattr(holder['server'], 'should_exit', True))
    config = uvicorn.Config(app, host='127.0.0.1', port=port, log_config=None, access_log=False,
                            loop='asyncio', http='h11', ws='none', timeout_graceful_shutdown=3)
    server = uvicorn.Server(config)
    holder['server'] = server
    url = f'http://127.0.0.1:{port}/#session={token}'
    session = root / 'session.json'

    def ready():
        while not server.started and not server.should_exit:
            time.sleep(0.05)
        if server.started:
            session.write_text(json.dumps({'url': url, 'pid': os.getpid(), 'demo': args.demo}), encoding='utf-8')
            session.chmod(0o600)
            if not args.no_browser:
                webbrowser.open(url)

    threading.Thread(target=ready, daemon=True).start()
    try:
        server.run(sockets=[listener])
    finally:
        session.unlink(missing_ok=True)
        listener.close()
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
