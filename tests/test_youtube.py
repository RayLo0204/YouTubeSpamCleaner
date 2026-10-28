import json
import threading

import pytest
import requests

from cleaner.youtube import ApiError, YouTube


class Session:
    def __init__(self, responses):
        self.responses=list(responses); self.calls=[]

    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        result=self.responses.pop(0)
        if isinstance(result,Exception): raise result
        return result

    def close(self): pass


def response(status, body=None):
    r=requests.Response();r.status_code=status
    r._content=b'' if body is None else json.dumps(body).encode()
    return r


def test_correct_moderation_api_and_no_permanent_delete():
    session=Session([response(204)])
    client=YouTube(None,threading.Event(),session=session)
    client.moderate(['one','two'],'ban')
    args,kwargs=session.calls[0]
    assert args==('POST','https://www.googleapis.com/youtube/v3/comments/setModerationStatus')
    assert kwargs['params']=={'id':'one,two','moderationStatus':'rejected','banAuthor':'true'}


def test_transient_read_is_retried_without_waiting_in_test():
    class Cancel:
        def is_set(self): return False
        def wait(self,seconds): return False
    session=Session([response(503),response(200,{'items':[]})])
    client=YouTube(None,Cancel(),session=session)
    assert client.threads('', 'owner', None, 100, 'published')=={'items':[]}
    assert len(session.calls)==2
    assert session.calls[1][1]['params']['textFormat']=='plainText'


@pytest.mark.parametrize('result',[requests.Timeout(),response(503)])
def test_write_failures_are_not_blindly_retried(result):
    session=Session([result]); client=YouTube(None,threading.Event(),session=session)
    with pytest.raises(ApiError) as error: client.moderate(['one'],'hold')
    assert error.value.uncertain
    assert len(session.calls)==1


def test_permission_and_quota_are_explicit_errors():
    for reason in ('forbidden','quotaExceeded'):
        session=Session([response(403,{'error':{'errors':[{'reason':reason}]}})])
        client=YouTube(None,threading.Event(),session=session)
        with pytest.raises(ApiError) as error: client.account()
        assert error.value.reason==reason
        assert len(session.calls)==1
