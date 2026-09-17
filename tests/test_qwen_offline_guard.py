import inspect

from backend.backends import qwen_llm_backend


def test_qwen_loaders_do_not_force_process_global_hf_offline_mode():
    """Cached Qwen loads must not mutate process-global HuggingFace offline state."""
    pytorch_source = inspect.getsource(qwen_llm_backend.PyTorchQwenLLMBackend._load_model_sync)
    mlx_source = inspect.getsource(qwen_llm_backend.MLXQwenLLMBackend._load_model_sync)

    assert "force_offline_if_cached" not in pytorch_source
    assert "force_offline_if_cached" not in mlx_source
