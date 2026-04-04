"""
main.py — Coordinateur du pipeline YouTube
Chaîne : Biographies de femmes historiques oubliées

Usage :
  python main.py --slug "ada-lovelace" --name "Ada Lovelace"
  python main.py --slug "ada-lovelace" --name "Ada Lovelace" --stage research
  python main.py --list-pending
  python main.py --retry-failed
"""

import argparse
import sqlite3
import json
import os
import time
import logging
from datetime import datetime
from pathlib import Path

import structlog

# ── Configuration ────────────────────────────────────────────────────────────

DB_PATH = os.getenv("PIPELINE_DB_PATH", "config/pipeline.db")
KB_PATH = os.getenv("KNOWLEDGE_BASE_PATH", "knowledge_base")
LOG_PATH = os.getenv("LOG_PATH", "logs")

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# ── Base de données ───────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS subjects (
            slug             TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            status           TEXT DEFAULT 'pending',
            confidence_score INTEGER,
            llm_source       TEXT,
            fact_check_verdict TEXT,
            youtube_url      TEXT,
            error_message    TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            slug         TEXT REFERENCES subjects(slug),
            stage        TEXT,
            duration_sec REAL,
            success      BOOLEAN,
            error        TEXT,
            ran_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def update_status(slug: str, status: str, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values())
    if fields:
        conn.execute(
            f"UPDATE subjects SET status = ?, {fields}, updated_at = ? WHERE slug = ?",
            [status] + values + [datetime.now(), slug]
        )
    else:
        conn.execute(
            "UPDATE subjects SET status = ?, updated_at = ? WHERE slug = ?",
            [status, datetime.now(), slug]
        )
    conn.commit()
    conn.close()

# ── Stages du pipeline ────────────────────────────────────────────────────────

def stage_research(slug: str, name: str) -> bool:
    """Scraping Wikipedia + sources académiques → knowledge_base"""
    log.info("stage_start", stage="research", slug=slug)
    start = time.time()
    try:
        # TODO : importer et appeler 01-research/scraper.py
        # from research.scraper import run_research
        # run_research(slug=slug, name=name)
        log.info("stage_done", stage="research", slug=slug,
                 duration_sec=round(time.time() - start, 1))
        update_status(slug, "research_done")
        return True
    except Exception as e:
        log.error("stage_error", stage="research", slug=slug, error=str(e))
        update_status(slug, "error", error_message=f"research: {e}")
        return False

def stage_script(slug: str, name: str) -> bool:
    """Génération script Gemini 2 passes + fact-check + routage"""
    log.info("stage_start", stage="script", slug=slug)
    start = time.time()
    try:
        # TODO : importer et appeler 02-scripts/generator.py
        # from scripts.generator import generate_and_route
        # result = generate_and_route(slug=slug, name=name)
        # update_status(slug, result["status"],
        #               confidence_score=result["score"],
        #               llm_source=result["source"])
        log.info("stage_done", stage="script", slug=slug,
                 duration_sec=round(time.time() - start, 1))
        return True
    except Exception as e:
        log.error("stage_error", stage="script", slug=slug, error=str(e))
        update_status(slug, "error", error_message=f"script: {e}")
        return False

def stage_assets(slug: str) -> bool:
    """Génération images ComfyUI + voix off TTS"""
    log.info("stage_start", stage="assets", slug=slug)
    start = time.time()
    try:
        # TODO : appel API FastAPI worker pour ComfyUI (async)
        # TODO : génération voix off + sound design
        log.info("stage_done", stage="assets", slug=slug,
                 duration_sec=round(time.time() - start, 1))
        update_status(slug, "assets_done")
        return True
    except Exception as e:
        log.error("stage_error", stage="assets", slug=slug, error=str(e))
        update_status(slug, "error", error_message=f"assets: {e}")
        return False

def stage_edit(slug: str) -> bool:
    """Montage FFmpeg — Ken Burns + transitions + sous-titres"""
    log.info("stage_start", stage="edit", slug=slug)
    start = time.time()
    try:
        # TODO : importer et appeler 04-edit/editor.py
        log.info("stage_done", stage="edit", slug=slug,
                 duration_sec=round(time.time() - start, 1))
        update_status(slug, "edit_done")
        return True
    except Exception as e:
        log.error("stage_error", stage="edit", slug=slug, error=str(e))
        update_status(slug, "error", error_message=f"edit: {e}")
        return False

def stage_upload(slug: str) -> bool:
    """Upload YouTube + notification Telegram"""
    log.info("stage_start", stage="upload", slug=slug)
    start = time.time()
    try:
        # TODO : importer et appeler 05-upload/uploader.py
        log.info("stage_done", stage="upload", slug=slug,
                 duration_sec=round(time.time() - start, 1))
        update_status(slug, "done")
        return True
    except Exception as e:
        log.error("stage_error", stage="upload", slug=slug, error=str(e))
        update_status(slug, "error", error_message=f"upload: {e}")
        return False

# ── Coordinateur principal ────────────────────────────────────────────────────

STAGES = [
    ("research", stage_research),
    ("script",   stage_script),
    ("assets",   stage_assets),
    ("edit",     stage_edit),
    ("upload",   stage_upload),
]

def run_pipeline(slug: str, name: str, start_stage: str = "research"):
    """Lance le pipeline complet ou depuis un stage spécifique."""
    init_db()

    # Enregistrer le sujet si nouveau
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO subjects (slug, name) VALUES (?, ?)",
        (slug, name)
    )
    conn.commit()
    conn.close()

    log.info("pipeline_start", slug=slug, name=name, start_stage=start_stage)
    pipeline_start = time.time()

    active = False
    for stage_name, stage_fn in STAGES:
        if stage_name == start_stage:
            active = True
        if not active:
            continue

        if stage_name in ("research", "script"):
            success = stage_fn(slug, name)
        else:
            success = stage_fn(slug)

        if not success:
            log.error("pipeline_aborted", slug=slug, failed_stage=stage_name)
            return False

    total = round(time.time() - pipeline_start, 1)
    log.info("pipeline_complete", slug=slug, total_sec=total)
    return True

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pipeline YouTube — Coordinateur")
    parser.add_argument("--slug",  help="Identifiant URL (ex: ada-lovelace)")
    parser.add_argument("--name",  help="Nom complet (ex: Ada Lovelace)")
    parser.add_argument("--stage", help="Stage de départ", default="research",
                        choices=[s[0] for s in STAGES])
    parser.add_argument("--list-pending",  action="store_true")
    parser.add_argument("--retry-failed",  action="store_true")
    args = parser.parse_args()

    init_db()

    if args.list_pending:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT slug, name, status, confidence_score FROM subjects "
            "WHERE status NOT IN ('done', 'rejected') ORDER BY created_at"
        ).fetchall()
        for row in rows:
            print(f"{row[1]:30} | {row[2]:20} | score: {row[3]}")
        conn.close()
        return

    if args.retry_failed:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT slug, name FROM subjects WHERE status = 'error'"
        ).fetchall()
        conn.close()
        for slug, name in rows:
            print(f"Relance : {name}")
            update_status(slug, "pending")
            run_pipeline(slug, name)
        return

    if args.slug and args.name:
        run_pipeline(args.slug, args.name, start_stage=args.stage)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
