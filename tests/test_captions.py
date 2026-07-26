import pytest
from pathlib import Path
from yt_mem_ai.config import Config
from yt_mem_ai.transcript import captions

def _cfg():
    return Config(downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=None, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None, openrouter_model="openai/gpt-4o-mini",
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)

class _Snip:
    def __init__(self, text, start, duration):
        self.text, self.start, self.duration = text, start, duration

class _Fetched:
    def __init__(self, snips, language_code="en"):
        self._snips, self.language_code = snips, language_code
    def __iter__(self): return iter(self._snips)

def test_fetch_captions_maps_segments():
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            return _Fetched([_Snip("hello", 0.0, 1.0), _Snip("world", 1.0, 2.0)])
    res = captions.fetch_captions("abc", _cfg(), api_factory=FakeApi)
    assert res is not None
    assert res.source == "captions"
    assert res.full_text == "hello world"
    assert res.segments[1].start_s == 1.0
    assert res.segments[1].end_s == 3.0

def test_fetch_captions_returns_none_on_error():
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            raise Exception("no transcript")
        def list(self, vid):
            raise Exception("nothing")
    assert captions.fetch_captions("abc", _cfg(), api_factory=FakeApi) is None


class _Track:
    def __init__(self, lang, is_generated, snips):
        self.language_code, self.is_generated, self._snips = lang, is_generated, snips
    def fetch(self):
        return _Fetched(self._snips, language_code=self.language_code)


def test_fetch_captions_falls_back_to_any_language():
    # No English, but a Russian track exists → fetch it, keep lang="ru".
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            raise Exception("no en")
        def list(self, vid):
            return [_Track("ru", True, [_Snip("привет", 0.0, 2.0)])]
    res = captions.fetch_captions("abc", _cfg(), api_factory=FakeApi)
    assert res is not None
    assert res.lang == "ru"
    assert res.full_text == "привет"


def test_fetch_captions_prefers_manual_over_generated():
    # Two ru tracks: generated + manual → picks the manual one.
    manual = _Track("ru", False, [_Snip("manual", 0.0, 1.0)])
    generated = _Track("ru", True, [_Snip("auto", 0.0, 1.0)])
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            raise Exception("no en")
        def list(self, vid):
            return [generated, manual]  # unsorted; impl must prefer manual
    res = captions.fetch_captions("abc", _cfg(), api_factory=FakeApi)
    assert res.full_text == "manual"


def test_fetch_captions_raises_blocked_on_youtube_block():
    # A YouTube rate-limit/block must raise CaptionsBlocked, NOT be silently
    # reported as "no captions" (the captions may well exist).
    from yt_mem_ai.transcript.captions import _BLOCK_ERRORS
    from yt_mem_ai.transcript import CaptionsBlocked
    if not _BLOCK_ERRORS:
        pytest.skip("youtube-transcript-api block errors unavailable")
    Block = _BLOCK_ERRORS[0]

    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            raise Block(vid)  # block on the preferred-language fetch

    with pytest.raises(CaptionsBlocked):
        captions.fetch_captions("abc", _cfg(), api_factory=FakeApi)


def test_fetch_captions_respects_configured_langs():
    # cfg.caption_langs is passed through to api.fetch.
    seen = {}
    class FakeApi:
        def __init__(self, proxy_config=None): pass
        def fetch(self, vid, languages=("en",)):
            seen["langs"] = languages
            return _Fetched([_Snip("x", 0.0, 1.0)], language_code=languages[0])
    from dataclasses import replace
    res = captions.fetch_captions("abc", replace(_cfg(), caption_langs=("ru", "en")),
                                  api_factory=FakeApi)
    assert seen["langs"] == ("ru", "en")
    assert res.lang == "ru"
