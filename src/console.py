"""
Console estilizado para o sistema de agentes.

Inspirado no estilo visual do Claude Code: prefixos coloridos por agente,
spinner animado com cronometro HH:MM:SS, paineis de cabecalho e resumo.

SOLID - SRP: Exclusivamente responsavel pela apresentacao no terminal.
KISS        : API minima — spinner(), print_agent(), print_header(), print_summary().
DRY         : Toda logica de formatacao centralizada aqui; agentes so chamam funcoes.
"""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Singleton ────────────────────────────────────────────────────────────────
# Todos os modulos importam este objeto.
# SOLID - DIP: dependencia na abstracao Console, nao em print() direto.
console = Console(highlight=False)

# ── Paleta de cores por papel ─────────────────────────────────────────────────
# Cada agente tem uma cor unica para facilitar a leitura no terminal.
AGENT_COLOR: dict[str, str] = {
    "planner":  "cyan",
    "coder":    "green",
    "reviewer": "magenta",
    "writer":   "yellow",
    "system":   "white",
}

# ── Frames do spinner ─────────────────────────────────────────────────────────
# ASCII classico: compativel com qualquer terminal.
_FRAMES = ("|", "/", "-", "\\")


# ── Resultado do spinner ──────────────────────────────────────────────────────

@dataclass
class SpinnerResult:
    """
    Carrega o tempo decorrido do bloco monitorado pelo spinner.

    Disponivel apos o `with spinner(...)` encerrar:

        with spinner("planner", "Chamando modelo") as s:
            response = llm.invoke(...)
        print(s.elapsed_str())  # "00:00:07"
    """
    elapsed: float = 0.0

    def elapsed_str(self) -> str:
        """Retorna o tempo no formato HH:MM:SS."""
        h, rem = divmod(int(self.elapsed), 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


# ── Context manager principal ─────────────────────────────────────────────────

@contextmanager
def spinner(agent: str, message: str) -> Generator[SpinnerResult, None, None]:
    """
    Exibe um spinner animado com cronometro enquanto o bloco executa.

    - O spinner eh transient: desaparece ao sair, sem sujar o historico.
    - Um thread separado atualiza o timer sem bloquear o LLM.
    - Ao sair, SpinnerResult.elapsed contem o tempo total do bloco.

    Exemplo:
        with spinner("coder", "Gerando src/main.py") as s:
            content = llm.invoke(messages)
        print_agent("coder", f"OK  ({s.elapsed_str()})")

    Visual enquanto roda:
        / CODER       Gerando src/main.py  00:00:04
    """
    color  = AGENT_COLOR.get(agent.lower(), "white")
    result = SpinnerResult()
    start  = time.monotonic()
    stop   = threading.Event()
    idx    = [0]

    def _render() -> Text:
        elapsed  = time.monotonic() - start
        h, rem   = divmod(int(elapsed), 3600)
        m, s     = divmod(rem, 60)
        timer    = f"{h:02d}:{m:02d}:{s:02d}"
        frame    = _FRAMES[idx[0] % len(_FRAMES)]
        idx[0]  += 1

        t = Text()
        t.append(f"  {frame} ", style=color)
        t.append(f"{agent.upper():<10}", style=f"{color} bold")
        t.append(f"  {message}")
        t.append(f"  {timer}", style=f"{color} dim")
        return t

    with Live(_render(), console=console, refresh_per_second=10, transient=True) as live:

        def _loop() -> None:
            """Thread que atualiza o render a cada 100ms."""
            while not stop.is_set():
                live.update(_render())
                time.sleep(0.1)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()

        try:
            yield result
        finally:
            stop.set()
            thread.join(timeout=1.0)
            result.elapsed = time.monotonic() - start


# ── Funcoes de impressao ──────────────────────────────────────────────────────

def print_agent(agent: str, message: str, *, dim: bool = False) -> None:
    """
    Imprime uma linha com o prefixo colorido do agente.

    Visual:
        > PLANNER     Plano criado: 3 arquivo(s)  (00:00:05)
        > PLANNER       src/calculator.py          <- dim=True
    """
    color = AGENT_COLOR.get(agent.lower(), "white")
    muted = f"{color} dim"

    t = Text()
    t.append("  > ", style=muted if dim else color)
    t.append(f"{agent.upper():<10}", style=muted if dim else f"{color} bold")
    t.append(f"  {message}", style="dim" if dim else "default")
    console.print(t)


def print_separator(title: str = "") -> None:
    """
    Linha separadora horizontal com titulo opcional.

    Visual:
        ─────────────────── PLANNER ───────────────────
    """
    console.print()
    if title:
        console.rule(f"[white dim] {title} [/white dim]", style="white dim")
    else:
        console.rule(style="white dim")
    console.print()


def print_header(
    planner_model: str,
    coder_model: str,
    reviewer_model: str,
    output_dir: str,
    langsmith_project: str | None = None,
) -> None:
    """
    Painel de cabecalho com os modelos e o diretorio de saida.

    Visual (sem LangSmith):
        ╭── Sistema de Agentes LangGraph + Ollama ──╮
        │                                           │
        │  Planner   qwen3.5:9b                     │
        │  Coder     qwen2.5-coder:7b               │
        │  Reviewer  qwen3.5:9b                     │
        │  Saida     ./output/                      │
        │                                           │
        ╰───────────────────────────────────────────╯

    Visual (com LangSmith):
        │  LangSmith like_claude (ativo)            │
    """
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", min_width=10)
    grid.add_column()
    grid.add_row("Planner",  f"[cyan]{planner_model}[/cyan]")
    grid.add_row("Coder",    f"[green]{coder_model}[/green]")
    grid.add_row("Reviewer", f"[magenta]{reviewer_model}[/magenta]")
    grid.add_row("Saida",    f"[yellow]./{output_dir}/[/yellow]")
    if langsmith_project:
        grid.add_row("LangSmith", f"[blue]{langsmith_project}[/blue] [blue dim](ativo)[/blue dim]")

    console.print(
        Panel(
            grid,
            title="[bold white]Sistema de Agentes LangGraph + Ollama[/bold white]",
            border_style="white dim",
            padding=(1, 2),
        )
    )


def print_demand(demand: str) -> None:
    """Exibe a demanda recebida antes de iniciar o grafo."""
    t = Text()
    t.append("  > ", style="white")
    t.append("SYSTEM    ", style="white bold")
    t.append(f'  Demanda: "{demand}"', style="white")
    console.print(t)
    console.print()


def print_summary(created_paths: list, plan: dict) -> None:
    """
    Painel final com objetivo e lista dos arquivos gerados.

    Visual:
        ╭── CONCLUIDO — 3 arquivo(s) gerado(s) ──╮
        │                                         │
        │  Calculadora Python com 4 operacoes     │
        │                                         │
        │  > output/src/calculator.py             │
        │  > output/src/main.py                   │
        │  > output/tests/test_calculator.py      │
        │                                         │
        ╰─────────────────────────────────────────╯
    """
    body = Text()

    if plan.get("objective"):
        body.append(plan["objective"] + "\n\n", style="italic dim")

    for i, path in enumerate(created_paths):
        body.append("  > ", style="green bold")
        # Sem \n na ultima linha para nao gerar espaco extra antes do border
        suffix = "\n" if i < len(created_paths) - 1 else ""
        body.append(str(path) + suffix, style="green")

    console.print()
    console.print(
        Panel(
            body,
            title=f"[green bold]  CONCLUIDO -- {len(created_paths)} arquivo(s) gerado(s)  [/green bold]",
            border_style="green",
            padding=(1, 2),
        )
    )


def print_review(review: dict) -> None:
    """
    Painel com o resultado da revisao do ReviewerAgent.

    Visual (ok):
        ╭── REVISAO -- ok ──╮
        │  Todos os arquivos implementados corretamente.  │
        │  > src/main.py       ok                        │
        ╰────────────────────────────────────────────────╯

    Visual (issues_found):
        ╭── REVISAO -- issues_found ──╮
        │  Foram encontrados problemas em 1 arquivo.      │
        │  > src/main.py       incomplete                 │
        │      ! import nao declarado no plano            │
        ╰────────────────────────────────────────────────╯
    """
    status = review.get("status", "unknown")
    color  = "green" if status == "ok" else "yellow"

    body = Text()
    summary = review.get("summary", "")
    if summary:
        body.append(summary + "\n\n", style="italic dim")

    for frev in review.get("files", []):
        fname   = frev.get("filename", "?")
        fstatus = frev.get("status", "?")
        fcolor  = "green" if fstatus == "ok" else "yellow"

        body.append("  > ", style=f"{fcolor} bold")
        body.append(f"{fname:<40}", style=fcolor)
        body.append(f"  {fstatus}\n", style=f"{fcolor} bold")

        for issue in frev.get("issues", []):
            body.append(f"      ! {issue}\n", style="yellow dim")
        for sug in frev.get("suggestions", []):
            body.append(f"      * {sug}\n", style="dim")

    # Remove \n final para nao gerar espaco extra antes do border.
    # body.rstrip() (sem args) usa a API oficial do Rich e atualiza
    # _spans + _length corretamente — manipular _text diretamente corrompe
    # os offsets internos e causa IndexError no render.
    body.rstrip()

    console.print()
    console.print(
        Panel(
            body,
            title=f"[{color} bold]  REVISAO -- {status}  [/{color} bold]",
            border_style=color,
            padding=(1, 2),
        )
    )


def print_error(message: str) -> None:
    """Exibe uma mensagem de erro em destaque vermelho."""
    console.print(f"\n[red bold]  ! ERRO[/red bold]  [red]{message}[/red]\n")
