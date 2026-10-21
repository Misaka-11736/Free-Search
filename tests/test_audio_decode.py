import wave
import numpy as np

from free_search.models import LocalModels


def test_audio_resampled_for_whisper(tmp_path, monkeypatch):
    audio = tmp_path / "音频.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(bytes(1600 * 2))

    class Model:
        def transcribe(self, samples, **kwargs):
            assert samples.dtype == np.float32
            assert len(samples) == 3200
            return [], None

    models = LocalModels(tmp_path)
    monkeypatch.setattr(models, "_load", lambda _: Model())
    assert models.transcribe(audio) == []
