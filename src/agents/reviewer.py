"""
Agente Revisor.

SOLID - SRP: Analisa os arquivos gerados pelo CoderAgent contra o plano
             do PlannerAgent e reporta problemas encontrados.
             Nao gera codigo. Nao salva arquivos. So revisa.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.base import BaseAgent
from src.config import config
from src.console import print_agent, print_separator, spinner
from src.utils import extract_json


class ReviewerAgent(BaseAgent):
    """
    Recebe o plano e os arquivos gerados e verifica a conformidade entre eles.

    Para cada arquivo gerado, o Reviewer verifica:
      - O arquivo foi realmente implementado?
      - O conteudo corresponde a descricao e ao content_hint do plano?
      - Ha inconsistencias de imports ou referencias entre arquivos?
      - O objetivo geral do projeto foi atendido?

    Retorna um relatorio estruturado em JSON com status por arquivo
    e um resumo geral.
    """

    SYSTEM_PROMPT = """/no_think
You are a senior code reviewer. Analyze the generated files against the project plan.

STRICT RULES:
1. Respond ONLY with valid JSON - no explanations, no markdown, no extra text.
2. Be specific and concise about each issue found.
3. Check: completeness (all plan items implemented), correctness (logic works),
   adherence to plan (description and content_hint respected), and inter-file
   consistency (imports, class names, and references match across files).

REQUIRED JSON FORMAT:
{
  "status": "ok",
  "summary": "One sentence overall assessment",
  "files": [
    {
      "filename": "folder/file.ext",
      "status": "ok",
      "issues": [],
      "suggestions": []
    }
  ]
}

Use "status": "issues_found" (top-level) if ANY file has problems.
Per-file status values: "ok", "incomplete", "wrong"."""

    def __init__(self):
        super().__init__(model=config.reviewer_model)

    def run(self, state: dict) -> dict:
        """
        Revisa todos os arquivos gerados contra o plano.

        Fluxo:
          1. Imprime separador de secao com numero da iteracao atual
          2. Monta prompt com o plano completo e o conteudo de cada arquivo gerado
          3. Chama o LLM com spinner + cronometro
          4. Extrai o JSON da resposta
          5. Exibe resumo do resultado (ok ou issues_found)
          6. Se issues_found e ainda ha iteracoes disponiveis, avisa que voltara ao Coder
          7. Retorna {"review", "review_iterations"} para atualizar o estado do grafo

        Args:
            state: Deve conter "plan" (dict), "generated_files" (list[dict])
                   e "review_iterations" (int).

        Returns:
            {"review": dict, "review_iterations": int, "messages": list}
        """
        plan             = state["plan"]
        generated_files  = state["generated_files"]
        iteration        = state.get("review_iterations", 0) + 1  # 1-based para exibicao
        max_iter         = config.max_review_iterations

        print_separator(f"REVIEWER  ({iteration}/{max_iter})")

        user_prompt = self._build_prompt(plan, generated_files)

        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        with spinner("reviewer", f"Revisando {len(generated_files)} arquivo(s) com {config.reviewer_model}") as s:
            response = self.llm.invoke(messages)

        review = extract_json(response.content)

        status   = review.get("status", "unknown")
        n_issues = sum(1 for f in review.get("files", []) if f.get("status") != "ok")

        if status == "ok":
            print_agent("reviewer", f"OK -- todos os arquivos aprovados  ({s.elapsed_str()})")
        else:
            print_agent("reviewer", f"{n_issues} arquivo(s) com problema(s)  ({s.elapsed_str()})")

        for frev in review.get("files", []):
            fname   = frev.get("filename", "?")
            fstatus = frev.get("status", "?")
            issues  = frev.get("issues", [])
            print_agent("reviewer", f"{fname}  --  {fstatus}", dim=(fstatus == "ok"))
            for issue in issues:
                print_agent("reviewer", f"  ! {issue}", dim=True)

        # Avisa o usuario sobre o que acontecera a seguir
        if status == "issues_found":
            if iteration < max_iter:
                print_agent("reviewer", f"Devolvendo ao Coder para correcao (tentativa {iteration}/{max_iter - 1})")
            else:
                print_agent("reviewer", f"Limite de {max_iter} revisoes atingido -- encerrando com problemas pendentes")

        return {
            "review":            review,
            "review_iterations": iteration,
            "messages":          [response],
        }

    # ── Metodos privados ──────────────────────────────────────────────────────

    def _build_prompt(self, plan: dict, generated_files: list[dict]) -> str:
        """
        Monta o prompt com o plano completo e o conteudo dos arquivos gerados.

        DRY: logica de montagem centralizada aqui para nao duplicar em run().

        Args:
            plan           : Plano completo do PlannerAgent.
            generated_files: Lista de dicts {"filename", "content"} do CoderAgent.

        Returns:
            String com o prompt completo para o LLM.
        """
        lines: list[str] = []

        # Contexto do plano
        lines.append("== PROJECT PLAN ==")
        lines.append(f"Objective: {plan['objective']}")
        lines.append(f"Architecture notes: {plan['notes']}")
        lines.append("")
        lines.append("Expected files:")
        for f in plan["files"]:
            lines.append(f"  - {f['filename']}")
            lines.append(f"    Description : {f['description']}")
            lines.append(f"    Must contain: {f['content_hint']}")

        # Conteudo dos arquivos gerados
        lines.append("")
        lines.append("== GENERATED FILES ==")
        gen_map = {f["filename"]: f["content"] for f in generated_files}
        for f in plan["files"]:
            fname = f["filename"]
            content = gen_map.get(fname)
            lines.append(f"\n--- {fname} ---")
            if content:
                lines.append(content)
            else:
                lines.append("[FILE NOT GENERATED]")

        # Instrucao final
        lines.append("")
        lines.append("Review each generated file against its plan specification.")
        lines.append("Output ONLY the JSON review report:")

        return "\n".join(lines)
