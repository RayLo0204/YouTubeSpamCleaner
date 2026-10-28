"""One serialized worker shared by manual jobs and the persistent scheduler."""
import json
import queue
import threading
import time

from .rules import RuleBook
from .youtube import ApiError, Cancelled, ReadLimit, YouTube


class BusyError(ValueError):
    pass


class Engine:
    def __init__(self, store, auth, client_factory=None, demo=False):
        self.store, self.auth, self.demo = store, auth, demo
        self.client_factory = client_factory or (lambda cancel: YouTube(auth, cancel))
        self.guard = threading.RLock()
        self.pending = False
        self.current = None
        self.cancel = threading.Event()
        self.closed = threading.Event()
        self.queue = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True, name='cleaner-worker')
        self.scheduler = threading.Thread(target=self._schedule, daemon=True, name='cleaner-scheduler')

    def start(self):
        self.worker.start()
        self.scheduler.start()

    def busy(self):
        with self.guard:
            return self.pending

    def idle(self):
        if self.busy():
            raise BusyError('Wait for the current task, or cancel it before changing these settings.')

    def submit(self, kind, payload=None):
        with self.guard:
            if self.pending or self.closed.is_set():
                raise BusyError('Another task is running. Wait for it to finish or cancel it.')
            self.pending = True
            self.cancel.clear()
            key = self.store.create_job(kind)
            self.current = key
            self.queue.put((key, kind, payload or {}))
            return key

    def stop(self):
        self.closed.set()
        self.cancel.set()

    def _work(self):
        while not self.closed.is_set():
            try:
                key, kind, payload = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            client = None
            try:
                self.store.update_job(key, 'running')
                self.store.event(key, f'{kind.title()} started.' + (' Demo mode: no YouTube requests.' if self.demo else ''))
                if kind == 'login':
                    if self.demo:
                        raise ValueError('Google login is disabled in demo mode.')
                    self.auth.login()
                client = self.client_factory(self.cancel)
                account = client.account()
                previous = self.store.setting('account', {})
                if kind != 'login' and previous and previous['id'] != account['id']:
                    raise ValueError('Connected channel changed. Reconnect and review the target before continuing.')
                self.store.set_setting('account', account)
                if kind in {'scan', 'automatic'}:
                    self.scan(key, payload, client, account)
                    if kind == 'automatic':
                        candidates = self.store.comments(account['id'], view='flagged', limit=1000)['items']
                        # Scope automatic actions to the target and moderation state just scanned.
                        target = client.check_video(payload['target'], account['id']) if payload.get('target') else ''
                        candidates = [c for c in candidates if (not target or c['video_id'] == target)
                                      and c['moderation'] == payload.get('status', 'published')]
                        self.moderate(key, [c['id'] for c in candidates], payload['action'], client, account)
                elif kind == 'moderate':
                    self.moderate(key, payload['ids'], payload['action'], client, account)
                self.store.update_job(key, 'completed')
                self.store.event(key, 'Task completed.')
            except Cancelled:
                self.store.update_job(key, 'cancelled')
                self.store.event(key, 'Cancelled. Completed actions are retained; in-flight requests may finish.', 'warning')
            except Exception as exc:
                message = str(exc)[:1500] or 'The task could not be completed.'
                self.store.update_job(key, 'failed', error=message)
                self.store.event(key, message, 'error')
                if kind == 'automatic' or (isinstance(exc, ApiError) and exc.reason in {'quotaExceeded','dailyLimitExceeded'}):
                    schedule = self.store.setting('schedule', {})
                    schedule['enabled'] = False
                    self.store.set_setting('schedule', schedule)
                    self.store.event(key, 'Automatic cleaning paused. Review the error before enabling it again.', 'warning')
            finally:
                if client:
                    client.close()
                with self.guard:
                    self.pending, self.current = False, None
                self.queue.task_done()

    def scan(self, key, payload, client, account):
        owner = account['id']
        target = client.check_video(payload['target'], owner) if payload.get('target') else ''
        status = payload.get('status', 'published')
        cursor_key = f'cursor:{owner}:{target}:{status}'
        cursor = self.store.setting(cursor_key) if payload.get('resume') else None
        book = RuleBook(self.store.rules())
        counts = {'threads': 0, 'replies': 0, 'flagged': 0, 'read_requests': 0, 'partial': False}
        maximum = payload.get('max_threads', 500)
        try:
            while counts['threads'] < maximum:
                if self.cancel.is_set():
                    raise Cancelled()
                # Save the current page until every item and its replies have been processed.
                self.store.set_setting(cursor_key, cursor)
                page = client.threads(target, owner, cursor, min(100, maximum - counts['threads']), status)
                reply_partial = False
                for thread in page.get('items', []):
                    if self.cancel.is_set():
                        raise Cancelled()
                    snippet = thread['snippet']
                    comment = snippet['topLevelComment']
                    self._save(comment, owner, snippet.get('videoId', target), '', status, book, counts)
                    counts['threads'] += 1
                    if payload.get('include_replies', True) and snippet.get('totalReplyCount', 0):
                        reply_key = 'reply:' + comment['id']
                        reply_token = self.store.setting(reply_key) if payload.get('resume') else None
                        for _ in range(10):
                            self.store.set_setting(reply_key, reply_token)
                            replies = client.replies(comment['id'], reply_token)
                            for reply in replies.get('items', []):
                                self._save(reply, owner, snippet.get('videoId', target), comment['id'],
                                           reply['snippet'].get('moderationStatus', 'published'), book, counts)
                                counts['replies'] += 1
                            reply_token = replies.get('nextPageToken')
                            self.store.set_setting(reply_key, reply_token)
                            if not reply_token:
                                break
                        if reply_token:
                            counts['partial'] = True
                            reply_partial = True
                            self.store.event(key, 'A reply thread reached the 1,000-reply limit; Resume continues its saved reply cursor.', 'warning')
                    counts['read_requests'] = client.reads
                    if counts['threads'] % 10 == 0:
                        self.store.update_job(key, progress=counts)
                if reply_partial:
                    # Keep this top-level page until its long reply chains have drained.
                    break
                cursor = page.get('nextPageToken')
                self.store.set_setting(cursor_key, cursor)
                if not cursor:
                    break
            if cursor:
                counts['partial'] = True
        except ReadLimit:
            counts['partial'] = True
            self.store.event(key, 'Read-request budget reached. Use Resume to continue the current page.', 'warning')
        counts['read_requests'] = client.reads
        self.store.update_job(key, progress=counts)
        self.store.event(key, f"Scanned {counts['threads']} threads and {counts['replies']} replies; {counts['flagged']} rule matches." +
                         (' Scan is partial; use Resume or increase the thread limit.' if counts['partial'] else ''))

    def _save(self, comment, owner, video, parent, status, book, counts):
        snippet = comment['snippet']
        text = snippet.get('textOriginal', snippet.get('textDisplay', ''))
        author_id = snippet.get('authorChannelId', {}).get('value', '')
        reasons = book.match(text, author_id)
        row = {'id': comment['id'], 'owner': owner, 'video_id': video or '', 'parent_id': parent,
            'author': snippet.get('authorDisplayName', 'Unknown author'), 'author_id': author_id,
            'text': text, 'published': snippet.get('publishedAt', ''),
            'moderation': snippet.get('moderationStatus', status)}
        self.store.save_comment(row, reasons)
        counts['flagged'] += bool(reasons)

    def moderate(self, key, ids, action, client, account):
        ids = list(dict.fromkeys(ids))
        comments = self.store.selected(ids, account['id'])
        if len(comments) != len(ids):
            raise ValueError('Some selected comments do not belong to the connected channel or are no longer in the local list.')
        eligible = []
        for comment in comments:
            if self.store.uncertain(comment['id']):
                raise ValueError('A previous action has an unknown result. Verify it in YouTube Studio before processing it again.')
            if action == 'publish' and comment['moderation'] != 'heldForReview':
                raise ValueError('Only comments held for review can be published by this application.')
            if comment['last_action'] == action:
                continue
            eligible.append(comment['id'])
        completed = 0
        for offset in range(0, len(eligible), 50):
            if self.cancel.is_set():
                raise Cancelled()
            batch = eligible[offset:offset + 50]
            journal = [self.store.begin_action(key, ident, action) for ident in batch]
            try:
                client.moderate(batch, action)
            except BaseException as exc:
                uncertain = not isinstance(exc, ApiError) or exc.uncertain
                for entry in journal:
                    self.store.finish_action(entry, 'unknown' if uncertain else 'failed', str(exc))
                raise
            for entry in journal:
                self.store.finish_action(entry, 'confirmed', 'Simulated; no YouTube request.' if self.demo else 'YouTube accepted the moderation request.')
            completed += len(batch)
            self.store.update_job(key, progress={'processed': completed, 'selected': len(eligible), 'action': action})
        self.store.event(key, f'{completed} comments processed ({action}).' + (' Simulation only.' if self.demo else ''))

    def _schedule(self):
        while not self.closed.wait(1):
            with self.guard:
                schedule = self.store.setting('schedule', {})
                if not schedule.get('enabled') or self.busy():
                    continue
                if not self.demo and not self.auth.connected():
                    schedule['enabled'] = False
                    self.store.set_setting('schedule', schedule)
                    continue
                if time.time() < schedule.get('next_run', 0):
                    continue
                try:
                    self.submit('automatic', schedule)
                except BusyError:
                    continue
                schedule['next_run'] = time.time() + schedule.get('interval_minutes', 15) * 60
                self.store.set_setting('schedule', schedule)
