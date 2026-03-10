"""
Agente Programador.

SOLID - SRP: Implementa codigo baseado no plano recebido.
             Nao planeja. Nao salva arquivos no disco. So gera codigo.

O comportamento e a personalidade do agente estao definidos em SOUL.md,
no mesmo diretorio deste arquivo. Edite o SOUL.md para mudar o prompt
sem tocar em codigo Python.
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.agents.base import BaseAgent
from src.config import config
from src.console import print_agent, print_separator, spinner
from src.tools.file_reader import FILE_READER_TOOLS
from src.utils import extract_code

# Numero maximo de iteracoes do tool loop.
# Evita loops infinitos caso o LLM fique chamando ferramentas repetidamente.
_MAX_TOOL_ITERATIONS = 5


class CoderAgent(BaseAgent):
    """
    Recebe o plano do PlannerAgent e implementa cada arquivo especificado.

    Opera em dois modos dependendo do estado recebido:

    Modo normal (primeira execucao):
      - Gera todos os arquivos do plano do zero.

    Modo correcao (chamado pelo loop coder <-> reviewer):
      - Re-gera APENAS os arquivos com status != "ok", incluindo o
        feedback especifico do Reviewer no prompt de cada arquivo.
      - Mantem os arquivos aprovados intactos.
      - Retorna a lista completa mesclada (aprovados + corrigidos).

    O system prompt e carregado de SOUL.md em tempo de execucao.
    Para alterar o comportamento do agente, edite apenas esse arquivo.
    """

    def __init__(self):
        super().__init__(model=config.coder_model, temperature=0.2)
        # Carrega o prompt do SOUL.md co-localizado com este pacote.
        self._system_prompt = (Path(__file__).parent / "SOUL.md").read_text(encoding="utf-8")

        # LLM com ferramentas vinculadas — o modelo recebe o schema JSON
        # de cada tool e pode emitir tool_calls na sua resposta.
        # SOLID - OCP: adicionar novas ferramentas nao muda esta classe,
        #              basta atualizar FILE_READER_TOOLS em file_reader.py.
        self.llm_with_tools = self.llm.bind_tools(FILE_READER_TOOLS)

        # Mapa nome -> funcao para executar tool calls do LLM
        self._tool_map = {t.name: t for t in FILE_READER_TOOLS}

    def run(self, state: dict) -> dict:
        """
        Implementa (ou corrige) arquivos do plano, um por vez.

        Args:
            state: Deve conter "plan" (dict). Opcionalmente "review" (dict)
                   e "generated_files" (list[dict]) para o modo correcao.

        Returns:
            {"generated_files": list[dict]}  -- lista completa e atualizada
        """
        plan          = state["plan"]
        review        = state.get("review")
        prev_files    = state.get("generated_files", [])
        is_correction = bool(review and review.get("status") == "issues_found")

        if is_correction:
            feedback_map: dict[str, list[str]] = {}
            for frev in review.get("files", []):
                if frev.get("status") != "ok":
                    feedback_map[frev["filename"]] = (
                        frev.get("issues", []) + frev.get("suggestions", [])
                    )

            files_to_generate = [
                f for f in plan["files"] if f["filename"] in feedback_map
            ]
            total     = len(files_to_generate)
            iteration = state.get("review_iterations", 1)

            print_separator("CODER")
            print_agent("coder", f"Correcao {iteration}: {total} arquivo(s) para re-gerar")
        else:
            files_to_generate = plan["files"]
            total             = len(files_to_generate)
            feedback_map      = {}

            print_separator("CODER")
            print_agent("coder", f"{total} arquivo(s) para gerar com {config.coder_model}")

        context_files: list[dict] = list(prev_files)
        newly_generated: list[dict] = []

        for i, file_spec in enumerate(files_to_generate, start=1):
            filename      = file_spec["filename"]
            review_issues = feedback_map.get(filename, [])

            with spinner("coder", f"({i}/{total}) {filename}") as s:
                content = self._generate_file(plan, file_spec, context_files, review_issues)

            lines = len(content.splitlines())
            print_agent("coder", f"({i}/{total}) {filename}  -  {lines} linhas  ({s.elapsed_str()})")

            context_files = [f for f in context_files if f["filename"] != filename]
            context_files.append({"filename": filename, "content": content})
            newly_generated.append({"filename": filename, "content": content})

        prev_map = {f["filename"]: f["content"] for f in prev_files}
        for gen in newly_generated:
            prev_map[gen["filename"]] = gen["content"]

        final_files = [{"filename": fn, "content": ct} for fn, ct in prev_map.items()]
        return {"generated_files": final_files}

    # ── Metodos privados ──────────────────────────────────────────────────────

    def _generate_file(
        self,
        plan: dict,
        file_spec: dict,
        already_generated: list[dict],
        review_issues: list[str] | None = None,
    ) -> str:
        """
        Gera o conteudo de um unico arquivo via tool loop.

        Args:
            plan             : Plano completo do projeto.
            file_spec        : Especificacao do arquivo a gerar.
            already_generated: Arquivos ja gerados/disponiveis como contexto.
            review_issues    : Problemas apontados pelo Reviewer (modo correcao).

        Returns:
            Conteudo do arquivo como string pura.
        """
        context = self._build_context(plan, file_spec, already_generated)

        feedback_section = ""
        if review_issues:
            feedback_section = "\nREVIEWER FEEDBACK -- fix ALL of these issues:\n"
            feedback_section += "\n".join(f"  - {issue}" for issue in review_issues)
            feedback_section += "\n"

        user_prompt = f"""PROJECT OVERVIEW:
