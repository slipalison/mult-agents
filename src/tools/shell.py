"""
Ferramenta de execucao de comandos PowerShell para o CoderAgent.

Permite que o Coder execute a aplicacao gerada e rode testes unitarios
para verificar se o codigo funciona antes de finalizar.

SOLID - SRP: Apenas executa comandos no diretorio de saida. Nao sabe
             nada de LLMs, grafos ou agentes.
Seguranca  : Executa APENAS no diretorio output/ — sem acesso ao projeto
             fonte. Timeout de 30s evita travamentos.
"""

import subprocess
from pathlib import Path

from langchain_core.tools import tool

from src.config import config

# Diretorio onde os arquivos gerados sao salvos.
# Resolvido no momento do import — mesmo padrao do file_reader.py.
_OUTPUT_DIR = (Path.cwd() / config.output_dir).resolve()

# Limite de tempo por comando para evitar travamentos
_TIMEOUT_SECONDS = 30

# Limite de caracteres do output para nao explodir o contexto do LLM
_MAX_OUTPUT_CHARS = 4000


@tool
def run_powershell(command: str) -> str:
    """
    Run a PowerShell command inside the output/ directory where generated files live.

    Use this tool to build, run, and test the generated project in any language.
    Adapt the command to whatever language and toolchain the project uses.

    Examples by language (adapt as needed):
      Python  : "python main.py" | "pytest tests/ -q" | "pip install -r requirements.txt"
      Node.js : "node index.js"  | "npm test"          | "npm install"
      Go      : "go run ."       | "go test ./..."      | "go build ."
      C#/.NET : "dotnet run"     | "dotnet test"        | "dotnet build"
      Java    : "mvn test"       | "gradle test"        | "java -jar app.jar"
      Rust    : "cargo run"      | "cargo test"         | "cargo build"
      Ruby    : "ruby main.rb"   | "rspec"              | "bundle install"
      General : "Get-ChildItem -Recurse" to inspect the directory structure.

    The command runs with a 30-second timeout.
    Both stdout and stderr are returned. A non-zero exit code is reported.

    Args:
        command: PowerShell command to execute (runs inside the output/ directory).

    Returns:
        Combined stdout/stderr output and exit code (if non-zero).
    """
    if not _OUTPUT_DIR.exists():
        return (
            f"Output directory not found: {_OUTPUT_DIR}\n"
            "Files have not been written to disk yet. "
            "They will be available on the next correction pass."
        )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=_OUTPUT_DIR,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {_TIMEOUT_SECONDS}s: {command}"
    except FileNotFoundError:
        return "PowerShell executable not found. Ensure 'powershell' is in PATH."
    except OSError as e:
        return f"Failed to start process: {e}"

    parts: list[str] = []
    if result.stdout.strip():
        parts.append(result.stdout)
    if result.stderr.strip():
        parts.append(f"STDERR:\n{result.stderr}")
    if result.returncode != 0:
        parts.append(f"Exit code: {result.returncode}")

    output = "\n".join(parts).strip() or "(no output)"

    if len(output) > _MAX_OUTPUT_CHARS:
        output = output[:_MAX_OUTPUT_CHARS] + "\n... (output truncated)"

    return output


# Lista exportada — adicionada ao FILE_READER_TOOLS + SHELL_TOOLS no CoderAgent
SHELL_TOOLS = [run_powershell]
