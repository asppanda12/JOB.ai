# JOB.ai

Local-first job discovery: multi-source ingestion, hybrid retrieval
(dense + lexical + graph), cross-encoder reranking, and personalised
recommendations reasoned about by a local Qwen 7B through Ollama.

No external LLM API keys. Nothing leaves your machine except the job scraping
itself.

---

## Architecture

```
                         JOB SOURCES
                              │
             ┌────────────────┼────────────────┐
             ↓                ↓                ↓
      Portals (2)       ATS boards (6)    Aggregators (6)
     LinkedIn, Naukri   Greenhouse,       RemoteOK, Remotive,
                        Lever, Ashby,     Arbeitnow, Himalayas,
                        SmartRecruiters,  Jobicy, WeWorkRemotely
                        Workable,
                        Recruitee
             │                │                │
             └────────────────┼────────────────┘
                              ↓
                   Common Job Schema  (jobai/schema.py)
                              ↓
              Normalize + Deduplicate  (jobai/normalize, jobai/dedup.py)
                              ↓
                   ┌──────────┴──────────┐
                   ↓                     ↓
               MongoDB                Indexing
            (structured store)            │
                            ┌─────────────┼─────────────┐
                            ↓             ↓             ↓
                         FAISS          BM25          Graph
                        (dense)      (lexical)    (skills/roles)
                            └─────────────┼─────────────┘
                                          ↓
                            Reciprocal Rank Fusion  +  metadata filters
                                          ↓
                                    Top 50–100
                                          ↓
                             Cross-encoder reranker
                                          ↓
                                    Top 10–20
                                          ↓
                          Transparent scoring (signals + weights)
                                          ↓
                                     Qwen 7B
                             (explains; never re-ranks)
                                          ↓
                            Personalised recommendations
                                          ↓
                                     Telegram
```

### Why each stage exists

| Stage | Why it is there |
|---|---|
| **FAISS** (dense) | Semantic recall: finds "LLM inference optimisation" for a query about "GenAI engineering". Blurry on exact tokens. |
| **BM25** (lexical) | Exact tokens: `PyTorch`, `LangGraph`, `C++`, `Kafka`. A dense vector cannot reliably separate LangChain from LangGraph; BM25 can. |
| **Graph** | Relational questions embeddings cannot answer: which jobs need skills *related* to mine, what am I missing, which companies keep hiring my stack. |
| **Metadata filters** | Hard constraints: location, experience band, salary, recency, source. Applied after fusion, and relaxed rather than returning an empty list. |
| **RRF** | The three retrievers produce incomparable numbers (cosine in `[0,1]`, unbounded Okapi, an overlap ratio). RRF fuses their *orderings*, which are comparable. |
| **Reranker** | A cross-encoder reads query and job *together* and is far more accurate than any first-stage scorer — but costs a forward pass each, so it only sees the ~80 survivors. |
| **Qwen 7B** | High-level reasoning **last**, on 10–20 jobs: why this fits, what is missing, how to prepare. It never sees 1,000 jobs and never decides the ranking. |

---

## Job sources

Fourteen sources in three families. `python -m jobai sources` lists them all;
any name below, or a group name, works with `ingest --sources`.

| Group | Sources | Transport | Notes |
|---|---|---|---|
| `portals` | LinkedIn, Naukri | LinkedIn: HTTP guest endpoints. Naukri: **Playwright** | Naukri needs a headed browser (see below) |
| `ats` | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee | HTTP (public JSON) | First-party company boards. Highest signal: complete text, real posting dates, stable ids |
| `boards` | RemoteOK, Remotive, Arbeitnow, Himalayas, Jobicy, WeWorkRemotely | HTTP (public JSON/RSS) | Cross-company aggregators, remote-heavy |
| `fast` | everything except Naukri | HTTP only | No browser needed; safe to run on a schedule |
| `all` | all 14 | | |

```bash
python -m jobai sources                                   # list sources and groups
python -m jobai ingest --sources ats --limit 100          # every ATS board
python -m jobai ingest --sources fast --limit 50          # everything browser-free
python -m jobai ingest --sources all --limit 25           # the lot
python -m jobai ingest --sources greenhouse remoteok      # pick individually
```

### ATS boards are configuration, not code

Each ATS platform is one adapter over a public endpoint keyed by company slug,
so tracking a new company is an environment change:

