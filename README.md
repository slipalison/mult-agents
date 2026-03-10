# Sistema de Agentes LangGraph + Ollama

Sistema didático de três agentes de IA que conversam entre si para transformar
uma demanda em linguagem natural em arquivos de código prontos no disco.

---

## Índice

1. [O que é e o que faz](#o-que-é-e-o-que-faz)
2. [Como funciona — visão geral](#como-funciona--visão-geral)
3. [O que é LangGraph](#o-que-é-langgraph)
4. [Modelos utilizados](#modelos-utilizados)
5. [Instalação](#instalação)
6. [Como usar](#como-usar)
7. [Estrutura do projeto](#estrutura-do-projeto)
8. [Arquivos explicados](#arquivos-explicados)
9. [Como adicionar um novo agente](#como-adicionar-um-novo-agente)
10. [Princípios de arquitetura](#princípios-de-arquitetura)
11. [Console estilizado](#console-estilizado)

---

## O que é e o que faz

Você digita uma demanda como:

```
crie uma API REST com Flask que gerencia uma lista de tarefas
```

O sistema executa três agentes locais em sequência (com loop de correção):

1. **PlannerAgent** — entende a demanda e decide *quais arquivos* precisam existir e *o que cada um deve conter*
2. **CoderAgent** — recebe esse plano e *implementa* cada arquivo, um por vez
3. **ReviewerAgent** — lê o plano e o código gerado, verifica a conformidade e devolve ao Coder se encontrar problemas — repete até tudo estar aprovado ou atingir o limite de iterações

Ao final, os arquivos gerados são salvos na pasta `output/`.

Tudo roda 100% local via **Ollama** — sem nenhuma chamada a APIs externas.

---

## Como funciona — visão geral

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              LANGGRAPH                                   │
│                                                                          │
│  ┌───────┐   ┌──────────────────┐   ┌───────────────┐                   │
│  │ START │──▶│  PlannerAgent    │──▶│  CoderAgent   │◀──────────┐       │
│  └───────┘   │  qwen3.5:9b      │   │  qwen2.5-     │           │       │
│              │                  │   │  coder:7b     │      re-gera       │
│              │  Lê: demand      │   │               │      arquivos      │
│              │  Escreve: plan   │   │  Lê: plan     │    reprovados      │
│              └──────────────────┘   │  Escreve:     │           │       │
│                                     │  generated_   │           │       │
│                                     │  files        │           │       │
│                                     └───────┬───────┘           │       │
│                                             │                   │       │
│                                             ▼                   │       │
│                                     ┌───────────────┐           │       │
│                                     │ ReviewerAgent │───issues──┘       │
│                                     │ qwen3.5:9b    │                   │
│                                     │               │──── ok ───▶ END   │
│                                     └───────────────┘                   │
└──────────────────────────────────────────────────────────────────────────┘
                            (apos END)
                                 │
                                 ▼
                          ┌─────────────┐
                          │ FileWriter  │
                          │ output/     │
                          └─────────────┘
```

### O que cada parte faz

| Componente | Responsabilidade | Fala com quem |
|------------|-----------------|---------------|
| `main.py` | Lê a demanda, inicia o grafo, chama FileWriter | Grafo + FileWriter |
| `PlannerAgent` | Produz um plano JSON (lista de arquivos) | LLM qwen3.5:9b |
| `CoderAgent` | Gera o código de cada arquivo; em modo correção, re-gera só os reprovados com feedback do Reviewer | LLM qwen2.5-coder:7b |
| `ReviewerAgent` | Verifica se cada arquivo cumpre o plano; reprova e devolve ao Coder se necessário | LLM qwen3.5:9b |
| `FileWriter` | Salva os arquivos gerados no disco | Sistema de arquivos |
| `GraphState` | Estado compartilhado — todos os nós lêem e escrevem aqui | — |

---

## O que é LangGraph

**LangGraph** é uma biblioteca para construir fluxos de trabalho com LLMs como um **grafo de nós**.

Conceitos fundamentais:

### Estado (`GraphState`)

Um dicionário tipado (`TypedDict`) que é o "banco de dados em memória" do grafo.
Todos os nós lêem do estado e retornam **apenas as chaves que modificaram**.

```python
class GraphState(TypedDict):
    demand: str                                           # entrada do usuário
    plan: Optional[dict]                                  # saída do Planner
    generated_files: list[dict]                           # saída do Coder
    review: Optional[dict]                                # saída do Reviewer
    review_iterations: int                                # contador do loop coder↔reviewer
    messages: Annotated[list[BaseMessage], add_messages]  # histórico LLM
```

A anotação `add_messages` é especial: em vez de **substituir** a lista de mensagens,
o LangGraph **acumula** automaticamente (append). Os outros campos sobrescrevem normalmente.

### Nós

Cada nó é uma função com a assinatura:

```python
def meu_no(state: dict) -> dict:
    # lê o que precisa do estado
    # faz seu trabalho
    return {"chave_que_atualizei": novo_valor}
```

O LangGraph faz o **merge** do retorno com o estado existente automaticamente.

### Arestas

Definem a ordem de execução. Arestas podem ser fixas ou condicionais:

```python
# Arestas fixas
graph.add_edge(START,     "planner")   # começa no planner
graph.add_edge("planner", "coder")     # planner termina → coder começa
graph.add_edge("coder",   "reviewer")  # coder termina → reviewer avalia

# Aresta condicional: reviewer decide o próximo nó
graph.add_conditional_edges(
    "reviewer",
    _route_after_review,               # função que inspeciona o estado
    {"coder": "coder", END: END},      # mapa de destinos possíveis
)
# _route_after_review retorna "coder" se há problemas e ainda há iterações,
# ou END se está tudo ok ou o limite foi atingido
```

### Por que LangGraph?

- **Fluxo explícito**: você vê exatamente quem executa e em que ordem
- **Estado tipado**: erros de chave são detectáveis antes de rodar
- **Extensível**: adicionar um novo nó não muda os outros
- **Testável**: cada nó é uma função pura que recebe e retorna dicts

---

## Modelos utilizados

Ambos rodam localmente via Ollama. Para contexto didático escolhemos os
**menores modelos disponíveis** que ainda produzem resultados de qualidade —
velocidade de iteração importa mais do que perfeição.

| Agente | Modelo | VRAM | Por que este? |
|--------|--------|------|---------------|
| Planner | `qwen3.5:9b` | ~6.6 GB | Família Qwen3.5 tem raciocínio encadeado integrado (`<think>`). Confiável para gerar JSON estruturado. |
| Coder | `qwen2.5-coder:7b` | ~4.7 GB | Fine-tuned especificamente para código. Supera modelos gerais maiores em geração de código. |
| Reviewer | `qwen3.5:9b` | — | Mesmo modelo do Planner — bom para raciocínio analítico e saída JSON. Compartilha VRAM já alocada. |
| **Total** | | **~11 GB** | Os três cabem simultaneamente na RTX 4090 (24 GB) |

### Quer modelos mais potentes?

Edite apenas `src/config.py`:

```python
@dataclass(frozen=True)
class Config:
    planner_model:        str = "qwen3.5:27b"       # mais lento, mais preciso
    coder_model:          str = "qwen2.5-coder:32b" # mais lento, código melhor
    reviewer_model:       str = "qwen3.5:27b"       # idem
    max_review_iterations: int = 3                  # ajuste o loop aqui
```

Nenhum outro arquivo precisa ser alterado.

---

## Instalação

### Pré-requisitos

- Python 3.10+
- [Ollama](https://ollama.com) instalado e rodando
- Os modelos baixados:

```bash
ollama pull qwen3.5:9b
ollama pull qwen2.5-coder:7b
# qwen3.5:9b é reutilizado pelo Reviewer — não precisa de pull extra
```

### Dependências Python

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
langgraph>=0.2.0
langchain-ollama>=0.2.0
langchain-core>=0.3.0
```

---

## Como usar

```bash
# Demanda como argumento direto:
python main.py "crie uma calculadora em Python com as 4 operacoes basicas"

# Ou modo interativo (digita após o prompt):
python main.py
```

Os arquivos gerados aparecem em `output/` mantendo a estrutura de pastas
que o Planner decidir (ex: `output/src/main.py`, `output/tests/test_calc.py`).

### Exemplo de execução

```
============================================================
  Sistema de Agentes LangGraph + Ollama
============================================================
  Planner : qwen3.5:9b
  Coder   : qwen2.5-coder:7b
  Saida   : ./output/
============================================================

Demanda recebida: "crie uma calculadora em Python"

[NO 1/2] PLANNER
  [Planner] Chamando qwen3.5:9b...
  [Planner] Plano criado: 3 arquivo(s) planejado(s)
    -> src/calculator.py: Logica das operacoes aritmeticas
    -> src/main.py: Interface de linha de comando
    -> tests/test_calculator.py: Testes unitarios

[NO 2/2] CODER
  [Coder] (1/3) Gerando: src/calculator.py
  [Coder] OK src/calculator.py - 24 linha(s)
  [Coder] (2/3) Gerando: src/main.py
  ...

============================================================
  CONCLUIDO!
  3 arquivo(s) gerado(s):
    [OK] output\src\calculator.py
    [OK] output\src\main.py
    [OK] output\tests\test_calculator.py
============================================================
```

---

## Estrutura do projeto

```
like_claude/
│
├── main.py                    # Ponto de entrada — orquestra tudo
├── requirements.txt
├── MAPA.md                    # Mapa rapido de arquivos e responsabilidades
│
├── src/
│   ├── config.py              # Configuracao central (modelos, paths, limites)
│   ├── utils.py               # Helpers: extract_json(), extract_code()
│   │
│   ├── agents/
│   │   ├── base.py            # BaseAgent(ABC) — contrato comum
│   │   ├── planner.py         # PlannerAgent — analisa demanda, cria plano
│   │   ├── coder.py           # CoderAgent — implementa/corrige arquivos do plano
│   │   └── reviewer.py        # ReviewerAgent — verifica conformidade, devolve ao Coder se necessario
│   │
│   ├── graph/
│   │   ├── state.py           # GraphState(TypedDict) — estado do grafo
│   │   └── builder.py         # build_graph() — monta a topologia com aresta condicional
│   │
│   ├── tools/
│   │   ├── file_reader.py     # Tools LangChain: list_directory, read_file
│   │   └── file_writer.py     # FileWriter — salva arquivos no disco
│   │
│   └── console.py             # Console estilizado (cores, spinner, paineis)
│
└── output/                    # Arquivos gerados pelos agentes ficam aqui
```

---

## Arquivos explicados

### `src/config.py`

Único lugar onde configurações vivem. Para trocar modelo, URL do Ollama ou
diretório de saída — edite aqui. Nenhum outro arquivo precisa mudar.

```python
config = Config()  # instancia global importada pelos outros módulos
```

### `src/utils.py`

Dois helpers reutilizados por `planner.py` e `coder.py`:

- **`extract_json(text)`** — extrai JSON válido de uma resposta de LLM que pode
  conter tags `<think>...</think>` (Qwen3) ou blocos markdown ` ```json ``` `
- **`extract_code(text)`** — extrai código limpo, removendo as mesmas sujeiras

Sem esta camada, cada agente precisaria duplicar essa lógica. **(DRY)**

### `src/agents/base.py`

Classe abstrata que define o contrato de todos os agentes:

```python
class BaseAgent(ABC):
    def __init__(self, model: str, temperature: float | None = None):
        self.llm = ChatOllama(model=model, ...)  # injeta o LLM

    @abstractmethod
    def run(self, state: dict) -> dict:           # todo agente implementa isso
        ...
```

Benefícios:
- Novo agente = nova subclasse. A base nunca muda. **(OCP)**
- Qualquer agente pode ser usado onde `BaseAgent` for esperado **(LSP)**
- Troca de LLM (ex: para OpenAI): muda só aqui **(DIP)**

### `src/agents/planner.py`

Chama `qwen3.5:9b`, pede um JSON com a lista de arquivos a criar e retorna:

```python
{"plan": {"objective": ..., "files": [...], "notes": ...}}
```

Responsabilidade única: **planejar**. Não sabe que o Coder existe.

### `src/agents/coder.py`

Opera em dois modos dependendo do estado recebido:

**Modo normal** (primeira execução — sem `review` no estado):

```
1. Monta prompt (plano + contexto)
        │
        ▼
2. LLM with tools ──── tool_calls? ──YES──▶ executa ferramenta
        │                                        │
       NO                              adiciona ToolMessage
        │                                        │
        ▼                               volta ao passo 2
3. Extrai e retorna o código
```

**Modo correção** (chamado pelo loop — `review.status == "issues_found"`):
- Re-gera **apenas** os arquivos com `status != "ok"` no review
- Injeta o feedback do Reviewer no prompt de cada arquivo reprovado (`REVIEWER FEEDBACK -- fix ALL of these issues`)
- Mantém os arquivos aprovados intactos
- Retorna a lista completa mesclada (aprovados + corrigidos)

Responsabilidade única: **codificar**. Não sabe nada de planejamento ou disco.

### `src/tools/file_reader.py`

Dois **LangChain tools** (`@tool`) disponíveis para o CoderAgent:

| Tool | O que faz | Argumento |
|------|-----------|-----------|
| `list_directory` | Lista todos os arquivos de um diretório | `subdirectory` (default `.`) |
| `read_file` | Lê o conteúdo de um arquivo | `filepath` |

Ambos são restritos ao diretório raiz do projeto — tentativas de path
traversal (`../`) são bloqueadas e retornam erro.

```python
# Como as ferramentas sao vinculadas ao LLM (em CoderAgent.__init__)
self.llm_with_tools = self.llm.bind_tools(FILE_READER_TOOLS)

# Como uma chamada de ferramenta e executada (em _execute_tool)
result = tool_fn.invoke(tool_call["args"])
messages.append(ToolMessage(content=result, tool_call_id=tool_call["id"]))
```

Para adicionar uma nova ferramenta: crie uma funcao com `@tool` em
`file_reader.py` e adicione-a à lista `FILE_READER_TOOLS`. O CoderAgent
não precisa ser modificado. **(OCP)**

### `src/graph/state.py`

Define a "memória compartilhada" do grafo. Cada nó recebe o estado
completo e retorna apenas o que modificou.

### `src/graph/builder.py`

Monta a topologia `START → planner → coder ⇄ reviewer → END` e compila o grafo.
Contém a função `_route_after_review` que decide, após cada revisão, se volta ao
Coder (problemas encontrados + iterações disponíveis) ou encerra (aprovado ou limite atingido).
Para adicionar nós, edite **apenas este arquivo**.

### `src/tools/file_writer.py`

Persiste os arquivos gerados no disco. Separado dos agentes intencionalmente:
agentes geram conteúdo, `FileWriter` persiste — são responsabilidades distintas.

---

## Como adicionar um novo agente

Este é o passo a passo completo para adicionar, por exemplo, um **DocWriterAgent**
que gera um `README.md` automático para o projeto criado.

### Passo 1 — Crie o agente em `src/agents/doc_writer.py`

Extenda `BaseAgent` e implemente `run()`. Nenhum outro arquivo existente
precisa ser tocado nesta etapa.

```python
# src/agents/doc_writer.py

from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.base import BaseAgent
from src.config import config
from src.console import print_agent, print_separator, spinner
from src.utils import extract_code


class DocWriterAgent(BaseAgent):
    """
    Gera documentacao (README.md) a partir do plano e dos arquivos gerados.
    SRP: apenas documenta, nao planeja nem codifica.
    """

    SYSTEM_PROMPT = """/no_think
You are a technical writer. Generate a clear README.md for the project.
Output ONLY the raw markdown content, no extra text."""

    def __init__(self):
        super().__init__(model=config.planner_model)

    def run(self, state: dict) -> dict:
        plan       = state["plan"]
        gen_files  = state["generated_files"]

        files_list = "\n".join(f"- {f['filename']}" for f in gen_files)

        print_separator("DOC WRITER")

        with spinner("writer", "Gerando README.md") as s:
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=f"Project: {plan['objective']}\nFiles:\n{files_list}"),
            ])

        doc = extract_code(response.content)
        print_agent("writer", f"README.md gerado  ({s.elapsed_str()})")

        # Retorna uma nova chave — nao interfere com as existentes
        return {"documentation": doc}
```

### Passo 2 — Adicione `documentation` ao `GraphState`

```python
class GraphState(TypedDict):
    demand: str
    plan: Optional[dict]
    generated_files: list[dict]
    review: Optional[dict]
    review_iterations: int
    documentation: Optional[str]                          # <- NOVO
    messages: Annotated[list[BaseMessage], add_messages]
```

### Passo 3 — Conecte o nó no grafo

```python
from src.agents.doc_writer import DocWriterAgent   # <- NOVO

def build_graph():
    planner    = PlannerAgent()
    coder      = CoderAgent()
    reviewer   = ReviewerAgent()
    doc_writer = DocWriterAgent()                  # <- NOVO

    graph.add_node("doc_writer", doc_writer.run)   # <- NOVO

    # Aresta após o reviewer aprovar vai para doc_writer antes do END
    # (ajuste _route_after_review para retornar "doc_writer" em vez de END)
```

### Resumo do que é tocado

| Arquivo | O que muda |
|---------|------------|
| `src/agents/doc_writer.py` | **Criado** — nova subclasse de `BaseAgent` |
| `src/graph/state.py` | Adicionar campo `documentation` |
| `src/graph/builder.py` | Adicionar nó + aresta |
| `planner.py`, `coder.py`, `reviewer.py`, `base.py` | **Nada muda** |

Isso é o princípio **Open/Closed** na prática: o sistema é estendido
sem modificar o que já funciona.

---

## Princípios de arquitetura

### SOLID

| Letra | Princípio | Onde está |
|-------|-----------|-----------|
| **S** — Single Responsibility | Cada classe tem uma razão para existir | `PlannerAgent` só planeja, `CoderAgent` só codifica, `FileWriter` só salva |
| **O** — Open/Closed | Aberto para extensão, fechado para modificação | Adicionar `ReviewerAgent` não toca nos agentes existentes |
| **L** — Liskov Substitution | Subclasses substituem a base sem quebrar | Qualquer `BaseAgent` pode ser passado como nó LangGraph |
| **I** — Interface Segregation | Interfaces mínimas | `BaseAgent` expõe apenas `run()` — sem métodos que agentes não precisam |
| **D** — Dependency Inversion | Dependa de abstrações | Agentes dependem de `ChatOllama` (interface), não de um modelo específico |

### KISS (Keep It Simple)

O grafo tem um fluxo claro: `START → planner → coder ⇄ reviewer → END`.
O único ponto de decisão é a aresta condicional do Reviewer — uma função
de 3 linhas (`_route_after_review`) que inspeciona duas chaves do estado.
Se algo falha, o erro aparece claramente sem lógica oculta.

### DRY (Don't Repeat Yourself)

`extract_json()` e `extract_code()` em `utils.py` existem porque tanto
o Planner quanto o Coder precisavam da mesma lógica de limpeza de resposta.
Definida uma vez, usada em dois lugares.

### YAGNI (You Aren't Gonna Need It)

Não há:
- CLI com flags (`--verbose`, `--model`, `--output`)
- Persistência de histórico entre sessões
- Retry automático em falhas
- Configuração via arquivo `.env`

Tudo isso seria útil em produção, mas não foi pedido — então não existe.
Adicionar quando (e se) necessário.

---

## Console estilizado

O arquivo `src/console.py` centraliza toda a apresentação visual, inspirado
no estilo do Claude Code: prefixo colorido por agente, spinner animado com
cronômetro, painéis de cabeçalho e resumo.

### Visual de execução

```
+---------- Sistema de Agentes LangGraph + Ollama ----------+
|                                                           |
|  Planner   qwen3.5:9b                                     |
|  Coder     qwen2.5-coder:7b                               |
|  Saida     ./output/                                      |
|                                                           |
+-----------------------------------------------------------+
  > SYSTEM      Demanda: "crie uma calculadora em Python"


---------------------------  PLANNER  ---------------------------

  / PLANNER     Chamando qwen3.5:9b  00:00:07        <- spinner animado
  > PLANNER     Plano criado: 3 arquivo(s)  (00:00:10)
  > PLANNER     src/calculator.py  -  Logica aritmetica    <- dim
  > PLANNER     src/main.py  -  Interface CLI               <- dim

----------------------------  CODER  ----------------------------

  > CODER       3 arquivo(s) para gerar com qwen2.5-coder:7b
  / CODER       (1/3) src/calculator.py  00:00:04    <- spinner animado
  > CODER       (1/3) src/calculator.py  -  46 linhas  (00:00:06)
  ...

+------ CONCLUIDO -- 3 arquivo(s) gerado(s) ------+
|                                                 |
|  Calculadora Python com as 4 operacoes...       |
|                                                 |
|    > output\src\calculator.py                   |
|    > output\src\main.py                         |
|    > output\tests\test_calculator.py            |
|                                                 |
+-------------------------------------------------+
```

### API do console

```python
from src.console import spinner, print_agent, print_separator

# Spinner com cronometro — envolve a chamada bloqueante ao LLM
with spinner("meu_agente", "Chamando modelo") as s:
    response = self.llm.invoke(messages)
# Apos o bloco: s.elapsed_str() retorna "00:00:07"
print_agent("meu_agente", f"Pronto  ({s.elapsed_str()})")

# Linha informativa com prefixo colorido
print_agent("meu_agente", "mensagem normal")
print_agent("meu_agente", "detalhe em cinza", dim=True)

# Separador de secao
print_separator("NOME DA SECAO")
```

### Cores por agente

| Agente | Cor |
|--------|-----|
| planner | cyan |
| coder | green |
| reviewer | magenta |
| writer | yellow |
| system | white |

Para adicionar um novo agente, inclua a entrada em `AGENT_COLOR` em `src/console.py`:

```python
AGENT_COLOR: dict[str, str] = {
    "planner":  "cyan",
    "coder":    "green",
    "reviewer": "magenta",
    "writer":   "yellow",
    "novo":     "blue",    # <- novo agente
}
```

---

## Diagrama de dependências

```
main.py
  ├── src/config.py
  ├── src/console.py
  ├── src/graph/builder.py
  │     ├── src/config.py
  │     ├── src/graph/state.py
  │     ├── src/agents/planner.py
  │     │     ├── src/agents/base.py  ──>  langchain_ollama.ChatOllama
  │     │     ├── src/console.py
  │     │     └── src/utils.py
  │     ├── src/agents/coder.py
  │     │     ├── src/agents/base.py
  │     │     ├── src/console.py
  │     │     ├── src/utils.py
  │     │     └── src/tools/file_reader.py
  │     └── src/agents/reviewer.py
  │           ├── src/agents/base.py
  │           ├── src/console.py
  │           └── src/utils.py
  └── src/tools/file_writer.py
```

Nenhum modulo de `agents/` importa de `graph/` ou `tools/`.
`console.py` nao importa de agentes, grafo ou ferramentas — sem circular.
O fluxo de dependencia e sempre de fora para dentro.
