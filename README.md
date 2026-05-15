# CAKB — Codebase Analysis & Knowledge Base

**RAG-пайплайн для аналізу Java-проєктів**: парсинг сирцевого коду, групування по доменах, генерація wiki-документації, enrichment через LLM, індексація у векторну базу та пошуковий API.

Проєкт побудований так, щоб бути **пере Використаним для будь-якого Java-проєкту**, не тільки для MyBookingPal.

---

## Архітектура

```
Java Source Code (sources/)
        │
        ▼
┌─────────────────────────────────────────────┐
│  RAG Pipeline  (run_rag.py)                 │
│                                             │
│  1. Parse    → java_parser.py               │
│  2. Group    → domain_grouper.py            │
│  3. Markdown → markdown_writer.py           │
│  4. Enrich   → enricher.py   (LLM)         │
│  4.5 Flows   → flow_generator.py (LLM)     │
│  5. Index    → indexer.py    (ChromaDB)     │
│                                             │
│  state → data/parsed/, data/domains/        │
│  wiki  → rag/  (git submodule)              │
│  index → data/vectorstore/                  │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Dashboard API  (dashboard.py)   :8090      │
│                                             │
│  GET  /              — Web UI               │
│  POST /api/query     — Semantic search      │
│  POST /api/ask       — RAG: search + LLM   │
│  GET  /api/status    — Pipeline status      │
│  GET  /api/history   — Request history      │
│  GET  /api/stats     — Usage stats          │
└─────────────────────────────────────────────┘
```

Також є **CrewAI-пайплайн** (`pipeline/`, `run_pipeline.py`) — альтернативний підхід з використанням AI-агентів для exploration та генерації wiki.

---

## Структура проєкту

```
cakb/
├── .env                        # API ключі (ZAI_API_KEY, тощо)
├── .env.example                # Приклад конфігурації
├── .gitignore
├── .gitmodules                 # rag/ — git submodule з wiki
├── cakb-api.service            # systemd unit для Dashboard API
│
├── dashboard.py                # FastAPI сервер — пошук, RAG-запити, UI
├── db.py                       # SQLite — історія запитів API
├── generate_entity_table_map.py # Утиліта: мапінг Java entity → DB таблиці
│
├── run_rag.py                  # ⭐ Головний ранер RAG-пайплайну
├── rag_pipeline/               # Модулі RAG-пайплайну
│   ├── java_parser.py          #   Парсинг Java коду (класи, методи, анотації)
│   ├── domain_grouper.py       #   Групування класів по доменах
│   ├── markdown_writer.py      #   Генерація wiki-сторінок (.md)
│   ├── enricher.py             #   LLM enrichment доменів (описи, зв'язки)
│   ├── flow_generator.py       #   LLM генерація cross-domain flow документів
│   ├── indexer.py              #   Індексація wiki у ChromaDB vectorstore
│   └── models.py               #   Data моделі (ParsedClass, Domain, тощо)
│
├── run_pipeline.py             # Ранер CrewAI-пайплайну (агентний підхід)
├── pipeline/                   # Модулі CrewAI-пайплайну
│   ├── orchestrator.py         #   Оркестратор: explore → generate → review
│   ├── decomposer.py           #   Розбиття великих модулів на домени
│   ├── pipeline_state.py       #   Менеджер стану (JSON файл)
│   ├── crews/
│   │   ├── explorer_crew.py    #   Агент: сканування коду, визначення wiki-сторінок
│   │   └── wiki_crew.py        #   Агент: генерація та рев'ю wiki
│   └── models/
│       └── domain.py           #   Data моделі (Domain, WikiPage, ModulePlan)
│
├── config/
│   └── modules.yaml            # Список модулів для CrewAI-пайплайну
│
├── scripts/
│   ├── run_pipeline.sh         # Bash wrapper для run_rag.py
│   └── status.sh               # Скрипт статусу (моніторинг)
│
├── sources/                    # ← Java сирці (не в git, поклади сюди)
├── rag/                        # Git submodule — згенерована wiki (markdown)
├── data/                       # Runtime дані (не в git)
│   ├── parsed/parsed.json      #   Результат парсингу Java коду
│   ├── domains/domains.json    #   Згруповані домени
│   ├── vectorstore/            #   ChromaDB індекс
│   └── api_history.db          #   Історія API запитів
└── logs/                       # Логи пайплайну та API
```

---

## Встановлення

### 1. Клонування

```bash
git clone <repo-url> cakb
cd cakb
git submodule update --init --recursive
```

### 2. Python-оточення

```bash
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn chromadb sentence-transformers openai pydantic PyYAML markdown-it-py
```

Для CrewAI-пайплайну додатково:

```bash
pip install crewai crewai-tools
```

### 3. Конфігурація

Створіть `.env` у корені проєкту:

```env
# Обов'язково для enrichment та RAG-відповідей
ZAI_API_KEY=your_api_key_here

# Опціонально (мають дефолтні значення)
LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4
LLM_MODEL=glm-5-turbo
LLM_FALLBACK_MODEL=glm-4.7
INDEX_MAX_RETRIES=3
```

### 4. Підготувати сирцевий код

Покладіть Java-проєкт у директорію `sources/`:

```bash
mkdir -p sources
# Наприклад:
ln -s /path/to/your/java/project sources/my-project
```

Структура `sources/` має містити піддиректорії з `.java` файлами. Кожна піддиректорія = один модуль:

```
sources/
├── module-a/
│   └── com/example/...
├── module-b/
│   └── com/example/...
└── ...
```

