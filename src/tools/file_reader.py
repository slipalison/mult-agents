"""
Ferramentas de leitura do sistema de arquivos para o CoderAgent.

O CoderAgent pode chamar estas ferramentas antes de gerar codigo,
permitindo que ele leia arquivos existentes no projeto para entender
o contexto (imports, classes disponiveis, convencoes de codigo, etc.).

SOLID - SRP: Apenas le arquivos. Nao sabe nada de LLMs ou grafos.
KISS        : Dois tools com uma responsabilidade cada.
Seguranca   : Leitura restrita ao diretorio raiz do projeto (sem path traversal).
"""

from pathlib import Path

from langchain_core.tools import tool

# Raiz do projeto — resolvida no momento do import.
# Todos os caminhos sao validados contra este diretorio.
_PROJECT_ROOT = Path.cwd().resolve()

# Diretorios ignorados ao listar arquivos (ruido para o LLM)
_IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


@tool
def list_directory(subdirectory: str = ".") -> str:
    """
    List all files inside a directory of the project.

    Returns a plain-text list with one relative path per line.
    Use "." to list the entire project root.

    Args:
        subdirectory: Path relative to the project root (default: ".").
    """
    target = (_PROJECT_ROOT / subdirectory).resolve()

    # Seguranca: bloqueia acesso fora da raiz do projeto
    if not str(target).startswith(str(_PROJECT_ROOT)):
        return "Error: access outside the project root is not allowed."

    if not target.exists():
        return f"Directory not found: {subdirectory}"

    if not target.is_dir():
        return f"Not a directory: {subdirectory}"

    files = [
        str(p.relative_to(_PROJECT_ROOT))
        for p in sorted(target.rglob("*"))
        if p.is_file() and not any(part in _IGNORE_DIRS for part in p.parts)
    ]

    if not files:
        return f"No files found in: {subdirectory}"

    return "\n".join(files)


@tool
def read_file(filepath: str) -> str:
    """
    Read and return the full content of a file in the project.

    Args:
        filepath: Path relative to the project root (e.g., "src/config.py").
    """
    target = (_PROJECT_ROOT / filepath).resolve()

    # Seguranca: bloqueia path traversal
    if not str(target).startswith(str(_PROJECT_ROOT)):
        return "Error: access outside the project root is not allowed."

    if not target.exists():
        return f"File not found: {filepath}"

    if not target.is_file():
        return f"Not a file: {filepath}"

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: binary file cannot be read as text: {filepath}"
    except OSError as e:
        return f"Error reading file: {e}"


# Lista exportada — usada pelo CoderAgent para bind_tools e para o tool_map
FILE_READER_TOOLS = [list_directory, read_file]
