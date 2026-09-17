import asyncio
import io
import logging

import pytest
from fastapi import HTTPException, UploadFile

from backend.routes import transcription
from backend.utils import audio as audio_utils
from backend.utils import tasks as task_utils


class FakeWhisperModel:
    def __init__(self, gate: asyncio.Event | None = None):
        self.model_size = "base"
        self.gate = gate
        self.load_calls = 0

    def is_loaded(self):
        return False

    def _is_model_cached(self, model_size: str):
        return False

    async def load_model_async(self, model_size: str):
        self.load_calls += 1
        if self.gate is not None:
            await self.gate.wait()


async def _call_transcribe(monkeypatch, whisper):
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(audio_utils, "load_audio", lambda _path: ([0.0], 1))
    upload = UploadFile(filename="sample.m4a", file=io.BytesIO(b"audio"))
    with pytest.raises(HTTPException) as exc:
        await transcription.transcribe_audio(file=upload, model="base")
    assert exc.value.status_code == 202


def test_duplicate_transcribe_requests_share_active_whisper_download(monkeypatch):
    async def run():
        task_utils._task_manager = task_utils.TaskManager()
        gate = asyncio.Event()
        whisper = FakeWhisperModel(gate)

        await _call_transcribe(monkeypatch, whisper)
        await asyncio.sleep(0)
        assert whisper.load_calls == 1

        await _call_transcribe(monkeypatch, whisper)
        await asyncio.sleep(0)
        assert whisper.load_calls == 1

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())


def test_transcribe_logs_internal_exception_before_500(monkeypatch, caplog):
    class FailingWhisperModel(FakeWhisperModel):
        def is_loaded(self):
            return True

        async def transcribe(self, *_args, **_kwargs):
            raise RuntimeError("synthetic transcription failure")

    async def run():
        whisper = FailingWhisperModel()
        monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
        monkeypatch.setattr(audio_utils, "load_audio", lambda _path: ([0.0], 1))
        upload = UploadFile(filename="sample.m4a", file=io.BytesIO(b"audio"))
        with pytest.raises(HTTPException) as exc:
            await transcription.transcribe_audio(file=upload, model="base")
        assert exc.value.status_code == 500

    with caplog.at_level(logging.ERROR):
        asyncio.run(run())

    assert "synthetic transcription failure" in caplog.text


def test_non_wav_upload_is_transcoded_before_whisper(monkeypatch):
    async def run():
        seen = {}

        class LoadedWhisper(FakeWhisperModel):
            def is_loaded(self):
                return True

            async def transcribe(self, path, _language, _model_size):
                seen["stt_path"] = path
                return "ok"

        monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: LoadedWhisper())
        monkeypatch.setattr(audio_utils, "load_audio", lambda path: (seen.setdefault("load_path", path) and [0.0], 1))
        monkeypatch.setattr(audio_utils, "save_audio", lambda _audio, path, _sr: seen.setdefault("save_path", path))

        upload = UploadFile(filename="browser.webm", file=io.BytesIO(b"audio"))
        result = await transcription.transcribe_audio(file=upload, model="base")

        assert result.text == "ok"
        assert seen["load_path"].endswith(".webm")
        assert seen["save_path"].endswith(".stt.wav")
        assert seen["stt_path"] == seen["save_path"]

    asyncio.run(run())