```bash
ATS_GREENHOUSE=stripe,figma,databricks,anthropic,discord
ATS_LEVER=palantir
ATS_ASHBY=ramp,notion,linear
ATS_SMARTRECRUITERS=Continental
ATS_WORKABLE=scalable
ATS_RECRUITEE=hygraph
```

Find a slug from the company's careers URL — `boards.greenhouse.io/stripe`
gives `stripe`, `jobs.lever.co/palantir` gives `palantir`, and so on.

### Why HTTP for these and Playwright for Naukri

Playwright drives the sources whose data only exists after JavaScript renders
a DOM. The ATS and aggregator sources publish documented JSON endpoints, so a
browser would add a page load and a JS engine to fetch bytes already available
— more cost and more to break, with nothing gained. Using the right transport
per source is what keeps 12 of the 14 running with no browser at all.

### Naukri needs a headed browser

Naukri answers HTTP 403 to every headless configuration — Playwright's bundled
Chromium and the real Chrome channel alike — while the same request from a
visible window returns 200. So the Naukri source opens a real window
regardless of `SCRAPER_HEADLESS`. Set `NAUKRI_HEADLESS=1` to force headless and
accept the likely 403. Its JSON API is reCAPTCHA-gated and is deliberately not
bypassed; a 403 is reported as *blocked*, not worked around.

---

## Local setup

### 1. Python

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium      # browser for the DOM-scraped sources
```

### 2. Ollama + Qwen 7B (required)

```bash
# macOS:  brew install ollama       (or download from https://ollama.com)
# Linux:  curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull qwen2.5:7b
```

Use a different model by setting `OLLAMA_MODEL`; nothing is hard-coded.

### 3. MongoDB (required)

```bash
# macOS
brew tap mongodb/brew && brew install mongodb-community
brew services start mongodb-community

# Docker
docker run -d --name jobai-mongo -p 27017:27017 mongo:7
```

### 4. Neo4j (optional)

Graph retrieval works without it — an equivalent in-process graph is built from
the job store automatically. Neo4j simply makes it persistent and queryable.

```bash
docker run -d --name jobai-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/jobai-local-password \
  neo4j:5

# then in .env:
#   GRAPH_DB_URI=bolt://localhost:7687
#   GRAPH_DB_USER=neo4j
#   GRAPH_DB_PASSWORD=jobai-local-password
```

### 5. Configure

```bash
cp .env.example .env    # every value has a working default
```

### 6. Verify

```bash
python -m jobai doctor
```

Reports Ollama, MongoDB, FAISS, the reranker and the graph, with an actionable
hint for anything that is not ready.

---

## Usage

```bash
# Ingest: scrape → normalize → dedup → MongoDB → FAISS → BM25 → graph
python -m jobai ingest --sources linkedin naukri --limit 100

# Normalize data you already have, without re-scraping
python -m jobai migrate --source faiss     # from the committed FAISS index
python -m jobai migrate --source mongo     # from USER_1.JOB_Data

# Rebuild BM25 + the graph from FAISS
python -m jobai reindex

# Ad-hoc hybrid search
python -m jobai search "GenAI Engineer" \
  --skills Python PyTorch LangChain --locations Bengaluru --experience 2 --explain

# Recommend for a registered Telegram user
python -m jobai recommend --chat-id 7748640302 --explain

# Run the bot
python -m telegram_bot.telegram_bot
```

Per-source entry points still work and now take arguments instead of
hard-coded paths:

```bash
python -m Linkedin.start_scrapping --keywords "GenAI Engineer" --locations India --limit 50 --index
python -m naukri.start_scrapping   --keywords "data scientist" --locations bangalore --limit 50
python -m combined_single_data.master_data
```

---

## Telegram bot

| Command | Does |
|---|---|
| `/start` | Register: name, phone, email, years of experience, CV (PDF) |
| `/update` | Personalised recommendations, 10 per page, "Send More Jobs" |
| `/search <role>` | Search a specific role through the same funnel |
| `/gaps` | Skill-gap analysis across your recommendations |
| `/help` | Command list |

Each job carries **Referral**, **Cover Letter** and **Cold Email** buttons, plus
a match score, the reasons it matched, and the skills you are missing.

---

## Testing

```bash
# Fast: unit tests only, no services needed
pytest -m "not integration"

# Full suite (needs Ollama + MongoDB + the FAISS index; skips what is absent)
pytest

