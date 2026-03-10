"""
Construção e compilação do grafo LangGraph.

SOLID - SRP: Este módulo apenas monta a topologia do grafo.
             Não contém lógica de agente nem de arquivo.
SOLID - OCP: Para adicionar um novo nó (ex: ReviewerAgent), basta estender
             este arquivo — sem tocar nos agentes existentes.
KISS        : Grafo linear simples. Sem condicionais ou loops por enquanto.
YAGNI       : Não adicionamos checkpoints ou memória persistente porque
              não foram solicitados.
"""

from langgraph.graph import END, START, StateGraph

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.config import config
from src.graph.state import GraphState


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

        START → planner → coder → reviewer → END

    Topologia (com correcoes):

        START → planner → coder → reviewer ─┐
                                    ▲        │ issues_found
                                    └────────┘ (ate max_review_iterations)

    Os agentes são instanciados aqui (não dentro dos nós) para que o
    objeto LLM seja criado uma vez e reutilizado em execuções repetidas.

    Returns:
        CompiledGraph: Grafo compilado, pronto para .invoke() ou .stream().
    """
    # Instancia agentes — cada um carrega seu modelo Ollama
    planner  = PlannerAgent()
    coder    = CoderAgent()
    reviewer = ReviewerAgent()

    # Cria o grafo tipado com GraphState
    graph = StateGraph(GraphState)

    # --- Nós ---
    graph.add_node("planner",  planner.run)
    graph.add_node("coder",    coder.run)
    graph.add_node("reviewer", reviewer.run)

    # --- Arestas fixas ---
    graph.add_edge(START,     "planner")   # Entrada → Planner
    graph.add_edge("planner", "coder")     # Planner → Coder
    graph.add_edge("coder",   "reviewer")  # Coder   → Reviewer

    # --- Aresta condicional: Reviewer → Coder (correcao) ou END ---
    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {"coder": "coder", END: END},
    )

    # Compila valida o grafo e gera o executor otimizado
    return graph.compile()
