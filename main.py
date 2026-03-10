"""
Ponto de entrada do sistema de agentes LangGraph + Ollama.

SOLID - SRP: Apenas orquestra a execucao — nao contem logica de agente,
             LLM ou sistema de arquivos.
KISS        : Fluxo linear: input -> grafo -> salvar -> exibir resultado.
YAGNI       : Sem CLI complexa, sem argumentos opcionais.
"""

import sys

from src.config import config
from src.console import (
    console,
    print_demand,
    print_error,
    print_header,
    print_review,
    print_separator,
    print_summary,
    spinner,
    print_agent,
)
from src.graph.builder import build_graph
from src.tools.file_writer import FileWriter


def main() -> None:
    """
    Fluxo principal:

        1. Exibe cabecalho com painel de configuracoes
        2. Le a demanda (argumento CLI ou input interativo)
        3. Executa o grafo: PLANNER -> CODER  (com spinners internos)
        4. Salva os arquivos gerados em ./output/  (com spinner)
        5. Exibe painel de resumo final
    """
    # 1. Cabecalho
    print_header(config.planner_model, config.coder_model, config.reviewer_model, config.output_dir)

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

    # 3. Executa o grafo
    # Os agentes imprimem seus proprios separadores e spinners internamente.
    graph = build_graph()

    result = graph.invoke({
        "demand": demand,
        "plan": None,
        "generated_files": [],
        "review": None,
        "review_iterations": 0,
        "messages": [],
    })

    generated = result.get("generated_files", [])
    if not generated:
        print_error("Nenhum arquivo foi gerado. Verifique os logs acima.")
        sys.exit(1)

    # 4. Salva os arquivos (com spinner para o writer)
    print_separator("WRITER")

    with spinner("writer", f"Salvando {len(generated)} arquivo(s) em ./{config.output_dir}/") as s:
        writer = FileWriter(config.output_dir)
        created_paths = writer.write_all(generated)

    print_agent("writer", f"Salvo {len(created_paths)} arquivo(s)  ({s.elapsed_str()})")

    # 5. Resultado da revisao
    review = result.get("review")
    if review:
        print_review(review)

    # 6. Resumo final
    print_summary(created_paths, result.get("plan", {}))


if __name__ == "__main__":
    main()
