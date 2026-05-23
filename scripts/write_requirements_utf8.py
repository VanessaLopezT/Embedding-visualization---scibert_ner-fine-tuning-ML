"""Write requirements*.txt as UTF-8 (avoid UTF-16 from editors on Windows)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQ = """# SciBERT NER - Python 3.11, CPU (Django + NER + PDF).
# Install in Docker: pip install -r requirements-prod.txt

# --- Web (Django 5.2 LTS; Python 3.10-3.13) ---
Django==5.2.11
asgiref==3.8.1
sqlparse==0.5.3
gunicorn==23.0.0
whitenoise==6.8.2

# --- PyTorch ecosystem (torch via requirements-prod.txt) ---
sympy==1.13.1
mpmath==1.3.0
networkx==3.4.2
jinja2==3.1.6
MarkupSafe==3.0.2
filelock==3.16.1
fsspec==2024.10.0
typing-extensions==4.12.2
packaging==24.2

# --- Hugging Face / NER ---
transformers==4.48.3
tokenizers==0.21.0
huggingface-hub==0.27.1
safetensors==0.5.2
regex==2024.11.6
tqdm==4.67.1
requests==2.32.3
certifi==2024.8.30
urllib3==2.2.3
idna==3.10
charset-normalizer==3.4.0
PyYAML==6.0.2

# --- Scientific (t-SNE, PCA, sklearn) ---
numpy==2.1.3
scipy==1.14.1
scikit-learn==1.5.2
joblib==1.4.2
threadpoolctl==3.5.0

# --- PDF extraction (pdfplumber pins pdfminer.six + pypdfium2) ---
pdfplumber==0.11.9
pypdf==5.1.0
PyPDF2==3.0.1
pillow==11.0.0
"""

PROD = """# Production Docker: PyTorch CPU wheels + application deps.
--extra-index-url https://download.pytorch.org/whl/cpu

torch==2.5.1

-r requirements.txt
"""


def main() -> None:
    (ROOT / "requirements.txt").write_bytes(REQ.encode("utf-8"))
    (ROOT / "requirements-prod.txt").write_bytes(PROD.encode("utf-8"))
    for name in ("requirements.txt", "requirements-prod.txt"):
        raw = (ROOT / name).read_bytes()
        raw.decode("utf-8")
        if b"\x00" in raw:
            raise SystemExit(f"{name}: UTF-16 detected")
        print(f"Wrote {name} ({len(raw)} bytes, UTF-8)")


if __name__ == "__main__":
    main()
