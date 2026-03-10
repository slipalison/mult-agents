"""
Utilitários compartilhados entre os agentes.

DRY: A lógica de extração de resposta dos LLMs fica aqui,
     evitando que planner.py e coder.py dupliquem o mesmo código.

SOLID - SRP: Este módulo só cuida de parsear/limpar texto de LLMs.
"""

import json
import re


def extract_json(text: str) -> dict:
    """
    Extrai JSON válido de uma resposta bruta de LLM.

    Lida com os três formatos mais comuns que modelos locais retornam:

      1. Tags <think>...</think> do Qwen3 (modo de raciocínio interno)
         → Removidas antes de tudo.

      2. JSON dentro de bloco markdown:
         ```json
         { "key": "value" }
         ```
         → Extraído o conteúdo interno.

      3. JSON puro sem formatação extra
         → Parseado diretamente.

    Args:
        text: Texto bruto da resposta do LLM.

    Returns:
        Dicionário Python parseado do JSON encontrado.

    Raises:
        ValueError: Se não for possível extrair JSON válido.
    """
    # Passo 1: remove blocos de raciocínio <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Passo 2: tenta extrair conteúdo de bloco ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    # Passo 3: tenta parsear diretamente
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Passo 4: último recurso — encontra o primeiro { e o último }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Não foi possível extrair JSON válido da resposta.\n"
            f"Erro original: {e}\n"
            f"Texto recebido (primeiros 500 chars):\n{text[:500]}"
        )


def extract_code(text: str) -> str:
    """
    Extrai código puro de uma resposta de LLM.

    Remove tags <think> e blocos markdown (``` ... ```) se presentes,
    retornando apenas o código limpo.

    Args:
        text: Texto bruto da resposta do LLM.

    Returns:
        Código limpo, sem formatação extra.
    """
    # Remove raciocínio interno
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Se vier em bloco markdown, extrai só o código
    match = re.search(r"```(?:\w+)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()

    return text.strip()
