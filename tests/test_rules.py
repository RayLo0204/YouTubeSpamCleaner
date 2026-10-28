import pytest

from cleaner.rules import RuleBook, normalize, validate_rule
from cleaner.youtube import video_id


def book(kind='contains', pattern='telegram'):
    return RuleBook([{'kind':kind, 'pattern':pattern}])


@pytest.mark.parametrize('text', ['Telegram me', 'TELEGRAM', 'Ｔｅｌｅｇｒａｍ', 'tele\u200bgram'])
def test_normalized_matching(text):
    assert book().match(text, 'author')


def test_allowlist_uses_id_not_display_name():
    rules = RuleBook([{'kind':'contains','pattern':'spam'}, {'kind':'allow_author','pattern':'trusted-id'}])
    assert rules.match('spam', 'trusted-id') == []
    assert rules.match('spam', 'other-id') == ['contains: spam']


def test_whole_phrase_does_not_match_substring():
    assert book('phrase','free').match('get free prizes', 'a')
    assert not book('phrase','free').match('freedom matters', 'a')


def test_regex_and_disabled_rules():
    assert book('regex', r'earn\s+\d+').match('EARN 100 daily', 'a')
    assert RuleBook([{'kind':'contains','pattern':'earn','enabled':False}]).match('earn', 'a') == []


@pytest.mark.parametrize('kind,pattern', [('bad','x'),('contains','  '),('regex','['),('contains','x'*301)])
def test_invalid_rule(kind, pattern):
    with pytest.raises(ValueError):
        validate_rule(kind, pattern)


def test_hostile_regex_has_time_limit():
    with pytest.raises(ValueError, match='too long'):
        book('regex', '(a+)+$').match('a'*20000+'!', 'a')


@pytest.mark.parametrize('url', ['dQw4w9WgXcQ','https://youtu.be/dQw4w9WgXcQ?t=10',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ','https://youtube.com/shorts/dQw4w9WgXcQ'])
def test_video_inputs(url):
    assert video_id(url) == 'dQw4w9WgXcQ'


@pytest.mark.parametrize('url', ['https://evil.test/watch?v=dQw4w9WgXcQ','file:///etc/passwd','short','https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ'])
def test_non_youtube_inputs(url):
    with pytest.raises(ValueError):
        video_id(url)
