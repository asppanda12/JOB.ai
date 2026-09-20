"""Deterministic skill normalization.

Rule-based on purpose: an LLM is neither reproducible nor fast enough to sit on
the ingestion hot path, and the same surface form must map to the same token
every time or BM25, the graph and the metadata filters silently disagree with
each other.  The LLM is still used to *extract* skills from free text; it is
never used to decide their canonical spelling.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Set

# Canonical name -> aliases. Aliases are matched case- and separator-insensitively,
# so "Py Torch", "py-torch" and "pytorch" all collapse to "PyTorch".
SKILL_ALIASES: Dict[str, List[str]] = {
    "Python": ["python3", "python 3", "py"],
    "JavaScript": ["js", "ecmascript", "java script"],
    "TypeScript": ["ts", "type script"],
    "C++": ["cpp", "c plus plus", "cplusplus"],
    "C#": ["csharp", "c sharp"],
    "Go": ["golang"],
    "Java": ["core java", "java se"],
    "SQL": ["structured query language", "ansi sql"],
    "NoSQL": ["no sql"],
    "PyTorch": ["py torch", "torch", "pytorch lightning"],
    "TensorFlow": ["tensor flow", "tf", "tensorflow2", "keras"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "LangChain": ["lang chain", "langchain framework"],
    "LangGraph": ["lang graph"],
    "LlamaIndex": ["llama index", "gpt index"],
    "Hugging Face": ["huggingface", "hugging face transformers", "hf transformers"],
    "Transformers": ["transformer models", "transformer architecture"],
    "LLM": ["large language model", "large language models", "llms", "foundation model", "foundation models"],
    "RAG": ["retrieval augmented generation", "retrieval-augmented generation"],
    "Prompt Engineering": ["prompting", "prompt design"],
    "Vector Database": ["vector db", "vector store", "vectordb", "vector databases"],
    "FAISS": ["faiss index"],
    "Pinecone": [],
    "Weaviate": [],
    "Qdrant": [],
    "ChromaDB": ["chroma", "chroma db"],
    "NLP": ["natural language processing"],
    "Computer Vision": ["image processing", "computer-vision"],
    "Machine Learning": ["ml", "machine-learning"],
    "Deep Learning": ["dl", "deep-learning", "neural networks", "neural network"],
    "Generative AI": ["genai", "gen ai", "generative artificial intelligence"],
    "MLOps": ["ml ops", "ml-ops"],
    "AWS": ["amazon web services", "aws cloud"],
    "Azure": ["microsoft azure", "ms azure"],
    "GCP": ["google cloud", "google cloud platform"],
    "Kubernetes": ["k8s", "kube"],
    "Docker": ["containerization", "containers"],
    "Terraform": ["hashicorp terraform"],
    "Kafka": ["apache kafka"],
    "Spark": ["apache spark", "pyspark"],
    "Airflow": ["apache airflow"],
    "Hadoop": ["apache hadoop"],
    "FastAPI": ["fast api"],
    "Flask": [],
    "Django": [],
    "Node.js": ["nodejs", "node js", "node"],
    "React": ["reactjs", "react js", "react.js"],
    "Angular": ["angularjs", "angular js"],
    "Vue.js": ["vuejs", "vue js", "vue"],
    "Next.js": ["nextjs", "next js"],
    "PostgreSQL": ["postgres", "postgre sql"],
    "MySQL": ["my sql"],
    "MongoDB": ["mongo", "mongo db"],
    "Redis": [],
    "Elasticsearch": ["elastic search", "elk", "opensearch"],
    "Neo4j": ["neo 4j", "neo4j graph"],
    "GraphQL": ["graph ql"],
    "REST API": ["rest", "restful api", "restful apis", "rest apis"],
    "gRPC": ["grpc"],
    "Microservices": ["micro services", "micro-services"],
    "CI/CD": ["cicd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment"],
    "Git": ["github", "gitlab", "version control"],
    "Linux": ["unix", "shell scripting", "bash"],
    "Pandas": ["pandas library"],
    "NumPy": ["numpy library", "np"],
    "Power BI": ["powerbi", "power-bi"],
    "Tableau": [],
    "Excel": ["microsoft excel", "ms excel"],
    "Statistics": ["statistical modeling", "statistical modelling", "statistical analysis"],
    "Data Analysis": ["data analytics", "analytics"],
    "Data Engineering": ["data pipelines", "etl", "elt"],
    "Data Science": ["data scientist"],
    "System Design": ["systems design", "high level design", "hld"],
    "DSA": ["data structures", "data structures and algorithms", "algorithms"],
    "Agile": ["scrum", "kanban"],
}

# Symmetric "these two are adjacent" edges, used by the graph layer to answer
# "jobs that need skills related to mine" and to price near-miss skill gaps.
RELATED_SKILLS: Dict[str, List[str]] = {
    "PyTorch": ["Deep Learning", "TensorFlow", "Transformers", "Machine Learning"],
    "TensorFlow": ["Deep Learning", "PyTorch", "Machine Learning"],
    "LangChain": ["LLM", "RAG", "LangGraph", "Vector Database", "Generative AI"],
    "LangGraph": ["LangChain", "LLM", "Generative AI"],
    "LlamaIndex": ["RAG", "LLM", "Vector Database"],
    "RAG": ["Vector Database", "LLM", "NLP", "Embeddings"],
    "LLM": ["NLP", "Transformers", "Generative AI", "Prompt Engineering"],
    "Generative AI": ["LLM", "RAG", "Prompt Engineering"],
    "Vector Database": ["FAISS", "Pinecone", "Weaviate", "Qdrant", "ChromaDB", "RAG"],
    "FAISS": ["Vector Database", "Embeddings"],
    "NLP": ["Transformers", "LLM", "Machine Learning"],
    "Machine Learning": ["Deep Learning", "Python", "scikit-learn", "Statistics"],
    "Deep Learning": ["PyTorch", "TensorFlow", "Machine Learning"],
    "MLOps": ["Docker", "Kubernetes", "CI/CD", "AWS"],
    "AWS": ["Azure", "GCP", "Docker", "Kubernetes"],
    "Azure": ["AWS", "GCP"],
    "GCP": ["AWS", "Azure"],
    "Kubernetes": ["Docker", "Terraform", "Microservices"],
    "Docker": ["Kubernetes", "CI/CD"],
    "Kafka": ["Spark", "Data Engineering", "Microservices"],
    "Spark": ["Hadoop", "Data Engineering", "Python"],
    "FastAPI": ["Python", "REST API", "Flask"],
    "Flask": ["Python", "FastAPI", "Django"],
    "Django": ["Python", "Flask", "REST API"],
    "React": ["JavaScript", "TypeScript", "Next.js"],
    "PostgreSQL": ["SQL", "MySQL"],
    "MongoDB": ["NoSQL", "Redis"],
    "Neo4j": ["GraphQL", "NoSQL", "Vector Database"],
    "Python": ["Pandas", "NumPy", "Machine Learning"],
    "Embeddings": ["Vector Database", "RAG", "NLP"],
}

# Surface forms that are real skill abbreviations but are also ordinary English,
# so they may only be matched inside an explicit skill *tag*, never sniffed out
# of free text. Without this, "send us your CV" became Computer Vision, "go
# through the process" became Go, and "excel at collaboration" became Excel.
AMBIGUOUS_IN_TEXT = {
    "go", "r", "c", "ml", "dl", "tf", "np", "ts", "js", "py", "cv", "ai",
    "excel", "vision", "research", "analytical", "training", "infrastructure",
    "agile", "scrum", "git", "node", "spark", "storm", "pandas", "swift",
}

# Tokens that show up in skill lists but carry no signal.
_STOPWORDS = {
    "", "n/a", "na", "none", "null", "other", "others", "etc", "skills", "skill",
    "experience", "knowledge", "strong", "good", "excellent", "working",
}


def _key(value: str) -> str:
    """Collapse to a comparison key: lowercase, separators removed."""
    value = value.strip().lower()
    value = re.sub(r"[\s_\-./]+", "", value)
    return value


def _build_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for canonical, aliases in SKILL_ALIASES.items():
        lookup[_key(canonical)] = canonical
        for alias in aliases:
            lookup.setdefault(_key(alias), canonical)
    return lookup


_LOOKUP = _build_lookup()


def normalize_skill(skill: str) -> str:
    """Map one surface form to its canonical spelling.

    Unknown skills are kept (titled-cased when they look like plain words) so
    the vocabulary is not silently truncated to the alias table.
    """
    if not skill:
        return ""
    cleaned = re.sub(r"\s+", " ", str(skill)).strip().strip(".,;:|/-")
    # Strip parentheticals: "Natural Language Processing (NLP)" -> both halves
    # are handled by the caller; here we keep the longer, outer form.
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", cleaned).strip()
    if not cleaned or cleaned.lower() in _STOPWORDS:
        return ""
    if len(cleaned) > 60:
        return ""
    hit = _LOOKUP.get(_key(cleaned))
    if hit:
        return hit
    # Preserve acronyms and deliberate casing (AWS, PyTorch, C++, Node.js);
    # only re-case all-lowercase multi-word phrases.
    if cleaned.islower():
        return " ".join(word.capitalize() for word in cleaned.split())
    return cleaned


def normalize_skills(skills: Iterable[str] | str | None) -> List[str]:
    """Normalize, de-duplicate and stably order a skill collection."""
    if skills is None:
        return []
    if isinstance(skills, str):
        skills = re.split(r"[,;|\n]|\s{2,}", skills)
    out: List[str] = []
    seen: Set[str] = set()
    for raw in skills:
        for piece in _split_compound(str(raw)):
            canonical = normalize_skill(piece)
            if not canonical:
                continue
            key = _key(canonical)
            if key in seen:
                continue
            seen.add(key)
            out.append(canonical)
    return out


def _split_compound(value: str) -> List[str]:
    """Split "Python, Django and SQL" into its parts, keeping "C++" intact."""
    value = value.strip()
    if not value or value.lower() in _STOPWORDS:
        return []
    # A known skill is never split, so "CI/CD" and "Node.js" survive intact.
    if _key(value) in _LOOKUP:
        return [value]
    parts = re.split(r"\s*(?:,|;|\||/|\band\b|\bor\b)\s*", value, flags=re.IGNORECASE)
    # A parenthesised acronym is a skill in its own right: keep both.
    extra = re.findall(r"\(([A-Za-z0-9+#.\- ]{2,20})\)", value)
    return [p for p in parts + extra if p.strip() and p.strip().lower() not in _STOPWORDS]


def related_skills(skill: str, depth: int = 1) -> List[str]:
    """Skills adjacent to ``skill`` in the (symmetric) relatedness graph."""
    canonical = normalize_skill(skill)
    if not canonical:
        return []
    frontier = {canonical}
    seen = {canonical}
    for _ in range(max(0, depth)):
        nxt: Set[str] = set()
        for node in frontier:
            for neighbour in RELATED_SKILLS.get(node, []):
                if neighbour not in seen:
                    seen.add(neighbour)
                    nxt.add(neighbour)
            # The table is declared one-directionally; treat it as symmetric.
            for other, neighbours in RELATED_SKILLS.items():
                if node in neighbours and other not in seen:
                    seen.add(other)
                    nxt.add(other)
        frontier = nxt
        if not frontier:
            break
    return sorted(seen - {canonical})


def extract_skills_from_text(text: str, vocabulary: Iterable[str] | None = None) -> List[str]:
    """Find known skills mentioned in free text.

    Used as a deterministic backstop when a source gives a description but no
    skill tags, and as a cheap fallback when the LLM is unavailable.
    """
    if not text:
        return []
    haystack = " " + re.sub(r"\s+", " ", text.lower()) + " "
    found: List[str] = []
    candidates = list(vocabulary) if vocabulary is not None else list(SKILL_ALIASES)
    for canonical in candidates:
        surfaces = [canonical] + SKILL_ALIASES.get(canonical, [])
        for surface in surfaces:
            lowered = surface.lower()
            # Short or ordinary-English surfaces are too noisy to sniff from prose.
            if lowered in AMBIGUOUS_IN_TEXT or len(lowered) < 3:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(lowered) + r"(?![a-z0-9])"
            if re.search(pattern, haystack):
                found.append(canonical)
                break
    return normalize_skills(found)


def parse_skill_blob(text: str) -> List[str]:
    """Recover a skill list from a legacy space-joined blob.

    The pre-upgrade cleaning scripts stored skills as ``" ".join(skills)``, so
    a row reads ``"Python Generative AI LLMs NLP"`` with no delimiter at all.
    Splitting on whitespace would shred "Generative AI" into two tokens, so we
    first match known vocabulary against the blob, then keep whatever
    capitalised runs are left over as unknown-but-real skills.
    """
    if not text or not isinstance(text, str):
        return []
    if re.search(r"[,;|\n]|\s{2,}", text):
        return normalize_skills(text)

    known = extract_skills_from_text(text)
    remainder = text
    for skill in known:
        for surface in [skill] + SKILL_ALIASES.get(skill, []):
            remainder = re.sub(
                r"(?<![a-z0-9])" + re.escape(surface) + r"(?![a-z0-9])", " ", remainder, flags=re.IGNORECASE
            )
    # "Generative AI Engineering Kubernetes" -> keep the capitalised runs.
    leftovers = re.findall(r"\b[A-Z][A-Za-z0-9+#.]*(?:\s+[A-Z][A-Za-z0-9+#.]*){0,2}\b", remainder)
    return normalize_skills(known + [l for l in leftovers if len(l) > 1])


def skills_from_metadata(metadata: Dict[str, object]) -> List[str]:
    """Read a job's skills from either the canonical or the legacy metadata shape.

    New rows carry ``skills_list`` (a real list). Legacy rows carry ``skills``
    as a space-joined blob. Both must produce the same canonical tokens or
    BM25, the graph and the scorer disagree about what a job requires.
    """
    listed = metadata.get("skills_list")
    if isinstance(listed, (list, tuple)) and listed:
        return normalize_skills(listed)
    raw = metadata.get("skills")
    if isinstance(raw, (list, tuple)):
        return normalize_skills(raw)
    if isinstance(raw, str) and raw.strip():
        return parse_skill_blob(raw)
    return []
