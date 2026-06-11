from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import threading
import time
import traceback
import uuid
import zipfile
from queue import Queue
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None

try:
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub
except Exception:  # pragma: no cover
    ebooklib = None
    BeautifulSoup = None
    epub = None

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

try:
    from rapidocr import RapidOCR
except Exception:  # pragma: no cover
    RapidOCR = None


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("SERVER_DATA_DIR", BASE_DIR / "server_data"))
ORIGINALS_DIR = Path(os.getenv("ORIGINAL_FILES_DIR", DATA_DIR / "originals"))
DERIVED_DIR = Path(os.getenv("DERIVED_DATA_DIR", DATA_DIR / "derived"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", DATA_DIR / "backups"))
DB_PATH = DATA_DIR / "metadata.db"
STAGES = [
    "upload",
    "metadata",
    "layout_analysis",
    "ocr",
    "image_extract",
    "image_caption",
    "image_embedding",
    "table_extract",
    "formula_extract",
    "chunk",
    "text_embedding",
    "rerank_ready",
    "index",
    "ai_suggestion",
    "done",
]
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".jpg", ".jpeg", ".png", ".epub"}
OCR_MIN_TEXT_CHARS = int(os.getenv("OCR_MIN_TEXT_CHARS", "30"))
OCR_ENGINE_NAME = "RapidOCR"
_OCR_ENGINE = None
_OCR_INIT_FAILED = False
MINERU_ENABLED = os.getenv("MINERU_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
MINERU_METHOD = os.getenv("MINERU_METHOD", "ocr")
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")
MINERU_LANG = os.getenv("MINERU_LANG", "chinese_cht")
MINERU_FORMULA = os.getenv("MINERU_FORMULA", "true").lower() in {"1", "true", "yes", "on"}
MINERU_TABLE = os.getenv("MINERU_TABLE", "true").lower() in {"1", "true", "yes", "on"}
MINERU_TIMEOUT_SECONDS = int(os.getenv("MINERU_TIMEOUT_SECONDS", "0"))
MINERU_MODEL_SOURCE = os.getenv("MINERU_MODEL_SOURCE", "huggingface")
IMAGE_EMBEDDING_ENABLED = os.getenv("IMAGE_EMBEDDING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
IMAGE_EMBEDDING_MODEL = os.getenv("IMAGE_EMBEDDING_MODEL") or "openai/clip-vit-base-patch32"
IMAGE_CAPTION_ENABLED = os.getenv("IMAGE_CAPTION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
IMAGE_CAPTION_MODEL = os.getenv("IMAGE_CAPTION_MODEL") or "Salesforce/blip-image-captioning-base"
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "")
MAX_CONCURRENT_FILE_JOBS = max(1, int(os.getenv("MAX_CONCURRENT_FILE_JOBS", "1")))
JOB_QUEUE_POLL_SECONDS = float(os.getenv("JOB_QUEUE_POLL_SECONDS", "1"))
_IMAGE_EMBEDDER = None
_IMAGE_EMBEDDER_FAILED = False
_IMAGE_CAPTIONER = None
_IMAGE_CAPTIONER_FAILED = False
_JOB_QUEUE: Queue[str] = Queue()
_JOB_QUEUE_IDS: set[str] = set()
_JOB_QUEUE_LOCK = threading.Lock()
_JOB_WORKERS_STARTED = False
_JOB_STOP = threading.Event()


app = FastAPI(title="Evidence-First Knowledge Engine", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/health", "/auth/login", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/assets/") or path.startswith("/static/") or path in PUBLIC_PATHS:
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if token:
        session = one("SELECT * FROM sessions WHERE token=?", (token,))
        if not session:
            return await call_next(request)
        try:
            expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                with db() as conn:
                    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        except Exception:
            pass
    return await call_next(request)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for path in (DATA_DIR, ORIGINALS_DIR, DERIVED_DIR, BACKUP_DIR):
        path.mkdir(parents=True, exist_ok=True)


def db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with db() as conn:
        return rowdict(conn.execute(query, params).fetchone())


def init_db() -> None:
    ensure_dirs()
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                template TEXT NOT NULL,
                source_rank TEXT NOT NULL DEFAULT 'A',
                settings_json TEXT NOT NULL DEFAULT '{}',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                version_id TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY(file_id) REFERENCES files(id)
            );
            CREATE TABLE IF NOT EXISTS job_stages (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                error TEXT,
                processed_count INTEGER NOT NULL DEFAULT 0,
                current_file TEXT,
                log TEXT,
                UNIQUE(job_id, stage),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS blocks (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                block_id TEXT NOT NULL,
                block_type TEXT NOT NULL,
                bbox TEXT,
                reading_order INTEGER NOT NULL,
                source_path TEXT NOT NULL,
                confidence REAL NOT NULL,
                content TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(file_id) REFERENCES files(id)
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                block_ref TEXT NOT NULL,
                file_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                chunk_id TEXT NOT NULL,
                chunk_version TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(block_ref) REFERENCES blocks(id)
            );
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                block_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                path TEXT NOT NULL,
                caption TEXT NOT NULL,
                ocr_text TEXT NOT NULL DEFAULT '',
                embedding_status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_knowledge (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_file_id TEXT,
                source_chunk_id TEXT,
                source_block_id TEXT,
                content TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                model_name TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                model_name TEXT,
                prompt_version TEXT,
                sources_json TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL DEFAULT '{}',
                confidence REAL,
                batch_id TEXT,
                project_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_history (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                project TEXT,
                mode TEXT NOT NULL,
                filters_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                answer TEXT NOT NULL,
                user TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS wiki_pages (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                images_json TEXT NOT NULL DEFAULT '[]',
                model_name TEXT NOT NULL DEFAULT '',
                section_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
            CREATE INDEX IF NOT EXISTS idx_blocks_file ON blocks(file_id);
            """
        )
        username = os.getenv("DEFAULT_USERNAME", "admin")
        if not conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            conn.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), username, sha(os.getenv("DEFAULT_PASSWORD", "12345")), "admin", 1, now()),
            )


def sha(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage(job_id: str, name: str, status: str, log: str = "", count: int = 0, error: str | None = None) -> None:
    stamp = now()
    with db() as conn:
        job = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job["status"] == "removed":
            return
        existing = conn.execute("SELECT id, started_at, status FROM job_stages WHERE job_id=? AND stage=?", (job_id, name)).fetchone()
        if existing:
            reset_stage = status == "processing" and existing["status"] in {"completed", "failed", "not_implemented"}
            conn.execute(
                """UPDATE job_stages SET status=?, started_at=?, ended_at=?, error=?, processed_count=?,
                log=?, current_file=? WHERE id=?""",
                (
                    status,
                    stamp if reset_stage else existing["started_at"],
                    stamp if status in {"completed", "failed", "not_implemented"} else None,
                    error,
                    count,
                    log if reset_stage else (conn.execute("SELECT log FROM job_stages WHERE id=?", (existing["id"],)).fetchone()["log"] or "") + (("\n" + log) if log else ""),
                    log[:240],
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                "INSERT INTO job_stages VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), job_id, name, status, stamp, stamp if status in {"completed", "failed", "not_implemented"} else None, error, count, log[:240], log),
            )
        if status == "processing":
            job_status = "processing"
        elif status == "failed" or name == "failed":
            job_status = "failed"
        elif name == "done" and status == "completed":
            job_status = "done"
        else:
            job_status = job["status"]
        conn.execute("UPDATE jobs SET current_stage=?, status=?, updated_at=?, error=COALESCE(?, error) WHERE id=?", (name, job_status, stamp, error, job_id))


def job_removed(job_id: str) -> bool:
    job = one("SELECT status FROM jobs WHERE id=?", (job_id,))
    return not job or job["status"] == "removed"


def stage_exists(job_id: str, name: str) -> bool:
    return one("SELECT id FROM job_stages WHERE job_id=? AND stage=?", (job_id, name)) is not None


def stage_if_missing(job_id: str, name: str, status: str, log: str = "", count: int = 0) -> None:
    if not stage_exists(job_id, name):
        stage(job_id, name, status, log, count)


def iso_seconds(started_at: str | None, ended_at: str | None = None) -> float:
    if not started_at:
        return 0.0
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat((ended_at or now()).replace("Z", "+00:00"))
        return max(0.0, (end - start).total_seconds())
    except Exception:
        return 0.0


def pct(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, round((value / total) * 100)))


def split_chunks(text: str, size: int = 900, overlap: int = 120) -> list[tuple[int, int, str]]:
    clean = " ".join(text.split())
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        chunks.append((start, end, clean[start:end]))
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def ocr_available() -> bool:
    return get_ocr_engine() is not None


def get_ocr_engine():
    global _OCR_ENGINE, _OCR_INIT_FAILED
    if RapidOCR is None or _OCR_INIT_FAILED:
        return None
    if _OCR_ENGINE is None:
        try:
            _OCR_ENGINE = RapidOCR()
        except Exception:
            _OCR_INIT_FAILED = True
            return None
    return _OCR_ENGINE


def run_ocr(image_path: Path) -> str:
    text, _items = run_ocr_with_items(image_path)
    return text


def run_ocr_with_items(image_path: Path) -> tuple[str, list[dict[str, Any]]]:
    engine = get_ocr_engine()
    if engine is None:
        return "", []
    try:
        result = engine(str(image_path))
    except Exception:
        return "", []
    if hasattr(result, "txts"):
        raw_texts = getattr(result, "txts", None) or []
        texts = [text for text in raw_texts if text]
        boxes = getattr(result, "boxes", None)
        scores = getattr(result, "scores", None)
        boxes = [] if boxes is None else boxes
        scores = [] if scores is None else scores
        items = []
        for index, text in enumerate(texts):
            box = boxes[index] if index < len(boxes) else None
            score = scores[index] if index < len(scores) else None
            items.append(ocr_item(text, box, score))
        return "\n".join(texts).strip(), items
    if isinstance(result, tuple) and result:
        items = result[0] or []
    elif isinstance(result, list):
        items = result
    else:
        items = []
    texts = []
    parsed_items = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            texts.append(str(item[1]))
            parsed_items.append(ocr_item(str(item[1]), item[0], item[2] if len(item) >= 3 else None))
        elif isinstance(item, dict) and item.get("text"):
            texts.append(str(item["text"]))
            parsed_items.append(ocr_item(str(item["text"]), item.get("box") or item.get("bbox"), item.get("score")))
    return "\n".join(texts).strip(), parsed_items


def ocr_item(text: str, box: Any, score: Any = None) -> dict[str, Any]:
    points = []
    try:
        points = [[float(v) for v in point] for point in box]
    except Exception:
        points = []
    xs = [point[0] for point in points if len(point) >= 2]
    ys = [point[1] for point in points if len(point) >= 2]
    return {
        "text": text,
        "x": min(xs) if xs else 0.0,
        "y": min(ys) if ys else 0.0,
        "height": (max(ys) - min(ys)) if ys else 12.0,
        "score": float(score) if score is not None else None,
    }


def insert_text_block(
    conn: sqlite3.Connection,
    file_row: dict[str, Any],
    page_number: int,
    block_id: str,
    block_type: str,
    content: str,
    bbox: Any = None,
    reading_order: int = 1,
    confidence: float = 1.0,
) -> int:
    if not content.strip():
        return 0
    block_pk = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            block_pk,
            file_row["id"],
            file_row["id"],
            file_row["project_id"],
            page_number,
            block_id,
            block_type,
            json.dumps(bbox, ensure_ascii=False) if bbox is not None else None,
            reading_order,
            file_row["source_path"],
            confidence,
            content,
            file_row["source_hash"],
            now(),
        ),
    )
    chunk_count = 0
    for cidx, (start, end, chunk) in enumerate(split_chunks(content), start=1):
        conn.execute(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                block_pk,
                file_row["id"],
                file_row["project_id"],
                page_number,
                f"{block_id}_c{cidx:03d}",
                "chunk-v1",
                start,
                end,
                chunk,
                sha(chunk),
                file_row["source_hash"],
                now(),
            ),
        )
        chunk_count += 1
    return chunk_count


MATH_LINE_RE = re.compile(
    r"(?=.*(?:=|≈|≠|≤|≥|±|√|∑|Σ|∫|π|\^|\\frac|\\sqrt|\\sum|\\int|\\begin|\\end|[A-Za-z]\s*[+\-*/]\s*[A-Za-z0-9]))"
    r"^[\sA-Za-z0-9_.,;:(){}\[\]+\-*/=<>^%|\\≈≠≤≥±√∑Σ∫παβγδθλμσΩ]+$"
)


def extract_formula_lines(text: str) -> list[str]:
    formulas: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = " ".join(raw.strip().split())
        if len(line) < 3 or len(line) > 240:
            continue
        if MATH_LINE_RE.search(line) and not line.endswith(("。", "！", "？")):
            key = line.lower()
            if key not in seen:
                seen.add(key)
                formulas.append(line)
    return formulas


def table_to_markdown(table: list[list[Any]]) -> str:
    if not table:
        return ""
    rows_out = []
    for row in table:
        cells = [str(cell or "").replace("\n", " ").strip() for cell in row]
        if any(cells):
            rows_out.append(cells)
    if not rows_out:
        return ""
    width = max(len(row) for row in rows_out)
    rows_out = [row + [""] * (width - len(row)) for row in rows_out]
    header = rows_out[0]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows_out[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def ocr_items_to_table(items: list[dict[str, Any]]) -> str:
    usable = [item for item in items if item.get("text", "").strip()]
    if len(usable) < 4:
        return ""
    usable.sort(key=lambda item: (item["y"], item["x"]))
    avg_height = sum(max(6.0, item.get("height") or 12.0) for item in usable) / len(usable)
    row_gap = max(10.0, avg_height * 1.4)
    rows_out: list[list[str]] = []
    row_items: list[dict[str, Any]] = []
    current_y: float | None = None
    for item in usable:
        if current_y is None or abs(item["y"] - current_y) <= row_gap:
            row_items.append(item)
            current_y = item["y"] if current_y is None else (current_y + item["y"]) / 2
            continue
        rows_out.append(ocr_row_to_cells(row_items))
        row_items = [item]
        current_y = item["y"]
    if row_items:
        rows_out.append(ocr_row_to_cells(row_items))
    rows_out = [row for row in rows_out if any(cell.strip() for cell in row)]
    if len(rows_out) < 2 or max(len(row) for row in rows_out) < 2:
        return ""
    return table_to_markdown(rows_out)


def ocr_row_to_cells(row_items: list[dict[str, Any]]) -> list[str]:
    cells: list[str] = []
    for item in sorted(row_items, key=lambda value: value["x"]):
        text = item.get("text", "").strip()
        if not text:
            continue
        split_cells = [part.strip() for part in re.split(r"\s{2,}|\t+|\|", text) if part.strip()]
        cells.extend(split_cells or [text])
    return cells


def extract_pdf_tables(page: Any) -> list[tuple[str, Any]]:
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return []
    try:
        result = finder()
    except Exception:
        return []
    tables = getattr(result, "tables", []) or []
    output: list[tuple[str, Any]] = []
    for item in tables:
        try:
            markdown = table_to_markdown(item.extract() or [])
        except Exception:
            markdown = ""
        if markdown:
            output.append((markdown, getattr(item, "bbox", None)))
    return output


def extract_html_tables(soup: Any) -> list[str]:
    tables: list[str] = []
    for table in soup.find_all("table"):
        rows_out = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            if any(cells):
                rows_out.append(cells)
        markdown = table_to_markdown(rows_out)
        if markdown:
            tables.append(markdown)
    return tables


def mineru_command() -> str | None:
    local_cmd = BASE_DIR / ".venv" / "bin" / "mineru"
    if local_cmd.exists() and os.access(local_cmd, os.X_OK):
        return str(local_cmd)
    return shutil.which("mineru")


def mineru_available() -> bool:
    return MINERU_ENABLED and mineru_command() is not None


def bool_arg(value: bool) -> str:
    return "true" if value else "false"


def run_mineru(file_row: dict[str, Any], output_root: Path, job_id: str | None = None, total_pages: int = 0) -> subprocess.CompletedProcess[str]:
    cmd_path = mineru_command()
    if cmd_path is None:
        raise RuntimeError("Server venv 尚未安裝 MinerU，請重新執行 Server install.sh。")
    output_root.mkdir(parents=True, exist_ok=True)
    command = [
        cmd_path,
        "-p",
        file_row["source_path"],
        "-o",
        str(output_root),
        "-m",
        MINERU_METHOD,
        "-b",
        MINERU_BACKEND,
        "-l",
        MINERU_LANG,
        "-f",
        bool_arg(MINERU_FORMULA),
        "-t",
        bool_arg(MINERU_TABLE),
    ]
    env = os.environ.copy()
    venv_bin = str(BASE_DIR / ".venv" / "bin")
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    env["MINERU_MODEL_SOURCE"] = MINERU_MODEL_SOURCE
    env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    process = subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    output_parts: list[str] = []
    started = time.time()
    last_update = 0.0
    assert process.stdout is not None
    try:
        for raw_line in process.stdout:
            output_parts.append(raw_line)
            if job_id:
                last_update = update_mineru_progress(job_id, raw_line, total_pages, last_update)
            if MINERU_TIMEOUT_SECONDS > 0 and time.time() - started > MINERU_TIMEOUT_SECONDS:
                process.kill()
                raise TimeoutError(f"MinerU 執行超過 {MINERU_TIMEOUT_SECONDS} 秒。")
    finally:
        return_code = process.wait()
    return subprocess.CompletedProcess(command, return_code, "".join(output_parts), "")


def update_mineru_progress(job_id: str, line: str, total_pages: int, last_update: float) -> float:
    text = line.replace("\r", "\n")
    now_ts = time.time()
    if now_ts - last_update < 2 and "Completed batch" not in text:
        return last_update
    match = re.search(r"Submitting batch\s+(\d+)/(\d+).*?(\d+) page total", text)
    if match:
        stage(job_id, "ocr", "processing", f"MinerU 已送出第 {match.group(1)}/{match.group(2)} 批，總頁數 {match.group(3)}。", int(match.group(3)))
        return now_ts
    match = re.search(r"Completed batch\s+(\d+)/(\d+).*?Processed\s+(\d+)/(\d+) page", text)
    if match:
        done = int(match.group(3))
        total = int(match.group(4))
        stage(job_id, "ocr", "processing", f"MinerU OCR/版面分析進度：已完成 {done}/{total} 頁。", done)
        stage(job_id, "layout_analysis", "processing", f"MinerU 版面分析進度：已完成批次 {match.group(1)}/{match.group(2)}。", done)
        return now_ts
    match = re.search(r"batch\s+(\d+)/(\d+):\s+(\d+)/(\d+) pages", text)
    if match:
        done = int(match.group(3))
        total = int(match.group(4))
        stage(job_id, "layout_analysis", "processing", f"MinerU 正在分析第 {match.group(1)}/{match.group(2)} 批，頁數 {done}/{total}。", done)
        return now_ts
    if "Layout Predict" in text:
        stage(job_id, "layout_analysis", "processing", "MinerU 正在做版面偵測。", 0)
        return now_ts
    if "OCR-det" in text or "OCR-rec" in text:
        stage(job_id, "ocr", "processing", f"MinerU 正在做 OCR 文字辨識{f'，總頁數 {total_pages}' if total_pages else ''}。", total_pages)
        return now_ts
    if "Table" in text or "table" in text:
        stage(job_id, "table_extract", "processing", "MinerU 正在做表格偵測/辨識。", 0)
        return now_ts
    return last_update


def newest_file(root: Path, patterns: list[str]) -> Path | None:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(root.rglob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def mineru_content_file(root: Path) -> Path | None:
    classic = [path for path in root.rglob("*_content_list.json") if "_content_list_v2" not in path.name]
    if classic:
        return max(classic, key=lambda path: path.stat().st_mtime)
    return newest_file(root, ["*_content_list_v2.json", "*content_list*.json"])


def load_json_file(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text("utf-8", errors="ignore"))


def mineru_content_items(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("content_list", "content_list_v2", "pages", "items"):
            value = data.get(key)
            if isinstance(value, list):
                if key == "pages":
                    output: list[dict[str, Any]] = []
                    for page_index, page in enumerate(value, start=1):
                        if isinstance(page, dict):
                            page_items = page.get("items") or page.get("content") or page.get("blocks") or []
                            for item in page_items if isinstance(page_items, list) else []:
                                if isinstance(item, dict):
                                    item.setdefault("page_number", page.get("page_number", page_index))
                                    output.append(item)
                    return output
                return [item for item in value if isinstance(item, dict)]
    return []


def mineru_flat_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(part for part in (mineru_flat_text(item) for item in value) if part).strip()
    if isinstance(value, dict):
        for key in ("content", "text", "paragraph_content", "title_content", "item_content", "table_body", "latex", "equation"):
            if key in value:
                text = mineru_flat_text(value[key])
                if text:
                    return text
        if "list_items" in value:
            return mineru_flat_text(value["list_items"])
    return ""


def mineru_page_number(item: dict[str, Any], fallback: int) -> int:
    for key in ("page_number", "page_no", "page"):
        value = item.get(key)
        if isinstance(value, int):
            return max(1, value)
        if isinstance(value, str) and value.isdigit():
            return max(1, int(value))
    value = item.get("page_idx") or item.get("page_id")
    if isinstance(value, int):
        return max(1, value + 1)
    if isinstance(value, str) and value.isdigit():
        return max(1, int(value) + 1)
    return fallback


def mineru_item_type(item: dict[str, Any]) -> str:
    raw = str(item.get("type") or item.get("block_type") or item.get("category") or "text").lower()
    if raw in {"title", "header", "footer", "page_number", "text", "plain text", "aside_text", "page_footnote", "ref_text", "list", "paragraph", "index", "page_header"}:
        return "text"
    if "table" in raw:
        return "table"
    if raw in {"equation", "formula", "interline_equation", "inline_equation"} or "equation" in raw or "formula" in raw:
        return "formula"
    if "image" in raw or raw in {"figure", "chart"}:
        return "image"
    return "text"


def mineru_item_text(item: dict[str, Any], block_type: str) -> str:
    if block_type == "table":
        for key in ("table_body", "table", "html", "content", "text", "markdown"):
            value = item.get(key)
            text = mineru_flat_text(value)
            if text:
                return text
        return ""
    if block_type == "formula":
        for key in ("latex", "text", "content", "formula", "equation"):
            value = item.get(key)
            text = mineru_flat_text(value)
            if text:
                return text
        return ""
    if block_type == "image":
        captions = item.get("image_caption") or item.get("caption") or item.get("img_caption") or ""
        if isinstance(captions, list):
            return " ".join(str(value).strip() for value in captions if str(value).strip())
        return str(captions).strip()
    for key in ("text", "content", "markdown"):
        value = item.get(key)
        text = mineru_flat_text(value)
        if text:
            return text
    if isinstance(item.get("list_items"), list):
        return "\n".join(str(value).strip() for value in item["list_items"] if str(value).strip())
    return ""


def resolve_mineru_asset_path(output_root: Path, item: dict[str, Any]) -> Path | None:
    values: list[Any] = [item.get(key) for key in ("img_path", "image_path", "path", "src")]
    content = item.get("content")
    if isinstance(content, dict):
        image_source = content.get("image_source")
        if isinstance(image_source, dict):
            values.append(image_source.get("path"))
        values.append(content.get("img_path"))
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = Path(value)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        direct = output_root / value
        if direct.exists():
            return direct
        matches = list(output_root.rglob(Path(value).name))
        if matches:
            return matches[0]
    return None


def store_mineru_image(
    conn: sqlite3.Connection,
    file_row: dict[str, Any],
    output_root: Path,
    asset_root: Path,
    item: dict[str, Any],
    page_number: int,
    image_index: int,
) -> int:
    source = resolve_mineru_asset_path(output_root, item)
    caption = mineru_item_text(item, "image") or f"MinerU 圖片來源：{file_row['filename']} 第 {page_number} 頁。"
    block_id = f"p{page_number:04d}_mineru_image_{image_index:04d}"
    target = ""
    if source and source.exists():
        ext = source.suffix or ".png"
        destination = asset_root / f"{block_id}{ext}"
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        target = str(destination)
    conn.execute(
        "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            file_row["id"],
            file_row["project_id"],
            page_number,
            block_id,
            "image",
            target,
            caption,
            item.get("ocr_text", "") if isinstance(item.get("ocr_text"), str) else "",
            "pending",
            json.dumps({"source_hash": file_row["source_hash"], "mineru": item}, ensure_ascii=False),
            now(),
        ),
    )
    return 1


def get_image_embedder():
    global _IMAGE_EMBEDDER, _IMAGE_EMBEDDER_FAILED
    if not IMAGE_EMBEDDING_ENABLED or _IMAGE_EMBEDDER_FAILED:
        return None
    if _IMAGE_EMBEDDER is not None:
        return _IMAGE_EMBEDDER
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
    except Exception:
        _IMAGE_EMBEDDER_FAILED = True
        return None
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        processor = CLIPProcessor.from_pretrained(IMAGE_EMBEDDING_MODEL)
        model = CLIPModel.from_pretrained(IMAGE_EMBEDDING_MODEL).to(device)
        model.eval()
        _IMAGE_EMBEDDER = (torch, processor, model, device)
        return _IMAGE_EMBEDDER
    except Exception:
        _IMAGE_EMBEDDER_FAILED = True
        return None


def embed_image(path: Path) -> list[float] | None:
    embedder = get_image_embedder()
    if embedder is None or not path.exists():
        return None
    torch, processor, model, device = embedder
    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            vector = model.get_image_features(**inputs)
            vector = vector / vector.norm(dim=-1, keepdim=True)
        return [round(float(value), 6) for value in vector[0].detach().cpu().tolist()]
    except Exception:
        return None


def embed_file_images(file_row: dict[str, Any], job_id: str) -> int:
    assets = rows("SELECT id, path, metadata_json FROM assets WHERE file_id=? AND asset_type='image' AND path<>''", (file_row["id"],))
    if not assets:
        stage(job_id, "image_embedding", "not_implemented", "此檔案沒有可向量化的圖片資產。", 0)
        return 0
    if not IMAGE_EMBEDDING_ENABLED:
        stage(job_id, "image_embedding", "not_implemented", "圖片向量化已關閉。", 0)
        return 0
    if get_image_embedder() is None:
        stage(job_id, "image_embedding", "not_implemented", f"圖片向量模型無法載入：{IMAGE_EMBEDDING_MODEL}。", 0)
        return 0
    completed = 0
    stage(job_id, "image_embedding", "processing", f"開始圖片向量化，共 {len(assets)} 張。", 0)
    for index, asset in enumerate(assets, start=1):
        vector = embed_image(Path(asset["path"]))
        if vector is None:
            continue
        try:
            metadata = json.loads(asset["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        metadata["image_embedding"] = {
            "model": IMAGE_EMBEDDING_MODEL,
            "dimension": len(vector),
            "vector": vector,
            "path_hash": file_sha(Path(asset["path"])),
        }
        with db() as conn:
            conn.execute("UPDATE assets SET embedding_status=?, metadata_json=? WHERE id=?", ("completed", json.dumps(metadata, ensure_ascii=False), asset["id"]))
        completed += 1
        if index == 1 or index % 10 == 0 or index == len(assets):
            stage(job_id, "image_embedding", "processing", f"圖片向量化進度：{index}/{len(assets)}，完成 {completed} 張。", completed)
    status = "completed" if completed else "not_implemented"
    stage(job_id, "image_embedding", status, f"圖片向量化完成：{completed}/{len(assets)} 張。", completed)
    return completed


def get_image_captioner():
    global _IMAGE_CAPTIONER, _IMAGE_CAPTIONER_FAILED
    if not IMAGE_CAPTION_ENABLED or _IMAGE_CAPTIONER_FAILED:
        return None
    if _IMAGE_CAPTIONER is not None:
        return _IMAGE_CAPTIONER
    try:
        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor
    except Exception:
        _IMAGE_CAPTIONER_FAILED = True
        return None
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        processor = BlipProcessor.from_pretrained(IMAGE_CAPTION_MODEL)
        model = BlipForConditionalGeneration.from_pretrained(IMAGE_CAPTION_MODEL).to(device)
        model.eval()
        _IMAGE_CAPTIONER = (torch, processor, model, device)
        return _IMAGE_CAPTIONER
    except Exception:
        _IMAGE_CAPTIONER_FAILED = True
        return None


def caption_image(path: Path) -> str:
    captioner = get_image_captioner()
    if captioner is None or not path.exists():
        return ""
    torch, processor, model, device = captioner
    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        inputs = processor(image, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            ids = model.generate(**inputs, max_new_tokens=32)
        return processor.decode(ids[0], skip_special_tokens=True).strip()
    except Exception:
        return ""


def caption_file_images(file_row: dict[str, Any], job_id: str) -> int:
    assets = rows("SELECT id, page_number, path, caption, metadata_json FROM assets WHERE file_id=? AND asset_type='image' AND path<>''", (file_row["id"],))
    if not assets:
        stage(job_id, "image_caption", "not_implemented", "此檔案沒有可產生說明的圖片。", 0)
        return 0
    if get_image_captioner() is None:
        stage(job_id, "image_caption", "not_implemented", f"圖片說明模型無法載入：{IMAGE_CAPTION_MODEL}。", 0)
        return 0
    completed = 0
    stage(job_id, "image_caption", "processing", f"開始產生圖片說明，共 {len(assets)} 張。", 0)
    for index, asset in enumerate(assets, start=1):
        try:
            metadata = json.loads(asset["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        if metadata.get("image_caption", {}).get("caption"):
            completed += 1
            continue
        model_caption = caption_image(Path(asset["path"]))
        if not model_caption:
            continue
        caption = f"{asset['caption']} 模型說明：{model_caption}"
        metadata["image_caption"] = {"model": IMAGE_CAPTION_MODEL, "caption": model_caption}
        with db() as conn:
            conn.execute("UPDATE assets SET caption=?, metadata_json=? WHERE id=?", (caption, json.dumps(metadata, ensure_ascii=False), asset["id"]))
        completed += 1
        if index == 1 or index % 10 == 0 or index == len(assets):
            stage(job_id, "image_caption", "processing", f"圖片說明進度：{index}/{len(assets)}，完成 {completed} 張。", completed)
    status = "completed" if completed else "not_implemented"
    stage(job_id, "image_caption", status, f"圖片說明完成：{completed}/{len(assets)} 張。", completed)
    return completed


def get_llm_config() -> dict[str, str]:
    settings = {r["key"]: r["value"] for r in rows("SELECT key, value FROM settings WHERE key LIKE 'llm_%'")}
    return {
        "provider": settings.get("llm_provider", os.getenv("LLM_PROVIDER", "ollama")),
        "base_url": settings.get("llm_base_url", LLM_BASE_URL),
        "api_key": settings.get("llm_api_key", LLM_API_KEY),
        "model": settings.get("llm_model", LLM_MODEL),
    }


def call_llm(prompt: str) -> str | None:
    return call_llm_with("你是繁體中文知識整理助手。只能根據使用者提供的 evidence 摘要，不可補充外部資訊。", prompt)


def call_llm_with(system_prompt: str, user_prompt: str) -> str | None:
    cfg = get_llm_config()
    base_url = cfg["base_url"]
    model = cfg["model"]
    if not base_url or not model:
        return None
    try:
        if cfg["provider"] == "ollama":
            resp = httpx.post(
                f"{base_url}/api/generate",
                json={"model": model, "system": system_prompt, "prompt": user_prompt, "stream": False},
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def generate_ai_summary(file_row: dict[str, Any], job_id: str) -> str:
    stats = {
        "blocks": one("SELECT COUNT(*) AS count FROM blocks WHERE file_id=?", (file_row["id"],))["count"],
        "chunks": one("SELECT COUNT(*) AS count FROM chunks WHERE file_id=?", (file_row["id"],))["count"],
        "images": one("SELECT COUNT(*) AS count FROM assets WHERE file_id=?", (file_row["id"],))["count"],
        "tables": one("SELECT COUNT(*) AS count FROM blocks WHERE file_id=? AND block_type='table'", (file_row["id"],))["count"],
        "formulas": one("SELECT COUNT(*) AS count FROM blocks WHERE file_id=? AND block_type='formula'", (file_row["id"],))["count"],
    }
    snippets = rows("SELECT page_number, content FROM chunks WHERE file_id=? ORDER BY page_number, char_start LIMIT 24", (file_row["id"],))
    evidence = "\n".join(f"頁 {item['page_number']}：{item['content'][:260]}" for item in snippets)
    prompt = f"""請根據以下資料，替這本文件產生繁體中文整理。
檔名：{file_row['filename']}
統計：{json.dumps(stats, ensure_ascii=False)}
Evidence：
{evidence}

請輸出：
1. 文件主題
2. 重要內容摘要
3. 可查詢的關鍵詞
4. 圖片/表格/公式是否值得檢查
"""
    summary = call_llm(prompt)
    model_name = LLM_MODEL if summary else "rule-extractive"
    if not summary:
        summary = (
            f"文件主題初判：{file_row['filename']}\n"
            f"內容統計：文字區塊 {stats['blocks']}、chunks {stats['chunks']}、圖片 {stats['images']}、表格 {stats['tables']}、公式 {stats['formulas']}。\n"
            "重要內容摘錄：\n"
            + "\n".join(f"- {item['content'][:180]}" for item in snippets[:8])
        )
    with db() as conn:
        conn.execute(
            "INSERT INTO ai_knowledge VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                file_row["project_id"],
                file_row["id"],
                None,
                None,
                summary,
                "file_summary",
                0.75 if model_name != "rule-extractive" else 0.55,
                model_name,
                "file-summary-v1",
                str(uuid.uuid4()),
                "active",
                now(),
            ),
        )
    stage(job_id, "ai_suggestion", "completed", f"AI 自動整理已完成：{model_name}。", 1)
    return summary


def import_mineru_output(file_row: dict[str, Any], job_id: str, output_root: Path) -> dict[str, int]:
    content_path = mineru_content_file(output_root)
    middle_path = newest_file(output_root, ["*_middle.json", "*middle*.json"])
    markdown_path = newest_file(output_root, ["*.md"])
    items = mineru_content_items(load_json_file(content_path))
    markdown_text = markdown_path.read_text("utf-8", errors="ignore").strip() if markdown_path else ""
    asset_root = DERIVED_DIR / file_row["id"] / "images"
    asset_root.mkdir(parents=True, exist_ok=True)
    counts = {"blocks": 0, "images": 0, "tables": 0, "formulas": 0, "ocr_pages": 0}
    with db() as conn:
        if items:
            reading_order = 1
            image_index = 1
            last_page = 1
            for item in items:
                page_number = mineru_page_number(item, last_page)
                last_page = page_number
                block_type = mineru_item_type(item)
                bbox = item.get("bbox") or item.get("poly") or item.get("position")
                if block_type == "image":
                    counts["images"] += store_mineru_image(conn, file_row, output_root, asset_root, item, page_number, image_index)
                    image_index += 1
                    continue
                text = mineru_item_text(item, block_type)
                if not text:
                    continue
                block_id = f"p{page_number:04d}_mineru_{block_type}_{reading_order:05d}"
                insert_text_block(conn, file_row, page_number, block_id, block_type, text, bbox, reading_order, 0.92)
                counts["blocks"] += 1
                if block_type == "table":
                    counts["tables"] += 1
                if block_type == "formula":
                    counts["formulas"] += 1
                reading_order += 1
        elif markdown_text:
            insert_text_block(conn, file_row, 1, "mineru_markdown_0001", "text", markdown_text, {"mineru_markdown": str(markdown_path)}, 1, 0.9)
            counts["blocks"] = 1
            counts["tables"] = markdown_text.count("\n|")
            counts["formulas"] = len(extract_formula_lines(markdown_text))
        else:
            raise RuntimeError("MinerU 執行完成，但沒有找到可匯入的 Markdown 或 content_list JSON。")
    if middle_path:
        try:
            middle = load_json_file(middle_path)
            pdf_info = middle.get("pdf_info") if isinstance(middle, dict) else None
            if isinstance(pdf_info, list):
                counts["ocr_pages"] = len(pdf_info)
        except Exception:
            pass
    if not counts["ocr_pages"]:
        pages = {mineru_page_number(item, 1) for item in items} if items else {1}
        counts["ocr_pages"] = len(pages)
    return counts


def extract_pdf(file_row: dict[str, Any], job_id: str) -> None:
    if not mineru_available():
        stage(job_id, "ocr", "failed", "Server venv 尚未安裝 MinerU，請重新執行 Server install.sh。")
        raise RuntimeError("Server venv 尚未安裝 MinerU。")
    output_root = DERIVED_DIR / file_row["id"] / "mineru"
    if output_root.exists():
        shutil.rmtree(output_root, ignore_errors=True)
    page_count = 0
    if fitz is not None:
        try:
            with fitz.open(file_row["source_path"]) as doc:
                page_count = doc.page_count
        except Exception:
            page_count = 0
    stage(job_id, "layout_analysis", "processing", f"MinerU 開始解析 PDF{f'，共 {page_count} 頁' if page_count else ''}。")
    stage(job_id, "ocr", "processing", f"MinerU OCR 已啟用：method={MINERU_METHOD}，backend={MINERU_BACKEND}，lang={MINERU_LANG}。")
    stage(job_id, "table_extract", "processing", "MinerU 表格抽取已啟用。")
    stage(job_id, "formula_extract", "processing", "MinerU 公式抽取已啟用。")
    result = run_mineru(file_row, output_root, job_id, page_count)
    if result.returncode != 0:
        log = "\n".join(part for part in [result.stdout[-4000:], result.stderr[-4000:]] if part)
        raise RuntimeError(f"MinerU 執行失敗，returncode={result.returncode}\n{log}")
    counts = import_mineru_output(file_row, job_id, output_root)
    stage(job_id, "layout_analysis", "completed", f"MinerU PDF 解析完成，內容區塊：{counts['blocks']}。", counts["blocks"])
    stage(job_id, "ocr", "completed", f"MinerU OCR 完成，處理頁數：{counts['ocr_pages']}。", counts["ocr_pages"])
    stage(job_id, "image_extract", "completed" if counts["images"] else "not_implemented", f"MinerU 圖片擷取：{counts['images']}。", counts["images"])
    stage(job_id, "table_extract", "completed", f"MinerU 表格抽取完成，表格數：{counts['tables']}。", counts["tables"])
    stage(job_id, "formula_extract", "completed", f"MinerU 公式抽取完成，公式數：{counts['formulas']}。", counts["formulas"])
    return

    # Legacy PDF parser kept below for reference, but PDF processing now uses MinerU.
    if fitz is None:
        stage(job_id, "layout_analysis", "not_implemented", "PyMuPDF 未安裝，無法解析 PDF。")
        return
    doc = fitz.open(file_row["source_path"])
    asset_root = DERIVED_DIR / file_row["id"] / "images"
    ocr_root = DERIVED_DIR / file_row["id"] / "ocr_pages"
    asset_root.mkdir(parents=True, exist_ok=True)
    ocr_root.mkdir(parents=True, exist_ok=True)
    block_count = 0
    image_count = 0
    ocr_count = 0
    table_count = 0
    formula_count = 0
    stage(job_id, "layout_analysis", "processing", f"PDF 開始解析，共 {doc.page_count} 頁。")
    stage(job_id, "table_extract", "processing", "PDF 表格抽取已啟用：使用 PyMuPDF 版面表格偵測。")
    stage(job_id, "formula_extract", "processing", "公式抽取已啟用：擷取可追溯的公式/算式文字。")
    if ocr_available():
        stage(job_id, "ocr", "processing", f"OCR 已啟用：{OCR_ENGINE_NAME}（Server venv 內）")
    else:
        stage(job_id, "ocr", "not_implemented", "Server venv 未安裝 RapidOCR；掃描頁無法辨識文字。")
    for page_index, page in enumerate(doc, start=1):
        page_blocks = page.get_text("blocks") or []
        page_block_count = 0
        page_image_count = 0
        page_text_chars = 0
        page_texts: list[str] = []
        with db() as conn:
            for order, item in enumerate(page_blocks, start=1):
                x0, y0, x1, y1, text, *_ = item
                text = (text or "").strip()
                if not text:
                    continue
                page_text_chars += len(text)
                page_texts.append(text)
                block_pk = str(uuid.uuid4())
                block_id = f"p{page_index:04d}_b{order:04d}"
                conn.execute(
                    "INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        block_pk,
                        file_row["id"],
                        file_row["id"],
                        file_row["project_id"],
                        page_index,
                        block_id,
                        "text",
                        json.dumps([x0, y0, x1, y1]),
                        order,
                        file_row["source_path"],
                        1.0,
                        text,
                        file_row["source_hash"],
                        now(),
                    ),
                )
                for cidx, (start, end, chunk) in enumerate(split_chunks(text), start=1):
                    conn.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            str(uuid.uuid4()),
                            block_pk,
                            file_row["id"],
                            file_row["project_id"],
                            page_index,
                            f"{block_id}_c{cidx:03d}",
                            "chunk-v1",
                            start,
                            end,
                            chunk,
                            sha(chunk),
                            file_row["source_hash"],
                            now(),
                        ),
                    )
                block_count += 1
                page_block_count += 1
            for image_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                image = doc.extract_image(xref)
                ext = image.get("ext", "png")
                name = f"page_{page_index:03d}_image_{image_index:03d}.{ext}"
                path = asset_root / name
                path.write_bytes(image["image"])
                block_id = f"p{page_index:04d}_image_{image_index:04d}"
                caption = f"圖片來源：{file_row['filename']} 第 {page_index} 頁，區塊 {block_id}。"
                conn.execute(
                    "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), file_row["id"], file_row["project_id"], page_index, block_id, "image", str(path), caption, "", "not_implemented", json.dumps({"source_hash": file_row["source_hash"]}), now()),
                )
                image_count += 1
                page_image_count += 1
            for table_index, (table_text, bbox) in enumerate(extract_pdf_tables(page), start=1):
                block_id = f"p{page_index:04d}_table_{table_index:04d}"
                insert_text_block(conn, file_row, page_index, block_id, "table", table_text, bbox, 8000 + table_index, 0.85)
                table_count += 1
            for formula_index, formula in enumerate(extract_formula_lines("\n".join(page_texts)), start=1):
                block_id = f"p{page_index:04d}_formula_{formula_index:04d}"
                insert_text_block(conn, file_row, page_index, block_id, "formula", formula, None, 9000 + formula_index, 0.8)
                formula_count += 1
        if ocr_available() and page_text_chars < OCR_MIN_TEXT_CHARS:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            ocr_image = ocr_root / f"page_{page_index:04d}.png"
            pix.save(str(ocr_image))
            ocr_text, ocr_items = run_ocr_with_items(ocr_image)
            if ocr_text:
                with db() as conn:
                    page_ocr_formulas = extract_formula_lines(ocr_text)
                    if ocr_text:
                        insert_text_block(conn, file_row, page_index, f"p{page_index:04d}_ocr_0001", "ocr_text", ocr_text, {"ocr_image": str(ocr_image)}, 9999, 0.75)
                        ocr_table = ocr_items_to_table(ocr_items)
                        if ocr_table:
                            insert_text_block(conn, file_row, page_index, f"p{page_index:04d}_ocr_table_0001", "table", ocr_table, {"ocr_image": str(ocr_image)}, 10050, 0.7)
                            table_count += 1
                        for formula_index, formula in enumerate(page_ocr_formulas, start=1):
                            insert_text_block(conn, file_row, page_index, f"p{page_index:04d}_ocr_formula_{formula_index:04d}", "formula", formula, {"ocr_image": str(ocr_image)}, 10000 + formula_index, 0.7)
                            formula_count += 1
                        ocr_count += 1
        if page_index == 1 or page_index % 5 == 0 or page_index == doc.page_count:
            stage(job_id, "layout_analysis", "processing", f"PDF 解析第 {page_index}/{doc.page_count} 頁；本頁文字區塊 {page_block_count}，圖片 {page_image_count}。", block_count)
            stage(job_id, "image_extract", "processing", f"PDF 圖片擷取進度：第 {page_index}/{doc.page_count} 頁，累計圖片 {image_count}。", image_count)
            stage(job_id, "table_extract", "processing", f"PDF 表格抽取第 {page_index}/{doc.page_count} 頁，累計表格 {table_count}。", table_count)
            stage(job_id, "formula_extract", "processing", f"PDF 公式抽取第 {page_index}/{doc.page_count} 頁，累計公式 {formula_count}。", formula_count)
            if ocr_available():
                stage(job_id, "ocr", "processing", f"OCR 進度：第 {page_index}/{doc.page_count} 頁，已辨識 {ocr_count} 頁。", ocr_count)
    stage(job_id, "layout_analysis", "completed", f"完成 PDF 版面文字區塊：{block_count}", block_count)
    stage(job_id, "image_extract", "completed" if image_count else "not_implemented", f"擷取圖片：{image_count}", image_count)
    stage(job_id, "table_extract", "completed", f"PDF 表格抽取完成，表格數：{table_count}", table_count)
    stage(job_id, "formula_extract", "completed", f"PDF 公式抽取完成，公式數：{formula_count}", formula_count)
    if ocr_available():
        stage(job_id, "ocr", "completed", f"OCR 完成，辨識頁數：{ocr_count}", ocr_count)


def extract_text_or_image(file_row: dict[str, Any], job_id: str) -> None:
    ext = Path(file_row["filename"]).suffix.lower()
    if ext == ".txt":
        text = Path(file_row["source_path"]).read_text("utf-8", errors="ignore")
        formulas = extract_formula_lines(text)
        with db() as conn:
            block_pk = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (block_pk, file_row["id"], file_row["id"], file_row["project_id"], 1, "p0001_b0001", "text", None, 1, file_row["source_path"], 1.0, text, file_row["source_hash"], now()),
            )
            for cidx, (start, end, chunk) in enumerate(split_chunks(text), start=1):
                conn.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), block_pk, file_row["id"], file_row["project_id"], 1, f"p0001_b0001_c{cidx:03d}", "chunk-v1", start, end, chunk, sha(chunk), file_row["source_hash"], now()),
                )
            for formula_index, formula in enumerate(formulas, start=1):
                insert_text_block(conn, file_row, 1, f"p0001_formula_{formula_index:04d}", "formula", formula, None, 9000 + formula_index, 0.8)
        stage(job_id, "layout_analysis", "completed", "TXT 已建立文字區塊。", 1)
        stage(job_id, "table_extract", "completed", "TXT 無固定版面表格可抽取。", 0)
        stage(job_id, "formula_extract", "completed", f"TXT 公式抽取完成，公式數：{len(formulas)}", len(formulas))
    elif ext in {".jpg", ".jpeg", ".png"} and mineru_available():
        output_root = DERIVED_DIR / file_row["id"] / "mineru"
        if output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)
        stage(job_id, "layout_analysis", "processing", "MinerU 開始解析圖片。")
        stage(job_id, "ocr", "processing", f"MinerU 圖片 OCR 已啟用：method={MINERU_METHOD}，backend={MINERU_BACKEND}，lang={MINERU_LANG}。")
        stage(job_id, "table_extract", "processing", "MinerU 圖片表格抽取已啟用。")
        stage(job_id, "formula_extract", "processing", "MinerU 圖片公式抽取已啟用。")
        result = run_mineru(file_row, output_root, job_id, 1)
        if result.returncode != 0:
            log = "\n".join(part for part in [result.stdout[-4000:], result.stderr[-4000:]] if part)
            raise RuntimeError(f"MinerU 圖片解析失敗，returncode={result.returncode}\n{log}")
        counts = import_mineru_output(file_row, job_id, output_root)
        stage(job_id, "layout_analysis", "completed", f"MinerU 圖片解析完成，內容區塊：{counts['blocks']}。", counts["blocks"])
        stage(job_id, "ocr", "completed", f"MinerU 圖片 OCR 完成，處理頁數：{counts['ocr_pages']}。", counts["ocr_pages"])
        stage(job_id, "image_extract", "completed" if counts["images"] else "not_implemented", f"MinerU 圖片擷取：{counts['images']}。", counts["images"])
        stage(job_id, "table_extract", "completed", f"MinerU 圖片表格抽取完成，表格數：{counts['tables']}。", counts["tables"])
        stage(job_id, "formula_extract", "completed", f"MinerU 圖片公式抽取完成，公式數：{counts['formulas']}。", counts["formulas"])
    else:
        asset_root = DERIVED_DIR / file_row["id"] / "images"
        asset_root.mkdir(parents=True, exist_ok=True)
        target = asset_root / Path(file_row["source_path"]).name
        shutil.copy2(file_row["source_path"], target)
        caption = f"使用者上傳圖片：{file_row['filename']}。OCR 與圖片 embedding 需要外部模型後重建。"
        with db() as conn:
            ocr_text, ocr_items = run_ocr_with_items(target) if ocr_available() else ("", [])
            conn.execute(
                "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), file_row["id"], file_row["project_id"], 1, "p0001_image_0001", "image", str(target), caption, ocr_text, "not_implemented", json.dumps({"source_hash": file_row["source_hash"]}), now()),
            )
            if ocr_text:
                insert_text_block(conn, file_row, 1, "p0001_image_ocr_0001", "ocr_text", ocr_text, {"image": str(target)}, 9999, 0.75)
                ocr_table = ocr_items_to_table(ocr_items)
                if ocr_table:
                    insert_text_block(conn, file_row, 1, "p0001_image_table_0001", "table", ocr_table, {"image": str(target)}, 10050, 0.7)
                for formula_index, formula in enumerate(extract_formula_lines(ocr_text), start=1):
                    insert_text_block(conn, file_row, 1, f"p0001_image_formula_{formula_index:04d}", "formula", formula, {"image": str(target)}, 10000 + formula_index, 0.7)
        stage(job_id, "layout_analysis", "not_implemented", "圖片檔沒有文字版面，已保留圖片來源。")
        stage(job_id, "ocr", "completed" if ocr_available() else "not_implemented", "圖片 OCR 已完成。" if ocr_text else "圖片 OCR 已執行，未辨識到文字。", 1 if ocr_text else 0)
        stage(job_id, "image_extract", "completed", "原始圖片已納入圖片索引。", 1)
        image_table_count = 1 if ocr_text and ocr_items_to_table(ocr_items) else 0
        stage(job_id, "table_extract", "completed", f"圖片 OCR 表格抽取完成，表格數：{image_table_count}", image_table_count)
        formula_count = len(extract_formula_lines(ocr_text)) if ocr_text else 0
        stage(job_id, "formula_extract", "completed", f"圖片 OCR 公式抽取完成，公式數：{formula_count}", formula_count)


def safe_asset_ext(name: str, media_type: str) -> str:
    ext = Path(name).suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg", "png", "gif", "webp"}:
        return "jpg" if ext == "jpeg" else ext
    if media_type == "image/jpeg":
        return "jpg"
    if media_type == "image/png":
        return "png"
    if media_type == "image/gif":
        return "gif"
    if media_type == "image/webp":
        return "webp"
    return "bin"


def epub_name_aliases(name: str) -> list[str]:
    aliases: list[str] = []
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return aliases
    for encoding in ("utf-8", "gbk", "big5", "cp950"):
        try:
            alias = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if alias != name and alias not in aliases:
            aliases.append(alias)
    return aliases


def repair_epub_filename_aliases(source_path: str, file_id: str, job_id: str) -> str:
    fixed_root = DERIVED_DIR / file_id / "epub_repaired"
    fixed_root.mkdir(parents=True, exist_ok=True)
    fixed_path = fixed_root / "content.epub"
    alias_count = 0
    with zipfile.ZipFile(source_path) as source, zipfile.ZipFile(fixed_path, "w") as target:
        existing = set(source.namelist())
        for info in source.infolist():
            data = source.read(info.filename)
            target.writestr(info, data)
            for alias in epub_name_aliases(info.filename):
                if alias in existing:
                    continue
                alias_info = zipfile.ZipInfo(alias, date_time=info.date_time)
                alias_info.compress_type = info.compress_type
                alias_info.external_attr = info.external_attr
                alias_info.comment = info.comment
                target.writestr(alias_info, data)
                existing.add(alias)
                alias_count += 1
    if alias_count:
        stage(job_id, "metadata", "completed", f"EPUB 中文檔名編碼已建立別名：{alias_count} 個。", alias_count)
        return str(fixed_path)
    return source_path


def extract_epub(file_row: dict[str, Any], job_id: str) -> None:
    if ebooklib is None or epub is None or BeautifulSoup is None:
        stage(job_id, "layout_analysis", "not_implemented", "EbookLib / BeautifulSoup 未安裝，無法解析 EPUB。")
        return
    epub_path = file_row["source_path"]
    try:
        book = epub.read_epub(epub_path)
    except KeyError as exc:
        stage(job_id, "metadata", "processing", f"EPUB 內部檔名可能有中文編碼不一致，正在建立暫存修正版：{exc}")
        epub_path = repair_epub_filename_aliases(file_row["source_path"], file_row["id"], job_id)
        book = epub.read_epub(epub_path)
    doc_count = 0
    block_count = 0
    image_count = 0
    ocr_count = 0
    table_count = 0
    formula_count = 0
    asset_root = DERIVED_DIR / file_row["id"] / "epub_images"
    asset_root.mkdir(parents=True, exist_ok=True)
    document_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    image_items = list(book.get_items_of_type(ebooklib.ITEM_IMAGE))
    stage(job_id, "layout_analysis", "processing", f"EPUB 開始解析，文字文件 {len(document_items)}，圖片 {len(image_items)}。")
    stage(job_id, "table_extract", "processing", "EPUB 表格抽取已啟用：解析 HTML table。")
    stage(job_id, "formula_extract", "processing", "EPUB 公式抽取已啟用：解析 MathML 與文字算式。")
    for doc_index, item in enumerate(document_items, start=1):
        raw = item.get_content()
        soup = BeautifulSoup(raw, "html.parser")
        title = ""
        if soup.find(["h1", "h2", "title"]):
            title = soup.find(["h1", "h2", "title"]).get_text(" ", strip=True)
        text = soup.get_text(" ", strip=True)
        tables = extract_html_tables(soup)
        math_texts = [node.get_text(" ", strip=True) for node in soup.find_all(["math", "mrow", "msup", "msub", "mfrac", "msqrt"]) if node.get_text(" ", strip=True)]
        formulas = []
        seen_formulas = set()
        for formula in math_texts + extract_formula_lines(text):
            key = formula.lower()
            if key not in seen_formulas:
                seen_formulas.add(key)
                formulas.append(formula)
        if not text:
            content = ""
        else:
            doc_count += 1
            content = f"{title}\n{text}".strip() if title and title not in text[:200] else text
        with db() as conn:
            if content:
                block_pk = str(uuid.uuid4())
                block_id = f"epub_doc_{doc_index:04d}_b0001"
                conn.execute(
                    "INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        block_pk,
                        file_row["id"],
                        file_row["id"],
                        file_row["project_id"],
                        doc_index,
                        block_id,
                        "text",
                        json.dumps({"epub_item": item.get_name()}, ensure_ascii=False),
                        1,
                        file_row["source_path"],
                        1.0,
                        content,
                        file_row["source_hash"],
                        now(),
                    ),
                )
                for cidx, (start, end, chunk) in enumerate(split_chunks(content), start=1):
                    conn.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            str(uuid.uuid4()),
                            block_pk,
                            file_row["id"],
                            file_row["project_id"],
                            doc_index,
                            f"{block_id}_c{cidx:03d}",
                            "chunk-v1",
                            start,
                            end,
                            chunk,
                            sha(chunk),
                            file_row["source_hash"],
                            now(),
                        ),
                    )
                block_count += 1
            for table_index, table_text in enumerate(tables, start=1):
                insert_text_block(conn, file_row, doc_index, f"epub_doc_{doc_index:04d}_table_{table_index:04d}", "table", table_text, {"epub_item": item.get_name()}, 8000 + table_index, 0.85)
                table_count += 1
            for formula_index, formula in enumerate(formulas, start=1):
                insert_text_block(conn, file_row, doc_index, f"epub_doc_{doc_index:04d}_formula_{formula_index:04d}", "formula", formula, {"epub_item": item.get_name()}, 9000 + formula_index, 0.8)
                formula_count += 1
        if doc_index == 1 or doc_index % 10 == 0 or doc_index == len(document_items):
            stage(job_id, "layout_analysis", "processing", f"EPUB 文字解析 {doc_index}/{len(document_items)}，累計文字區塊 {block_count}。", block_count)
            stage(job_id, "table_extract", "processing", f"EPUB 表格抽取 {doc_index}/{len(document_items)}，累計表格 {table_count}。", table_count)
            stage(job_id, "formula_extract", "processing", f"EPUB 公式抽取 {doc_index}/{len(document_items)}，累計公式 {formula_count}。", formula_count)
    stage(job_id, "image_extract", "processing", f"EPUB 開始擷取圖片，共 {len(image_items)} 張。")
    if ocr_available():
        stage(job_id, "ocr", "processing", f"EPUB 圖片 OCR 已啟用：{OCR_ENGINE_NAME}（Server venv 內）")
    else:
        stage(job_id, "ocr", "not_implemented", "Server venv 未安裝 RapidOCR；EPUB 掃描圖片無法辨識文字。")
    for image_index, image in enumerate(image_items, start=1):
        name = image.get_name()
        ext = safe_asset_ext(name, getattr(image, "media_type", ""))
        path = asset_root / f"epub_image_{image_index:04d}.{ext}"
        path.write_bytes(image.get_content())
        block_id = f"epub_image_{image_index:04d}"
        caption = f"EPUB 圖片來源：{file_row['filename']}，item {name}，區塊 {block_id}。"
        ocr_text, ocr_items = run_ocr_with_items(path) if ocr_available() else ("", [])
        with db() as conn:
            conn.execute(
                "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    file_row["id"],
                    file_row["project_id"],
                    max(1, doc_count),
                    block_id,
                    "image",
                    str(path),
                    caption,
                    ocr_text,
                    "not_implemented",
                    json.dumps({"source_hash": file_row["source_hash"], "epub_item": name, "media_type": getattr(image, "media_type", "")}, ensure_ascii=False),
                    now(),
                ),
            )
            if ocr_text:
                insert_text_block(conn, file_row, max(1, doc_count), f"{block_id}_ocr_0001", "ocr_text", ocr_text, {"epub_item": name, "image": str(path)}, 9999, 0.75)
                ocr_table = ocr_items_to_table(ocr_items)
                if ocr_table:
                    insert_text_block(conn, file_row, max(1, doc_count), f"{block_id}_ocr_table_0001", "table", ocr_table, {"epub_item": name, "image": str(path)}, 10050, 0.7)
                    table_count += 1
                for formula_index, formula in enumerate(extract_formula_lines(ocr_text), start=1):
                    insert_text_block(conn, file_row, max(1, doc_count), f"{block_id}_ocr_formula_{formula_index:04d}", "formula", formula, {"epub_item": name, "image": str(path)}, 10000 + formula_index, 0.7)
                    formula_count += 1
                ocr_count += 1
        image_count += 1
        if image_index == 1 or image_index % 20 == 0 or image_index == len(image_items):
            stage(job_id, "image_extract", "processing", f"EPUB 圖片擷取 {image_index}/{len(image_items)}。", image_count)
            if ocr_available():
                stage(job_id, "ocr", "processing", f"EPUB 圖片 OCR {image_index}/{len(image_items)}，已辨識 {ocr_count} 張。", ocr_count)
            stage(job_id, "formula_extract", "processing", f"EPUB 圖片 OCR 公式抽取 {image_index}/{len(image_items)}，累計公式 {formula_count}。", formula_count)
    stage(job_id, "layout_analysis", "completed" if block_count else "not_implemented", f"EPUB 文字文件：{doc_count}，文字區塊：{block_count}", block_count)
    stage(job_id, "image_extract", "completed" if image_count else "not_implemented", f"EPUB 圖片擷取：{image_count}", image_count)
    stage(job_id, "table_extract", "completed", f"EPUB 表格抽取完成，表格數：{table_count}", table_count)
    stage(job_id, "formula_extract", "completed", f"EPUB 公式抽取完成，公式數：{formula_count}", formula_count)
    if ocr_available():
        stage(job_id, "ocr", "completed", f"EPUB 圖片 OCR 完成，辨識圖片：{ocr_count}", ocr_count)


def process_file(job_id: str) -> None:
    job = one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        return
    file_row = one("SELECT * FROM files WHERE id=?", (job["file_id"],))
    if not file_row:
        return
    try:
        with db() as conn:
            conn.execute("UPDATE jobs SET status='processing', current_stage='metadata', updated_at=?, error=NULL WHERE id=? AND status!='removed'", (now(), job_id))
            conn.execute("UPDATE files SET status='processing' WHERE id=?", (file_row["id"],))
        stage(job_id, "metadata", "completed", "metadata、hash、版本紀錄已建立。", 1)
        ext = Path(file_row["filename"]).suffix.lower()
        if ext == ".pdf":
            extract_pdf(file_row, job_id)
        elif ext == ".epub":
            extract_epub(file_row, job_id)
        else:
            extract_text_or_image(file_row, job_id)
        caption_file_images(file_row, job_id)
        embed_file_images(file_row, job_id)
        generate_ai_summary(file_row, job_id)
        for name, message in [
            ("ocr", "PDF OCR 已改由 MinerU 處理；非 PDF 圖片/EPUB 圖片仍需後續獨立重建。"),
            ("image_caption", "此檔案沒有可產生說明的圖片。"),
            ("image_embedding", "此檔案沒有可向量化的圖片資產。"),
            ("table_extract", "此檔案沒有偵測到可抽取表格。"),
            ("formula_extract", "此檔案沒有偵測到公式或算式文字。"),
        ]:
            stage_if_missing(job_id, name, "not_implemented", message)
        chunk_count = one("SELECT COUNT(*) AS count FROM chunks WHERE file_id=?", (file_row["id"],))["count"]
        stage(job_id, "chunk", "completed", f"完成 chunk：{chunk_count}", chunk_count)
        stage(job_id, "text_embedding", "completed", "已建立 SHA256 token hash 作為可重建索引版本；外部 embedding 可重跑覆蓋衍生資料。", chunk_count)
        stage(job_id, "rerank_ready", "completed", "Lexical reranker 可用；外部 reranker 模型可在設定後接入。")
        stage(job_id, "index", "completed", "SQLite evidence index 可搜尋。")
        stage_if_missing(job_id, "ai_suggestion", "not_implemented", "沒有足夠內容可產生自動整理。")
        stage(job_id, "done", "completed", "處理完成。")
        with db() as conn:
            conn.execute("UPDATE files SET status='ready' WHERE id=?", (file_row["id"],))
            conn.execute("UPDATE jobs SET status='done', current_stage='done', updated_at=? WHERE id=? AND status!='removed'", (now(), job_id))
    except Exception as exc:
        error_text = f"{exc}\n{traceback.format_exc()}"
        stage(job_id, "failed", "failed", "處理失敗。", error=error_text)
        with db() as conn:
            conn.execute("UPDATE files SET status='failed' WHERE id=?", (file_row["id"],))
            conn.execute("UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=? AND status!='removed'", (error_text, now(), job_id))


def enqueue_job(job_id: str) -> None:
    with _JOB_QUEUE_LOCK:
        if job_id in _JOB_QUEUE_IDS:
            return
        _JOB_QUEUE_IDS.add(job_id)
        _JOB_QUEUE.put(job_id)
    with db() as conn:
        conn.execute("UPDATE jobs SET status='queued', updated_at=? WHERE id=? AND status!='removed'", (now(), job_id))


def job_worker(worker_index: int) -> None:
    while not _JOB_STOP.is_set():
        try:
            job_id = _JOB_QUEUE.get(timeout=JOB_QUEUE_POLL_SECONDS)
        except Exception:
            continue
        with _JOB_QUEUE_LOCK:
            _JOB_QUEUE_IDS.discard(job_id)
        try:
            job = one("SELECT status FROM jobs WHERE id=?", (job_id,))
            if job and job["status"] not in {"removed", "done"}:
                process_file(job_id)
        finally:
            _JOB_QUEUE.task_done()


def recover_queued_jobs() -> None:
    stamp = now()
    with db() as conn:
        conn.execute("UPDATE jobs SET status='queued', current_stage='queued', updated_at=? WHERE status='processing'", (stamp,))
        conn.execute("UPDATE files SET status='queued' WHERE id IN (SELECT file_id FROM jobs WHERE status='queued')")
    for job in rows("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at"):
        enqueue_job(job["id"])


def start_job_workers() -> None:
    global _JOB_WORKERS_STARTED
    if _JOB_WORKERS_STARTED:
        return
    _JOB_WORKERS_STARTED = True
    for index in range(MAX_CONCURRENT_FILE_JOBS):
        thread = threading.Thread(target=job_worker, args=(index + 1,), daemon=True, name=f"rag-job-worker-{index + 1}")
        thread.start()


def clear_rag_content() -> dict[str, Any]:
    with _JOB_QUEUE_LOCK:
        while not _JOB_QUEUE.empty():
            try:
                _JOB_QUEUE.get_nowait()
                _JOB_QUEUE.task_done()
            except Exception:
                break
        _JOB_QUEUE_IDS.clear()
    with db() as conn:
        for table in ("job_stages", "jobs", "chunks", "blocks", "assets", "ai_knowledge", "files", "search_history"):
            conn.execute(f"DELETE FROM {table}")
    with db() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    removed_dirs = []
    for path in (ORIGINALS_DIR, DERIVED_DIR, DATA_DIR / "exports"):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed_dirs.append(str(path))
    ensure_dirs()
    (DATA_DIR / "exports").mkdir(parents=True, exist_ok=True)
    (ORIGINALS_DIR / "_incoming").mkdir(parents=True, exist_ok=True)
    return {"removed_dirs": removed_dirs}


def query_tokens(text: str) -> set[str]:
    return {t.lower() for t in text.replace("，", " ").replace("。", " ").split() if len(t.strip()) >= 2}


def search_evidence(query: str, project_ids: list[str] | None, top_k: int = 10) -> list[dict[str, Any]]:
    tokens = query_tokens(query)
    where = ""
    params: list[Any] = []
    if project_ids:
        where = "WHERE c.project_id IN (%s)" % ",".join("?" for _ in project_ids)
        params.extend(project_ids)
    sql = f"""
        SELECT c.*, b.block_id, b.block_type, b.bbox, f.filename, f.source_path, f.source_hash,
               p.name AS project_name, p.source_rank
        FROM chunks c
        JOIN blocks b ON b.id=c.block_ref
        JOIN files f ON f.id=c.file_id
        JOIN projects p ON p.id=c.project_id
        {where}
    """
    candidates: list[dict[str, Any]] = []
    with db() as conn:
        for original_rank, row in enumerate(conn.execute(sql, tuple(params)).fetchall(), start=1):
            content = row["content"]
            lower = content.lower()
            lexical = sum(1 for token in tokens if token in lower)
            phrase = 3 if query.lower() in lower else 0
            score = lexical + phrase
            if score:
                item = dict(row)
                item["original_rank"] = original_rank
                item["rerank_score"] = round(score / max(1, len(tokens)), 4)
                candidates.append(item)
        for asset in conn.execute("SELECT a.*, f.filename, f.source_path, p.name AS project_name, p.source_rank FROM assets a JOIN files f ON f.id=a.file_id JOIN projects p ON p.id=a.project_id").fetchall():
            text = f"{asset['caption']} {asset['ocr_text']}".lower()
            score = sum(1 for token in tokens if token in text)
            if score and (not project_ids or asset["project_id"] in project_ids):
                item = dict(asset)
                item.update({"content": asset["caption"], "block_type": "image", "original_rank": 9999, "rerank_score": round(score / max(1, len(tokens)), 4), "chunk_id": "", "source_hash": ""})
                candidates.append(item)
    rank_weight = {"A": 0.4, "B": 0.25, "C": 0.1, "D": 0.0}
    candidates.sort(key=lambda x: (x["rerank_score"] + rank_weight.get(x.get("source_rank", "A"), 0)), reverse=True)
    results = []
    for item in candidates[:top_k]:
        results.append(
            {
                "original_rank": item["original_rank"],
                "rerank_score": item["rerank_score"],
                "source_file": item["filename"],
                "source_path": item["source_path"],
                "page_number": item["page_number"],
                "block_id": item["block_id"],
                "chunk_id": item.get("chunk_id", ""),
                "project": item["project_name"],
                "source_rank": item.get("source_rank", "A"),
                "evidence_text": item["content"],
                "evidence_assets": [{"type": "image", "path": item["path"], "caption": item["caption"]}] if item.get("asset_type") == "image" else [],
                "trace": {"file_id": item["file_id"], "project_id": item["project_id"], "bbox": item.get("bbox"), "source_hash": item.get("source_hash", "")},
            }
        )
    return results


def answer_from_evidence(query: str, mode: str, evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "資料庫中未找到足夠證據。"
    evidence_block = ""
    for idx, ev in enumerate(evidence[:8], start=1):
        evidence_block += f"[{idx}] {ev['evidence_text'][:400]}\n    來源：{ev['source_file']}，頁 {ev['page_number']}，區塊 {ev['block_id']}，專案：{ev.get('project','')}\n\n"
    if mode == "research":
        system_prompt = """你是 Evidence-First 知識整理助手。使用者會給你一組搜尋到的 Evidence，你必須：
1. 先列出所有 Evidence 摘要（每則 1-2 句）
2. 比較這些 Evidence 的異同
3. 給出結論
4. 標示不確定性（高/中/低）
5. 只根據提供的 Evidence 回答，不要補充外部知識
6. 找不到足夠證據時明確說「證據不足」"""
        user_prompt = f"使用者問題：{query}\n\n以下是從知識庫搜尋到的 Evidence：\n\n{evidence_block}\n請根據以上 Evidence 整理回答。"
    else:
        system_prompt = """你是 Evidence-First 知識整理助手。使用者會給你一組搜尋到的 Evidence，你必須：
1. 根據 Evidence 直接回答問題
2. 回答要簡潔扼要（200 字以內）
3. 必須引用來源（文件名稱和頁碼）
4. 只根據提供的 Evidence 回答，不要補充外部知識
5. 找不到足夠證據時說「資料庫中未找到足夠證據」"""
        user_prompt = f"使用者問題：{query}\n\n以下是從知識庫搜尋到的 Evidence：\n\n{evidence_block}\n請直接回答。"
    llm_answer = call_llm_with(system_prompt, user_prompt)
    if llm_answer:
        sources = "\n".join(f"- {ev['source_file']} 頁 {ev['page_number']} 區塊 {ev['block_id']}" for ev in evidence[:5])
        return f"{llm_answer}\n\n📚 來源：\n{sources}"
    lines = [f"⚠️ LLM 未設定，以下為原始 Evidence：\n"]
    for idx, ev in enumerate(evidence[:5], start=1):
        lines.append(f"[{idx}] {ev['evidence_text'][:220]}（來源：{ev['source_file']}，頁 {ev['page_number']}）")
    return "\n".join(lines)


class LoginBody(BaseModel):
    username: str
    password: str


class ProjectBody(BaseModel):
    name: str
    template: str = "自訂"
    source_rank: str = "A"
    settings: dict[str, Any] = {}


class UserBody(BaseModel):
    username: str
    password: str
    role: str = "user"


class QueryBody(BaseModel):
    query: str
    mode: str = "answer"
    project_ids: list[str] | None = None
    top_k: int = 10
    user: str = "admin"


class SettingBody(BaseModel):
    key: str
    value: str


LOG_MAX_SIZE_MB = 50
LOG_MAX_FILES = 5


def rotate_logs() -> None:
    log_dir = BASE_DIR / "logs"
    log_file = log_dir / "server.log"
    if not log_file.exists():
        return
    size_mb = log_file.stat().st_size / (1024 * 1024)
    if size_mb < LOG_MAX_SIZE_MB:
        return
    for i in range(LOG_MAX_FILES - 1, 0, -1):
        src = log_dir / f"server.log.{i}"
        dst = log_dir / f"server.log.{i + 1}"
        if src.exists():
            if dst.exists():
                dst.unlink()
            src.rename(dst)
    rotated = log_dir / "server.log.1"
    if rotated.exists():
        rotated.unlink()
    log_file.rename(rotated)


@app.on_event("startup")
def startup() -> None:
    rotate_logs()
    init_db()
    recover_queued_jobs()
    start_job_workers()


@app.get("/health")
def health() -> dict[str, Any]:
    init_db()
    return {
        "status": "ok",
        "data_dir": str(DATA_DIR),
        "queue": "in-process-worker-queue",
        "max_concurrent_file_jobs": MAX_CONCURRENT_FILE_JOBS,
        "queued_jobs": _JOB_QUEUE.qsize(),
    }


SESSION_EXPIRY_HOURS = 24


def create_session(user: dict[str, Any]) -> str:
    token = sha(f"{user['username']}:{user['id']}:{time.time()}")
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRY_HOURS)
    expires_str = expires.isoformat()
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)", (token, user["id"], user["username"], user["role"], now(), expires_str))
    return token


def get_current_user(request: Request) -> dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "未登入")
    session = one("SELECT * FROM sessions WHERE token=?", (token,))
    if not session:
        raise HTTPException(401, "登入已過期，請重新登入")
    try:
        expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
        if expires < datetime.now(timezone.utc):
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            raise HTTPException(401, "登入已過期，請重新登入")
    except HTTPException:
        raise
    except Exception:
        pass
    return {"user_id": session["user_id"], "username": session["username"], "role": session["role"]}


@app.post("/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    user = one("SELECT * FROM users WHERE username=? AND password_hash=?", (body.username, sha(body.password)))
    if not user:
        raise HTTPException(401, "帳號或密碼錯誤")
    token = create_session(user)
    return {"token": token, "user": {"username": user["username"], "role": user["role"], "must_change_password": bool(user["must_change_password"])}}


@app.post("/auth/logout")
def logout(request: Request) -> dict[str, str]:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    return {"message": "已登出"}


@app.post("/auth/change-password")
def change_password(request: Request, body: dict[str, Any]) -> dict[str, str]:
    current = get_current_user(request)
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")
    if not old_password or not new_password:
        raise HTTPException(400, "請提供舊密碼與新密碼")
    if len(new_password) < 4:
        raise HTTPException(400, "新密碼至少需要 4 個字元")
    user = one("SELECT * FROM users WHERE id=?", (current["user_id"],))
    if not user or user["password_hash"] != sha(old_password):
        raise HTTPException(401, "舊密碼錯誤")
    with db() as conn:
        conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (sha(new_password), current["user_id"]))
    return {"message": "密碼已修改"}


@app.get("/users")
def users() -> list[dict[str, Any]]:
    return rows("SELECT id, username, role, must_change_password, created_at FROM users ORDER BY created_at")


@app.post("/users")
def create_user(body: UserBody) -> dict[str, Any]:
    username = body.username.strip()
    if not username:
        raise HTTPException(400, "帳號不可空白")
    if len(body.password) < 4:
        raise HTTPException(400, "密碼至少需要 4 個字元")
    if body.role not in {"admin", "user", "readonly"}:
        raise HTTPException(400, "角色只能是 admin、user 或 readonly")
    user_id = str(uuid.uuid4())
    try:
        with db() as conn:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (user_id, username, sha(body.password), body.role, 1, now()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "帳號已存在")
    return one("SELECT id, username, role, must_change_password, created_at FROM users WHERE id=?", (user_id,))


class UserUpdateBody(BaseModel):
    role: str | None = None
    password: str | None = None


@app.put("/users/{user_id}")
def update_user(user_id: str, body: UserUpdateBody) -> dict[str, Any]:
    user = one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user:
        raise HTTPException(404, "找不到使用者")
    if body.role and body.role not in {"admin", "user", "readonly"}:
        raise HTTPException(400, "角色只能是 admin、user 或 readonly")
    with db() as conn:
        if body.role:
            conn.execute("UPDATE users SET role=? WHERE id=?", (body.role, user_id))
        if body.password:
            if len(body.password) < 4:
                raise HTTPException(400, "密碼至少需要 4 個字元")
            conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (sha(body.password), user_id))
    return one("SELECT id, username, role, must_change_password, created_at FROM users WHERE id=?", (user_id,))


@app.delete("/users/{user_id}")
def delete_user(user_id: str) -> dict[str, str]:
    user = one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user:
        raise HTTPException(404, "找不到使用者")
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return {"message": f"已刪除使用者 {user['username']}"}


@app.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return rows("SELECT * FROM projects WHERE archived=0 ORDER BY created_at DESC")


def file_page_count(file_row: dict[str, Any]) -> int:
    ext = Path(file_row["filename"]).suffix.lower()
    if ext == ".pdf" and fitz is not None:
        try:
            with fitz.open(file_row["source_path"]) as doc:
                return doc.page_count
        except Exception:
            return 0
    max_page = one("SELECT MAX(page_number) AS page FROM blocks WHERE file_id=?", (file_row["id"],))
    return int((max_page or {}).get("page") or 1)


def parse_bbox_value(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if isinstance(parsed, list) and len(parsed) == 4:
        try:
            return [float(item) for item in parsed]
        except Exception:
            return None
    return None


def page_bbox_space(file_row: dict[str, Any], page_number: int) -> dict[str, float]:
    width = 1000.0
    height = 1400.0
    if Path(file_row["filename"]).suffix.lower() == ".pdf" and fitz is not None:
        try:
            with fitz.open(file_row["source_path"]) as doc:
                if 1 <= page_number <= doc.page_count:
                    rect = doc[page_number - 1].rect
                    width = float(rect.width)
                    height = float(rect.height)
        except Exception:
            pass
    for block in rows("SELECT bbox FROM blocks WHERE file_id=? AND page_number=?", (file_row["id"], page_number)):
        bbox = parse_bbox_value(block.get("bbox"))
        if bbox:
            width = max(width, bbox[0], bbox[2])
            height = max(height, bbox[1], bbox[3])
    return {"width": round(width, 2), "height": round(height, 2)}


def file_page_stats(file_id: str, page_count: int) -> list[dict[str, Any]]:
    raw = {r["page_number"]: r for r in rows(
        """SELECT page_number,
        COUNT(*) AS blocks,
        SUM(LENGTH(content)) AS chars,
        SUM(CASE WHEN block_type='table' THEN 1 ELSE 0 END) AS tables,
        SUM(CASE WHEN block_type='formula' THEN 1 ELSE 0 END) AS formulas
        FROM blocks WHERE file_id=? GROUP BY page_number""",
        (file_id,),
    )}
    assets = {r["page_number"]: r["count"] for r in rows("SELECT page_number, COUNT(*) AS count FROM assets WHERE file_id=? GROUP BY page_number", (file_id,))}
    pages = []
    for page_number in range(1, max(page_count, max(raw.keys(), default=0), max(assets.keys(), default=0)) + 1):
        item = raw.get(page_number, {})
        chars = int(item.get("chars") or 0)
        blocks = int(item.get("blocks") or 0)
        status = "missing" if blocks == 0 else ("low_text" if chars < 80 else "ok")
        pages.append(
            {
                "page_number": page_number,
                "blocks": blocks,
                "chars": chars,
                "tables": int(item.get("tables") or 0),
                "formulas": int(item.get("formulas") or 0),
                "assets": int(assets.get(page_number) or 0),
                "status": status,
            }
        )
    return pages


def latest_file_summary(file_id: str) -> dict[str, Any] | None:
    summary = one("SELECT * FROM ai_knowledge WHERE source_file_id=? AND relation_type='file_summary' ORDER BY created_at DESC LIMIT 1", (file_id,))
    return summary


@app.get("/projects/{project_id}/summary")
def project_summary(project_id: str) -> dict[str, Any]:
    project = one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "找不到專案")
    file_rows = rows("SELECT * FROM files WHERE project_id=? ORDER BY uploaded_at DESC", (project_id,))
    files_out: list[dict[str, Any]] = []
    totals = {"files": len(file_rows), "chunks": 0, "text_blocks": 0, "tables": 0, "formulas": 0, "images": 0, "image_embeddings": 0, "ai_summaries": 0}
    for file_row in file_rows:
        block_counts = {r["block_type"]: r["count"] for r in rows("SELECT block_type, COUNT(*) AS count FROM blocks WHERE file_id=? GROUP BY block_type", (file_row["id"],))}
        chunks = one("SELECT COUNT(*) AS count FROM chunks WHERE file_id=?", (file_row["id"],))["count"]
        asset_counts = {r["embedding_status"]: r["count"] for r in rows("SELECT embedding_status, COUNT(*) AS count FROM assets WHERE file_id=? GROUP BY embedding_status", (file_row["id"],))}
        images = sum(asset_counts.values())
        image_embeddings = asset_counts.get("completed", 0)
        sample_text = rows("SELECT page_number, block_type, content FROM blocks WHERE file_id=? AND content<>'' ORDER BY page_number, reading_order LIMIT 3", (file_row["id"],))
        sample_images = rows("SELECT id, page_number, caption, embedding_status FROM assets WHERE file_id=? ORDER BY page_number LIMIT 6", (file_row["id"],))
        summary = latest_file_summary(file_row["id"])
        tables = block_counts.get("table", 0)
        formulas = block_counts.get("formula", 0)
        text_blocks = sum(count for kind, count in block_counts.items() if kind != "table" and kind != "formula")
        totals["chunks"] += chunks
        totals["text_blocks"] += text_blocks
        totals["tables"] += tables
        totals["formulas"] += formulas
        totals["images"] += images
        totals["image_embeddings"] += image_embeddings
        totals["ai_summaries"] += 1 if summary else 0
        files_out.append(
            {
                "id": file_row["id"],
                "filename": file_row["filename"],
                "status": file_row["status"],
                "uploaded_at": file_row["uploaded_at"],
                "version_id": file_row["version_id"],
                "counts": {
                    "chunks": chunks,
                    "text_blocks": text_blocks,
                    "tables": tables,
                    "formulas": formulas,
                    "images": images,
                    "image_embeddings": image_embeddings,
                    "block_counts": block_counts,
                    "asset_counts": asset_counts,
                },
                "samples": {
                    "text": sample_text,
                    "images": [{**img, "url": f"/assets/{img['id']}"} for img in sample_images],
                },
                "ai_summary": summary["content"] if summary else "",
            }
        )
    return {"project": project, "totals": totals, "files": files_out}


@app.post("/projects")
def create_project(body: ProjectBody) -> dict[str, Any]:
    pid = str(uuid.uuid4())
    with db() as conn:
        conn.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?)", (pid, body.name, body.template, body.source_rank, json.dumps(body.settings, ensure_ascii=False), 0, now()))
    return one("SELECT * FROM projects WHERE id=?", (pid,))


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    project = one("SELECT id, name FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "找不到專案")
    file_rows = rows("SELECT id, source_path FROM files WHERE project_id=?", (project_id,))
    file_ids = [item["id"] for item in file_rows]
    project_original_dir = ORIGINALS_DIR / project_id
    project_derived_dirs = [DERIVED_DIR / file_id for file_id in file_ids]
    with db() as conn:
        conn.execute(
            "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                "project_deleted",
                None,
                None,
                json.dumps([{"project_id": project_id}], ensure_ascii=False),
                json.dumps({"project_name": project["name"]}, ensure_ascii=False),
                None,
                None,
                project_id,
                now(),
            ),
        )
        job_ids = [r["id"] for r in conn.execute("SELECT id FROM jobs WHERE project_id=?", (project_id,)).fetchall()]
        if job_ids:
            conn.executemany("DELETE FROM job_stages WHERE job_id=?", [(job_id,) for job_id in job_ids])
        conn.execute("DELETE FROM jobs WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM chunks WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM blocks WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM assets WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM ai_knowledge WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM files WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    for path in project_derived_dirs:
        shutil.rmtree(path, ignore_errors=True)
    shutil.rmtree(project_original_dir, ignore_errors=True)
    return {"message": "專案已刪除；相關工作、metadata、索引與專案原始檔目錄已移除。"}


@app.post("/upload")
async def upload(project_id: str = Form(...), duplicate_strategy: str = Form("skip"), file: UploadFile = File(...)) -> dict[str, Any]:
    project = one("SELECT id FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "找不到專案")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "只支援 PDF、TXT、JPG、JPEG、PNG、EPUB")
    temp = ORIGINALS_DIR / "_incoming"
    temp.mkdir(parents=True, exist_ok=True)
    tmp_path = temp / f"{uuid.uuid4()}{ext}"
    with tmp_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    source_hash = file_sha(tmp_path)
    duplicate = one("SELECT * FROM files WHERE source_hash=? AND project_id=?", (source_hash, project_id))
    if duplicate and duplicate_strategy == "skip":
        tmp_path.unlink(missing_ok=True)
        return {"duplicate": True, "file": duplicate, "message": "檔案已存在，已跳過。"}
    file_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    safe_name = Path(file.filename or f"upload{ext}").name
    final_dir = ORIGINALS_DIR / project_id / file_id
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / safe_name
    shutil.move(str(tmp_path), final_path)
    job_id = str(uuid.uuid4())
    with db() as conn:
        conn.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)", (file_id, project_id, safe_name, str(final_path), source_hash, version_id, "queued", json.dumps({"content_type": file.content_type}), now()))
        conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)", (job_id, file_id, project_id, "queued", "upload", now(), now(), None))
    stage(job_id, "upload", "completed", f"已保存原始檔：{safe_name}", 1)
    enqueue_job(job_id)
    return {"duplicate": False, "file_id": file_id, "job_id": job_id, "source_hash": source_hash}


def stage_total(stage_name: str, file_row: dict[str, Any], counts: dict[str, int], page_total: int) -> int:
    if stage_name in {"layout_analysis", "ocr"}:
        return page_total
    if stage_name in {"image_extract", "image_caption", "image_embedding"}:
        return counts.get("assets", 0)
    if stage_name in {"chunk", "text_embedding"}:
        return counts.get("chunks", 0)
    if stage_name == "table_extract":
        return counts.get("tables", 0)
    if stage_name == "formula_extract":
        return counts.get("formulas", 0)
    if stage_name in {"upload", "metadata", "rerank_ready", "index", "ai_suggestion", "done"}:
        return 1
    return 0


def stage_percent(stage_row: dict[str, Any], total: int) -> int:
    status = stage_row["status"]
    if status in {"completed", "failed", "not_implemented"}:
        return 100
    if status == "queued":
        return 0
    if total <= 0:
        return 0
    return pct(int(stage_row["processed_count"] or 0), total)


@app.get("/jobs")
def jobs() -> list[dict[str, Any]]:
    output = rows(
        """SELECT j.*, f.filename, f.source_path, f.status AS file_status, p.name AS project_name
        FROM jobs j
        JOIN files f ON f.id=j.file_id
        JOIN projects p ON p.id=j.project_id
        WHERE j.status!='removed'
        ORDER BY j.created_at DESC"""
    )
    for job in output:
        counts = {
            "assets": one("SELECT COUNT(*) AS count FROM assets WHERE file_id=?", (job["file_id"],))["count"],
            "chunks": one("SELECT COUNT(*) AS count FROM chunks WHERE file_id=?", (job["file_id"],))["count"],
            "tables": one("SELECT COUNT(*) AS count FROM blocks WHERE file_id=? AND block_type='table'", (job["file_id"],))["count"],
            "formulas": one("SELECT COUNT(*) AS count FROM blocks WHERE file_id=? AND block_type='formula'", (job["file_id"],))["count"],
        }
        page_total = file_page_count(job)
        stages_out = []
        for stage_row in rows("SELECT stage, status, started_at, ended_at, error, processed_count, current_file, log FROM job_stages WHERE job_id=? ORDER BY started_at", (job["id"],)):
            total = stage_total(stage_row["stage"], job, counts, page_total)
            elapsed = iso_seconds(stage_row["started_at"], stage_row["ended_at"])
            stage_row["total_count"] = total
            stage_row["percent"] = stage_percent(stage_row, total)
            stage_row["elapsed_seconds"] = round(elapsed, 1)
            stages_out.append(stage_row)
        job["stages"] = stages_out
        if stages_out:
            job["percent"] = round(sum(s["percent"] for s in stages_out) / len(stages_out))
            job["elapsed_seconds"] = round(sum(s["elapsed_seconds"] for s in stages_out), 1)
        else:
            job["percent"] = 0
            job["elapsed_seconds"] = 0
        job["totals"] = {**counts, "pages": page_total}
    return output


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, str]:
    job = one("SELECT id, status FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "找不到工作")
    with db() as conn:
        if job["status"] in {"processing", "queued"}:
            conn.execute("UPDATE jobs SET status='removed', current_stage='removed', updated_at=? WHERE id=?", (now(), job_id))
            conn.execute("DELETE FROM job_stages WHERE job_id=?", (job_id,))
            return {"message": "工作已標記移除並停止後續進度寫入。原始檔、metadata 與已建立索引不受影響。"}
        conn.execute("DELETE FROM job_stages WHERE job_id=?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"message": "工作進度紀錄已移除。原始檔、metadata 與索引不受影響。"}


@app.get("/files")
def files(project_id: str | None = None) -> list[dict[str, Any]]:
    if project_id:
        return rows("SELECT * FROM files WHERE project_id=? ORDER BY uploaded_at DESC", (project_id,))
    return rows("SELECT * FROM files ORDER BY uploaded_at DESC")


@app.get("/files/{file_id}/reader")
def file_reader(file_id: str) -> dict[str, Any]:
    file_row = one("SELECT * FROM files WHERE id=?", (file_id,))
    if not file_row:
        raise HTTPException(404, "找不到檔案")
    project = one("SELECT id, name, template, source_rank FROM projects WHERE id=?", (file_row["project_id"],))
    page_count = file_page_count(file_row)
    pages = file_page_stats(file_id, page_count)
    totals = {
        "pages": len(pages),
        "missing_pages": sum(1 for page in pages if page["status"] == "missing"),
        "low_text_pages": sum(1 for page in pages if page["status"] == "low_text"),
        "chars": sum(page["chars"] for page in pages),
        "blocks": sum(page["blocks"] for page in pages),
        "assets": sum(page["assets"] for page in pages),
        "tables": sum(page["tables"] for page in pages),
        "formulas": sum(page["formulas"] for page in pages),
    }
    return {"file": file_row, "project": project, "page_count": page_count, "pages": pages, "totals": totals}


@app.get("/files/{file_id}/pages/{page_number}")
def file_page(file_id: str, page_number: int) -> dict[str, Any]:
    file_row = one("SELECT * FROM files WHERE id=?", (file_id,))
    if not file_row:
        raise HTTPException(404, "找不到檔案")
    page = page_bbox_space(file_row, page_number)
    block_rows = rows(
        """SELECT id, page_number, block_id, block_type, bbox, reading_order, confidence, content
        FROM blocks WHERE file_id=? AND page_number=? ORDER BY reading_order, block_id""",
        (file_id, page_number),
    )
    blocks = []
    for block in block_rows:
        block["bbox_values"] = parse_bbox_value(block.get("bbox"))
        blocks.append(block)
    asset_rows = rows(
        "SELECT id, page_number, block_id, asset_type, path, caption, ocr_text, embedding_status, metadata_json FROM assets WHERE file_id=? AND page_number=? ORDER BY block_id",
        (file_id, page_number),
    )
    return {"file": file_row, "page": {"page_number": page_number, **page}, "blocks": blocks, "assets": [{**asset, "url": f"/assets/{asset['id']}"} for asset in asset_rows]}


@app.get("/files/{file_id}/pages/{page_number}/image")
def file_page_image(file_id: str, page_number: int):
    file_row = one("SELECT * FROM files WHERE id=?", (file_id,))
    if not file_row:
        raise HTTPException(404, "找不到檔案")
    if Path(file_row["filename"]).suffix.lower() != ".pdf" or fitz is None:
        raise HTTPException(404, "此檔案沒有可渲染的 PDF 頁面")
    try:
        with fitz.open(file_row["source_path"]) as doc:
            if page_number < 1 or page_number > doc.page_count:
                raise HTTPException(404, "頁碼超出範圍")
            rect = doc[page_number - 1].rect
            space = page_bbox_space(file_row, page_number)
            scale = max(space["width"] / float(rect.width), space["height"] / float(rect.height), 1.0)
            pix = doc[page_number - 1].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return StreamingResponse(io.BytesIO(pix.tobytes("png")), media_type="image/png")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"頁面渲染失敗：{exc}")


@app.delete("/files/{file_id}")
def delete_file(file_id: str) -> dict[str, str]:
    file_row = one("SELECT * FROM files WHERE id=?", (file_id,))
    if not file_row:
        raise HTTPException(404, "找不到檔案")
    job_ids = [row["id"] for row in rows("SELECT id FROM jobs WHERE file_id=?", (file_id,))]
    source_path = Path(file_row["source_path"])
    derived_path = DERIVED_DIR / file_id
    with db() as conn:
        if job_ids:
            conn.executemany("DELETE FROM job_stages WHERE job_id=?", [(job_id,) for job_id in job_ids])
        conn.execute("DELETE FROM jobs WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM chunks WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM blocks WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM assets WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM ai_knowledge WHERE source_file_id=?", (file_id,))
        conn.execute("DELETE FROM files WHERE id=?", (file_id,))
        conn.execute(
            "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                "file_deleted",
                None,
                None,
                json.dumps([{"file_id": file_id, "project_id": file_row["project_id"]}], ensure_ascii=False),
                json.dumps({"filename": file_row["filename"], "source_hash": file_row["source_hash"]}, ensure_ascii=False),
                None,
                None,
                file_row["project_id"],
                now(),
            ),
        )
    if source_path.exists():
        source_path.unlink(missing_ok=True)
        parent = source_path.parent
        if parent.exists() and parent != ORIGINALS_DIR:
            try:
                parent.rmdir()
            except OSError:
                pass
    shutil.rmtree(derived_path, ignore_errors=True)
    return {"message": "檔案/書籍已刪除；原始檔、metadata、工作紀錄、區塊、chunk、assets 與衍生資料已移除。"}


@app.post("/search")
def search(body: QueryBody) -> dict[str, Any]:
    evidence = search_evidence(body.query, body.project_ids, body.top_k)
    return {"query": body.query, "results": evidence}


@app.post("/rag/query")
def rag_query(body: QueryBody) -> dict[str, Any]:
    evidence = search_evidence(body.query, body.project_ids, body.top_k)
    answer = answer_from_evidence(body.query, body.mode, evidence)
    hid = str(uuid.uuid4())
    with db() as conn:
        conn.execute("INSERT INTO search_history VALUES (?,?,?,?,?,?,?,?,?)", (hid, body.query, ",".join(body.project_ids or []), body.mode, json.dumps({"top_k": body.top_k}), json.dumps(evidence, ensure_ascii=False), answer, body.user, now()))
    return {"id": hid, "query": body.query, "mode": body.mode, "answer": answer, "evidence": evidence}


@app.get("/evidence/{chunk_id}")
def evidence(chunk_id: str) -> dict[str, Any]:
    ev = one("SELECT c.*, b.block_id, b.bbox, f.filename, f.source_path FROM chunks c JOIN blocks b ON b.id=c.block_ref JOIN files f ON f.id=c.file_id WHERE c.chunk_id=?", (chunk_id,))
    if not ev:
        raise HTTPException(404, "找不到 Evidence")
    return ev


@app.get("/assets/{asset_id}")
def asset(asset_id: str) -> FileResponse:
    asset_row = one("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not asset_row:
        raise HTTPException(404, "找不到圖片")
    return FileResponse(asset_row["path"])


@app.get("/settings")
def get_settings() -> dict[str, str]:
    return {r["key"]: r["value"] for r in rows("SELECT key, value FROM settings ORDER BY key")}


@app.post("/settings")
def set_setting(body: SettingBody) -> dict[str, str]:
    with db() as conn:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (body.key, body.value))
    return {"message": "設定已保存"}


class LLMTestBody(BaseModel):
    provider: str = "ollama"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@app.post("/llm/test")
def test_llm_connection(body: LLMTestBody) -> dict[str, Any]:
    base_url = body.base_url.rstrip("/")
    if not base_url:
        return {"ok": False, "error": "請輸入 LLM API 位址"}
    try:
        if body.provider == "ollama":
            resp = httpx.get(f"{base_url}/api/tags", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"ok": True, "models": models, "provider": "ollama"}
        else:
            headers = {"Authorization": f"Bearer {body.api_key}"} if body.api_key else {}
            resp = httpx.get(f"{base_url}/v1/models", headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", [])]
            return {"ok": True, "models": models, "provider": body.provider}
    except httpx.ConnectError:
        return {"ok": False, "error": f"無法連線到 {base_url}，請確認位址正確且服務已啟動"}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"HTTP {exc.response.status_code}：{exc.response.text[:200]}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@app.post("/llm/test-query")
def test_llm_query(body: LLMTestBody) -> dict[str, Any]:
    base_url = body.base_url.rstrip("/")
    model = body.model
    if not base_url or not model:
        return {"ok": False, "error": "請輸入 API 位址並選擇模型"}
    try:
        if body.provider == "ollama":
            url = f"{base_url}/api/generate"
            payload = {"model": model, "prompt": "請回答：1+1等於多少？只回答數字。", "stream": False}
        else:
            url = f"{base_url}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {body.api_key}"} if body.api_key else {}
            payload = {"model": model, "messages": [{"role": "user", "content": "請回答：1+1等於多少？只回答數字。"}], "max_tokens": 50}
        resp = httpx.post(url, json=payload, headers=headers if body.provider != "ollama" else {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if body.provider == "ollama":
            answer = data.get("response", "").strip()
        else:
            answer = data["choices"][0]["message"]["content"].strip()
        return {"ok": True, "answer": answer, "model": model}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def extract_wiki_topics(project_id: str) -> list[str]:
    topics: dict[str, int] = {}
    for row in rows("SELECT content FROM chunks WHERE project_id=? LIMIT 500", (project_id,)):
        text = row["content"].lower()
        for word in re.findall(r'[\u4e00-\u9fff]{2,6}|[a-zA-Z]{3,}', text):
            word = word.strip()
            if len(word) >= 2:
                topics[word] = topics.get(word, 0) + 1
    for row in rows("SELECT content FROM ai_knowledge WHERE project_id=? AND relation_type='file_summary'", (project_id,)):
        text = row["content"]
        for line in text.splitlines():
            line = line.strip().lstrip("#*-•1234567890.、）） ")
            if 4 <= len(line) <= 40:
                topics[line] = topics.get(line, 0) + 5
    sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
    seen: set[str] = set()
    result: list[str] = []
    for topic, count in sorted_topics:
        if count >= 2 and topic not in seen and len(result) < 30:
            seen.add(topic)
            result.append(topic)
    return result


@app.get("/wiki/{project_id}")
def get_wiki(project_id: str) -> dict[str, Any]:
    project = one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "找不到專案")
    pages = rows("SELECT * FROM wiki_pages WHERE project_id=? ORDER BY section_order, created_at", (project_id,))
    return {"project": project, "pages": pages, "total": len(pages)}


_WIKI_JOBS: dict[str, dict[str, Any]] = {}
_WIKI_LOCK = threading.Lock()


def wiki_worker(project_id: str, job_id: str) -> None:
    with _WIKI_LOCK:
        _WIKI_JOBS[job_id] = {"project_id": project_id, "status": "running", "total": 0, "done": 0, "current": "", "error": None, "stopped": False}
    try:
        project = one("SELECT * FROM projects WHERE id=?", (project_id,))
        if not project:
            with _WIKI_LOCK:
                _WIKI_JOBS[job_id]["status"] = "failed"
                _WIKI_JOBS[job_id]["error"] = "找不到專案"
            return
        with db() as conn:
            conn.execute("DELETE FROM wiki_pages WHERE project_id=?", (project_id,))
        topics = extract_wiki_topics(project_id)
        if not topics:
            with _WIKI_LOCK:
                _WIKI_JOBS[job_id]["status"] = "done"
                _WIKI_JOBS[job_id]["total"] = 0
            return
        with _WIKI_LOCK:
            _WIKI_JOBS[job_id]["total"] = len(topics)
        pages_created = 0
        for order, topic in enumerate(topics, start=1):
            while True:
                with _WIKI_LOCK:
                    state = _WIKI_JOBS[job_id]
                    if state["stopped"]:
                        state["status"] = "stopped"
                        return
                    if state["status"] == "paused":
                        continue
                break
            with _WIKI_LOCK:
                _WIKI_JOBS[job_id]["current"] = topic
                _WIKI_JOBS[job_id]["done"] = order - 1
            evidence = search_evidence(topic, [project_id], top_k=5)
            evidence_text = "\n".join(f"- {ev['evidence_text'][:300]}（來源：{ev['source_file']}，頁 {ev['page_number']}）" for ev in evidence)
            if not evidence_text:
                with _WIKI_LOCK:
                    _WIKI_JOBS[job_id]["done"] = order
                continue
            image_hits = rows(
                "SELECT a.id, a.caption, a.path FROM assets a WHERE a.project_id=? AND (a.caption LIKE ? OR a.ocr_text LIKE ?) LIMIT 3",
                (project_id, f"%{topic}%", f"%{topic}%"),
            )
            images_json = json.dumps([{"id": img["id"], "caption": img["caption"]} for img in image_hits], ensure_ascii=False)
            sources_json = json.dumps([{"file": ev["source_file"], "page": ev["page_number"], "block": ev["block_id"]} for ev in evidence[:5]], ensure_ascii=False)
            prompt = f"""根據以下 evidence，為主題「{topic}」撰寫一段維基百科風格的知識條目。
要求：
1. 200-400 字
2. 先給定義，再說明重要概念
3. 使用繁體中文
4. 不要編造 evidence 中沒有的資訊

Evidence：
{evidence_text}
"""
            content = call_llm(prompt)
            cfg = get_llm_config()
            model_name = cfg["model"] if content else "rule-extractive"
            if not content:
                content = f"## {topic}\n\n{evidence_text}"
            else:
                content = f"## {topic}\n\n{content}"
            with db() as conn:
                conn.execute(
                    "INSERT INTO wiki_pages VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), project_id, topic, content, sources_json, images_json, model_name, order, now(), now()),
                )
            pages_created += 1
            with _WIKI_LOCK:
                _WIKI_JOBS[job_id]["done"] = order
        with _WIKI_LOCK:
            _WIKI_JOBS[job_id]["status"] = "done"
            _WIKI_JOBS[job_id]["done"] = _WIKI_JOBS[job_id]["total"]
    except Exception as exc:
        with _WIKI_LOCK:
            _WIKI_JOBS[job_id]["status"] = "failed"
            _WIKI_JOBS[job_id]["error"] = str(exc)[:200]


@app.get("/wiki/{project_id}")
def get_wiki(project_id: str) -> dict[str, Any]:
    project = one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "找不到專案")
    pages = rows("SELECT * FROM wiki_pages WHERE project_id=? ORDER BY section_order, created_at", (project_id,))
    return {"project": project, "pages": pages, "total": len(pages)}


@app.post("/wiki/generate/{project_id}")
def generate_wiki(project_id: str) -> dict[str, Any]:
    project = one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "找不到專案")
    with _WIKI_LOCK:
        for jid, state in _WIKI_JOBS.items():
            if state["project_id"] == project_id and state["status"] in ("running", "paused"):
                return {"message": "此專案已有維基產生工作正在執行", "job_id": jid}
    job_id = str(uuid.uuid4())
    thread = threading.Thread(target=wiki_worker, args=(project_id, job_id), daemon=True)
    thread.start()
    return {"message": "維基產生已開始", "job_id": job_id}


@app.get("/wiki/job/{job_id}")
def wiki_job_status(job_id: str) -> dict[str, Any]:
    with _WIKI_LOCK:
        state = _WIKI_JOBS.get(job_id)
    if not state:
        raise HTTPException(404, "找不到維基工作")
    return state


@app.post("/wiki/job/{job_id}/pause")
def wiki_job_pause(job_id: str) -> dict[str, str]:
    with _WIKI_LOCK:
        state = _WIKI_JOBS.get(job_id)
        if not state or state["status"] != "running":
            return {"message": "工作不在執行中"}
        state["status"] = "paused"
    return {"message": "已暫停"}


@app.post("/wiki/job/{job_id}/resume")
def wiki_job_resume(job_id: str) -> dict[str, str]:
    with _WIKI_LOCK:
        state = _WIKI_JOBS.get(job_id)
        if not state or state["status"] != "paused":
            return {"message": "工作未暫停"}
        state["status"] = "running"
    return {"message": "已繼續"}


@app.post("/wiki/job/{job_id}/stop")
def wiki_job_stop(job_id: str) -> dict[str, str]:
    with _WIKI_LOCK:
        state = _WIKI_JOBS.get(job_id)
        if not state:
            return {"message": "找不到工作"}
        state["stopped"] = True
    return {"message": "已停止"}


@app.delete("/wiki/{project_id}")
def delete_wiki(project_id: str) -> dict[str, str]:
    with db() as conn:
        conn.execute("DELETE FROM wiki_pages WHERE project_id=?", (project_id,))
    return {"message": "維基已刪除"}


@app.post("/admin/rebuild")
def rebuild() -> dict[str, str]:
    created_jobs: list[str] = []
    with db() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM blocks")
        conn.execute("DELETE FROM assets")
        files_to_rebuild = conn.execute("SELECT * FROM files").fetchall()
        for file_row in files_to_rebuild:
            job_id = str(uuid.uuid4())
            conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)", (job_id, file_row["id"], file_row["project_id"], "queued", "upload", now(), now(), None))
            conn.execute("UPDATE files SET status='queued' WHERE id=?", (file_row["id"],))
            created_jobs.append(job_id)
    for job_id in created_jobs:
        stage(job_id, "upload", "completed", "使用既有原始檔重建。", 1)
        enqueue_job(job_id)
    return {"message": f"已建立重建工作：{len(created_jobs)} 個，將依佇列處理。"}


@app.post("/admin/backup")
def backup() -> dict[str, str]:
    ensure_dirs()
    name = f"evidence_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    target = BACKUP_DIR / name
    with tarfile.open(target, "w:gz") as tar:
        if DB_PATH.exists():
            tar.add(DB_PATH, arcname="metadata.db")
        if ORIGINALS_DIR.exists():
                tar.add(ORIGINALS_DIR, arcname="originals")
    return {"backup_path": str(target)}


@app.post("/admin/clear-rag")
def clear_rag() -> dict[str, Any]:
    active = one("SELECT COUNT(*) AS count FROM jobs WHERE status IN ('queued','processing')")["count"]
    if active:
        raise HTTPException(409, f"目前仍有 {active} 個排隊或處理中的工作；請先停止 Server 或移除工作後再清空。")
    result = clear_rag_content()
    return {"message": "RAG 內容已清空，帳號、設定與專案已保留。", **result}


@app.post("/admin/restore")
def restore(backup_path: str = Form(...)) -> dict[str, str]:
    source = Path(backup_path)
    if not source.exists():
        raise HTTPException(404, "找不到備份檔")
    with tarfile.open(source, "r:gz") as tar:
        tar.extractall(DATA_DIR)
    return {"message": "已還原，請執行 rebuild_index.sh 重建衍生資料。"}


@app.get("/history")
def history() -> list[dict[str, Any]]:
    return rows("SELECT * FROM search_history ORDER BY timestamp DESC LIMIT 100")


@app.get("/export/{history_id}.{fmt}", response_model=None)
def export(history_id: str, fmt: str):
    item = one("SELECT * FROM search_history WHERE id=?", (history_id,))
    if not item:
        raise HTTPException(404, "找不到搜尋紀錄")
    results = json.loads(item["results_json"])
    if fmt == "json":
        return StreamingResponse(io.BytesIO(json.dumps(item, ensure_ascii=False, indent=2).encode("utf-8")), media_type="application/json")
    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["query", "answer", "source_file", "page_number", "block_id", "rerank_score"])
        for ev in results:
            writer.writerow([item["query"], item["answer"], ev["source_file"], ev["page_number"], ev["block_id"], ev["rerank_score"]])
        return StreamingResponse(io.BytesIO(out.getvalue().encode("utf-8-sig")), media_type="text/csv")
    md = [f"# 查詢匯出\n", f"問題：{item['query']}", f"模式：{item['mode']}", "", "## 答案", item["answer"], "", "## Evidence"]
    for ev in results:
        md.append(f"- {ev['source_file']} 頁 {ev['page_number']} 區塊 {ev['block_id']} score={ev['rerank_score']}\n  {ev['evidence_text']}")
    return PlainTextResponse("\n".join(md), media_type="text/markdown")


init_db()
