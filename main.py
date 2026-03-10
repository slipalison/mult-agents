"""
Ponto de entrada do sistema de agentes LangGraph + Ollama.

SOLID - SRP: Apenas orquestra a execucao — nao contem logica de agente,
             LLM ou sistema de arquivos.
KISS        : Fluxo linear: input -> grafo -> exibir resultado.
YAGNI       : Sem CLI complexa, sem argumentos opcionais.
"""

import os
import sys
from pathlib import Path

# Carrega .env antes de importar config (que le os.environ no __init__)
# python-dotenv e opcional — sem ele, use variaveis de ambiente diretamente.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.config import config

# LangSmith: ativa o tracing antes de qualquer importacao LangChain/LangGraph.
# Quando LANGSMITH_API_KEY esta definido, todos os nos do grafo sao rastreados
# automaticamente — sem nenhuma alteracao nos agentes.
if config.langsmith_enabled:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"]    = config.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"]    = config.langsmith_project

from src.console import (
    console,
    print_demand,
    print_error,
    print_header,
    print_review,
    print_summary,
)
from src.graph.builder import build_graph


def main() -> None:
    """
    Fluxo principal:

        1. Exibe cabecalho com painel de configuracoes
        2. Le a demanda (argumento CLI ou input interativo)
        3. Executa o grafo: planner → coder → writer → reviewer (loop)
           Os arquivos sao salvos no disco pelo no `writer` dentro do grafo.
        4. Exibe resultado da revisao
        5. Exibe painel de resumo final
    """
    # 1. Cabecalho
    print_header(
        config.planner_model,
        config.coder_model,
        config.reviewer_model,
        config.output_dir,
        langsmith_project=config.langsmith_project if config.langsmith_enabled else None,
    )

    # 2. Le a demanda
    if len(sys.argv) > 1:
        demand = " ".join(sys.argv[1:])
    else:
        console.print("[white bold]O que voce quer construir?[/white bold]")
        demand = input("> ").strip()

    if not demand:
        print_error("Demanda vazia. Encerrando.")
        sys.exit(1)

    print_demand(demand)

    # 3. Executa o grafo.
    # O no `writer` dentro do grafo ja salva os arquivos no disco apos cada
    # passagem do Coder — nao e necessario salvar novamente aqui.
    graph = build_graph()

    result = graph.invoke({
        "demand": demand,
        "plan": None,
        "generated_files": [],
        "review": None,
        "review_iterations": 0,
        "project_dir": None,
        "messages": [],
    })

    generated = result.get("generated_files", [])
    if not generated:
        print_error("Nenhum arquivo foi gerado. Verifique os logs acima.")
        sys.exit(1)

    # Reconstroi os paths usando o diretorio do projeto definido pelo writer node.
    project_dir   = result.get("project_dir") or config.output_dir
    created_paths = [Path(project_dir) / f["filename"] for f in generated]

    # 4. Resultado da revisao
    review = result.get("review")
    if review:
        print_review(review)

    # 5. Resumo final
    print_summary(created_paths, result.get("plan", {}))


if __name__ == "__main__":
    main()
