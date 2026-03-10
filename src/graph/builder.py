"""
Construção e compilação do grafo LangGraph.

SOLID - SRP: Este módulo apenas monta a topologia do grafo.
             Não contém lógica de agente.
SOLID - OCP: Para adicionar um novo nó, basta estender este arquivo —
             sem tocar nos agentes existentes.
"""

import re
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.config import config
from src.console import print_agent, print_separator, spinner
from src.graph.state import GraphState
from src.tools.file_writer import FileWriter


def _slugify(text: str, max_len: int = 50) -> str:
    """
    Converte texto livre em slug seguro para nome de diretório.

    Ex: "Calculadora Python com operacoes basicas" -> "calculadora_python_com_operacoes_basicas"
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("_")
    return text[:max_len].rstrip("_") or "projeto"


def _unique_dir(base: Path, name: str) -> Path:
    """
    Retorna um Path inexistente dentro de base.

    Tenta: base/name → base/name_2 → base/name_3 → ...
    Garante que nunca sobrescreve um projeto anterior.
    """
    candidate = base / name
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = base / f"{name}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def _writer_node(state: dict) -> dict:
    """
    Persiste os generated_files no disco apos cada passagem do Coder.

    Isso e necessario para que o CoderAgent possa usar o run_powershell
    tool nas passagens de correcao — os arquivos precisam estar no disco
    para que pytest, python, etc. consigam executa-los.

    Posicao no grafo: entre coder e reviewer.
    O loop fica: coder → writer → reviewer → coder → writer → ...

    Na primeira execucao, determina o diretorio do projeto a partir do
    objetivo do plano e garante unicidade (nunca sobrescreve projetos
    anteriores). Nas passagens seguintes (correcoes), reutiliza o mesmo
    diretorio armazenado em state["project_dir"].

    Returns:
        {"project_dir": str} na primeira execucao; {} nas seguintes.
    """
    generated = state.get("generated_files", [])
    if not generated:
        return {}

    # Determina o diretório do projeto: reutiliza se já existe, cria se for
    # a primeira passagem. Isso garante que correcoes sobrescrevem os mesmos
    # arquivos em vez de criar uma pasta nova a cada iteracao.
    project_dir_str = state.get("project_dir")
    if not project_dir_str:
        plan      = state.get("plan") or {}
        objective = plan.get("objective", "projeto")
        slug      = _slugify(objective)
        project_dir = _unique_dir(Path(config.output_dir), slug)
        project_dir_str = str(project_dir)
    else:
        project_dir = Path(project_dir_str)

    print_separator("WRITER")

    with spinner("writer", f"Salvando {len(generated)} arquivo(s) em ./{project_dir}/") as s:
        writer  = FileWriter(project_dir_str)
        created = writer.write_all(generated)

    print_agent("writer", f"Salvo {len(created)} arquivo(s)  ({s.elapsed_str()})")

    return {"project_dir": project_dir_str}


def _route_after_review(state: dict) -> str:
    """
    Decide o proximo no apos o Reviewer executar.

    Regras:
      - Se o review aprovou tudo (status == "ok")  → END
      - Se ha problemas E ainda ha iteracoes disponíveis → "coder" (re-gera)
      - Se ha problemas mas o limite foi atingido         → END (encerra mesmo assim)

    O limite e config.max_review_iterations. O contador review_iterations
    e incrementado pelo proprio ReviewerAgent a cada execucao.
    """
    review     = state.get("review", {})
    iterations = state.get("review_iterations", 0)

    if review.get("status") == "issues_found" and iterations < config.max_review_iterations:
        return "coder"
    return END


def build_graph():
    """
    Monta e compila o grafo de agentes.

    Topologia (fluxo feliz):

        START → planner → coder → writer → reviewer → END

    Topologia (com correcoes):

        START → planner → coder → writer → reviewer ─┐
                               ▲                      │ issues_found
                               └──────────────────────┘ (ate max_review_iterations)

    O no `writer` salva os arquivos no disco apos cada passagem do Coder.
    Isso permite que o Coder use run_powershell para testar o codigo nas
    passagens de correcao (os arquivos do passe anterior estao no disco).

    Os agentes sao instanciados aqui (nao dentro dos nos) para que o
    objeto LLM seja criado uma vez e reutilizado em execucoes repetidas.

    Returns:
        CompiledGraph: Grafo compilado, pronto para .invoke() ou .stream().
    """
    planner  = PlannerAgent()
    coder    = CoderAgent()
    reviewer = ReviewerAgent()

    graph = StateGraph(GraphState)

    # --- Nos ---
    graph.add_node("planner",  planner.run)
    graph.add_node("coder",    coder.run)
    graph.add_node("writer",   _writer_node)   # salva arquivos entre coder e reviewer
    graph.add_node("reviewer", reviewer.run)

    # --- Arestas fixas ---
    graph.add_edge(START,      "planner")   # Entrada  → Planner
    graph.add_edge("planner",  "coder")     # Planner  → Coder
    graph.add_edge("coder",    "writer")    # Coder    → Writer  (salva no disco)
    graph.add_edge("writer",   "reviewer")  # Writer   → Reviewer

    # --- Aresta condicional: Reviewer → Coder (correcao) ou END ---
    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {"coder": "coder", END: END},
    )

    return graph.compile()
