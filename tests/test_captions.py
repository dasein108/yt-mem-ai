from pathlib import Path
from yt_summary.config import Config
from yt_summary.transcript import captions

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
    assert captions.fetch_captions("abc", _cfg(), api_factory=FakeApi) is None
