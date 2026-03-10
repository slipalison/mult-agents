"""
Classe base abstrata para todos os agentes.

SOLID - OCP (Open/Closed)      : Novos agentes estendem esta classe sem precisar
                                  modificá-la.
SOLID - LSP (Liskov)           : Qualquer subclasse pode ser usada onde BaseAgent
                                  for esperado.
SOLID - ISP (Interface Segr.)  : Interface mínima — apenas o método `run`.
SOLID - DIP (Dep. Inversion)   : Agentes dependem da abstração `ChatOllama`,
                                  não de uma implementação específica de LLM.
"""

from abc import ABC, abstractmethod

from langchain_ollama import ChatOllama

from src.config import config


class BaseAgent(ABC):
    """
    Contrato base que todos os agentes devem respeitar.

    Cada subclasse implementa UMA responsabilidade (SOLID - SRP):
      - PlannerAgent → apenas planeja
      - CoderAgent   → apenas codifica

    O LLM é injetado no construtor via ChatOllama, tornando fácil
    trocar de modelo sem alterar a lógica dos agentes.
    """

    def __init__(self, model: str, temperature: float | None = None):
        """
        Args:
            model      : Nome do modelo Ollama (ex: "qwen3.5:27b").
            temperature: Controla aleatoriedade (0 = determinístico, 1 = criativo).
                         None usa o valor padrão definido em config.
        """
        self.llm = ChatOllama(
            model=model,
            base_url=config.ollama_base_url,
            temperature=temperature if temperature is not None else config.temperature,
        )

    @abstractmethod
    def run(self, state: dict) -> dict:
        """
        Executa o agente com o estado atual do grafo LangGraph.

        LangGraph chama este método automaticamente quando o nó
        correspondente é ativado.

        Args:
            state: Estado atual do grafo (dict com os campos de GraphState).

        Returns:
            Dict com apenas as chaves do estado que este agente atualiza.
            LangGraph faz o merge com o estado existente automaticamente.
        """
        ...
