"""
Estado compartilhado do grafo LangGraph.

O estado é o "banco de dados em memória" que todos os nós lêem e escrevem.
Cada nó recebe o estado completo e retorna apenas as chaves que ele atualizou.
LangGraph faz o merge automaticamente.

SOLID - SRP: Este módulo existe apenas para definir a estrutura de dados do grafo.
KISS        : TypedDict simples, sem lógica, sem métodos.
"""

from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class GraphState(TypedDict):
    """
    Estado completo do grafo Planner → Coder.

    Campos:
        demand:
            A demanda original do usuário. Definida no início e nunca alterada.
            Ex: "Crie uma calculadora em Python com operações básicas."

        plan:
            Saída do PlannerAgent. Dict com a estrutura:
            {
                "objective": str,
                "files": [{"filename": str, "description": str, "content_hint": str}],
                "notes": str
            }
            None até o Planner executar.

        generated_files:
            Saída do CoderAgent. Lista de arquivos gerados:
            [{"filename": str, "content": str}, ...]
            Lista vazia até o Coder executar.

        messages:
            Histórico completo de mensagens trocadas com os LLMs.
            A anotação `add_messages` instrui o LangGraph a ACUMULAR
            (append) as mensagens em vez de substituir a lista inteira.
            Isso mantém o histórico de toda a conversa.
    """

    demand: str
    plan: Optional[dict]
    generated_files: list[dict]
    messages: Annotated[list[BaseMessage], add_messages]
