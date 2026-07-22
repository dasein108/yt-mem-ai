from pathlib import Path
from yt_summary.config import Config
from yt_summary.transcript import whisper

def _cfg():
    return Config(db_path=Path("x"), downloads_dir=Path("d"), proxy_username=None,
                  proxy_password=None, cookies_browser=None, whisper_model="small",
                  whisper_device="cpu", whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=Path("s"), embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None)

class _Seg:
    def __init__(self, start, end, text): self.start, self.end, self.text = start, end, text

class _Info:
    language = "en"

def test_transcribe_audio_maps_segments():
    captured = {}
    class FakeModel:
        def __init__(self, model, device, compute_type):
            captured.update(model=model, device=device, compute_type=compute_type)
        def transcribe(self, path, beam_size=5):
            return iter([_Seg(0.0, 1.0, " hi"), _Seg(1.0, 2.0, " there")]), _Info()
    res = whisper.transcribe_audio("/a/b.mp3", "abc", _cfg(), model_factory=FakeModel)
    assert res.source == "whisper"
    assert res.lang == "en"
    assert res.full_text == "hi there"
    assert res.segments[0].end_s == 1.0
    assert captured["compute_type"] == "int8"
