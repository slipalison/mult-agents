"""
Agente Programador.

SOLID - SRP: Implementa codigo baseado no plano recebido.
             Nao planeja. Nao salva arquivos no disco. So gera codigo.
"""

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

    Possui acesso a ferramentas de leitura do sistema de arquivos:
      - list_directory : lista arquivos do projeto
      - read_file      : le o conteudo de um arquivo

    O LLM decide autonomamente quando chamar essas ferramentas antes de
    gerar o codigo. Isso permite que ele leia codigo existente para
    manter consistencia de imports, nomes de classes, etc.

    Fluxo por arquivo:
        1. LLM recebe o prompt com o plano
        2. LLM (opcionalmente) chama ferramentas para ler contexto
        3. Ferramenta executa, resultado volta como ToolMessage
        4. LLM gera o codigo final
        5. Codigo e extraido e armazenado no estado
    """

    SYSTEM_PROMPT = """/no_think
You are an expert software developer implementing files from a project plan.

You have access to file reading tools. Use them when you need to understand
the existing codebase before writing a file (e.g., to check imports, class
names, or conventions already established by other files).

STRICT RULES:
1. After gathering context with tools, output ONLY raw code.
2. No markdown fences (```), no explanations before or after.
3. Write complete, working, production-quality code.
4. Follow SOLID, KISS, and DRY principles.
5. Add concise docstrings and comments where the logic is not obvious."""

    def __init__(self):
        super().__init__(model=config.coder_model, temperature=0.2)

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

        Modo normal (primeira execucao):
          - Gera todos os arquivos do plano do zero.

        Modo correcao (chamado pelo loop coder <-> reviewer):
          - Recebe o review do Reviewer com a lista de arquivos problematicos.
          - Re-gera APENAS os arquivos com status != "ok", incluindo o
            feedback especifico do Reviewer no prompt de cada arquivo.
          - Mantem os arquivos aprovados intactos (nao os re-gera).
          - Retorna a lista completa mesclada (aprovados + corrigidos).

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
            # Identifica quais arquivos precisam ser corrigidos e monta o
            # mapa de feedback: filename → lista de issues + suggestions
            feedback_map: dict[str, list[str]] = {}
            for frev in review.get("files", []):
                if frev.get("status") != "ok":
                    feedback_map[frev["filename"]] = (
                        frev.get("issues", []) + frev.get("suggestions", [])
                    )

            files_to_generate = [
                f for f in plan["files"] if f["filename"] in feedback_map
            ]
            total      = len(files_to_generate)
            iteration  = state.get("review_iterations", 1)

            print_separator("CODER")
            print_agent("coder", f"Correcao {iteration}: {total} arquivo(s) para re-gerar")
        else:
            files_to_generate = plan["files"]
            total             = len(files_to_generate)
            feedback_map      = {}

            print_separator("CODER")
            print_agent("coder", f"{total} arquivo(s) para gerar com {config.coder_model}")

        # Contexto inicial: arquivos gerados anteriormente (passagem anterior
        # ou arquivos ja gerados nesta rodada). Vai crescendo a cada arquivo.
        context_files: list[dict] = list(prev_files)
        newly_generated: list[dict] = []

        for i, file_spec in enumerate(files_to_generate, start=1):
            filename      = file_spec["filename"]
            review_issues = feedback_map.get(filename, [])

            with spinner("coder", f"({i}/{total}) {filename}") as s:
                content = self._generate_file(plan, file_spec, context_files, review_issues)

            lines = len(content.splitlines())
            print_agent("coder", f"({i}/{total}) {filename}  -  {lines} linhas  ({s.elapsed_str()})")

            # Atualiza o contexto para o proximo arquivo desta rodada
            context_files = [f for f in context_files if f["filename"] != filename]
            context_files.append({"filename": filename, "content": content})
            newly_generated.append({"filename": filename, "content": content})

        # Mescla: parte dos arquivos anteriores que NAO foram re-gerados
        # com os arquivos recém gerados/corrigidos nesta rodada.
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

        O loop permite que o LLM chame ferramentas de leitura antes de
        escrever o codigo final. A sequencia de mensagens cresce a cada
        iteracao com os resultados das ferramentas.

        Args:
            plan             : Plano completo do projeto.
            file_spec        : Especificacao do arquivo a gerar.
            already_generated: Arquivos ja gerados/disponiveis como contexto.
            review_issues    : Lista de problemas apontados pelo Reviewer para
                               este arquivo (modo correcao). None na primeira geracao.

        Returns:
            Conteudo do arquivo como string pura.
        """
        context = self._build_context(plan, file_spec, already_generated)

        # Secao de feedback do Reviewer — so aparece no modo correcao
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
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        return self._run_tool_loop(messages)

    def _run_tool_loop(self, messages: list) -> str:
        """
        Executa o loop LLM <-> ferramentas ate o LLM gerar o codigo.

        Cada iteracao:
          1. Chama o LLM com ferramentas vinculadas
          2. Se a resposta contem tool_calls  -> executa cada ferramenta,
             adiciona ToolMessage ao historico, continua o loop
          3. Se a resposta nao tem tool_calls -> e o codigo final, retorna

        Fallback: se o limite de iteracoes for atingido, faz uma chamada
        final sem ferramentas para forcsr a geracao de codigo.

        Args:
            messages: Historico inicial de mensagens (system + human).

        Returns:
            Conteudo do arquivo como string pura.
        """
        for _ in range(_MAX_TOOL_ITERATIONS):
            response = self.llm_with_tools.invoke(messages)
            messages.append(response)

            # Sem tool_calls -> o LLM decidiu gerar o codigo diretamente
            if not response.tool_calls:
                return extract_code(response.content)

            # Com tool_calls -> executa cada ferramenta e alimenta o resultado
            for tc in response.tool_calls:
                result = self._execute_tool(tc)
                messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

        # Fallback: forcsa resposta sem ferramentas apos esgotar iteracoes
        messages.append(HumanMessage(content="Now output ONLY the final code. Do not call any more tools."))
        response = self.llm.invoke(messages)
        return extract_code(response.content)

    def _execute_tool(self, tool_call: dict) -> str:
        """
        Executa uma chamada de ferramenta emitida pelo LLM.

        Imprime no console qual ferramenta foi chamada (dim) para
        o usuario acompanhar o raciocinio do agente.

        Args:
            tool_call: Dict com "name", "args" e "id" (formato LangChain).

        Returns:
            Resultado da ferramenta como string.
        """
        name = tool_call["name"]
        args = tool_call["args"]

        tool_fn = self._tool_map.get(name)
        if tool_fn is None:
            result = f"Unknown tool: {name}"
        else:
            result = tool_fn.invoke(args)

        # Exibe qual ferramenta foi chamada e quantos chars retornou
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