Objective: {plan['objective']}
Architecture notes: {plan['notes']}

{context}
{feedback_section}
YOUR TASK:
Implement the file: {file_spec['filename']}
Responsibility: {file_spec['description']}
Must contain: {file_spec['content_hint']}

If you need to read existing project files first, use the available tools.
When ready, output ONLY the complete content for {file_spec['filename']}:"""

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_prompt),
        ]

        return self._run_tool_loop(messages)

    def _run_tool_loop(self, messages: list) -> str:
        """
        Executa o loop LLM <-> ferramentas ate o LLM gerar o codigo.

        Fallback: se o limite de iteracoes for atingido, faz uma chamada
        final sem ferramentas para forcar a geracao de codigo.
        """
        for _ in range(_MAX_TOOL_ITERATIONS):
            response = self.llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                return extract_code(response.content)

            for tc in response.tool_calls:
                result = self._execute_tool(tc)
                messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

        messages.append(HumanMessage(content="Now output ONLY the final code. Do not call any more tools."))
        response = self.llm.invoke(messages)
        return extract_code(response.content)

    def _execute_tool(self, tool_call: dict) -> str:
        """Executa uma chamada de ferramenta emitida pelo LLM."""
        name = tool_call["name"]
        args = tool_call["args"]

        tool_fn = self._tool_map.get(name)
        if tool_fn is None:
            result = f"Unknown tool: {name}"
        else:
            result = tool_fn.invoke(args)

        args_display = ", ".join(f'{k}="{v}"' for k, v in args.items())
        print_agent("coder", f"[tool] {name}({args_display})  ->  {len(result)} chars", dim=True)

        return result

    def _build_context(
        self,
        plan: dict,
        current_file: dict,
        already_generated: list[dict],
    ) -> str:
        """
        Monta a secao de contexto do prompt com informacoes dos outros arquivos.

        DRY: Logica de contexto centralizada aqui, nao duplicada no prompt.
        """
        lines: list[str] = []

        planned_others = [
            f"  - {f['filename']}: {f['description']}"
            for f in plan["files"]
            if f["filename"] != current_file["filename"]
        ]
        if planned_others:
            lines.append("OTHER FILES IN THIS PROJECT (planned):")
            lines.extend(planned_others)

        if already_generated:
            lines.append("\nALREADY IMPLEMENTED FILES (use for imports/references):")
            for gen in already_generated:
                preview = "\n".join(gen["content"].splitlines()[:25])
                lines.append(f"\n--- {gen['filename']} (preview) ---\n{preview}")

        return "\n".join(lines)
