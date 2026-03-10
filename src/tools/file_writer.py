"""
Ferramenta de escrita de arquivos no disco.

SOLID - SRP: Esta classe existe apenas para persistir conteúdo no sistema de arquivos.
             Não sabe nada sobre LLMs, grafos ou agentes.
KISS        : Interface mínima — dois métodos públicos: write e write_all.
DRY         : O loop de escrita fica em write_all para não se repetir em main.py.
"""

from pathlib import Path


class FileWriter:
    """
    Persiste os arquivos gerados pelos agentes no disco.

    Separar esta responsabilidade dos agentes é intencional:
      - Agentes geram conteúdo (lógica de LLM)
      - FileWriter persiste conteúdo (lógica de I/O)

    Isso facilita testar os agentes sem precisar de sistema de arquivos,
    e trocar o destino (ex: S3, banco de dados) sem tocar nos agentes.
    """

    def __init__(self, output_dir: str):
        """
        Args:
            output_dir: Diretório raiz onde os arquivos serão salvos.
                        Criado automaticamente se não existir.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, filename: str, content: str) -> Path:
        """
        Salva um único arquivo no disco.

        Cria subdiretórios intermediários automaticamente.
        Sobrescreve o arquivo se já existir.

        Args:
            filename: Caminho relativo ao output_dir (ex: "src/main.py").
            content : Conteúdo do arquivo como string.

        Returns:
            Path absoluto do arquivo criado.
        """
        filepath = self.output_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def write_all(self, files: list[dict]) -> list[Path]:
        """
        Salva uma lista de arquivos de uma vez.

        DRY: centraliza o loop, evitando que main.py itere diretamente.

        Args:
            files: Lista de dicts com as chaves "filename" e "content".

        Returns:
            Lista de Paths dos arquivos criados, na mesma ordem da entrada.
        """
        return [self.write(f["filename"], f["content"]) for f in files]
