"""
Configuracao central do sistema.

KISS  : Todas as configuracoes em um unico lugar - facil de achar e mudar.
YAGNI : Apenas as configuracoes realmente necessarias agora.
DRY   : Valores definidos aqui, importados em qualquer lugar que precisar.

Guia de escolha de modelos (do mais leve ao mais potente):
---------------------------------------------------------------------------
Modelo                  VRAM    Velocidade  Qualidade   Quando usar
---------------------------------------------------------------------------
qwen2.5-coder:7b        ~4.7GB  Rapido      Boa codigo  Coder (padrao)
qwen3.5:9b              ~6.6GB  Rapido      Boa razao.  Planner (padrao)
llama3.1:8b             ~4.9GB  Rapido      Boa geral   Alternativa geral
qwen2.5-coder:32b       ~20GB   Lento       Excelente   Producao (codigo)
qwen3.5:27b             ~17GB   Lento       Excelente   Producao (razao.)
---------------------------------------------------------------------------
Para contexto DIDATICO: prefira modelos pequenos — iteracao rapida importa
mais do que saida perfeita.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """
    Configuracao imutavel do sistema.

    `frozen=True` evita mutacao acidental em tempo de execucao.
    Para trocar de modelo, basta editar o valor padrao do campo abaixo.

    SOLID - SRP: Esta classe existe apenas para guardar configuracao.
    """

    # --- Modelos Ollama ---
    # qwen3.5:9b       : 9.7B params, ~6.6GB VRAM
    #   - Familia Qwen3.5 tem raciocinio encadeado (<think>) integrado
    #   - Otimo para gerar JSON estruturado de forma confiavel
    #   - Muito mais rapido que o 27B para iteracao didatica
    #
    # qwen2.5-coder:7b : 7.6B params, ~4.7GB VRAM
    #   - Fine-tuned especificamente para geracao de codigo
    #   - Apesar do tamanho menor, supera modelos gerais maiores em codigo
    #   - Juntos os dois usam ~11GB — cabem simultaneamente na RTX 4090
    planner_model: str = "qwen3.5:9b"
    coder_model: str = "qwen2.5-coder:7b"
    reviewer_model: str = "qwen3.5:9b"

    # Numero maximo de vezes que o Reviewer pode reprovar e devolver ao Coder.
    # Com max=3: o Coder pode ser chamado para correcao ate 2 vezes apos a
    # primeira geracao (reviewer roda 3x no total antes de forcsar o END).
    max_review_iterations: int = 3

    # --- Conexao com Ollama ---
    ollama_base_url: str = "http://localhost:11434"

    # --- Saida ---
    output_dir: str = "output"

    # --- LLM ---
    # Temperatura baixa = respostas mais deterministicas (bom para JSON e codigo)
    temperature: float = 0.1


# Instancia global — importe `config` em vez de instanciar Config diretamente
config = Config()
