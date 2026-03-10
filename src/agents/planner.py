"""
Agente Planejador.

SOLID - SRP: Analisa a demanda e cria um plano estruturado.
             Nao escreve codigo. Nao salva arquivos. So planeja.
"""

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
    """

    # Constante de classe (DRY): prompt definido uma vez, reutilizado em cada chamada.
    # /no_think instrui o Qwen3 a nao usar o modo de raciocinio interno,
    # pois queremos JSON direto e o <think> atrapalharia o parse.
    SYSTEM_PROMPT = """/no_think
You are a software architect. Analyze the development demand and produce a clear implementation plan.

STRICT RULES:
1. Respond ONLY with valid JSON - no explanations, no markdown, no extra text.
2. Organize filenames in a logical folder structure.
3. Be specific about what each file must contain.

REQUIRED JSON FORMAT:
{
  "objective": "One sentence describing what will be built",
  "files": [
    {
      "filename": "folder/file.ext",
      "description": "This file's single responsibility",
      "content_hint": "Specific classes, functions, or logic this file must contain"
    }
  ],
  "notes": "Architecture decisions, design patterns, and dependencies to use"
}"""

    def __init__(self):
        super().__init__(model=config.planner_model)

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
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"Development demand: {demand}"),
        ]

        # Spinner envolve a chamada bloqueante ao LLM.
        # s.elapsed_str() fica disponivel apos o bloco encerrar.
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
