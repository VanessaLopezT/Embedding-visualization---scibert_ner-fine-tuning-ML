# SciBERT NER — Proyecto Integrado

Aplicación Django para extracción y visualización de entidades nombradas (NER)
en literatura científica. Soporta dos modelos:

- **tech**: SciBERT fine-tuned en literatura ML/NLP
- **cmt**: PubMedBERT fine-tuned en oncología veterinaria (Canine Mammary Tumor)

---

## Estructura del Proyecto

```
scibert_ner_project/
├── manage.py
├── requirements.txt
│
├── server/                         # Configuración Django
│   ├── settings.py                 ← CONFIGURAR RUTAS DE MODELOS AQUÍ
│   ├── urls.py
│   └── wsgi.py
│
├── articles/                       # App principal
│   └── views.py                    # Toda la lógica de API y pipeline
│
├── processing/                     # Pipeline de procesamiento (backend)
│   ├── mod_extractor.py            # Extracción PDF (smart engine selection)
│   ├── mod_sections.py             # Limpieza de secciones (refs, headers, etc.)
│   ├── mod_tables.py               # Detección y eliminación de tablas
│   ├── mod_symbols.py              # Limpieza de símbolos y encoding
│   ├── mod_chunker.py              # Chunking BERT-compatible
│   ├── prepare_article.py          # Preprocesador fallback (ArticlePreprocessor)
│   ├── process_ner.py              # NER + embeddings (SciBERTNERProcessor)
│   └── visualize_tsne_prepare.py   # Proyección t-SNE / PCA
│
├── templates/
│   └── index.html                  # Interfaz visual completa
│
├── web/                            # Estáticos (CSS + JS)
│   ├── css/
│   │   ├── style.css
│   │   └── textPanel.css
│   └── js/
│       ├── categoryColors.js
│       ├── dataLoader.js
│       ├── interactions.js
│       ├── textPanel.js
│       ├── tsneChart.js
│       └── tsneChartFrequency.js
│
└── data/
    ├── example/
    │   ├── tsne_tech.json          # Datos de ejemplo modelo tech
    │   └── tsne_cmt.json           # Datos de ejemplo modelo cmt (agregar)
    └── articles/                   # Artículos subidos (se crean automáticamente)
```

---

## Configuración

### 1. Rutas de modelos (`server/settings.py`)

```python
# Modelo ML / Technology (SciBERT)
MODEL_TECH_CHECKPOINT = r"scibert_20260304_171958\best_model"

# Modelo CMT (PubMedBERT)
MODEL_CMT_CHECKPOINT = r"biobert_20260304_200826\best_model"
```

Las rutas son relativas a `BASE_DIR` (raíz del proyecto). También puedes usar
rutas absolutas.

### 2. Datos de ejemplo CMT

Copia el archivo `tsne_data.json` generado por tu modelo CMT en:
```
data/example/tsne_cmt.json
```

---

## Instalación

```bash
# Crear entorno virtual
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar servidor
python manage.py runserver
```

Abre http://localhost:8000 en tu navegador.

---

## Flujo de procesamiento

Al subir un artículo PDF/TXT:

1. **Extracción** (`mod_extractor`): selección inteligente de motor PDF
   (pdfminer vs pdfplumber según calidad de extracción)
2. **Limpieza de secciones** (`mod_sections`): elimina referencias, cabeceras,
   pies de página, figuras y bloques de autores/afiliaciones
3. **Tablas** (`mod_tables`): detecta y elimina bloques tabulares
4. **Símbolos** (`mod_symbols`): limpia encoding, mojibake, ecuaciones LaTeX,
   caracteres decorativos
5. **Chunking** (`mod_chunker`): divide en chunks de ~506 tokens con overlap
   usando el tokenizador BERT para precisión
6. **NER** (`process_ner.SciBERTNERProcessor`): extrae entidades y embeddings
   (optimizado para RAM: flush incremental, solo penúltima capa hidden)
7. **t-SNE/PCA** (`visualize_tsne_prepare`): proyección 2D para visualización

Si el pipeline modular falla en cualquier paso, se usa `prepare_article.ArticlePreprocessor`
como fallback automático.

---

## API Endpoints

| Método | URL | Descripción |
|--------|-----|-------------|
| GET | `/` | Interfaz principal |
| GET | `/api/models` | Lista de modelos disponibles |
| GET | `/api/articles` | Lista de artículos subidos |
| POST | `/api/articles/upload` | Subir artículo (file + model) |
| GET | `/api/articles/{id}/tsne?model=tech` | Datos t-SNE del artículo |
| GET | `/api/articles/{id}/ner?model=tech` | Resultados NER |
| GET | `/api/articles/{id}/meta` | Estado y metadatos |
| GET | `/api/articles/{id}/cleaned-text` | Texto limpio del artículo |
| GET | `/api/example/tsne?model=tech` | Datos de ejemplo |
