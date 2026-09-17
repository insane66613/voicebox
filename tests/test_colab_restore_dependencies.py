import ast
from pathlib import Path

RESTORE = Path(__file__).resolve().parents[1] / "backend" / "colab_restore.py"


def load_dependency_planner():
    tree = ast.parse(RESTORE.read_text(encoding="utf-8"))
    fn = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef)
         and node.name == "build_colab_dependency_plan"),
        None,
    )
    assert fn is not None, "build_colab_dependency_plan is missing"
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(RESTORE), "exec"), namespace)
    return namespace["build_colab_dependency_plan"]


def test_python_313_uses_qwen_core_without_incompatible_optional_engines():
    plan = load_dependency_planner()((3, 13))
    joined = " ".join(plan)
    assert "qwen-tts==0.1.1" in joined
    assert "fastmcp>=3.0,<4.0" in joined
    assert "transformers==4.57.3" in joined
    assert "pedalboard==0.9.24" in joined
    assert "kokoro" not in joined.lower()
    assert "numba" not in joined.lower()


def test_restore_validates_actual_qwen_model_class_in_fresh_process():
    source = RESTORE.read_text(encoding="utf-8")
    assert "from qwen_tts import Qwen3TTSModel" in source
    assert "from backend.app import app" in source
    assert "from backend.utils.effects import BUILTIN_PRESETS" in source
