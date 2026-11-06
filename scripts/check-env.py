"""Read-only backend preflight; prints versions and provider name, never credentials."""
import importlib.metadata
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
    try:
        for name, value in os.environ.items():
            if name.startswith(('LLM_ROUTER_', 'DASHSCOPE_', 'DEEPSEEK_', 'ARK_', 'NOVEL_', 'CHARACTER_DRAFT_')) and name.endswith('_TIMEOUT_MS') and value:
                if not value.isdigit() or int(value) < 1000:
                    raise ValueError(f'{name} must be an integer of at least 1000 milliseconds')
        for name in ('fastapi', 'uvicorn', 'pydantic', 'httpx'):
            print(f'{name}: {importlib.metadata.version(name)}')
        from campus_lite.api import create_app  # import only; do not initialize storage
        from campus_lite.llm import LlmClient
        from campus_lite.storage_parts.common import DB_PATH
        if DB_PATH.exists() and not DB_PATH.is_file():
            raise ValueError('CAMPUS_DB_PATH must refer to a database file, not a directory')
        if os.getenv('LLM_ROUTER_API_KEY') and not os.getenv('LLM_ROUTER_BASE_URL'):
            raise ValueError('LLM_ROUTER_BASE_URL is required when LLM_ROUTER_API_KEY is set')
        client = LlmClient()
        print(f'Python: {sys.version.split()[0]} ({sys.executable})')
        print(f'Model provider: {client.provider_name() or "none (local fallback)"}; connectivity not tested')
        return 0
    except (ImportError, ValueError, importlib.metadata.PackageNotFoundError) as exc:
        print(f'Environment check failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
