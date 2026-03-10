# Mapa do Projeto — like_claude

Sistema educacional de tres agentes LangGraph + Ollama local.
Fluxo: `START → planner → coder ⇄ reviewer → END` (loop ate aprovacao ou limite)

---

## Visao geral do fluxo

```
main.py
  └─ build_graph()
       ├─ PlannerAgent   → analisa demanda → produz plano JSON
       │
       ├─ CoderAgent     → gera/corrige arquivos; usa run_powershell para testar
       │    ↑  (re-gera apenas arquivos com problemas, com feedback do Reviewer)
       │    │
       ├─ _writer_node   → salva generated_files no disco (output/)
       │    │               permite que o Coder teste com run_powershell
       │    │               na proxima passagem de correcao
       │    │
       └─ ReviewerAgent  → le plano + codigo → reporta conformidade
            │
            ├─ status "ok"           → END
            └─ status "issues_found" → volta ao CoderAgent (ate max_review_iterations)
```

---

## Arquivos raiz

| Arquivo | O que faz |
|---|---|
| `main.py` | Entry point. Le demanda (CLI ou input), executa o grafo, salva arquivos, exibe review e resumo. |
| `requirements.txt` | Dependencias: `langgraph`, `langchain-ollama`, `langchain-core`, `rich`. |

---

## src/

| Arquivo | O que faz |
|---|---|
| `src/config.py` | Unica fonte de verdade para configuracoes: modelos Ollama (`planner_model`, `coder_model`, `reviewer_model`), `max_review_iterations` (limite do loop coder↔reviewer), URL do Ollama, diretorio de saida, temperatura. `dataclass(frozen=True)` — imutavel em runtime. |
| `src/utils.py` | `extract_json(text)` — remove `<think>`, desempacota markdown, parseia JSON. `extract_code(text)` — remove `<think>` e fences markdown, retorna codigo limpo. Usado por Planner, Coder e Reviewer. |
| `src/console.py` | Toda apresentacao no terminal. `spinner(agent, msg)` — context manager com cronometro em thread separada. `print_agent()`, `print_separator()`, `print_header()`, `print_demand()`, `print_review()`, `print_summary()`, `print_error()`. Cores por agente: cyan=planner, green=coder, magenta=reviewer, yellow=writer. |

---

## src/agents/

Cada agente e um **pacote Python** com dois arquivos:
- `__init__.py` — classe do agente (logica Python)
- `SOUL.md` — system prompt do agente (editavel sem tocar em codigo)

| Pacote | Responsabilidade | Entrada (state) | Saida (state) |
|---|---|---|---|
| `base.py` | `BaseAgent(ABC)` — instancia `ChatOllama` no construtor, declara metodo abstrato `run(state)`. | — | — |
| `planner/` | `PlannerAgent` — envia demanda ao LLM, extrai JSON com plano (`objective`, `files`, `notes`). | `demand` | `plan`, `messages` |
| `coder/` | `CoderAgent` — modo normal: gera todos os arquivos do plano. Modo correcao: re-gera apenas os arquivos reprovados pelo Reviewer, injetando o feedback no prompt. | `plan`, `review` (opcional), `generated_files` | `generated_files` (lista completa mesclada) |
| `reviewer/` | `ReviewerAgent` — monta prompt com plano + conteudo de cada arquivo gerado, LLM analisa conformidade, retorna JSON de revisao. Incrementa `review_iterations` a cada execucao. | `plan`, `generated_files`, `review_iterations` | `review`, `review_iterations`, `messages` |

### Detalhes do CoderAgent — tool loop

```
_generate_file()
  └─ _run_tool_loop(messages)
       loop ate _MAX_TOOL_ITERATIONS (5):
         llm_with_tools.invoke()
           ├─ sem tool_calls → extract_code() → retorna
           └─ com tool_calls → _execute_tool() → ToolMessage → continua
       fallback: llm.invoke() sem tools → "output ONLY final code"
```

---

## src/graph/

| Arquivo | O que faz |
|---|---|
| `state.py` | `GraphState(TypedDict)` — contrato de dados do grafo. Campos: `demand` (str), `plan` (dict\|None), `generated_files` (list[dict]), `review` (dict\|None), `review_iterations` (int), `messages` (Annotated com `add_messages` para acumulo). |
| `builder.py` | `build_graph()` — instancia os 3 agentes, cria `StateGraph(GraphState)`, adiciona nos e arestas. Contem `_writer_node` (salva arquivos no disco entre coder e reviewer) e `_route_after_review` (aresta condicional `reviewer → coder \| END`). Retorna `CompiledGraph`. |

---

## src/tools/

| Arquivo | O que faz |
|---|---|
| `file_reader.py` | `@tool list_directory(subdirectory)` — lista arquivos do projeto (ignora `.git`, `__pycache__`, etc.). `@tool read_file(filepath)` — le conteudo de arquivo. Ambos restritos ao CWD (sem path traversal). Exporta `FILE_READER_TOOLS`. |
| `file_writer.py` | `FileWriter(output_dir)` — `write(filename, content)` salva um arquivo. `write_all(files)` itera a lista. Cria subdiretorios automaticamente. Salva em UTF-8. Usado pelo `_writer_node` no grafo. |
| `shell.py` | `@tool run_powershell(command)` — executa comando PowerShell no diretorio `output/`. Timeout 30s, output limitado a 4000 chars. Exporta `SHELL_TOOLS`. Usado pelo CoderAgent para testar o codigo gerado. |

---

## Estado do grafo — ciclo de vida

```
{ demand, plan: None, generated_files: [], review: None, review_iterations: 0, messages: [] }
         |
     [planner]
         |
{ ..., plan: {objective, files, notes}, ... }
         |
      [coder]  ← modo normal: gera todos os arquivos
         |
{ ..., generated_files: [{filename, content}, ...] }
         |
    [reviewer]  ← review_iterations torna-se 1
         |
{ ..., review: {status, summary, files: [...]}, review_iterations: 1 }
         |
    [_route_after_review]
         ├─ status "ok"           → END
         └─ status "issues_found" e iterations < max
                  |
               [coder]  ← modo correcao: re-gera so arquivos com problema
                  |
              [reviewer]  ← review_iterations torna-se 2
                  |
              (repete ate ok ou iterations == max_review_iterations)
```

---

## Como adicionar features

| Quero... | Onde mexer |
|---|---|
| Trocar modelo de qualquer agente | `src/config.py` — editar o campo do modelo |
| Ajustar limite do loop de correcao | `src/config.py` — campo `max_review_iterations` |
| Adicionar tool para o CoderAgent | `src/tools/file_reader.py` — novo `@tool`, adicionar a `FILE_READER_TOOLS` |
| Adicionar novo agente | Criar `src/agents/novo.py` herdando `BaseAgent`, registrar em `builder.py` e `state.py` |
| Mudar cor de um agente no terminal | `src/console.py` — dicionario `AGENT_COLOR` |
| Mudar diretorio de saida | `src/config.py` — campo `output_dir` |
