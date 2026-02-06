"""
prepare_article.py
Archivo auxiliar para procesar artículos académicos en inglés.
- Lee artículos en texto plano (.txt) o PDF (.pdf)
- Extrae texto de PDFs automáticamente
- Limpia referencias, citas, figuras, tablas y contenido sin valor
- Extrae párrafos coherentes
- Genera un archivo compatible con process_ner.py
- NO modifica ni ejecuta process_ner.py
"""

import re
import argparse
from pathlib import Path


class ArticlePreprocessor:
    """Preprocesa artículos académicos para uso con SciBERT NER."""

    def __init__(self):
        self.text = ""

    def load_article(self, file_path):
        """Carga un artículo desde archivo .txt o .pdf"""
        try:
            file_path = Path(file_path)
            
            if file_path.suffix.lower() == ".pdf":
                return self._load_pdf(file_path)
            elif file_path.suffix.lower() == ".txt":
                return self._load_txt(file_path)
            else:
                print(f"Error: Formato no soportado. Use .txt o .pdf")
                return False
                
        except Exception as e:
            print(f"Error al cargar archivo: {e}")
            return False

    def _load_txt(self, file_path):
        """Carga un archivo de texto plano"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.text = f.read()
            print(f"Artículo TXT cargado: {file_path}")
            return True
        except FileNotFoundError:
            print(f"Error: No se encontró el archivo {file_path}")
            return False

    def _load_pdf(self, file_path):
        """Carga un archivo PDF y extrae el texto"""
        try:
            try:
                import pdfplumber
            except ImportError:
                print("Error: pdfplumber no está instalado")
                print("Instala con: pip install pdfplumber")
                return False
            
            with pdfplumber.open(file_path) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                
                self.text = "\n".join(text_parts)
            
            print(f"Artículo PDF cargado: {file_path} ({len(pdf.pages)} páginas)")
            return True
            
        except Exception as e:
            print(f"Error al cargar PDF: {e}")
            return False

    def remove_references(self):
        """Elimina la sección de referencias"""
        patterns = [
            r"(?:References|Bibliography|Works Cited)[\s\S]*?$",
            r"\[[\d\s,]+\]",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "", self.text, flags=re.IGNORECASE)

    def remove_citations(self):
        """Elimina citas de estilo (Author, Year) y números entre corchetes"""
        patterns = [
            r"\([A-Z][a-z]+\s*(?:et\s+al\.?)?,?\s*\d{4}\)",  # (Author, 2020)
            r"\([A-Z][a-z]+\s+\d{4}\)",  # (Author 2020)
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "", self.text)

    def remove_figures_tables(self):
        """Elimina referencias a figuras, tablas y ecuaciones"""
        patterns = [
            r"(?:Fig(?:ure)?|Table|Eq\.?|Equation)\s*\.?\s*\d+[\s\S]*?(?:\.|$)",
            r"(?:See|shown in|as shown in)\s+(?:Fig|Figure|Table)\s*\.?\s*\d+",
            r"Figure \d+.*?\n",
            r"Table \d+.*?\n",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "", self.text, flags=re.IGNORECASE)

    def remove_special_sections(self):
        """Elimina secciones sin valor: Abstract, Acknowledgments, Appendix, etc."""
        patterns = [
            r"(?:Abstract|Acknowledgments?|Funding|Conflicts? of Interest|Author Contributions|Data Availability)[\s\S]*?(?=\n(?:[A-Z][a-z]+|[A-Z]{2,})|$)",
            r"(?:^|\n)Appendix[\s\S]*?(?=\n(?:[A-Z][a-z]+|$)|$)",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "", self.text, flags=re.IGNORECASE | re.MULTILINE)

    def remove_urls(self):
        """Elimina URLs"""
        self.text = re.sub(r"https?://[^\s]+", "", self.text)
        self.text = re.sub(r"www\.[^\s]+", "", self.text)

    def remove_extra_whitespace(self):
        """Limpia espacios en blanco excesivos"""
        self.text = re.sub(r"\n{3,}", "\n\n", self.text)  # Máximo 2 saltos de línea
        self.text = re.sub(r"[ \t]{2,}", " ", self.text)  # Múltiples espacios a uno
        self.text = re.sub(r"(?:^|\n)\s+", "\n", self.text)  # Espacios al inicio de línea

    def extract_paragraphs(self, min_length=50):
        """
        Extrae párrafos coherentes filtrando líneas muy cortas.
        min_length: longitud mínima en caracteres para considerar un párrafo válido
        """
        paragraphs = self.text.split("\n\n")
        cleaned = []

        for para in paragraphs:
            para = para.strip()
            if len(para) > min_length and not para.isdigit():
                # Verificar que no sea solo números o caracteres especiales
                if any(c.isalpha() for c in para):
                    cleaned.append(para)

        return cleaned

    def clean(self):
        """Aplica todas las limpiezas en orden lógico"""
        print("Limpiando artículo...")
        self.remove_references()
        self.remove_special_sections()
        self.remove_figures_tables()
        self.remove_citations()
        self.remove_urls()
        self.remove_extra_whitespace()
        print("Artículo limpiado")

    def get_paragraphs(self):
        """Retorna lista de párrafos procesados"""
        return self.extract_paragraphs()

    def save_processed(self, output_file="article_processed.txt"):
        """Guarda el texto procesado en archivo"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(self.text)
        print(f"Artículo procesado guardado en: {output_file}")

    def generate_for_process_ner(self, output_file="article_for_ner.txt"):
        """
        Genera archivo listo para pasar directamente a process_ner.py
        Guarda los párrafos uno por línea para fácil lectura
        """
        paragraphs = self.get_paragraphs()
        with open(output_file, "w", encoding="utf-8") as f:
            for para in paragraphs:
                f.write(para + "\n\n")
        print(f"Archivo generado para NER: {output_file}")
        print(f"Total de párrafos extraídos: {len(paragraphs)}")
        return paragraphs


def main():
    parser = argparse.ArgumentParser(
        description="Preprocesa artículos académicos en inglés (.txt o .pdf) para SciBERT NER"
    )
    parser.add_argument(
        "article",
        help="Ruta del archivo de artículo (.txt o .pdf)"
    )
    parser.add_argument(
        "--output",
        default="article_for_ner.txt",
        help="Archivo de salida (default: article_for_ner.txt)"
    )
    parser.add_argument(
        "--save-processed",
        action="store_true",
        help="Guardar también el texto procesado limpio"
    )

    args = parser.parse_args()

    preprocessor = ArticlePreprocessor()

    # Cargar artículo (detecta automáticamente si es PDF o TXT)
    if not preprocessor.load_article(args.article):
        return

    # Limpiar
    preprocessor.clean()

    # Guardar versión limpia si se pide
    if args.save_processed:
        preprocessor.save_processed("article_cleaned.txt")

    # Generar archivo para process_ner.py
    paragraphs = preprocessor.generate_for_process_ner(args.output)

    print("\n--- Resumen ---")
    print(f"Párrafos extraídos: {len(paragraphs)}")
    if paragraphs:
        print(f"\nPrimer párrafo ({len(paragraphs[0])} caracteres):")
        print(f"  {paragraphs[0][:100]}...")


if __name__ == "__main__":
    main()
