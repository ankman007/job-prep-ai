"""Shared pytest configuration for the Job Fit AI backend tests.

- Puts ``backend/`` on ``sys.path`` so ``import app...`` works from the repo root.
- Stubs ``google.genai`` when the real SDK is not installed, so modules that
  import it at top level (``app.service.llm.gemini``,
  ``app.service.interview_cheatsheet``) can be imported without network access
  or the SDK. Tests never call the real LLM either way.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _install_genai_stub() -> None:
    try:
        from google import genai  # noqa: F401
        from google.genai import types as _types  # noqa: F401
        return
    except Exception:
        pass

    google_mod = sys.modules.get("google") or types.ModuleType("google")
    if not hasattr(google_mod, "__path__"):
        google_mod.__path__ = []  # mark as package
    genai_mod = types.ModuleType("google.genai")
    genai_types = types.ModuleType("google.genai.types")

    class GenerateContentConfig:  # minimal stand-in recording kwargs
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Client:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("google.genai stub: tests must mock the client")

    genai_types.GenerateContentConfig = GenerateContentConfig
    genai_mod.types = genai_types
    genai_mod.Client = Client
    google_mod.genai = genai_mod
    sys.modules["google"] = google_mod
    sys.modules["google.genai"] = genai_mod
    sys.modules["google.genai.types"] = genai_types


_install_genai_stub()
