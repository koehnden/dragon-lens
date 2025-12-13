# DragonLens API v1 - Design Document

## API Summary

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/v1/runs` | GET | List runs (paginated, filterable) | `200 OK` + runs list |
| `/v1/runs` | POST | Create analysis run | `202 Accepted` + `run_id` |
| `/v1/runs/{run_id}` | GET | Get run status/results | `200 OK` + status/results |
| `/v1/runs/{run_id}` | DELETE | Delete a run | `200 OK` + confirmation |

---

## Design Decisions

### 1. Resource Naming: Why `runs`?

Considered alternatives:
- `analysis` - too generic
- `jobs` - implies batch processing semantics  
- `queries` - too narrow (we do more than query)
- `scans` - suggests security/compliance

**`runs`** clearly conveys:
- An execution that happens over time
- Has a start, progress, and end
- Can be re-run with same parameters

### 2. Async Pattern: 202 Accepted

```
Client                    Server                    Celery
  |                         |                         |
  |-- POST /runs ---------->|                         |
  |                         |-- queue task ---------->|
  |<-- 202 {run_id} --------|                         |
  |                         |                         |
  |-- GET /runs/{id} ------>|                         |
  |<-- {status: RUNNING} ---|                         |
  |                         |                         |
  |-- GET /runs/{id} ------>|                         |
  |<-- {status: COMPLETED,  |                         |
  |     results: {...}} ----|                         |
```

**Why 202 vs 201?**
- `201 Created` implies the resource is immediately available
- `202 Accepted` signals "request received, processing deferred"

### 3. List Endpoint Design

```
GET /v1/runs?brand=VW&status=COMPLETED&limit=10&sort=-created_at
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `brand` | string | - | Filter by brand name (partial match) |
| `vertical` | string | - | Filter by vertical (exact match) |
| `status` | enum | - | Filter by run status |
| `limit` | int | 20 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |
| `sort` | string | `-created_at` | Sort field, `-` prefix for descending |

**Use Cases:**
- Last run: `?limit=1`
- Run history: `?limit=20`
- Brand comparison: `?brand=VW&limit=50`
- Failed runs: `?status=FAILED`

### 4. Delete Endpoint Design

```
DELETE /v1/runs/{run_id} → 200 OK
```

**Behavior by status:**
| Status | Behavior |
|--------|----------|
| `PENDING` | Remove from queue, delete record |
| `RUNNING` | Attempt cancel, then delete |
| `COMPLETED` | Delete record + all responses |
| `FAILED` | Delete record + partial responses |

**Why 200 instead of 204?**
- 204 No Content is RESTful but loses context
- 200 with `{deleted: true, previous_status: "..."}` is more informative
- Helps client confirm what was deleted

### 5. Brand as Object (V2-Ready)

```json
{
  "brand": {
    "name": "Volkswagen",
    "aliases": ["VW", "大众"],
    "description": "German automotive manufacturer"
  }
}
```

**Why not just a string?**
- Chinese brands often have English + Chinese names
- Aliases improve mention detection accuracy
- Description helps LLM context (V2: competitive framing)
- Easy to extend: `competitors`, `products`, `regions`

### 6. Progress Tracking

```json
{
  "progress": {
    "total_tasks": 6,
    "completed_tasks": 2,
    "current_step": "querying_llm"
  }
}
```

Steps flow:
```
queued → translating_prompts → querying_llm → 
translating_responses → extracting_metrics → computing_scores → done
```

**Why expose steps?**
- Better UX: user knows *what's happening*, not just percentage
- Debugging: easier to identify where failures occur
- Monitoring: can alert on slow steps

### 7. Metrics Design

