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
from src.graph.state import GraphState


def build_graph():
    """
    Monta e compila o grafo de agentes.

    Topologia:

        START
          │
          ▼
       planner          ← PlannerAgent.run(state) → atualiza plan + messages
          │
          ▼
        coder            ← CoderAgent.run(state)   → atualiza generated_files
          │
          ▼
         END

    Os agentes são instanciados aqui (não dentro dos nós) para que o
    objeto LLM seja criado uma vez e reutilizado em execuções repetidas.

    Returns:
        CompiledGraph: Grafo compilado, pronto para .invoke() ou .stream().
    """
    # Instancia agentes — cada um carrega seu modelo Ollama
    planner = PlannerAgent()
    coder = CoderAgent()

    # Cria o grafo tipado com GraphState
    graph = StateGraph(GraphState)

    # --- Nós ---
    # O método .run de cada agente tem a assinatura correta para nó LangGraph:
    # (state: dict) -> dict
    graph.add_node("planner", planner.run)
    graph.add_node("coder", coder.run)

    # --- Arestas (fluxo de execução) ---
    graph.add_edge(START, "planner")    # Entrada → Planner
    graph.add_edge("planner", "coder")  # Planner → Coder
    graph.add_edge("coder", END)        # Coder → Saída

    # Compila valida o grafo e gera o executor otimizado
    return graph.compile()
