# Global Preferences

Python (PyTorch/ML), Bash, Lua, C++. Neovim. macOS local, Linux remote. zsh. uv. Python 3.12.

## Python Style
ruff, Google docstrings type hints (ty/mypy-compatible).

## Code Rules
- No decorative comment headers (`# ===`, `# ---`). If a file needs sections, split it into modules.
- Names over comments. Comment only the *why*, never the *what*.
- `pathlib.Path`, `logging` (not print), try/except at I/O boundaries, descriptive assertions.
- Conventional commits: `feat(model): add multi-head attention with rotary embeddings`

## Response Style
- Never guess package names, URLs, or CLI commands. Verify first or say you don't know.
- Challenge my assumptions. Push back when something doesn't hold up.
- Lead with the answer. Skip boilerplate for basic Python/PyTorch.
- `file_path:line_number` for code refs. ASCII diagrams for architecture.
- Refactors: readability over performance, minimal changes, note breaking changes, suggest tests.

Production-quality code by default. Project-level CLAUDE.md overrides these globals.
