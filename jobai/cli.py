"""JOB.ai command line.

    python -m jobai doctor                       # check Ollama / Mongo / FAISS / graph
    python -m jobai ingest --sources linkedin naukri --limit 50
    python -m jobai migrate                      # normalize existing data, no re-scrape
    python -m jobai reindex                      # rebuild BM25 + graph from FAISS
    python -m jobai search "GenAI Engineer" --skills Python PyTorch LangChain
    python -m jobai recommend --chat-id 7748640302
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from jobai.config import get_settings


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else getattr(logging, get_settings().log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )


# --------------------------------------------------------------------- doctor


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = get_settings()
    report: Dict[str, Any] = {}
    failures = 0

    # Ollama
    try:
        from jobai.llm import get_llm

        report["ollama"] = get_llm().health()
        if not report["ollama"]["model_installed"]:
            report["ollama"]["hint"] = f"ollama pull {settings.llm.model}"
            failures += 1
    except Exception as exc:
        report["ollama"] = {"reachable": False, "error": str(exc)}
        failures += 1

    # MongoDB
    try:
        from jobai.store import get_store

        store = get_store()
        ok = store.ping()
        report["mongodb"] = {"reachable": ok, "uri": _redact(store.uri)}
        if ok:
            report["mongodb"]["jobs"] = store.jobs.estimated_document_count()
            report["mongodb"]["users"] = store.users.estimated_document_count()
        else:
            failures += 1
    except Exception as exc:
        report["mongodb"] = {"reachable": False, "error": str(exc)}
        failures += 1

    # FAISS
    try:
        from jobai.retrieval.dense import DenseIndex

        dense = DenseIndex()
        report["faiss"] = {
            "path": str(dense.path),
            "exists": dense.exists(),
            "vectors": dense.count() if dense.exists() else 0,
            "embedding_model": settings.retrieval.embedding_model,
        }
        if not dense.exists():
            failures += 1
    except Exception as exc:
        report["faiss"] = {"error": str(exc)}
        failures += 1

    # Reranker
    try:
        from jobai.retrieval.rerank import get_reranker

        report["reranker"] = {
            "model": settings.retrieval.reranker_model,
            "loaded": get_reranker() is not None,
        }
    except Exception as exc:
        report["reranker"] = {"error": str(exc)}

    # Graph
    try:
        from jobai.retrieval.graph import JobGraph

        graph = JobGraph(allow_neo4j=True)
        report["graph"] = {
            "backend": "neo4j" if graph.using_neo4j else "in-memory (fallback)",
            "uri": settings.graph.uri,
            "jobs": len(graph.fallback.job_to_meta),
        }
    except Exception as exc:
        report["graph"] = {"error": str(exc)}

    print(json.dumps(report, indent=2))
    if failures:
        print(f"\n{failures} component(s) need attention. See README 'Local setup'.", file=sys.stderr)
    return 1 if failures else 0


def cmd_sources(args: argparse.Namespace) -> int:
    """List every source and group that ``ingest --sources`` accepts."""
    from jobai.ingest.runner import SOURCE_GROUPS, available_sources

    descriptions = {
        "linkedin": "LinkedIn public guest job search (HTTP)",
        "naukri": "Naukri public search pages (Playwright, needs a headed browser)",
        "greenhouse": "Greenhouse company boards (ATS_GREENHOUSE)",
        "lever": "Lever company boards (ATS_LEVER)",
        "ashby": "Ashby company boards (ATS_ASHBY)",
        "smartrecruiters": "SmartRecruiters company boards (ATS_SMARTRECRUITERS)",
        "workable": "Workable company boards (ATS_WORKABLE)",
        "recruitee": "Recruitee company boards (ATS_RECRUITEE)",
        "remoteok": "RemoteOK public feed",
        "remotive": "Remotive public feed",
        "arbeitnow": "Arbeitnow public feed",
        "himalayas": "Himalayas public feed",
        "jobicy": "Jobicy public feed",
        "weworkremotely": "We Work Remotely RSS",
        "mongo_archive": "Re-read jobs already in MongoDB (migration)",
        "faiss_archive": "Re-read jobs already in the FAISS index (migration)",
    }
    print("Sources:")
    for name in available_sources():
        print(f"  {name:<18} {descriptions.get(name, '')}")
    print("\nGroups:")
    for group, members in SOURCE_GROUPS.items():
        print(f"  {group:<18} {', '.join(members)}")
    print("\nExample:  python -m jobai ingest --sources ats boards --limit 50")
    return 0


# --------------------------------------------------------------------- ingest


def cmd_ingest(args: argparse.Namespace) -> int:
    from jobai.ingest.runner import ingest

    report = ingest(
        args.sources,
        limit_per_source=args.limit,
        semantic_dedup=args.semantic_dedup,
        write_store=not args.no_store,
        build_index=not args.no_index,
    )
    print(json.dumps(report, indent=2, default=str))
    failed = [n for n, s in report.get("sources", {}).items() if not s.get("ok")]
    if failed:
        print(f"\nSources that failed (others still ran): {', '.join(failed)}", file=sys.stderr)
    return 0 if report.get("harvested") else 1


def cmd_migrate(args: argparse.Namespace) -> int:
    """Normalize what is already stored, without scraping anything new."""
    from jobai.ingest.runner import ingest

    source = "mongo_archive" if args.source == "mongo" else "faiss_archive"
    report = ingest([source], limit_per_source=args.limit, write_store=True, build_index=True)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("harvested") else 1


def cmd_reindex(args: argparse.Namespace) -> int:
    from jobai.index_builder import rebuild_derived_indexes

    print(json.dumps(rebuild_derived_indexes(), indent=2))
    return 0


# --------------------------------------------------------------------- search


def cmd_search(args: argparse.Namespace) -> int:
    from jobai.recommend import recommend_for_profile
    from jobai.retrieval.filters import JobFilter

    profile = {
        "target_roles": args.roles or ([args.query] if args.query else []),
        "skills": args.skills or [],
        "years_experience": args.experience,
        "preferred_locations": args.locations or [],
    }
    job_filter = JobFilter(
        locations=args.locations or [],
        experience_years=args.experience,
        remote=args.remote,
        posted_within_days=args.within_days,
    )
    outcome = recommend_for_profile(
        profile, query=args.query, top_k=args.top_k, job_filter=job_filter, explain=args.explain
    )
    _print_jobs(outcome, args.json)
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    from jobai.recommend import recommend_for_user

    outcome = recommend_for_user(
        args.chat_id, query=args.query, top_k=args.top_k, explain=args.explain, persist=not args.dry_run
    )
    _print_jobs(outcome, args.json)
    return 0


def _print_jobs(outcome: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(outcome, indent=2, default=str))
        return
    diagnostics = outcome.get("diagnostics", {})
    print(f"Funnel: {diagnostics.get('stages')}  graph={diagnostics.get('graph_backend')}  "
          f"reranked={diagnostics.get('reranked')}")
    for position, job in enumerate(outcome.get("jobs", []), start=1):
        metadata = job.get("metadata", {})
        print(f"\n{position}. [{job.get('match_score'):.3f}] {metadata.get('job_title')} "
              f"@ {metadata.get('company_name')}")
        print(f"   {metadata.get('location')} | {metadata.get('experience')} | {metadata.get('Source')}")
        print(f"   {metadata.get('job_link')}")
        print(f"   why: {', '.join(job.get('explanation', []))}")
        if job.get("llm_verdict"):
            print(f"   qwen: {job['llm_verdict']}")
        if job.get("missing_skills"):
            print(f"   gaps: {', '.join(job['missing_skills'][:6])}")


def _redact(uri: str) -> str:
    import re

    return re.sub(r"://[^@/]+@", "://***@", uri or "")


# ----------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobai", description="JOB.ai command line")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="check every local component").set_defaults(func=cmd_doctor)
    subparsers.add_parser("sources", help="list every job source and group").set_defaults(func=cmd_sources)

    ingest_parser = subparsers.add_parser("ingest", help="scrape, normalize, dedup, store and index")
    ingest_parser.add_argument(
        "--sources", nargs="*", default=None,
        help="source or group names; run `python -m jobai sources` to list them",
    )
    ingest_parser.add_argument("--limit", type=int, default=None, help="max jobs per source")
    ingest_parser.add_argument("--semantic-dedup", action="store_true")
    ingest_parser.add_argument("--no-store", action="store_true", help="skip the MongoDB write")
    ingest_parser.add_argument("--no-index", action="store_true", help="skip the FAISS update")
    ingest_parser.set_defaults(func=cmd_ingest)

    migrate_parser = subparsers.add_parser("migrate", help="normalize existing data in place")
    migrate_parser.add_argument("--source", choices=["mongo", "faiss"], default="faiss")
    migrate_parser.add_argument("--limit", type=int, default=None)
    migrate_parser.set_defaults(func=cmd_migrate)

    subparsers.add_parser("reindex", help="rebuild BM25 and the graph from FAISS").set_defaults(func=cmd_reindex)

    search_parser = subparsers.add_parser("search", help="ad-hoc hybrid search")
    search_parser.add_argument("query")
    search_parser.add_argument("--skills", nargs="*", default=None)
    search_parser.add_argument("--roles", nargs="*", default=None)
    search_parser.add_argument("--locations", nargs="*", default=None)
    search_parser.add_argument("--experience", type=float, default=None)
    search_parser.add_argument("--remote", action="store_true", default=None)
    search_parser.add_argument("--within-days", type=int, default=None)
    search_parser.add_argument("--top-k", type=int, default=10)
    search_parser.add_argument("--explain", action="store_true", help="add Qwen reasoning")
    search_parser.add_argument("--json", action="store_true")
    search_parser.set_defaults(func=cmd_search)

    recommend_parser = subparsers.add_parser("recommend", help="recommend for a registered user")
    recommend_parser.add_argument("--chat-id", required=True)
    recommend_parser.add_argument("--query", default=None)
    recommend_parser.add_argument("--top-k", type=int, default=20)
    recommend_parser.add_argument("--explain", action="store_true")
    recommend_parser.add_argument("--dry-run", action="store_true", help="do not persist")
    recommend_parser.add_argument("--json", action="store_true")
    recommend_parser.set_defaults(func=cmd_recommend)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.getLogger("jobai").error("%s: %s", type(exc).__name__, exc)
        if args.verbose:
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