---

## Використання

### RAG-пайплайн (`run_rag.py`)

Це основний пайплайн. Всі кроки **ідемпотентні** — повторний запуск пропускає вже виконані кроки.

```bash
# Повний пайплайн (кроки 1-5)
python3 run_rag.py all

# Порядок кроків:
python3 run_rag.py parse       # 1. Парсинг Java → parsed.json
python3 run_rag.py group       # 2. Групування → domains.json
python3 run_rag.py markdown    # 3. Генерація wiki (.md файли в rag/)
python3 run_rag.py enrich      # 4. LLM enrichment (описи доменів)
python3 run_rag.py flows       # 4.5. Cross-domain flow документи (LLM)
python3 run_rag.py index       # 5. Індексація wiki → ChromaDB vectorstore
```

#### Корисні опції

```bash
# Перевірити поточний статус
python3 run_rag.py status

# Запит до векторної бази (без API сервера)
python3 run_rag.py query "how does reservation creation work?"

# Парсинг одного модуля
python3 run_rag.py parse --module redis

# Enrichment з лімітом (для тестування)
python3 run_rag.py enrich --limit 5

# Force — перезапустити крок навіть якщо він вже виконаний
python3 run_rag.py all --force
python3 run_rag.py index --force    # повна переіндексація

# Кількість результатів пошуку
python3 run_rag.py query "text" --top-k 10
```

#### Bash wrapper

```bash
./scripts/run_pipeline.sh              # all
./scripts/run_pipeline.sh --status     # статус
./scripts/run_pipeline.sh --force      # повний перезапуск
./scripts/run_pipeline.sh --reset      # видалити дані і запустити з нуля
./scripts/run_pipeline.sh --enrich     # тільки enrichment
./scripts/run_pipeline.sh --index      # тільки індексація
./scripts/run_pipeline.sh --stop       # зупинити запущений пайплайн
```

### CrewAI-пайплайн (`run_pipeline.py`)

Альтернативний підхід з AI-агентами. Автоматично досліджує код, планує wiki-сторінки, генерує і рев'ює їх.

```bash
# Запуск (безперервний, поки не обробить всі модулі)
python3 run_pipeline.py

# Запустити з нуля
python3 run_pipeline.py --reset
```

Конфігурація модулів: `config/modules.yaml`

```yaml
modules:
  - name: my-module
    path: sources/my-module
    priority: 1
    description: "Опис модуля"
    enabled: true
```

### Dashboard API (`dashboard.py`)

FastAPI сервер з web UI для пошуку та моніторингу.

```bash
# Запуск вручну
python3 dashboard.py

# Або через systemd
sudo systemctl start cakb-api
sudo systemctl enable cakb-api   # автозапуск
```

Сервер доступний на `http://localhost:8090`.

#### API Endpoints

| Method | Endpoint | Опис |
|--------|----------|------|
| `GET` | `/` | Dashboard UI |
| `POST` | `/api/query` | Семантичний пошук по wiki (`{"query": "..."}`) |
| `GET` | `/api/query?q=...` | Те саме через GET |
| `POST` | `/api/ask` | RAG: пошук + LLM відповідь (`{"query": "..."}`) |
| `GET` | `/api/ask?q=...` | Те саме через GET |
| `GET` | `/api/status` | Статус пайплайну |
| `GET` | `/api/status-rag` | Статистика ChromaDB індексу |
| `GET` | `/api/history` | Історія запитів (пагінація) |
| `GET` | `/api/history/{id}` | Деталі конкретного запиту |
| `GET` | `/api/stats` | Агрегована статистика використання |

Підтримується `?format=md` для отримання відповіді у Markdown форматі.

### Утиліта: Entity → Table Map

Генерує мапінг Java entity класів → MySQL таблиць через аналіз MyBatis mapper XML.

```bash
# Всі модулі
python3 generate_entity_table_map.py

# Один модуль
python3 generate_entity_table_map.py --module dataaccesslayer
```

Результат:
- `rag/entity-table-map.md` — документ для RAG
- `data/entity_table_map.json` — machine-readable JSON

---

## Крон-запуск

Для регулярного оновлення індексу:

```cron
# Щодня о 3:00 — повний пайплайн
0 3 * * * cd /home/r.dovgan/cakb && python3 run_rag.py all >> logs/cron.log 2>&1
```

---

## Дані та їх призначення

| Шлях | Що | Git |
|------|----|----|
| `data/parsed/parsed.json` | Розібраний Java код (класи, методи, анотації) | ❌ ігнорується |
| `data/domains/domains.json` | Згруповані домени з класами | ❌ ігнорується |
| `data/vectorstore/` | ChromaDB векторний індекс | ❌ ігнорується |
| `data/api_history.db` | SQLite з історією API запитів | ❌ ігнорується |
| `data/entity_table_map.json` | Entity→Table мапінг | ❌ ігнорується |
| `rag/` | Згенерована wiki (markdown) | ✅ git submodule |
| `logs/` | Логи пайплайну та API | ❌ ігнорується |

---

## Як адаптувати для нового проєкту

1. Покладіть Java сирці у `sources/` (кожен модуль — окрема папка)
2. Створіть `.env` з API ключем
3. Запустіть `python3 run_rag.py all`
4. Результат: wiki в `rag/`, векторний індекс у `data/vectorstore/`
5. Запустіть `python3 dashboard.py` для пошукового API

Для CrewAI-пайплайну: оновіть `config/modules.yaml` зі списком модулів вашого проєкту.
