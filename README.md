# SciBERT NER — Sistema de extracción y visualización de entidades nombradas

Aplicación web full-stack para **Named Entity Recognition (NER)** sobre literatura científica en PDF/TXT, con visualización interactiva de embeddings (t-SNE/PCA) y grafos de relaciones entre entidades. Soporta dos modelos fine-tuned desplegables en paralelo y operación **CPU-only** en contenedor Docker reproducible.

| Aspecto | Detalle |
|---------|---------|
| **Backend** | Django 5.2 LTS + Gunicorn + WhiteNoise |
| **ML** | PyTorch 2.5.1+cpu, Hugging Face Transformers 4.48.3 |
| **Frontend** | HTML/CSS/JS modular + [ECharts](https://echarts.apache.org/) |
| **Persistencia** | Sistema de archivos (`data/`) + SQLite mínimo |
| **Despliegue** | Docker Compose, puerto **9000** |
| **Python** | **3.11** (local y contenedor) |

> **Los modelos NLP no están en git.** Los checkpoints `TechBERT/` y `PatVetBERT/` debes obtenerlos y colocarlos manualmente en la raíz del proyecto. Están en `.gitignore` y `.dockerignore`; Docker los monta como volúmenes. Sin ellos la app arranca, pero no puede ejecutar NER.

---

## Tabla de contenidos

1. [Descripción general del proyecto](#1-descripción-general-del-proyecto)
2. [Arquitectura general](#2-arquitectura-general)
3. [Estructura completa del proyecto](#3-estructura-completa-del-proyecto)
4. [Dockerización](#4-dockerización)
5. [Modelos NLP](#5-modelos-nlp)
6. [Dependencias y compatibilidad](#6-dependencias-y-compatibilidad)
7. [Variables de entorno](#7-variables-de-entorno)
8. [Cómo ejecutar el proyecto](#8-cómo-ejecutar-el-proyecto)
9. [Verificaciones importantes](#9-verificaciones-importantes)
10. [Troubleshooting](#10-troubleshooting)
11. [Consideraciones de despliegue](#11-consideraciones-de-despliegue)
12. [License / Licencia](#12-license--licencia)

---

## 1. Descripción general del proyecto

### Qué hace el sistema

SciBERT NER permite a un investigador o analista:

1. **Subir** artículos científicos (PDF o TXT).
2. **Extraer y limpiar** el texto (referencias, tablas, símbolos, encoding defectuoso).
3. **Ejecutar NER** con un modelo BERT fine-tuned según el dominio.
4. **Generar embeddings** por entidad detectada.
5. **Proyectar** entidades en 2D (t-SNE/PCA) y explorar **relaciones** co-ocurrencia.
6. **Agrupar artículos** en *workspaces* para análisis agregado.

La interfaz (`templates/index.html` + `web/js/app.js`) consume una API REST JSON y renderiza gráficas ECharts sin recargar la página.

### Objetivo

Unificar en una sola aplicación:

- Pipeline de preprocesamiento documental (PDF → texto limpio → chunks BERT).
- Inferencia NER con checkpoints externos (no embebidos en git).
- Visualización analítica de resultados por artículo y por workspace.

### Problema que resuelve

Los flujos manuales de NER sobre papers implican scripts dispersos, modelos pesados mal versionados y ausencia de UI unificada. Este proyecto integra extracción PDF, inferencia, proyección dimensional y exploración visual en un servicio web mantenible.

### Tecnologías utilizadas

| Capa | Tecnología | Rol |
|------|------------|-----|
| Servidor HTTP | Gunicorn 23 | WSGI en producción |
| Framework | Django 5.2.11 | Routing, templates, settings |
| Estáticos prod | WhiteNoise 6.8 | `collectstatic` comprimido |
| Deep Learning | PyTorch 2.5.1 **CPU** | Tensor ops sin CUDA |
| NLP | Transformers 4.48.3 | `AutoModelForTokenClassification`, pipeline NER |
| PDF | pdfplumber, pdfminer.six, pypdf | Extracción multi-motor |
| ML clásico | scikit-learn, numpy, scipy | t-SNE, PCA, StandardScaler |
| Contenedor | Docker + Compose | Reproducibilidad multiplataforma |
| Visualización | ECharts 5.x (CDN) | Scatter, grafos, tooltips |

### Pipeline NLP (visión general)

```
PDF/TXT  →  mod_extractor  →  mod_sections  →  mod_tables  →  mod_symbols
                ↓ (fallback: prepare_article.py)
           mod_chunker (~506 tokens, overlap BERT)
                ↓
           SciBERTNERProcessor (process_ner.py)
                ↓
           ner_{model}.json + embeddings + tsne_{model}.json
                ↓
           API Django  →  ECharts (frontend)
```

**Pasos detallados al subir un artículo:**

| # | Módulo | Función |
|---|--------|---------|
| 1 | `mod_extractor.py` | Extrae texto PDF; elige motor (pdfminer vs pdfplumber) según calidad |
| 2 | `mod_sections.py` | Elimina referencias, headers, autores, figuras |
| 3 | `mod_tables.py` | Detecta y elimina bloques tabulares |
| 4 | `mod_symbols.py` | Corrige mojibake, LaTeX, caracteres decorativos |
| 5 | `mod_chunker.py` | Segmenta en chunks compatibles con tokenizador BERT |
| 6 | `process_ner.py` | NER + embeddings (penúltima hidden layer, flush incremental a disco) |
| 7 | `visualize_tsne_prepare.py` / runtime | Proyección 2D para visualización |

Si el pipeline modular falla, `prepare_article.ArticlePreprocessor` actúa como **fallback automático** (`articles/processing_runtime.py::_extract_and_clean`).

### Modelos soportados

Definidos en `articles/model_registry.py`:

| Clave API | Nombre | Checkpoint por defecto | Dominio |
|-----------|--------|------------------------|---------|
| `tech` | **TechBERT** | `TechBERT/best_model` | SciBERT fine-tuned — literatura ML/NLP |
| `cmt` | **PatVetBERT** | `PatVetBERT/best_model` | BioBERT/biomedical NER — oncología veterinaria (CMT) |

> **Importante:** estas carpetas de checkpoint **no se incluyen en el repositorio**. Debes disponer de los pesos fine-tuned por tu cuenta (transferencia local, almacenamiento institucional, etc.) antes de procesar artículos.

También existe soporte para modelo **combinado** (`combined_results.py`) que fusiona resultados de ambos checkpoints cuando el usuario selecciona ambos modelos en la UI.

---

## 2. Arquitectura general

### Diagrama de componentes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Navegador (ECharts UI)                          │
│              templates/index.html  +  web/js/app.js                     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP (puerto 9000 prod / 8000 dev)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gunicorn  →  Django WSGI (server/wsgi.py)                              │
│    ├── WhiteNoise (estáticos comprimidos en prod)                       │
│    ├── articles/views.py (API REST + render index)                      │
│    └── articles/processing_runtime.py (colas + workers por modelo)      │
└───────────────┬─────────────────────────────┬───────────────────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────────┐   ┌─────────────────────────────────────────┐
│  data/  (volúmenes)       │   │  processing/  (pipeline NLP)            │
│  articles/{id}/meta.json  │   │  mod_*.py, process_ner.py               │
│  ner_*.json, tsne_*.json  │   │  SciBERTNERProcessor + Transformers     │
│  workspaces/              │   └─────────────────────────────────────────┘
└───────────────────────────┘
                ▲
                │ bind mount :ro
┌───────────────────────────┐
│  TechBERT/best_model/     │
│  PatVetBERT/best_model/   │  ← NO en git ni en la imagen Docker
└───────────────────────────┘
```

### Flujo del contenedor (startup)

```
docker compose up
       │
       ▼
ENTRYPOINT /app/docker/entrypoint.sh
       │
       ├─ Verifica rutas MODEL_*_CHECKPOINT montadas
       ├─ mkdir data/articles, data/example, data/workspaces
       ├─ python manage.py migrate --noinput
       └─ exec gunicorn server.wsgi:application --bind 0.0.0.0:9000
                │
                ▼
       Django ArticlesConfig.ready()
                │
                └─ preload_registered_models()  [salvo DJANGO_SKIP_MODEL_PRELOAD=1]
                       ├─ Carga TechBERT en worker "tech"
                       └─ Carga PatVetBERT en worker "cmt"
```

### Carga de modelos y workers

- Cada modelo tiene un **`ModelWorker`** (hilo daemon) con cola FIFO propia.
- Los modelos se **precargan al arrancar** Gunicorn (`articles/apps.py` → `preload_registered_models`).
- Tras **600 s** sin trabajos (`PROCESSING_WORKER_IDLE_SECONDS`), el worker descarga el modelo de RAM para liberar memoria.
- Durante el **build** Docker, la precarga se omite con `DJANGO_SKIP_MODEL_PRELOAD=1` (solo `collectstatic`).

### Procesamiento PDF

`mod_extractor.py` compara calidad de extracción (ratio de “palabras pegadas”) entre motores disponibles y selecciona el mejor. Orden típico: **pdfminer.six** ↔ **pdfplumber** ↔ **pypdf** (fallback).

### Inferencia NER

`SciBERTNERProcessor` (`processing/process_ner.py`):

- Carga `AutoTokenizer` + `AutoModelForTokenClassification` desde checkpoint local.
- Usa `device = "cuda" if torch.cuda.is_available() else "cpu"` — en Docker **siempre CPU**.
- Pipeline Hugging Face con `aggregation_strategy="simple"`.
- Optimizaciones RAM: flush incremental de embeddings, solo penúltima capa hidden, `gc.collect()`.

### Backend Django — diseño

- **Sin modelos ORM complejos**: persistencia principal en JSON bajo `data/`.
- SQLite (`db.sqlite3`) para requisitos mínimos de Django; `migrate` en entrypoint es idempotente.
- Settings divididos: `server/settings/{base,development,production}.py`.
- `server/settings.py` reexporta **development** (compatibilidad con `manage.py` local).

---

## 3. Estructura completa del proyecto

```
scibert_ner/
├── manage.py                    # CLI Django (settings → server.settings → development)
├── app.py                       # Prototipo Flask legacy (no usado en Docker)
├── db.sqlite3                   # SQLite (crear antes de Docker; ver §8)
├── requirements.txt             # Dependencias app (sin torch)
├── requirements-prod.txt        # torch CPU + requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example                 # Plantilla de variables
├── .dockerignore
├── .gitattributes               # LF en scripts y requirements
│
├── docker/
│   └── entrypoint.sh            # Init: migrate + gunicorn
│
├── scripts/                     # Utilidades de mantenimiento (ver README)
│
├── server/                      # Proyecto Django
│   ├── settings/
│   │   ├── base.py              # Paths, DATA_DIR, modelos, apps
│   │   ├── development.py       # DEBUG=True, ALLOWED_HOSTS=*
│   │   └── production.py        # SECRET_KEY obligatorio, WhiteNoise
│   ├── settings.py              # Alias → development
│   ├── urls.py                  # Rutas API + static en DEBUG
│   └── wsgi.py                  # Punto de entrada Gunicorn
│
├── articles/                    # App principal Django
│   ├── apps.py                  # Precarga modelos en ready()
│   ├── model_registry.py        # Definición tech / cmt
│   ├── views.py                 # API REST + vista index
│   ├── processing_runtime.py    # Colas, workers, pipeline upload
│   ├── storage.py               # Metadatos artículos
│   ├── combined_results.py      # Fusión multi-modelo, t-SNE combinado
│   ├── article_projection.py    # Proyecciones por artículo
│   ├── article_relations.py     # Grafo relaciones artículo
│   ├── workspace_*.py           # CRUD workspaces, agregados, relaciones
│   └── services.py              # Utilidades subprocess (legacy)
│
├── processing/                  # Pipeline NLP (importado vía sys.path)
│   ├── mod_extractor.py         # PDF multi-motor
│   ├── mod_sections.py          # Limpieza secciones
│   ├── mod_tables.py            # Tablas
│   ├── mod_symbols.py           # Símbolos / encoding
│   ├── mod_chunker.py           # Chunking BERT
│   ├── prepare_article.py       # Fallback preprocesador
│   ├── process_ner.py           # SciBERTNERProcessor
│   └── visualize_tsne_prepare.py # t-SNE/PCA offline
│
├── templates/
│   └── index.html               # Shell HTML (~314 líneas)
│
├── web/                         # Estáticos (STATICFILES_DIRS)
│   ├── css/                     # app.css, responsive.css, …
│   ├── js/
│   │   ├── app.js               # Orquestación principal
│   │   ├── api/                 # dataLoader, workspaceApi
│   │   ├── charts/              # tsneChart, relations, workspace
│   │   ├── ui/                  # chartResize, panelResizer, textPanel
│   │   └── utils/               # colores, caché, ejes
│   ├── legacy/                  # Prototipo anterior (excluido de Docker)
│   └── VERIFICATION_CHECKLIST.md
│
├── data/                        # Datos runtime (volumen Docker)
│   ├── articles/{uuid}/         # Por artículo subido
│   │   ├── meta.json
│   │   ├── progress.json
│   │   ├── cleaned_text.txt
│   │   ├── ner_{tech|cmt}.json
│   │   └── tsne_{tech|cmt}.json
│   ├── example/                 # tsne_tech.json, tsne_cmt.json
│   └── workspaces/              # Metadatos workspaces
│
├── TechBERT/best_model/         # Checkpoint SciBERT (NO en git; volumen :ro)
└── PatVetBERT/best_model/       # Checkpoint PatVetBERT (NO en git; volumen :ro)
```

### Notas por carpeta

| Ruta | Propósito |
|------|-----------|
| `docker/` | Scripts de arranque del contenedor |
| `scripts/` | Mantenimiento (encoding, LF, refactor web) |
| `articles/` | Lógica de negocio Django: API, colas, workspaces |
| `processing/` | Pipeline NLP puro (sin dependencia Django directa) |
| `web/` | Assets estáticos; en prod se copian a `staticfiles/` vía `collectstatic` |
| `templates/` | Plantillas Django (solo `index.html` en producción) |
| `data/` | **No versionar** artículos procesados; montar como volumen |
| `TechBERT/`, `PatVetBERT/` | **No están en git.** Checkpoints Hugging Face que debes añadir localmente (`config.json`, tokenizer, `.safetensors` / `.bin`) |

> **No existe carpeta `media/`**: los uploads se guardan en `data/articles/`.

### Qué no incluye el repositorio

| Elemento | Motivo |
|----------|--------|
| `TechBERT/`, `PatVetBERT/` | Checkpoints de cientos de MB–GB; excluidos por `.gitignore` |
| `data/articles/` | Artefactos generados al subir PDFs |
| `.env` | Secretos y configuración local |
| `venv/`, `staticfiles/` | Entorno y build |

Tras clonar, **debes** crear o copiar `TechBERT/best_model/` y `PatVetBERT/best_model/` en el host antes de usar NER.

---

## 4. Dockerización

### Por qué Docker

- Aislar **Python 3.11**, PyTorch CPU y dependencias científicas sin contaminar el host.
- Excluir checkpoints (~GB) de la imagen: se montan como volúmenes.
- Reproducir el mismo entorno en Windows (Docker Desktop) y Linux (servidor).

### Imagen base: `python:3.11-slim-bookworm`

| Decisión | Razón |
|----------|-------|
| Python **3.11** | Compatible con Django 5.2, torch 2.5.1, numpy 2.x |
| **slim-bookworm** | Debian 12 estable; imagen ~150 MB vs ~1 GB full |
| **No** `python:3.12` | Evita incompatibilidades con pins actuales |
| **No** `build-essential` | Wheels precompilados de numpy/scipy/torch; solo `libgomp1` (OpenMP) |

### Dockerfile — etapas

```dockerfile
FROM python:3.11-slim-bookworm
WORKDIR /app

# 1. libgomp1 para numpy/scipy/torch CPU
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ...

# 2. Instalar deps (torch CPU primero vía requirements-prod.txt)
COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements-prod.txt \
    && python -c "import torch; assert not torch.cuda.is_available()" \
    && (pip list | grep -qi nvidia && exit 1 || true)

# 3. Código aplicación
COPY . .

# 4. Entrypoint: LF + ejecutable
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh && chmod +x ...

# 5. Estáticos (sin precargar modelos)
RUN DJANGO_SKIP_MODEL_PRELOAD=1 python manage.py collectstatic --noinput

ENTRYPOINT ["/app/docker/entrypoint.sh"]
EXPOSE 9000
```

### Entrypoint (`docker/entrypoint.sh`)

| Paso | Acción |
|------|--------|
| 1 | Lee `APP_PORT`, `GUNICORN_WORKERS`, `GUNICORN_TIMEOUT` |
| 2 | Comprueba existencia de checkpoints montados (warning si faltan) |
| 3 | Crea subdirectorios bajo `DATA_DIR` |
| 4 | `python manage.py migrate --noinput` |
| 5 | `exec gunicorn server.wsgi:application --bind 0.0.0.0:${APP_PORT}` |

Logs de Gunicorn van a **stdout/stderr** (`--access-logfile - --error-logfile -`), visibles con `docker compose logs`.

### docker-compose.yml

| Aspecto | Configuración |
|---------|---------------|
| Servicio | `web` → imagen `scibert_ner-web` |
| Puerto | `${APP_PORT:-9000}:9000` |
| Settings | `server.settings.production` |
| Entrypoint | `/app/docker/entrypoint.sh` |
| Restart | `unless-stopped` |
| Límite RAM | 8 GB (ajustable en `deploy.resources`) |

**Volúmenes:**

| Host | Contenedor | Modo |
|------|------------|------|
| `./data` | `/app/data` | rw — artículos, workspaces, ejemplos |
| `./TechBERT` | `/app/TechBERT` | **ro** — checkpoint SciBERT |
| `./PatVetBERT` | `/app/PatVetBERT` | **ro** — checkpoint PatVetBERT |
| `./db.sqlite3` | `/app/db.sqlite3` | rw — SQLite |

### `.dockerignore`

Excluye de la imagen: `venv/`, `.env`, `data/`, checkpoints (`TechBERT/`, `PatVetBERT/`, `*.safetensors`), `staticfiles/`.

### Compatibilidad Windows / Linux

| Tema | Windows | Linux |
|------|---------|-------|
| Docker | Docker Desktop + WSL2 recomendado | Docker Engine nativo |
| `db.sqlite3` | `type nul > db.sqlite3` antes del primer `up` | `touch db.sqlite3` |
| Modelos NLP | Colocar `TechBERT/` y `PatVetBERT/` manualmente (no vienen con `git clone`) | Igual |

---

## 5. Modelos NLP

### No incluidos en git

Los checkpoints **TechBERT** y **PatVetBERT** son artefactos externos al repositorio:

- Listados en `.gitignore` (no se suben a GitHub).
- Excluidos de la imagen Docker (`.dockerignore`).
- Montados en runtime desde el host vía `docker-compose.yml`.

```
scibert_ner/
├── TechBERT/best_model/      ← obtener y colocar manualmente
└── PatVetBERT/best_model/    ← obtener y colocar manualmente
```

Estructura esperada (formato Hugging Face):

```
best_model/
├── config.json
├── tokenizer.json  (o vocab.txt)
└── model.safetensors  (o pytorch_model.bin)
```

Rutas configurables con `MODEL_TECH_CHECKPOINT` y `MODEL_CMT_CHECKPOINT` en `.env`.

### Ubicación y acceso

Docker Compose monta `./TechBERT` y `./PatVetBERT` como volúmenes **read-only** en `/app/TechBERT` y `/app/PatVetBERT`. El entrypoint emite **AVISO** si no encuentra las rutas, pero no aborta (permite arrancar para diagnóstico).

### Carga en runtime

1. **Precarga (startup):** `ArticlesConfig.ready()` → `preload_registered_models()` carga ambos modelos en workers dedicados.
2. **Inferencia (upload):** `views.upload_article` → `submit_article_job` → worker del modelo procesa en background.
3. **Reutilización:** si existe `cleaned_text.txt`, se salta extracción PDF (`_load_cached_cleaned_inputs`).
4. **Descarga:** tras inactividad (`PROCESSING_WORKER_IDLE_SECONDS=600`), el worker libera el modelo de RAM.

### Implicaciones de memoria RAM

| Escenario | RAM estimada |
|-----------|--------------|
| 1 modelo BERT base cargado | ~500 MB – 1.5 GB |
| 2 modelos precargados (tech + cmt) | ~1 – 3 GB |
| Procesamiento activo + embeddings | Picos adicionales según longitud del paper |
| Límite Compose | **8 GB** (configurable) |

**Recomendación producción:** `GUNICORN_WORKERS=1` (default). Múltiples workers duplicarían modelos en RAM.

### CPU-only

| Aspecto | Detalle |
|---------|---------|
| Wheel | `torch==2.5.1` desde índice CPU de PyTorch |
| Runtime | Inferencia en CPU (`device="cpu"`) |

```bash
docker compose exec web python -c \
  "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

### Stack Hugging Face

| Paquete | Versión | Notas |
|---------|---------|-------|
| `transformers` | 4.48.3 | `AutoModelForTokenClassification`, pipeline NER |
| `tokenizers` | 0.21.0 | Alineado con transformers 4.48.x |
| `huggingface-hub` | 0.27.1 | Descarga/config local de checkpoints |
| `safetensors` | 0.5.2 | Carga pesos `.safetensors` |
| `torch` | 2.5.1+cpu | Backend tensor CPU |

---

## 6. Dependencias y compatibilidad

### Archivos de requirements

| Archivo | Contenido |
|---------|-----------|
| `requirements.txt` | Django, transformers, sklearn, PDF, utilidades torch (sin torch) |
| `requirements-prod.txt` | `--extra-index-url` PyTorch CPU + `torch==2.5.1` + `-r requirements.txt` |

**Instalación local (CPU):**

```bash
pip install -r requirements-prod.txt
```

### Pinning principal

| Paquete | Versión | Python 3.11 |
|---------|---------|-------------|
| Django | 5.2.11 LTS | ✅ |
| torch | 2.5.1+cpu | ✅ |
| sympy | 1.13.1 | ✅ (requerido por torch 2.5.1) |
| transformers | 4.48.3 | ✅ |
| numpy | 2.1.3 | ✅ |
| scipy | 1.14.1 | ✅ |
| scikit-learn | 1.5.2 | ✅ |
| pdfplumber | 0.11.9 | ✅ |

Instalar siempre con `pip install -r requirements-prod.txt` (incluye PyTorch CPU).

---

## 7. Variables de entorno

Copiar plantilla: `cp .env.example .env`

### Producción (Docker)

| Variable | Obligatoria | Default | Descripción |
|----------|-------------|---------|-------------|
| `DJANGO_SECRET_KEY` | **Sí** | — | Clave secreta Django; distinta de dev |
| `DJANGO_DEBUG` | No | `False` | **Debe ser False** en producción |
| `DJANGO_ALLOWED_HOSTS` | **Sí** | `localhost,127.0.0.1` | Hosts permitidos (comma-separated) |
| `DJANGO_SECURE_SSL` | No | `False` | Cookies secure + redirect HTTPS |
| `DJANGO_SETTINGS_MODULE` | No | `server.settings.production` | Fijado en Compose |
| `APP_PORT` | No | `9000` | Puerto interno Gunicorn |
| `GUNICORN_WORKERS` | No | `1` | Workers WSGI (**mantener 1** con NER) |
| `GUNICORN_TIMEOUT` | No | `600` | Timeout request (papers largos) |
| `DATA_DIR` | No | `/app/data` | Raíz datos en contenedor |
| `MODEL_TECH_CHECKPOINT` | No | `TechBERT/best_model` | Ruta checkpoint SciBERT |
| `MODEL_CMT_CHECKPOINT` | No | `PatVetBERT/best_model` | Ruta checkpoint PatVetBERT |
| `PROCESSING_MAX_ACTIVE_JOBS` | No | `1` | Jobs simultáneos globales |
| `PROCESSING_WORKER_IDLE_SECONDS` | No | `600` | Segundos antes de descargar modelo |
| `DJANGO_SKIP_MODEL_PRELOAD` | No | — | `1` = no precargar (solo build/tests) |

### Desarrollo local

| Aspecto | Valor |
|---------|-------|
| Settings | `server.settings` → `development.py` |
| `DEBUG` | `True` (hardcoded) |
| `SECRET_KEY` | `dev-secret-key-change-in-production` |
| `ALLOWED_HOSTS` | `["*"]` |
| Estáticos | Servidos por Django desde `web/` |
| Puerto | `8000` (`runserver`) |

---

## 8. Cómo ejecutar el proyecto

### 8.1 Requisitos previos

- **Docker:** Docker Desktop (Windows/macOS) o Docker Engine 24+ (Linux)
- **Git**
- **Checkpoints NLP** (obligatorio): carpetas `TechBERT/best_model/` y `PatVetBERT/best_model/` en la raíz del proyecto — **no vienen con el clone**
- (Opcional) Datos de ejemplo: `data/example/tsne_tech.json`, `tsne_cmt.json`

### 8.2 Clonar e inicializar

```bash
git clone <url-repositorio> scibert_ner
cd scibert_ner

# Colocar los modelos fine-tuned (no están en el repo)
# TechBERT/best_model/
# PatVetBERT/best_model/

cp .env.example .env
# Editar .env: DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS

# Crear SQLite vacío (IMPORTANTE en Windows)
type nul > db.sqlite3        # Windows CMD
# touch db.sqlite3           # Linux/macOS
```

### 8.3 Docker — build y arranque

```bash
# Build limpio (recomendado tras cambios en requirements o entrypoint)
docker compose build --no-cache

# Arrancar en background
docker compose up -d

# Seguir logs
docker compose logs -f web
```

Abrir: **http://localhost:9000/**

### 8.4 Docker — operaciones habituales

```bash
# Detener contenedores
docker compose down

# Detener y eliminar volúmenes anónimos
docker compose down -v

# Rebuild + restart
docker compose up --build -d

# Shell interactivo dentro del contenedor
docker compose exec web bash

# Inspeccionar entrypoint
docker compose run --rm --entrypoint "/bin/sh" web -c "ls -l /app/docker"
```

### 8.5 Desarrollo local (sin Docker)

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements-prod.txt

python manage.py runserver
# http://localhost:8000/
```

> En local, los modelos se leen desde `TechBERT/` y `PatVetBERT/` relativos a la raíz del proyecto (`server/settings/base.py`).

---

## 9. Verificaciones importantes

### Contenedor en ejecución

```bash
docker compose ps
# STATE debe ser "running"
```

### Gunicorn levantado

```bash
docker compose logs web 2>&1 | tail -20
# Buscar: "Booting worker" / "Listening at: http://0.0.0.0:9000"
```

### Modelos precargados

```bash
docker compose logs web 2>&1 | grep "\[INIT\]"
# Esperado:
# [INIT] Precargando modelo 'tech'...
# [INIT] Modelo 'tech' listo.
# [INIT] Precargando modelo 'cmt'...
# [INIT] Modelo 'cmt' listo.
```

### Torch en CPU

```bash
docker compose exec web python -c \
  "import torch; assert not torch.cuda.is_available(); print('OK', torch.__version__)"
```

### Sin paquetes NVIDIA

```bash
docker compose exec web pip list | grep -i nvidia
# (sin salida = correcto)
```

### Endpoint HTTP

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/
curl -s http://localhost:9000/api/models | python -m json.tool
```

---

## 10. Troubleshooting

| Problema | Causa probable | Qué hacer |
|----------|----------------|-----------|
| `[entrypoint] AVISO: MODEL_* no encontrado` | Faltan `TechBERT/` o `PatVetBERT/` en el host | Copiar checkpoints; verificar rutas en `.env` |
| Error SQLite al migrar | `db.sqlite3` no existe (Docker crea carpeta en Windows) | `type nul > db.sqlite3` antes de `docker compose up` |
| Contenedor sale con OOM (137) | RAM insuficiente con 2 modelos cargados | Subir límite en `docker-compose.yml`; `GUNICORN_WORKERS=1` |
| `ner_*.json` vacío | PDF ilegible o checkpoint incompleto | Revisar logs; probar TXT; verificar `config.json` del modelo |
| Cambios no se reflejan tras editar deps | Caché Docker | `docker compose build --no-cache` |

---

## 11. Consideraciones de despliegue

### Producción

- `DJANGO_DEBUG=False` (obligatorio vía `.env`).
- `DJANGO_SECRET_KEY` larga y aleatoria (≥ 50 caracteres).
- `DJANGO_ALLOWED_HOSTS` con dominio/IP real.
- Reverse proxy (nginx/Caddy) **delante** de Gunicorn para TLS — no incluido en este repo.
- `DJANGO_SECURE_SSL=True` si hay HTTPS terminado en proxy.

### Recursos

| Recurso | Mínimo recomendado | Notas |
|---------|-------------------|-------|
| RAM | **8 GB** | 2 modelos precargados + inferencia |
| CPU | 4 cores | Inferencia CPU es lenta pero funcional |
| Disco | 10 GB imagen + checkpoints | Checkpoints fuera de imagen |

### Persistencia

| Dato | Ubicación | Backup |
|------|-----------|--------|
| Artículos procesados | `data/articles/` | Copiar volumen |
| Workspaces | `data/workspaces/` | Idem |
| SQLite | `db.sqlite3` | Idem |
| Checkpoints | `TechBERT/`, `PatVetBERT/` | Almacenamiento separado |

### Seguridad

- Checkpoints montados **`:ro`** — el contenedor no puede modificarlos.
- `.env` en `.gitignore` y `.dockerignore` — nunca commitear secretos.
- CSRF activo en Django; uploads vía API con token implícito en sesión/forms.
- Sin autenticación de usuarios en versión actual — **no exponer a Internet público** sin capa auth adicional.

### Escalabilidad

- Arquitectura actual: **un proceso Gunicorn, un worker**, colas in-process.
- Escalar horizontalmente requeriría cola externa, almacenamiento compartido y evitar duplicar modelos en RAM por réplica.

---

## API REST — referencia rápida

| Método | URL | Descripción |
|--------|-----|-------------|
| GET | `/` | Interfaz principal |
| GET | `/api/models` | Modelos disponibles |
| GET | `/api/articles` | Lista artículos |
| POST | `/api/articles/upload` | Subir PDF/TXT + modelo |
| GET | `/api/articles/{id}/tsne?model=tech` | Datos t-SNE |
| GET | `/api/articles/{id}/ner?model=tech` | Resultados NER |
| GET | `/api/articles/{id}/meta` | Metadatos / estado |
| GET | `/api/articles/{id}/cleaned-text` | Texto limpio |
| GET | `/api/articles/{id}/relations` | Grafo relaciones |
| POST | `/api/articles/{id}/reprocess` | Reprocesar artículo |
| GET/POST | `/api/workspaces` | Listar / crear workspace |
| GET | `/api/workspaces/{id}/aggregate` | Agregado workspace |
| GET | `/api/workspaces/{id}/relations` | Relaciones workspace |
| GET | `/api/example/tsne?model=tech` | Datos demo |

---

## 12. License / Licencia

This project was developed as an undergraduate thesis and applied research project at **Universidad de los Llanos** by:

- **Vanessa López** ([@vanessalopezt](https://github.com/vanessalopezt))
- **Javier Rojas** ([@JavicR22](https://github.com/JavicR22))

Research seedbed: **AdaLab**  
Research group: **GITECX**  
Universidad de los Llanos — Villavicencio, Colombia

The licensing and distribution terms for this software depend on how **Universidad de los Llanos** has defined them in its institutional policies, and on the final decision of the authors.

---

Este proyecto fue desarrollado como trabajo de grado e investigación aplicada en la **Universidad de los Llanos** por:

- **Vanessa López** ([@vanessalopezt](https://github.com/vanessalopezt))
- **Javier Rojas** ([@JavicR22](https://github.com/JavicR22))

Semillero de investigación: **AdaLab**  
Grupo de investigación: **GITECX**  
Universidad de los Llanos — Villavicencio, Colombia

Los términos de licenciamiento y distribución del software dependen de cómo la **Universidad de los Llanos** los tenga definidos en sus lineamientos institucionales, y de la decisión final de los autores.
