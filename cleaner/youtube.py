"""Bounded official YouTube REST calls. Each worker owns its HTTP session."""
import json
import re
from urllib.parse import parse_qs, urlparse

import requests
from google.auth.transport.requests import AuthorizedSession


class Cancelled(Exception):
    pass


class ApiError(Exception):
    def __init__(self, message, reason='', uncertain=False):
        super().__init__(message)
        self.reason, self.uncertain = reason, uncertain


class ReadLimit(Exception):
    pass


def video_id(value):
    value = value.strip()
    if re.fullmatch(r'[\w-]{11}', value, re.ASCII):
        return value
    parsed = urlparse(value)
    if parsed.hostname in {'youtu.be', 'www.youtu.be'}:
        candidate = parsed.path.strip('/').split('/')[0]
    elif parsed.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        parts = parsed.path.strip('/').split('/')
        candidate = parts[1] if len(parts) == 2 and parts[0] in {'shorts','live','embed'} else parse_qs(parsed.query).get('v', [''])[0]
    else:
        candidate = ''
    if not re.fullmatch(r'[\w-]{11}', candidate, re.ASCII):
        raise ValueError('Enter a valid YouTube video URL or 11-character video ID.')
    return candidate


class YouTube:
    def __init__(self, auth, cancel, session=None, max_reads=500):
        self.auth, self.cancel = auth, cancel
        self.session = session or AuthorizedSession(auth.credentials())
        self.reads, self.max_reads = 0, max_reads

    def close(self):
        self.session.close()

    def request(self, method, resource, **params):
        if self.cancel.is_set():
            raise Cancelled()
        if method == 'GET':
            if self.reads >= self.max_reads:
                raise ReadLimit('Read-request budget reached. Resume the scan to continue.')
            self.reads += 1
        # Writes are never automatically retried: a timeout can follow a successful action.
        for attempt in range(4 if method == 'GET' else 1):
            try:
                response = self.session.request(method, 'https://www.googleapis.com/youtube/v3/' + resource,
                    params={k: v for k, v in params.items() if v is not None}, timeout=(8, 30))
            except requests.RequestException as exc:
                if method == 'GET' and attempt < 3:
                    if self.cancel.wait(2 ** attempt):
                        raise Cancelled() from exc
                    continue
                raise ApiError('Connection failed. For a moderation request, verify its result before retrying.',
                               'network', uncertain=method != 'GET') from exc
            if response.status_code < 400:
                return response.json() if response.content else {}
            try:
                error = response.json().get('error', {})
                reason = (error.get('errors') or [{}])[0].get('reason', '')
            except (ValueError, AttributeError):
                reason = ''
            if method == 'GET' and response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                if self.cancel.wait(2 ** attempt):
                    raise Cancelled()
                continue
            messages = {'quotaExceeded':'YouTube API quota is exhausted. Automatic cleaning has been paused.',
                'dailyLimitExceeded':'YouTube API daily quota is exhausted. Automatic cleaning has been paused.',
                'forbidden':'Google denied this action. Check that you own the selected channel or video.',
                'commentsDisabled':'Comments are disabled for this video.',
                'videoNotFound':'This video was not found or is not accessible.',
                'authError':'Your Google session is no longer valid. Connect your channel again.'}
            raise ApiError(messages.get(reason, f'YouTube returned HTTP {response.status_code} ({reason or "request failed"}).'),
                reason, uncertain=method != 'GET' and response.status_code >= 500)

    def account(self):
        items = self.request('GET', 'channels', part='snippet', mine='true').get('items', [])
        if not items:
            raise ValueError('This Google account has no accessible YouTube channel.')
        return {'id': items[0]['id'], 'title': items[0]['snippet']['title']}

    def check_video(self, value, owner):
        ident = video_id(value)
        items = self.request('GET', 'videos', part='snippet', id=ident).get('items', [])
        if not items or items[0]['snippet']['channelId'] != owner:
            raise ValueError('Choose a video belonging to the connected YouTube channel.')
        return ident

    def threads(self, target, owner, token, size, status):
        return self.request('GET', 'commentThreads', part='snippet', maxResults=size, order='time',
            textFormat='plainText', moderationStatus=status, pageToken=token,
            videoId=target or None, allThreadsRelatedToChannelId=None if target else owner)

    def replies(self, parent, token):
        return self.request('GET', 'comments', part='snippet', parentId=parent, maxResults=100,
                            textFormat='plainText', pageToken=token)

    def moderate(self, ids, action):
        status = {'hold':'heldForReview','reject':'rejected','ban':'rejected','publish':'published'}[action]
        return self.request('POST', 'comments/setModerationStatus', id=','.join(ids),
                            moderationStatus=status, banAuthor='true' if action == 'ban' else None)
