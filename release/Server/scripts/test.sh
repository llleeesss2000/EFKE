#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
python - <<'PY'
from pathlib import Path
import time
import uuid
import zipfile
from fastapi.testclient import TestClient
from app.main import app, init_db, recover_queued_jobs, start_job_workers

client = TestClient(app)
init_db()
recover_queued_jobs()
start_job_workers()

def wait_job(job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = client.get("/jobs").json()
        job = next((item for item in jobs if item["id"] == job_id), None)
        if job and job["status"] in {"done", "failed"}:
            assert job["status"] == "done", job
            return job
        time.sleep(0.2)
    raise AssertionError("job timeout: " + job_id)

assert client.get("/health").status_code == 200
login = client.post("/auth/login", json={"username": "admin", "password": "12345"})
assert login.status_code == 200, login.text
new_user = client.post("/users", json={"username": "readonly_" + uuid.uuid4().hex[:8], "password": "12345", "role": "readonly"})
assert new_user.status_code == 200, new_user.text
assert new_user.json()["role"] == "readonly"
project = client.post("/projects", json={"name": "化工", "template": "化工", "source_rank": "A"}).json()
sample = Path("sample.txt")
needle = "蒸餾塔" + uuid.uuid4().hex[:8]
sample.write_text("化工 Evidence First 測試文件。" + needle + " 操作需要根據來源頁碼回答。", encoding="utf-8")
with sample.open("rb") as handle:
    upload = client.post("/upload", data={"project_id": project["id"]}, files={"file": ("sample.txt", handle, "text/plain")})
assert upload.status_code == 200, upload.text
jobs = client.get("/jobs").json()
assert jobs, "沒有建立 job"
job_id = jobs[0]["id"]
wait_job(job_id)
result = client.post("/rag/query", json={"query": needle, "mode": "research", "project_ids": [project["id"]]}).json()
assert "來源" in result["answer"], result
missing = client.post("/rag/query", json={"query": "不存在的專有名詞XYZ", "mode": "answer", "project_ids": [project["id"]]}).json()
assert missing["answer"] == "資料庫中未找到足夠證據。"
file_id = upload.json()["file_id"]
delete_file_project = client.post("/projects", json={"name": "刪檔測試", "template": "自訂", "source_rank": "A"}).json()
delete_sample = Path("delete_file_sample.txt")
delete_sample.write_text("污染檔案刪除測試", encoding="utf-8")
with delete_sample.open("rb") as handle:
    delete_upload = client.post("/upload", data={"project_id": delete_file_project["id"]}, files={"file": ("delete_file_sample.txt", handle, "text/plain")})
assert delete_upload.status_code == 200, delete_upload.text
wait_job(delete_upload.json()["job_id"])
delete_file = client.delete("/files/" + delete_upload.json()["file_id"])
assert delete_file.status_code == 200, delete_file.text
epub_path = Path("sample.epub")
epub_needle = "EPUB證據" + uuid.uuid4().hex[:8]
with zipfile.ZipFile(epub_path, "w") as zf:
    zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n</container>""")
    zf.writestr("OEBPS/content.opf", """<?xml version="1.0" encoding="UTF-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">\n  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">sample</dc:identifier><dc:title>Sample</dc:title><dc:language>zh-TW</dc:language></metadata>\n  <manifest><item id="chap1" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>\n  <spine><itemref idref="chap1"/></spine>\n</package>""")
    zf.writestr("OEBPS/chapter.xhtml", """<?xml version="1.0" encoding="UTF-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>EPUB 測試</title></head><body><h1>EPUB 測試</h1><p>""" + epub_needle + """ 這是一段 EPUB 文字。</p></body></html>""")
with epub_path.open("rb") as handle:
    epub_upload = client.post("/upload", data={"project_id": project["id"]}, files={"file": ("sample.epub", handle, "application/epub+zip")})
assert epub_upload.status_code == 200, epub_upload.text
wait_job(epub_upload.json()["job_id"])
epub_result = client.post("/rag/query", json={"query": epub_needle, "mode": "answer", "project_ids": [project["id"]]}).json()
assert "來源" in epub_result["answer"], epub_result
delete_job = client.delete("/jobs/" + job_id)
assert delete_job.status_code == 200, delete_job.text
delete_project = client.delete("/projects/" + project["id"])
assert delete_project.status_code == 200, delete_project.text
projects = client.get("/projects").json()
assert project["id"] not in [p["id"] for p in projects]
print("Server 測試通過：登入、新增帳號、專案、上傳、處理、查詢、無證據回答、移除工作、刪除專案")
PY

if [ -t 0 ]; then
  read -r -p "按 Enter 關閉此視窗..."
fi
