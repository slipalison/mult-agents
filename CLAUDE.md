# like_claude

Sistema educacional de agentes LangGraph + Ollama local.

## Fluxo do grafo
```
START → planner → coder → writer → reviewer → END
                     ▲                │ issues_found
                     └────────────────┘ (até max_review_iterations)
```

## Estrutura
```
like_claude/
├── src/
│   ├── config.py          # Config imutavel (dataclass frozen=True) + LangSmith opcional
│   ├── utils.py           # extract_json(), extract_code()
│   ├── console.py         # spinner(), print_agent(), print_header(), print_review(), paineis
│   ├── agents/
│   │   ├── base.py        # BaseAgent(ABC) com ChatOllama
│   │   ├── planner/       # PlannerAgent → {"plan": dict}
│   │   ├── coder/         # CoderAgent   → {"generated_files": list[dict]}
│   │   └── reviewer/      # ReviewerAgent→ {"review": dict}
│   ├── graph/
│   │   ├── state.py       # GraphState: demand, plan, generated_files, review,
│   │   │                  #             review_iterations, project_dir, messages
│   │   └── builder.py     # build_graph(), _writer_node(), _slugify(), _unique_dir()
│   └── tools/
│       ├── file_reader.py # @tool list_directory + read_file
│       └── file_writer.py # FileWriter.write_all()
├── output/                # Subpastas por projeto: output/<slug-do-objetivo>/
├── .env.example           # LANGSMITH_API_KEY, LANGSMITH_PROJECT
├── main.py                # Entry point
└── requirements.txt
```

## Saída de arquivos
- Cada execução cria `output/<slug>/` onde slug vem de `plan["objective"]`
- Se a pasta já existe: `output/<slug>_2/`, `_3/`, ...
- `project_dir` é armazenado no `GraphState` e reutilizado no loop de correção
- Lógica em `builder.py`: `_slugify()` + `_unique_dir()`

## LangSmith (opcional)
- Configure `LANGSMITH_API_KEY` no `.env` (copiar de `.env.example`)
- Tracing automático de todos os nós — zero mudanças nos agentes
- Status exibido no painel de cabeçalho quando ativo

## Regras importantes
- **NUNCA usar `—` (em-dash) em strings printadas** — Windows cp1252 quebra. Usar `--`
- `rich.Text.rstrip()` sem argumentos — API oficial do Rich
- Prints no terminal: ASCII puro. Arquivos gerados: UTF-8
- `config.py` é frozen=True — não modificar em runtime

## Como usar
```bash
pip install -r requirements.txt
python main.py "crie uma API REST com Flask"
```