| Metric | Range | Description |
|--------|-------|-------------|
| `share_of_voice` | 0-1 | % of responses mentioning brand |
| `prominence_score` | 0-1 | Weighted by position (earlier = higher) |
| `top_spot_share` | 0-1 | % of #1 rankings |
| `sentiment_index` | 0-1 | 0=negative, 0.5=neutral, 1=positive |
| `opportunity_rate` | 0-1 | % where brand *could* be mentioned but wasn't |
| `dragon_visibility_score` | 0-1 | Composite score |

**Dragon Visibility Score formula (proposed):**
```python
dvs = (
    0.25 * share_of_voice +
    0.25 * prominence_score +
    0.20 * top_spot_share +
    0.20 * sentiment_index +
    0.10 * (1 - opportunity_rate)  # inverted: lower opportunity = better
)
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        POST /v1/runs                            │
│  {prompts, models, brand, vertical}                             │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI                                 │
│  1. Validate request                                            │
│  2. Create Run record (SQLite) with status=PENDING              │
│  3. Queue Celery task with run_id                               │
│  4. Return 202 {run_id, status: PENDING}                        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Celery Worker                              │
│                                                                 │
│  Step 1: translating_prompts                                    │
│    - Detect language of each prompt                             │
│    - EN prompts → translate to ZH (store both)                  │
│    - ZH prompts → translate to EN (store both)                  │
│                                                                 │
│  Step 2: querying_llm                                           │
│    - For each (prompt_zh, model):                               │
│      - Call Ollama API with ZH prompt                           │
│      - Store raw response                                       │
│                                                                 │
│  Step 3: translating_responses                                  │
│    - Translate each ZH response → EN                            │
│    - Store both versions                                        │
│                                                                 │
│  Step 4: extracting_metrics                                     │
│    - For each response, extract:                                │
│      - mentioned: bool                                          │
│      - rank: int | null                                         │
│      - sentiment: positive/neutral/negative                     │
│      - evidence_snippet: str                                    │
│                                                                 │
│  Step 5: computing_scores                                       │
│    - Aggregate metrics across all responses                     │
│    - Compute share_of_voice, prominence, etc.                   │
│    - Compute dragon_visibility_score                            │
│                                                                 │
│  Step 6: done                                                   │
│    - Update Run record: status=COMPLETED, results={...}         │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GET /v1/runs/{run_id}                        │
│  Returns: {status, progress, results?, error?}                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## SQLite Schema (V1)

```sql
-- Core run tracking
CREATE TABLE runs (
    id TEXT PRIMARY KEY,  -- UUID
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Denormalized for filtering (also in config JSON)
    brand_name TEXT NOT NULL,
    vertical TEXT NOT NULL,
    
    -- Config (stored as JSON for flexibility)
    config JSON NOT NULL,
    
    -- Progress tracking
    total_tasks INTEGER NOT NULL,
    completed_tasks INTEGER DEFAULT 0,
    current_step TEXT DEFAULT 'queued',
    
    -- Results (NULL until COMPLETED)
    results JSON,
    
    -- Error info (NULL unless FAILED)
    error JSON
);

-- Indexes for list endpoint filtering
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_brand_name ON runs(brand_name);
CREATE INDEX idx_runs_vertical ON runs(vertical);
CREATE INDEX idx_runs_created_at ON runs(created_at DESC);

-- Individual prompt/model responses
CREATE TABLE run_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    prompt_index INTEGER NOT NULL,
    model TEXT NOT NULL,
    
    -- Prompts
    prompt_original TEXT NOT NULL,
    prompt_zh TEXT NOT NULL,
    prompt_en TEXT NOT NULL,
    
    -- Response
    response_zh TEXT,
    response_en TEXT,
    
    -- Extracted data
    brand_mentioned BOOLEAN,
    brand_rank INTEGER,
    sentiment TEXT,  -- positive/neutral/negative
    sentiment_score REAL,  -- 0.0-1.0
    evidence_snippet_zh TEXT,
    evidence_snippet_en TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_run_responses_run_id ON run_responses(run_id);
