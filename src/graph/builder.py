"""
Construção e compilação do grafo LangGraph.

SOLID - SRP: Este módulo apenas monta a topologia do grafo.
             Não contém lógica de agente.
SOLID - OCP: Para adicionar um novo nó, basta estender este arquivo —
             sem tocar nos agentes existentes.
"""

from langgraph.graph import END, START, StateGraph

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.config import config
from src.console import print_agent, print_separator, spinner
from src.graph.state import GraphState
from src.tools.file_writer import FileWriter


def _writer_node(state: dict) -> dict:
    """
    Persiste os generated_files no disco apos cada passagem do Coder.

    Isso e necessario para que o CoderAgent possa usar o run_powershell
    tool nas passagens de correcao — os arquivos precisam estar no disco
    para que pytest, python, etc. consigam executa-los.

    Posicao no grafo: entre coder e reviewer.
    O loop fica: coder → writer → reviewer → coder → writer → ...

    Returns:
        {} — nao atualiza o estado do grafo (apenas efeito colateral de I/O).
    """
    generated = state.get("generated_files", [])
    if not generated:
        return {}

    print_separator("WRITER")

    with spinner("writer", f"Salvando {len(generated)} arquivo(s) em ./{config.output_dir}/") as s:
        writer = FileWriter(config.output_dir)
        created = writer.write_all(generated)

    print_agent("writer", f"Salvo {len(created)} arquivo(s)  ({s.elapsed_str()})")

    return {}


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
