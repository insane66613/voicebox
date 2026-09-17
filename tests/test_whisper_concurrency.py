import asyncio
import time

from backend.backends.pytorch_backend import PyTorchSTTBackend


def test_whisper_load_is_single_flight():
    backend = PyTorchSTTBackend()
    calls = []

    def fake_load(model_size: str):
        calls.append(model_size)
        time.sleep(0.05)
        backend.model = object()
        backend.processor = object()
        backend.model_size = model_size

    backend._load_model_sync = fake_load

    async def run():
        await asyncio.gather(*(backend.load_model_async("base") for _ in range(3)))

    asyncio.run(run())
    assert calls == ["base"]