```

**Note:** `ON DELETE CASCADE` ensures that when a run is deleted, all its responses are automatically removed.

---

## V2 Extension Points

The API is designed for these V2 additions:

### 1. Multi-Model Support
```yaml
# V2: models array accepts remote models
models:
  - "qwen2.5:7b"        # local Ollama
  - "kimi:kimi-2"       # remote Kimi API
  - "deepseek:v3"       # remote DeepSeek API
```

### 2. API Key Management
```yaml
# New endpoint for V2
POST /v1/credentials
{
  "provider": "kimi",
  "api_key": "sk-..."
}
```

### 3. Scheduled Runs
```yaml
# V2: Add schedule to create run request
POST /v1/runs
{
  "prompts": [...],
  "schedule": {
    "frequency": "daily",
    "time": "09:00",
    "timezone": "Asia/Shanghai"
  }
}
```

### 4. Web Search Integration
```yaml
# V2: Add search_enabled flag
POST /v1/runs
{
  "prompts": [...],
  "options": {
    "web_search_enabled": true,
    "search_provider": "serper"
  }
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Request body validation failed |
| `INVALID_MODEL` | 400 | Unsupported model specified |
| `RUN_NOT_FOUND` | 404 | Run ID doesn't exist |
| `DELETE_CONFLICT` | 409 | Cannot delete run in current state |
| `MODEL_UNAVAILABLE` | 503 | Can't connect to Ollama |
| `LLM_TIMEOUT` | 500 | Model didn't respond in time |
| `TRANSLATION_FAILED` | 500 | Translation service error |
| `EXTRACTION_FAILED` | 500 | Metrics extraction error |

---

## Implementation Notes for Claude Code

### FastAPI Structure
```
dragonlens/
├── api/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, CORS, error handlers
│   ├── routes/
│   │   ├── __init__.py
│   │   └── runs.py       # /runs endpoints
│   └── deps.py           # Dependencies (DB session, etc.)
├── schemas/
│   ├── __init__.py
│   ├── runs.py           # Pydantic models from OpenAPI
│   └── metrics.py        # Metric schemas
├── models/
│   ├── __init__.py
│   └── run.py            # SQLAlchemy models
├── services/
│   ├── __init__.py
│   ├── translation.py    # EN<->ZH translation
│   ├── llm.py            # Ollama client
│   └── extraction.py     # Metrics extraction
├── tasks/
│   ├── __init__.py
│   ├── celery_app.py     # Celery configuration
│   └── analysis.py       # Main analysis task
└── db/
    ├── __init__.py
    └── database.py       # SQLite connection
```

### Key Pydantic Models
```python
# schemas/runs.py
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class BrandInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    description: Optional[str] = Field(None, max_length=1000)

class CreateRunRequest(BaseModel):
    prompts: list[str] = Field(..., min_items=1, max_items=50)
    models: list[str] = Field(..., min_items=1)
    brand: BrandInput
    vertical: str = Field(..., min_length=1, max_length=100)
```

### Celery Task Skeleton
```python
# tasks/analysis.py
from celery import shared_task
from db.database import get_db
from models.run import Run

@shared_task(bind=True)
def run_analysis(self, run_id: str):
    db = next(get_db())
    run = db.query(Run).filter(Run.id == run_id).first()
    
    try:
        run.status = "RUNNING"
        
        # Step 1: Translate prompts
        run.current_step = "translating_prompts"
        db.commit()
        translated = translate_prompts(run.config["prompts"])
        
        # Step 2: Query LLMs
        run.current_step = "querying_llm"
        db.commit()
        responses = query_llms(translated, run.config["models"])
        
        # ... more steps
        
        run.status = "COMPLETED"
        run.results = compute_results(responses)
        
    except Exception as e:
        run.status = "FAILED"
        run.error = {"code": "UNKNOWN", "message": str(e)}
    
    finally:
        run.completed_at = datetime.utcnow()
        db.commit()
```
