import threading
import time

import pytest

from cleaner.engine import BusyError, Engine
from cleaner.store import Store
from cleaner.youtube import ApiError, Cancelled


class FakeAuth:
    def connected(self):
        return True


class FakeYouTube:
    def __init__(self, cancel, total=125):
        self.cancel, self.total, self.reads = cancel, total, 0
        self.calls, self.failure = [], None

    def account(self):
        return {'id':'own-channel','title':'Test channel'}

    def close(self):
        pass

    def check_video(self, value, owner):
        if value != 'own_video01':
            raise ValueError('Not an owned video')
        return value

    def threads(self, target, owner, token, size, status):
        self.reads += 1
        start = int(token or 0)
        end = min(start + size, self.total)
        items = [{'snippet':{'topLevelComment':self.comment(i), 'videoId':'own_video01', 'totalReplyCount':1 if i == 0 else 0}} for i in range(start,end)]
        return {'items':items,'nextPageToken':str(end) if end < self.total else None}

    def comment(self, number):
        return {'id':f'c{number}', 'snippet':{'textOriginal':f'spam {number}', 'authorDisplayName':'Test author',
            'authorChannelId':{'value':'author-id'},'publishedAt':'2026-01-01T00:00:00Z'}}

    def replies(self, parent, token):
        self.reads += 1
        return {'items':[self.comment(1000 if not token else 1001)],'nextPageToken':None if token else 'next'}

    def moderate(self, ids, action):
        self.calls.append((ids,action))
        if self.failure:
            raise self.failure


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path/'test.db')
    store.add_rule('contains','spam')
    engine=Engine(store,FakeAuth())
    client=FakeYouTube(engine.cancel)
    return store,engine,client


def scan(store,engine,client,**kwargs):
    key=store.create_job('scan')
    engine.scan(key,{'max_threads':500,'include_replies':True,**kwargs},client,client.account())
    return key


def test_all_thread_and_reply_pages(setup):
    store,engine,client=setup
    scan(store,engine,client)
    assert store.stats('own-channel')['total'] == 127
    assert store.stats('own-channel')['flagged'] == 127
    assert client.reads == 4


def test_bounded_scan_resume_and_dedup(setup):
    store,engine,client=setup
    scan(store,engine,client,max_threads=50,include_replies=False)
    assert store.stats('own-channel')['total']==50
    scan(store,engine,client,max_threads=50,include_replies=False,resume=True)
    assert store.stats('own-channel')['total']==100
    scan(store,engine,client,max_threads=50,include_replies=False,resume=True)
    assert store.stats('own-channel')['total']==125
    scan(store,engine,client,max_threads=50,include_replies=False)
    assert store.stats('own-channel')['total']==125


def test_cancellation_preserves_resume(setup):
    store,engine,client=setup
    engine.cancel.set()
    with pytest.raises(Cancelled):
        scan(store,engine,client)
    assert store.stats('own-channel')['total']==0


def test_long_reply_thread_resumes_saved_page(setup):
    store,engine,client=setup
    client.total=1
    def replies(parent,token):
        client.reads+=1
        number=int(token or 0)
        return {'items':[client.comment(2000+number)],
                'nextPageToken':str(number+1) if number<11 else None}
    client.replies=replies
    first=scan(store,engine,client)
    assert store.jobs()[0]['progress']['partial']
    assert store.stats('own-channel')['total']==11
    scan(store,engine,client,resume=True)
    assert store.stats('own-channel')['total']==13
    assert not store.jobs()[0]['progress']['partial']


def test_edited_comment_can_be_flagged_again(setup):
    store,engine,client=setup
    scan(store,engine,client,max_threads=1,include_replies=False)
    engine.moderate(store.create_job('moderate'),['c0'],'hold',client,client.account())
    original=client.comment
    def edited(number):
        row=original(number)
        row['snippet']['textOriginal']='edited spam text'
        return row
    client.comment=edited
    scan(store,engine,client,max_threads=1,include_replies=False)
    assert store.stats('own-channel')['flagged']==1


