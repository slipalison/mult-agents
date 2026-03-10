"""
Agente Revisor.

SOLID - SRP: Analisa os arquivos gerados pelo CoderAgent contra o plano
             do PlannerAgent e reporta problemas encontrados.
             Nao gera codigo. Nao salva arquivos. So revisa.

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

    O system prompt e carregado de SOUL.md em tempo de execucao.
    Para alterar o comportamento do agente, edite apenas esse arquivo.
    """

    def __init__(self):
        super().__init__(model=config.reviewer_model)
        # Carrega o prompt do SOUL.md co-localizado com este pacote.
        self._system_prompt = (Path(__file__).parent / "SOUL.md").read_text(encoding="utf-8")

    def run(self, state: dict) -> dict:
        """
        Revisa todos os arquivos gerados contra o plano.

        Args:
            state: Deve conter "plan" (dict), "generated_files" (list[dict])
                   e "review_iterations" (int).

        Returns:
            {"review": dict, "review_iterations": int, "messages": list}
        """
        plan             = state["plan"]
        generated_files  = state["generated_files"]
        iteration        = state.get("review_iterations", 0) + 1
        max_iter         = config.max_review_iterations

        print_separator(f"REVIEWER  ({iteration}/{max_iter})")

        user_prompt = self._build_prompt(plan, generated_files)

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_prompt),
        ]

        with spinner("reviewer", f"Revisando {len(generated_files)} arquivo(s) com {config.reviewer_model}") as s:
            response = self.llm.invoke(messages)

        review   = extract_json(response.content)
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
        """
        lines: list[str] = []

        lines.append("== PROJECT PLAN ==")
        lines.append(f"Objective: {plan['objective']}")
        lines.append(f"Architecture notes: {plan['notes']}")
        lines.append("")
        lines.append("Expected files:")
        for f in plan["files"]:
            lines.append(f"  - {f['filename']}")
            lines.append(f"    Description : {f['description']}")
            lines.append(f"    Must contain: {f['content_hint']}")

        lines.append("")
        lines.append("== GENERATED FILES ==")
        gen_map = {f["filename"]: f["content"] for f in generated_files}
        for f in plan["files"]:
            fname   = f["filename"]
            content = gen_map.get(fname)
            lines.append(f"\n--- {fname} ---")
            if content:
                lines.append(content)
            else:
                lines.append("[FILE NOT GENERATED]")

        lines.append("")
        lines.append("Review each generated file against its plan specification.")
        lines.append("Output ONLY the JSON review report:")

        return "\n".join(lines)
