"""Generic LLM client configuration.

Reads from environment variables (optionally via a project-root `.env`
file, which is gitignored). Names are provider-agnostic: put any
OpenAI-compatible chat-completions key in ``LLM_API_KEY``.

Environment variables:
    LLM_API_KEY: API key for an OpenAI-compatible chat API (required).
    LLM_BASE_URL: API base URL. Defaults to the ASU endpoint.
    LLM_MODEL: Default model name for tool-using runs.

The project-root ``.env`` file is loaded first but never overrides
variables already present in the environment.
"""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://openai.rc.asu.edu/v1"
DEFAULT_MODEL = "llama3-groq-70b-tool-use"


def _unquote(value: str) -> str:
    """Strip one layer of matched surrounding quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def load_dotenv(env_path: Path | None = None) -> None:
    """Load KEY=VALUE lines from a `.env` file into os.environ.

    Existing environment variables always win. Lines starting with `#`
    and blank lines are skipped. Surrounding quotes are stripped.
    """
    path = env_path or Path(__file__).resolve().parent.parent / ".env"
    try:
        text = path.read_text()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = _unquote(value.strip())
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL


def get_llm_config() -> LLMConfig:
    """Return the LLM configuration from the environment.

    Raises:
        RuntimeError: If LLM_API_KEY is not set anywhere.
    """
    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set. Put your LLM API key in the "
            "project-root .env file as LLM_API_KEY=<key> (see .env.example), "
            "or export LLM_API_KEY in your shell."
        )
    base_url = os.environ.get("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL
    model = os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODEL
    return LLMConfig(api_key=api_key, base_url=base_url.rstrip("/"), model=model)