# Targeted
pytest tests/test_schema.py tests/test_normalize.py tests/test_dedup.py -q  # data layer
pytest tests/test_retrieval.py -q                                          # BM25, graph, RRF, filters, scoring
pytest tests/test_index_builder.py -q                                      # incremental indexing
pytest tests/test_llm.py -q                                                # Ollama + "no external provider" guard
pytest tests/test_ingest.py -q                                             # failure isolation, malformed input
pytest tests/test_pipeline_e2e.py -q                                       # resume → retrieval → rerank → Qwen
pytest -m network -q                                                       # live LinkedIn / Naukri scraping
```

Manual checks:

```bash
python -m jobai doctor                                    # Ollama, Mongo, FAISS, reranker, graph
python -m Linkedin.start_scrapping --limit 3 -v           # LinkedIn live
python -m naukri.start_scrapping --limit 3 -v             # Naukri live
python -m jobai search "GenAI Engineer" --skills Python PyTorch   # retrieval + rerank
python -m jobai ingest --sources linkedin --limit 5       # full ingestion
```

---

## Configuration

Everything lives in `.env` — see `.env.example` for the annotated list. The
settings worth knowing:

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5:7b` | The one LLM, used by every feature |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | **Do not change** without re-indexing: the committed FAISS vectors are 1024-d from this model |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Second-stage cross-encoder |
| `FUSION_K` / `RERANK_K` | `80` / `20` | The "top 50–100" and "top 10–20" funnel widths |
| `WEIGHT_*` | see `.env.example` | Scoring weights; no magic numbers in code |
| `FRESHNESS_HALF_LIFE_DAYS` | `21` | Recency decay. Old jobs are down-weighted, never deleted |
| `GRAPH_ENABLED` | `1` | Graph arm; falls back in-process when Neo4j is absent |

---

## Failure isolation

| If this fails | What still works |
|---|---|
| LinkedIn | Naukri and every other source ingest normally |
| Naukri | LinkedIn and every other source ingest normally |
| Neo4j | FAISS + BM25 + metadata retrieval, via the in-process graph |
| Cross-encoder | The fused RRF ordering is used as-is |
| Ollama | Retrieval, ranking and scoring all work; you get a clear, actionable error instead of reasoning |
| MongoDB | Ingestion still updates the vector index |

---

## Migrating existing data

Nothing is destructive, and no re-scrape is required.

* **FAISS** — the committed `vector_store/` (3,298 vectors, `IndexFlatL2`, 1024-d)
  loads unchanged. Same path, same embeddings, same LangChain docstore format.
* **MongoDB** — the same databases and collections (`USER.JOB_USER`,
  `USER_1.JOB_Data`, `USER_1.Job_specific`). Jobs are now **upserted** by
  `job_id` rather than the collection being wiped on every run.
* **Job metadata** — every legacy key (`job_title`, `company_name`, `job_link`,
  `yoe`, `job_indx`, …) is still written, so pre-upgrade readers keep working.
  Canonical fields (`job_id`, `skills_list`, `required_skills`,
  `experience_min/max`, `content_hash`, `sources`) ride alongside.
* **Registered users** — old `resume_json` profiles are read through a
  compatibility path, so existing users need not re-upload a CV.

To normalize existing rows into the canonical schema in place:

```bash
python -m jobai migrate --source faiss    # or --source mongo
```

This re-reads what is stored, normalizes and deduplicates it, upserts it, and
re-embeds **only** the jobs whose content actually changed.

---

## Repository layout

```
jobai/                  the shared backend every interface calls
  config.py             all configuration, read from the environment
  schema.py             the canonical Job + legacy adapters
  dedup.py              five-level deduplication
  profile.py            structured user profiles, cached by resume hash
  scoring.py            transparent match signals and weights
  index_builder.py      incremental indexing
  recommend.py          the recommendation service
  cli.py                python -m jobai …
  normalize/            skills, experience, canonical text
  llm/                  the one Ollama client, prompts, and every LLM task
  retrieval/            dense, lexical, graph, filters, fusion, rerank, pipeline
  ingest/               source contract, browser plumbing, LinkedIn, Naukri, legacy
  store/                MongoDB adapter

Data_base/              legacy facades, now delegating to jobai/
resume_cold_mail/       resume parsing and email generation (on Ollama)
telegram_bot/           the bot
Linkedin/ naukri/ cuvete/ wellfound/ Scrape_entire_web/   per-source entry points
data_cleaning/ combined_single_data/                      cleaning and merge scripts
tests/                  unit + integration suites
vector_store/           the FAISS index (committed)
```
