"""Loopback-only browser API. Session capabilities are never sent to Google."""
import csv
import io
import json
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .auth import Auth
from .demo import DemoYouTube, OWNER
from .engine import BusyError, Engine
from .rules import RuleBook, validate_rule
from .store import Store


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Scan(Input):
    target: str = Field(default='', max_length=300)
    max_threads: int = Field(default=500, ge=1, le=5000)
    include_replies: bool = True
    resume: bool = False
    status: Literal['published', 'heldForReview'] = 'published'


class Schedule(Scan):
    enabled: bool = False
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    action: Literal['hold', 'reject', 'ban'] = 'hold'


class Rule(Input):
    kind: Literal['contains', 'phrase', 'regex', 'allow_author']
    pattern: str = Field(min_length=1, max_length=300)


class ImportRules(Input):
    text: str = Field(max_length=50000)


class Moderate(Input):
    ids: list[str] = Field(min_length=1, max_length=1000)
    action: Literal['hold', 'reject', 'ban', 'publish']


class Resolution(Input):
    state: Literal['confirmed', 'failed']


def create_app(root: Path, token=None, demo=False, client_factory=None, shutdown=None):
    root.mkdir(parents=True, exist_ok=True)
    store, auth = Store(root / 'cleaner.db'), Auth(root)
    token = token or secrets.token_urlsafe(32)
    if demo:
        client_factory = client_factory or (lambda cancel: DemoYouTube(store, cancel))
        store.set_setting('account', OWNER)
        if not store.setting('demo_initialized'):
            for pattern in ('telegram', 'whatsapp', 'guaranteed profit'):
                store.add_rule('contains', pattern)
            store.set_setting('demo_initialized', True)
    engine = Engine(store, auth, client_factory, demo)

    @asynccontextmanager
    async def lifespan(app):
        engine.start()
        if demo and not store.stats(OWNER['id'])['total']:
            engine.submit('scan', Scan().model_dump())
        yield
        engine.stop()
        engine.worker.join(timeout=2)

    app = FastAPI(title='YouTube Spam Cleaner', version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.auth, app.state.engine = store, auth, engine
    app.state.token = token

    @app.middleware('http')
    async def local_access(request: Request, call_next):
        host = request.url.hostname
        if host not in {'127.0.0.1', 'localhost', 'testserver'}:
            return JSONResponse({'detail': 'Only loopback access is supported.'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        if request.url.path.startswith('/api/'):
            provided = request.headers.get('authorization', '')
            if not secrets.compare_digest(provided, 'Bearer ' + token):
                return JSONResponse({'detail': 'Open this page from the application launcher to connect your local session.'}, status_code=401)
            if int(request.headers.get('content-length', '0') or 0) > 150000:
                return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409 if isinstance(exc, BusyError) else 400)

    @app.get('/health')
    def health():
        return {'application': 'YouTube Spam Cleaner', 'version': __version__, 'demo': demo}

    @app.get('/api/state')
    def state():
        account = store.setting('account')
        return {'version': __version__, 'demo': demo, 'configured': auth.configured(),
            'connected': bool(account) and (demo or auth.connected()), 'account': account,
            'stats': store.stats((account or {}).get('id', '')), 'busy': engine.busy(),
            'active_job': engine.current, 'jobs': store.jobs(), 'events': store.events(),
            'rules': store.rules(), 'schedule': store.setting('schedule', {}),
            'credential_storage': 'Windows DPAPI' if __import__('sys').platform == 'win32' else 'Restricted local file'}

    @app.post('/api/oauth/config')
    def configure(config: dict):
        if demo:
            raise ValueError('Demo mode cannot import credentials or connect to Google.')
        with engine.guard:
            engine.idle()
            auth.configure(config)
            store.set_setting('account', None)
            store.set_setting('schedule', {'enabled': False})
        return {'ok': True}

    @app.post('/api/login')
    def login():
        if demo:
            raise ValueError('Google login is disabled in demo mode.')
        return {'job_id': engine.submit('login')}

    @app.post('/api/logout')
    def logout():
        if demo:
            raise ValueError('Google login is disabled in demo mode.')
        with engine.guard:
            engine.idle()
            auth.forget_token()
            store.set_setting('account', None)
            store.set_setting('schedule', {'enabled': False})
        return {'ok': True}

    @app.post('/api/scan')
    def scan(payload: Scan):
        return {'job_id': engine.submit('scan', payload.model_dump())}

    @app.post('/api/cancel')
    def cancel():
        engine.cancel.set()
        return {'ok': True}

    @app.get('/api/comments')
    def comments(view: Literal['all','flagged','handled']='all', search: str='', offset: int=0, limit: int=50):
        owner = (store.setting('account') or {}).get('id', '')
        return store.comments(owner, view, search[:300], max(0, offset), min(100, max(1, limit)))

    @app.post('/api/moderate')
    def moderate(payload: Moderate):
        return {'job_id': engine.submit('moderate', payload.model_dump())}

    @app.post('/api/rules')
    def add_rule(payload: Rule):
        with engine.guard:
            engine.idle()
            validate_rule(payload.kind, payload.pattern)
            if len(store.rules()) >= 200:
                raise ValueError('Keep at most 200 active rules.')
            rules = store.rules()
            if not any(r['kind'] == payload.kind and r['pattern'] == payload.pattern.strip() for r in rules):
                rules.append({'id':uuid.uuid4().hex,'kind':payload.kind,'pattern':payload.pattern.strip()})
            store.replace_rules(rules)
        return {'ok': True}

    @app.delete('/api/rules/{ident}')
    def delete_rule(ident: str):
        with engine.guard:
            engine.idle()
            store.replace_rules([r for r in store.rules() if r['id'] != ident])
        return {'ok': True}

    @app.post('/api/rules/import')
    def import_rules(payload: ImportRules):
        patterns = list(dict.fromkeys(line.strip() for line in payload.text.splitlines() if line.strip()))
        with engine.guard:
            engine.idle()
            existing = {(r['kind'], r['pattern']) for r in store.rules()}
            if len(existing | {('contains', p) for p in patterns}) > 200:
                raise ValueError('Keep at most 200 rules. Import a smaller keyword list.')
            for pattern in patterns:
                validate_rule('contains', pattern)
            rules = store.rules()
            for pattern in patterns:
                if ('contains',pattern) not in existing:
                    rules.append({'id':uuid.uuid4().hex,'kind':'contains','pattern':pattern})
            store.replace_rules(rules)
        return {'ok': True, 'imported': len(patterns)}

    @app.post('/api/schedule')
    def schedule(payload: Schedule):
        if payload.enabled and not store.rules():
            raise ValueError('Add at least one matching rule before enabling automatic cleaning.')
        if payload.enabled and not demo and not auth.connected():
            raise ValueError('Connect your YouTube channel before enabling automatic cleaning.')
        value = payload.model_dump() | {'next_run': time.time() + payload.interval_minutes * 60}
        with engine.guard:
            store.set_setting('schedule', value)
            store.event(None, 'Automatic cleaning enabled.' if value['enabled'] else 'Automatic cleaning paused.')
        return {'ok': True}

    @app.post('/api/actions/{ident}/resolve')
    def resolve(ident: str, payload: Resolution):
        with engine.guard:
            engine.idle()
            entries = {a['id']: a for a in store.actions()}
            if ident not in entries or entries[ident]['state'] != 'unknown':
                raise ValueError('This action does not have an unresolved result.')
            store.finish_action(ident, payload.state, 'Manually reconciled by the user after checking YouTube Studio.')
        return {'ok': True}

    @app.get('/api/actions')
    def actions():
        return {'items': store.actions()}

    @app.get('/api/export')
    def export():
        owner = (store.setting('account') or {}).get('id', '')
        rows = store.comments(owner, limit=100000)['items']
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        fields = ['id','video_id','author','author_id','text','published','moderation','last_action']
        writer.writerow(fields + ['matched_rules'])
        for row in rows:
            values = [str(row[f]) for f in fields] + ['; '.join(row['reasons'])]
            writer.writerow(["'" + v if v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n')) else v for v in values])
        return Response('\ufeff' + output.getvalue(), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="comments.csv"'})

    @app.post('/api/shutdown')
    def quit_app():
        engine.stop()
        if shutdown:
            threading.Timer(0.3, shutdown).start()
        return {'ok': True}

    assets = Path(__file__).parent / 'static'
    app.mount('/assets', StaticFiles(directory=assets), name='assets')

    @app.get('/')
    def index():
        return FileResponse(assets / 'index.html')

    return app
