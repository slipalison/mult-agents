"""
Agente Planejador.

SOLID - SRP: Analisa a demanda e cria um plano estruturado.
             Nao escreve codigo. Nao salva arquivos. So planeja.

O comportamento e a personalidade do agente estao definidos em SOUL.md,
no mesmo diretorio deste arquivo. Edite o SOUL.md para mudar o prompt
sem tocar em codigo Python.
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.base import BaseAgent
from src.config import config
from src.console import print_agent, print_separator, spinner
from src.utils import extract_json


class PlannerAgent(BaseAgent):
    """
    Recebe uma demanda em linguagem natural e produz um plano de implementacao.

    O plano especifica:
      - Objetivo geral do projeto
      - Lista de arquivos a criar, com descricao e dicas de conteudo
      - Notas de arquitetura para orientar o CoderAgent

    Este plano e armazenado no estado do grafo e consumido pelo CoderAgent.

    O system prompt e carregado de SOUL.md em tempo de execucao.
    Para alterar o comportamento do agente, edite apenas esse arquivo.
    """

    def __init__(self):
        super().__init__(model=config.planner_model)
        # Carrega o prompt do SOUL.md co-localizado com este pacote.
        # Path(__file__).parent aponta para src/agents/planner/.
        self._system_prompt = (Path(__file__).parent / "SOUL.md").read_text(encoding="utf-8")

    def run(self, state: dict) -> dict:
        """
        Analisa a demanda do usuario e retorna um plano estruturado.

        Fluxo:
          1. Imprime separador de secao
          2. Chama o LLM com spinner + cronometro
          3. Extrai o JSON da resposta
          4. Exibe o plano criado
          5. Retorna {"plan": dict} para atualizar o estado do grafo

        Args:
            state: Deve conter a chave "demand" com a demanda do usuario.

        Returns:
            {"plan": dict, "messages": list}
        """
        demand = state["demand"]

        print_separator("PLANNER")

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=f"Development demand: {demand}"),
        ]

        with spinner("planner", f"Chamando {config.planner_model}") as s:
            response = self.llm.invoke(messages)

        plan = extract_json(response.content)

        print_agent("planner", f"Plano criado: {len(plan['files'])} arquivo(s)  ({s.elapsed_str()})")
        for f in plan["files"]:
            print_agent("planner", f"{f['filename']}  -  {f['description']}", dim=True)

        return {
            "plan": plan,
            "messages": [response],
        }