def test_rule_edit_rolls_back_if_matching_fails(setup,monkeypatch):
    store,engine,client=setup
    scan(store,engine,client,max_threads=1,include_replies=False)
    previous=store.rules()
    from cleaner.rules import RuleBook
    def timeout(*args):
        raise ValueError('Regex exceeded its time limit')
    monkeypatch.setattr(RuleBook,'match',timeout)
    with pytest.raises(ValueError,match='time limit'):
        store.replace_rules([{'id':'new','kind':'contains','pattern':'replacement'}])
    assert store.rules()==previous
    assert store.stats('own-channel')['flagged']==1


def test_batch_moderation_and_no_duplicate_actions(setup):
    store,engine,client=setup
    scan(store,engine,client,include_replies=False)
    key=store.create_job('moderate')
    ids=[f'c{i}' for i in range(125)]
    engine.moderate(key,ids,'reject',client,client.account())
    assert [len(ids) for ids,action in client.calls]==[50,50,25]
    assert store.stats('own-channel')['handled']==125
    engine.moderate(key,ids,'reject',client,client.account())
    assert len(client.calls)==3
    assert all(a['state']=='confirmed' for a in store.actions())


def test_ambiguous_write_is_not_retried(setup):
    store,engine,client=setup
    scan(store,engine,client,max_threads=1,include_replies=False)
    client.failure=ApiError('timeout','network',uncertain=True)
    key=store.create_job('moderate')
    with pytest.raises(ApiError):
        engine.moderate(key,['c0'],'ban',client,client.account())
    assert store.actions()[0]['state']=='unknown'
    with pytest.raises(ValueError,match='unknown result'):
        engine.moderate(key,['c0'],'ban',client,client.account())
    assert len(client.calls)==1


def test_explicit_failure_can_be_retried(setup):
    store,engine,client=setup
    scan(store,engine,client,max_threads=1,include_replies=False)
    key=store.create_job('moderate'); client.failure=ApiError('permission','forbidden')
    with pytest.raises(ApiError): engine.moderate(key,['c0'],'reject',client,client.account())
    assert store.actions()[0]['state']=='failed'
    client.failure=None
    engine.moderate(key,['c0'],'reject',client,client.account())
    assert store.stats('own-channel')['handled']==1


def test_rejected_cannot_be_published(setup):
    store,engine,client=setup
    scan(store,engine,client,max_threads=1,include_replies=False)
    key=store.create_job('moderate')
    engine.moderate(key,['c0'],'reject',client,client.account())
    with pytest.raises(ValueError,match='held for review'):
        engine.moderate(key,['c0'],'publish',client,client.account())


def test_cross_channel_selection_rejected(setup):
    store,engine,client=setup
    scan(store,engine,client,max_threads=1,include_replies=False)
    with pytest.raises(ValueError,match='do not belong'):
        engine.moderate(store.create_job('moderate'),['c0'],'reject',client,{'id':'other'})
    assert not client.calls


def test_interrupted_journal_is_recovered(setup):
    store,engine,client=setup
    key=store.create_job('moderate'); store.update_job(key,'running'); store.begin_action(key,'c0','reject')
    recovered=Store(store.path)
    assert recovered.jobs()[0]['state']=='interrupted'
    assert recovered.actions()[0]['state']=='unknown'


def test_queue_rejects_overlap(setup):
    store,engine,client=setup
    engine.submit('scan')
    with pytest.raises(BusyError): engine.submit('scan')


def test_automatic_failure_pauses_schedule(setup):
    store,engine,client=setup
    client.threads=lambda *args: (_ for _ in ()).throw(ApiError('quota','quotaExceeded'))
    engine.client_factory=lambda cancel:client
    store.set_setting('schedule',{'enabled':True,'next_run':time.time()+3600})
    engine.start()
    try:
        engine.submit('automatic',{'action':'hold'})
        end=time.time()+3
        while engine.busy() and time.time()<end: time.sleep(0.01)
        assert not engine.busy()
        assert store.jobs()[0]['state']=='failed'
        assert not store.setting('schedule')['enabled']
    finally:
        engine.stop(); engine.worker.join(2)
