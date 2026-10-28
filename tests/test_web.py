import json
import time

import pytest
from fastapi.testclient import TestClient

from cleaner.auth import Auth, protect
from cleaner.web import create_app

TOKEN='test-session-capability'
HEADERS={'Authorization':'Bearer '+TOKEN}


@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path,token=TOKEN,demo=True)
    with TestClient(app,headers=HEADERS) as test:
        end=time.time()+4
        while app.state.engine.busy() and time.time()<end: time.sleep(0.01)
        yield test


def test_web_shell_and_assets(client):
    root=client.get('/')
    assert root.status_code==200 and 'Make room for real conversations.' in root.text
    assert 'frame-ancestors' in root.headers['content-security-policy']
    assert client.get('/assets/app.js').status_code==200
    assert client.get('/assets/style.css').status_code==200


def test_session_required(client):
    assert client.get('/api/state',headers={'Authorization':''}).status_code==401


def test_cross_origin_and_dns_rebinding_blocked(client):
    assert client.post('/api/scan',json={},headers={'Origin':'https://evil.test'}).status_code==403
    assert client.get('/api/state',headers={'Host':'evil.test'}).status_code==403


def test_demo_is_offline_and_has_replies(client):
    state=client.get('/api/state').json()
    assert state['demo'] and state['stats']['total']==48 and state['stats']['flagged']>0
    assert client.post('/api/login').status_code==400
    assert client.post('/api/oauth/config',json={}).status_code==400


def test_import_dedup_and_reclassification(client):
    before=client.get('/api/state').json()['rules']
    assert client.post('/api/rules/import',json={'text':'telegram\nnew phrase\nnew phrase\n'}).status_code==200
    after=client.get('/api/state').json()['rules']
    assert len(after)==len(before)+1
    assert client.post('/api/rules',json={'kind':'regex','pattern':'['}).status_code==400


def test_paginated_search_and_csv(client):
    response=client.get('/api/comments?view=all&limit=10&offset=10').json()
    assert response['total']==48 and len(response['items'])==10
    assert client.get('/api/comments?search=guaranteed').json()['total']>0
    csv=client.get('/api/export')
    assert csv.status_code==200 and 'attachment' in csv.headers['content-disposition']
    assert 'matched_rules' in csv.text


def test_payload_validation(client):
    assert client.post('/api/scan',json={'max_threads':0}).status_code==422
    assert client.post('/api/moderate',json={'ids':[],'action':'reject'}).status_code==422
    assert client.post('/api/moderate',json={'ids':['x'],'action':'delete'}).status_code==422
    assert client.post('/api/rules',json={'kind':'contains','pattern':'\u200b'}).status_code==400


def test_csv_neutralizes_spreadsheet_formula(client):
    store=client.app.state.store
    owner=client.get('/api/state').json()['account']['id']
    row=store.comments(owner)['items'][0]
    row['text']='  =HYPERLINK("https://example.com")'
    store.save_comment(row,[])
    import csv,io
    rows=list(csv.DictReader(io.StringIO(client.get('/api/export').text.lstrip('\ufeff'))))
    assert next(r for r in rows if r['id']==row['id'])['text'].startswith("'  =")


def test_schedule_persists_without_starting_immediately(client):
    response=client.post('/api/schedule',json={'enabled':True,'interval_minutes':5,'action':'hold'})
    assert response.status_code==200
    value=client.get('/api/state').json()['schedule']
    assert value['enabled'] and value['next_run']>time.time()
    client.post('/api/schedule',json={'enabled':False})


def test_protected_credential_roundtrip(tmp_path):
    auth=Auth(tmp_path)
    auth.write('test',{'refresh_token':'example-only'})
    assert auth.read('test')=={'refresh_token':'example-only'}
    import sys
    if sys.platform=='win32':
        assert b'example-only' not in (tmp_path/'test.vault').read_bytes()


def test_oauth_config_rejects_redirected_endpoints(tmp_path):
    auth=Auth(tmp_path)
    config={'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'example',
        'auth_uri':'https://evil.test/auth','token_uri':'https://oauth2.googleapis.com/token'}}
    with pytest.raises(ValueError,match='Google Accounts'):
        auth.configure(config)
    assert not auth.configured()
