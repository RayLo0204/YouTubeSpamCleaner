"""Deterministic offline demo; it cannot authenticate or contact YouTube."""
from .youtube import Cancelled

OWNER = {'id': 'demo-channel', 'title': 'Northstar Studio (demo)'}

SAMPLES = [
    ('Maya', 'This breakdown finally made it click. Thank you!'),
    ('Crypto Rewards', 'Guaranteed profit every day. Contact me on Telegram for the next trade.'),
    ('Alex', 'The comparison at 04:20 was exactly what I needed.'),
    ('Support Desk', 'You won a prize! Message our WhatsApp number to claim it.'),
    ('Jamie', 'Could you do a follow-up on the smaller setup?'),
    ('Growth Expert', 'Tｅｌｅｇｒａｍ me for guaranteed profit. Limited spots.'),
    ('Sam', 'Great video. I shared it with the team this morning.'),
    ('Giveaway Team', 'Send us a WhatsApp message to receive your exclusive reward.'),
    ('Taylor', 'The audio sounds much better in this one.'),
    ('Noah', 'I tried this yesterday and the steps worked perfectly.'),
    ('Earnings Bot', 'Guaranteed profit with zero risk. Join our private group now.'),
    ('Riley', 'Would the same workflow work with an older machine?'),
]


class DemoYouTube:
    def __init__(self, store, cancel):
        self.store, self.cancel, self.reads = store, cancel, 0

    def close(self):
        pass

    def account(self):
        return OWNER.copy()

    def check_video(self, value, owner):
        if value not in {'demo_video1', 'https://youtu.be/demo_video1'}:
            raise ValueError('In demo mode, leave the video field empty or use demo_video1.')
        return 'demo_video1'

    def comment(self, number, reply=False):
        author, text = SAMPLES[number % len(SAMPLES)]
        key = ('reply-' if reply else 'comment-') + str(number)
        return {'id': key, 'snippet': {'textOriginal': text, 'authorDisplayName': author,
            'authorChannelId': {'value': 'author-' + str(number % len(SAMPLES))},
            'publishedAt': f'2026-10-{27 - number // 24:02d}T{23 - number % 24:02d}:00:00Z',
            'moderationStatus': self.store.setting('demo_actions', {}).get(key, 'published')}}

    def threads(self, target, owner, token, size, status):
        self.reads += 1
        if self.cancel.wait(0.03):
            raise Cancelled()
        data = []
        for i in range(36):
            comment = self.comment(i)
            if comment['snippet']['moderationStatus'] == status:
                data.append({'snippet': {'topLevelComment': comment, 'videoId':'demo_video1', 'totalReplyCount':2 if i % 6 == 0 else 0}})
        start = int(token or 0)
        end = start + size
        return {'items': data[start:end], 'nextPageToken': str(end) if end < len(data) else None}

    def replies(self, parent, token):
        self.reads += 1
        number = int(parent.split('-')[-1])
        return {'items': [self.comment(100 + number, True), self.comment(101 + number, True)]}

    def moderate(self, ids, action):
        if self.cancel.is_set():
            raise Cancelled()
        states = self.store.setting('demo_actions', {})
        states.update({i: {'hold':'heldForReview','reject':'rejected','ban':'rejected','publish':'published'}[action] for i in ids})
        self.store.set_setting('demo_actions', states)
