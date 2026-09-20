"""Graph retrieval over the job/skill graph.

The graph is an *additional* signal, never a replacement for vector search.
It answers the relational questions embeddings are bad at:

* which jobs require the skills I actually have,
* which jobs require skills *related* to mine (one hop through ``RELATED_TO``),
* which skills am I missing for the roles I want,
* which companies keep hiring for my skill set.

Neo4j is used when it is reachable. When it is not, an equivalent in-process
index is built from the job store and the pipeline carries on — a missing graph
database degrades the ranking slightly, it does not break retrieval.

Model::

    (User)-[:HAS_SKILL]->(Skill)
    (Job)-[:REQUIRES]->(Skill)      (Job)-[:PREFERS]->(Skill)
    (Job)-[:OFFERED_BY]->(Company)  (Job)-[:LOCATED_IN]->(Location)
    (Job)-[:BELONGS_TO]->(Role)     (Skill)-[:RELATED_TO]->(Skill)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from jobai.config import get_settings
from jobai.normalize.skills import RELATED_SKILLS, normalize_skills, skills_from_metadata

logger = logging.getLogger(__name__)


def _job_skills(metadata: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    required = metadata.get("required_skills") or []
    preferred = metadata.get("preferred_skills") or []
    required = normalize_skills(required) or skills_from_metadata(metadata)
    preferred = normalize_skills(preferred)
    return required, preferred


class InMemoryJobGraph:
    """The fallback graph. Same query surface as the Neo4j backend."""

    def __init__(self) -> None:
        self.skill_to_jobs: Dict[str, List[str]] = defaultdict(list)
        self.job_to_required: Dict[str, List[str]] = {}
        self.job_to_preferred: Dict[str, List[str]] = {}
        self.job_to_meta: Dict[str, Dict[str, Any]] = {}
        self.company_to_jobs: Dict[str, List[str]] = defaultdict(list)
        self.role_to_jobs: Dict[str, List[str]] = defaultdict(list)

    def build(self, metadatas: Sequence[Dict[str, Any]]) -> "InMemoryJobGraph":
        self.__init__()  # reset
        for metadata in metadatas:
            job_id = str(metadata.get("job_id") or metadata.get("id") or "")
            if not job_id:
                continue
            required, preferred = _job_skills(metadata)
            self.job_to_required[job_id] = required
            self.job_to_preferred[job_id] = preferred
            self.job_to_meta[job_id] = metadata
            for skill in set(required + preferred):
                self.skill_to_jobs[skill].append(job_id)
            company = str(metadata.get("company_name") or metadata.get("company") or "").strip().lower()
            if company:
                self.company_to_jobs[company].append(job_id)
            role = str(metadata.get("job_category") or metadata.get("job_type") or "").strip().lower()
            if role:
                self.role_to_jobs[role].append(job_id)
        logger.info(
            "Built in-memory job graph: %d jobs, %d skills", len(self.job_to_meta), len(self.skill_to_jobs)
        )
        return self

    def search(self, skills: Sequence[str], k: int = 100, related_weight: float = 0.4):
        """Score jobs by weighted skill overlap, direct hits worth more than related ones."""
        user_skills = set(normalize_skills(skills))
        if not user_skills:
            return []
        related: Dict[str, float] = {}
        for skill in user_skills:
            for neighbour in RELATED_SKILLS.get(skill, []):
                if neighbour not in user_skills:
                    related[neighbour] = related_weight
            for other, neighbours in RELATED_SKILLS.items():
                if skill in neighbours and other not in user_skills:
                    related.setdefault(other, related_weight)

        scores: Dict[str, float] = defaultdict(float)
        for skill in user_skills:
            for job_id in self.skill_to_jobs.get(skill, []):
                weight = 1.0 if skill in self.job_to_required.get(job_id, []) else 0.6
                scores[job_id] += weight
        for skill, weight in related.items():
            for job_id in self.skill_to_jobs.get(skill, []):
                scores[job_id] += weight * 0.6

        results = []
        for job_id, raw in scores.items():
            required = self.job_to_required.get(job_id, [])
            # Normalize by the job's own requirement count so a job asking for
            # 3 skills you have beats one asking for 30 of which you have 3.
            denominator = max(len(required), 1)
            results.append((self.job_to_meta[job_id], min(1.0, raw / denominator)))
        results.sort(key=lambda item: item[1], reverse=True)
        return results[:k]

    def missing_skills(self, skills: Sequence[str], job_id: str) -> List[str]:
        have = set(normalize_skills(skills))
        return [s for s in self.job_to_required.get(str(job_id), []) if s not in have]

    def companies_hiring(self, skills: Sequence[str], limit: int = 10) -> List[Tuple[str, int]]:
        user_skills = set(normalize_skills(skills))
        counts: Dict[str, int] = defaultdict(int)
        for company, job_ids in self.company_to_jobs.items():
            for job_id in job_ids:
                if user_skills & set(self.job_to_required.get(job_id, [])):
                    counts[company] += 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    def save(self, path: Path) -> None:
        """Persist just the fields the graph needs.

        ``default=str`` because legacy metadata can carry a raw ``datetime``
        in ``Posted_date``; the graph never reads it, so stringifying is fine.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        slim = [
            {
                "job_id": job_id,
                "job_title": meta.get("job_title") or meta.get("title"),
                "company_name": meta.get("company_name") or meta.get("company"),
                "location": meta.get("location"),
                "job_category": meta.get("job_category") or meta.get("job_type"),
                "skills_list": self.job_to_required.get(job_id, []),
                "preferred_skills": self.job_to_preferred.get(job_id, []),
            }
            for job_id, meta in self.job_to_meta.items()
        ]
        path.write_text(json.dumps({"jobs": slim}, default=str), encoding="utf-8")

    def load(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load graph fallback: %s", exc)
            return False
        self.build(payload.get("jobs", []))
        return True


class Neo4jJobGraph:
    """Neo4j backend. Constructed only when a driver connection succeeds."""

    def __init__(self, uri: str, user: str, password: str, database: str):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        self.database = database

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:
            pass

    def ensure_constraints(self) -> None:
        statements = [
            "CREATE CONSTRAINT job_id IF NOT EXISTS FOR (j:Job) REQUIRE j.job_id IS UNIQUE",
            "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT company_name IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT location_name IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE",
            "CREATE CONSTRAINT role_name IF NOT EXISTS FOR (r:Role) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.chat_id IS UNIQUE",
        ]
        with self._driver.session(database=self.database) as session:
            for statement in statements:
                session.run(statement)

    def upsert_jobs(self, metadatas: Sequence[Dict[str, Any]], batch_size: int = 200) -> int:
        rows = []
        for metadata in metadatas:
            job_id = str(metadata.get("job_id") or metadata.get("id") or "")
            if not job_id:
                continue
            required, preferred = _job_skills(metadata)
            rows.append(
                {
                    "job_id": job_id,
                    "title": metadata.get("job_title") or metadata.get("title") or "",
                    "company": (metadata.get("company_name") or metadata.get("company") or "").strip(),
                    "location": (metadata.get("location") or "").strip(),
                    "role": (metadata.get("job_category") or metadata.get("job_type") or "").strip(),
                    "required": required,
                    "preferred": preferred,
                    "content_hash": metadata.get("content_hash") or "",
                }
            )
        query = """
        UNWIND $rows AS row
        MERGE (j:Job {job_id: row.job_id})
          SET j.title = row.title, j.content_hash = row.content_hash
        WITH j, row
        FOREACH (_ IN CASE WHEN row.company <> '' THEN [1] ELSE [] END |
          MERGE (c:Company {name: row.company}) MERGE (j)-[:OFFERED_BY]->(c))
        FOREACH (_ IN CASE WHEN row.location <> '' THEN [1] ELSE [] END |
          MERGE (l:Location {name: row.location}) MERGE (j)-[:LOCATED_IN]->(l))
        FOREACH (_ IN CASE WHEN row.role <> '' THEN [1] ELSE [] END |
          MERGE (r:Role {name: row.role}) MERGE (j)-[:BELONGS_TO]->(r))
        FOREACH (skill IN row.required |
          MERGE (s:Skill {name: skill}) MERGE (j)-[:REQUIRES]->(s))
        FOREACH (skill IN row.preferred |
          MERGE (s:Skill {name: skill}) MERGE (j)-[:PREFERS]->(s))
        """
        written = 0
        with self._driver.session(database=self.database) as session:
            for start in range(0, len(rows), batch_size):
                chunk = rows[start : start + batch_size]
                session.run(query, rows=chunk)
                written += len(chunk)
        return written

    def upsert_skill_graph(self) -> None:
        pairs = [
            {"a": a, "b": b}
            for a, neighbours in RELATED_SKILLS.items()
            for b in neighbours
        ]
        query = """
        UNWIND $pairs AS pair
        MERGE (a:Skill {name: pair.a})
        MERGE (b:Skill {name: pair.b})
        MERGE (a)-[:RELATED_TO]->(b)
        MERGE (b)-[:RELATED_TO]->(a)
        """
        with self._driver.session(database=self.database) as session:
            session.run(query, pairs=pairs)

    def upsert_user(self, chat_id: Any, skills: Sequence[str]) -> None:
        query = """
        MERGE (u:User {chat_id: $chat_id})
        WITH u
        OPTIONAL MATCH (u)-[old:HAS_SKILL]->(:Skill)
        DELETE old
        WITH u
        UNWIND $skills AS skill
        MERGE (s:Skill {name: skill})
        MERGE (u)-[:HAS_SKILL]->(s)
        """
        with self._driver.session(database=self.database) as session:
            session.run(query, chat_id=str(chat_id), skills=normalize_skills(skills))

    def search(self, skills: Sequence[str], k: int = 100, related_weight: float = 0.4):
        """Weighted skill overlap, one hop through RELATED_TO, scored in Cypher."""
        user_skills = normalize_skills(skills)
        if not user_skills:
            return []
        query = """
        UNWIND $skills AS skill
        MATCH (s:Skill {name: skill})
        OPTIONAL MATCH (s)-[:RELATED_TO]->(rel:Skill)
        WITH collect(DISTINCT s.name) AS direct, collect(DISTINCT rel.name) AS related
        WITH direct, [x IN related WHERE NOT x IN direct] AS related
        MATCH (j:Job)-[r:REQUIRES|PREFERS]->(s:Skill)
        WHERE s.name IN direct OR s.name IN related
        WITH j,
             sum(CASE WHEN s.name IN direct AND type(r) = 'REQUIRES' THEN 1.0
                      WHEN s.name IN direct THEN 0.6
                      WHEN type(r) = 'REQUIRES' THEN $related_weight
                      ELSE $related_weight * 0.6 END) AS raw
        MATCH (j)-[:REQUIRES]->(req:Skill)
        WITH j, raw, count(req) AS req_count
        RETURN j.job_id AS job_id, raw / (CASE WHEN req_count = 0 THEN 1 ELSE req_count END) AS score
        ORDER BY score DESC LIMIT $k
        """
        with self._driver.session(database=self.database) as session:
            records = session.run(query, skills=user_skills, related_weight=related_weight, k=k)
            return [(str(r["job_id"]), min(1.0, float(r["score"]))) for r in records]

    def missing_skills(self, skills: Sequence[str], job_id: str) -> List[str]:
        query = """
        MATCH (j:Job {job_id: $job_id})-[:REQUIRES]->(s:Skill)
        WHERE NOT s.name IN $skills
        RETURN s.name AS name
        """
        with self._driver.session(database=self.database) as session:
            return [r["name"] for r in session.run(query, job_id=str(job_id), skills=normalize_skills(skills))]

    def companies_hiring(self, skills: Sequence[str], limit: int = 10) -> List[Tuple[str, int]]:
        query = """
        MATCH (j:Job)-[:REQUIRES]->(s:Skill) WHERE s.name IN $skills
        MATCH (j)-[:OFFERED_BY]->(c:Company)
        RETURN c.name AS company, count(DISTINCT j) AS jobs
        ORDER BY jobs DESC LIMIT $limit
        """
        with self._driver.session(database=self.database) as session:
            return [(r["company"], int(r["jobs"])) for r in session.run(
                query, skills=normalize_skills(skills), limit=limit)]


class JobGraph:
    """Facade that prefers Neo4j and silently falls back to the in-memory graph."""

    def __init__(self, metadatas: Optional[Sequence[Dict[str, Any]]] = None, allow_neo4j: bool = True):
        settings = get_settings()
        self.settings = settings.graph
        self.backend: Optional[Neo4jJobGraph] = None
        self.fallback = InMemoryJobGraph()
        self._meta_by_id: Dict[str, Dict[str, Any]] = {}

        if allow_neo4j and settings.retrieval.graph_enabled:
            try:
                self.backend = Neo4jJobGraph(
                    self.settings.uri, self.settings.user, self.settings.password, self.settings.database
                )
                logger.info("Connected to Neo4j at %s", self.settings.uri)
            except Exception as exc:
                logger.info("Neo4j unavailable (%s); using the in-memory job graph.", exc)
                self.backend = None

        if metadatas is not None:
            self.build(metadatas)
        elif not self.fallback.job_to_meta:
            self.fallback.load(self.settings.fallback_path)
            self._meta_by_id = dict(self.fallback.job_to_meta)

    @property
    def using_neo4j(self) -> bool:
        return self.backend is not None

    def build(self, metadatas: Sequence[Dict[str, Any]]) -> "JobGraph":
        self.fallback.build(metadatas)
        self._meta_by_id = dict(self.fallback.job_to_meta)
        if self.backend is not None:
            try:
                self.backend.ensure_constraints()
                self.backend.upsert_skill_graph()
                count = self.backend.upsert_jobs(metadatas)
                logger.info("Upserted %d jobs into Neo4j", count)
            except Exception as exc:
                logger.warning("Neo4j write failed (%s); keeping the in-memory graph.", exc)
                self.backend = None
        # Persisting is a cache optimisation; never let it break the build.
        try:
            self.fallback.save(self.settings.fallback_path)
        except Exception as exc:
            logger.debug("Could not persist graph fallback: %s", exc)
        return self

    def search(self, skills: Sequence[str], k: int = 100) -> List[Tuple[Dict[str, Any], float]]:
        if self.backend is not None:
            try:
                pairs = self.backend.search(skills, k=k)
                resolved = [
                    (self._meta_by_id[job_id], score)
                    for job_id, score in pairs
                    if job_id in self._meta_by_id
                ]
                if resolved:
                    return resolved
                logger.debug("Neo4j returned no resolvable jobs; using the in-memory graph.")
            except Exception as exc:
                logger.warning("Neo4j search failed (%s); using the in-memory graph.", exc)
        return self.fallback.search(skills, k=k)

    def missing_skills(self, skills: Sequence[str], job_id: str) -> List[str]:
        if self.backend is not None:
            try:
                return self.backend.missing_skills(skills, job_id)
            except Exception:
                pass
        return self.fallback.missing_skills(skills, job_id)

    def companies_hiring(self, skills: Sequence[str], limit: int = 10) -> List[Tuple[str, int]]:
        if self.backend is not None:
            try:
                return self.backend.companies_hiring(skills, limit=limit)
            except Exception:
                pass
        return self.fallback.companies_hiring(skills, limit=limit)

    def upsert_user(self, chat_id: Any, skills: Sequence[str]) -> None:
        if self.backend is not None:
            try:
                self.backend.upsert_user(chat_id, skills)
            except Exception as exc:
                logger.debug("Neo4j user upsert failed: %s", exc)
