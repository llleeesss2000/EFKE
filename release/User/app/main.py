from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
SERVER_API_URL = os.getenv("SERVER_API_URL", "http://127.0.0.1:8000").rstrip("/")
USER_DATA_DIR = Path(os.getenv("USER_DATA_DIR", BASE_DIR / "user_data"))
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Evidence-First User UI", version="1.0.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


async def proxy_request(method: str, path: str, token: str = "", **kwargs: Any) -> Any:
    try:
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request(method, f"{SERVER_API_URL}{path}", headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise HTTPException(exc.response.status_code, detail)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"無法連線到 Server：{exc}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "server_api_url": SERVER_API_URL,
        "quantized_data_location": os.getenv("QUANTIZED_DATA_LOCATION", "server"),
        "user_data_dir": str(USER_DATA_DIR),
        "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
        "llm_base_url": os.getenv("LLM_BASE_URL", ""),
        "llm_model": os.getenv("LLM_MODEL", ""),
    }


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


def extract_token(req: Request) -> str:
    return req.headers.get("authorization", "").removeprefix("Bearer ").strip()


@app.post("/api/auth/login")
async def login(body: LoginBody) -> Any:
    return await proxy_request("POST", "/auth/login", json=body.model_dump())


@app.post("/api/auth/logout")
async def logout(req: Request) -> Any:
    return await proxy_request("POST", "/auth/logout", token=extract_token(req))


@app.post("/api/auth/change-password")
async def change_password(req: Request, body: dict) -> Any:
    return await proxy_request("POST", "/auth/change-password", token=extract_token(req), json=body)


@app.get("/api/projects")
async def projects(req: Request) -> Any:
    return await proxy_request("GET", "/projects", token=extract_token(req))


@app.post("/api/projects")
async def create_project(req: Request, body: ProjectBody) -> Any:
    return await proxy_request("POST", "/projects", token=extract_token(req), json=body.model_dump())


@app.delete("/api/projects/{project_id}")
async def delete_project(req: Request, project_id: str) -> Any:
    return await proxy_request("DELETE", f"/projects/{project_id}", token=extract_token(req))


@app.get("/api/projects/{project_id}/summary")
async def project_summary(req: Request, project_id: str) -> Any:
    return await proxy_request("GET", f"/projects/{project_id}/summary", token=extract_token(req))


@app.get("/api/assets/{asset_id}")
async def asset(req: Request, asset_id: str) -> Response:
    try:
        headers = {}
        token = extract_token(req)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request("GET", f"{SERVER_API_URL}/assets/{asset_id}", headers=headers)
            response.raise_for_status()
            return Response(
                content=response.content,
                media_type=response.headers.get("content-type", "application/octet-stream"),
            )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, exc.response.text)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"無法連線到 Server：{exc}")


@app.get("/api/jobs")
async def jobs(req: Request) -> Any:
    return await proxy_request("GET", "/jobs", token=extract_token(req))


@app.delete("/api/jobs/{job_id}")
async def delete_job(req: Request, job_id: str) -> Any:
    return await proxy_request("DELETE", f"/jobs/{job_id}", token=extract_token(req))


@app.get("/api/files")
async def files(req: Request) -> Any:
    return await proxy_request("GET", "/files", token=extract_token(req))


@app.delete("/api/files/{file_id}")
async def delete_file(req: Request, file_id: str) -> Any:
    return await proxy_request("DELETE", f"/files/{file_id}", token=extract_token(req))


@app.get("/api/files/{file_id}/reader")
async def file_reader(req: Request, file_id: str) -> Any:
    return await proxy_request("GET", f"/files/{file_id}/reader", token=extract_token(req))


@app.get("/api/files/{file_id}/pages/{page_number}")
async def file_page(req: Request, file_id: str, page_number: int) -> Any:
    return await proxy_request("GET", f"/files/{file_id}/pages/{page_number}", token=extract_token(req))


@app.get("/api/files/{file_id}/pages/{page_number}/image")
async def file_page_image(req: Request, file_id: str, page_number: int) -> Response:
    try:
        headers = {}
        token = extract_token(req)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request("GET", f"{SERVER_API_URL}/files/{file_id}/pages/{page_number}/image", headers=headers)
            response.raise_for_status()
            return Response(content=response.content, media_type=response.headers.get("content-type", "image/png"))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, exc.response.text)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"無法連線到 Server：{exc}")


@app.get("/api/users")
async def users(req: Request) -> Any:
    return await proxy_request("GET", "/users", token=extract_token(req))


@app.post("/api/users")
async def create_user(req: Request, body: UserBody) -> Any:
    return await proxy_request("POST", "/users", token=extract_token(req), json=body.model_dump())


@app.put("/api/users/{user_id}")
async def update_user(req: Request, user_id: str, body: dict) -> Any:
    return await proxy_request("PUT", f"/users/{user_id}", token=extract_token(req), json=body)


@app.delete("/api/users/{user_id}")
async def delete_user(req: Request, user_id: str) -> Any:
    return await proxy_request("DELETE", f"/users/{user_id}", token=extract_token(req))


@app.post("/api/upload")
async def upload(req: Request, project_id: str = Form(...), duplicate_strategy: str = Form("skip"), file: UploadFile = File(...)) -> Any:
    content = await file.read()
    files = {"file": (file.filename, content, file.content_type)}
    data = {"project_id": project_id, "duplicate_strategy": duplicate_strategy}
    return await proxy_request("POST", "/upload", token=extract_token(req), data=data, files=files)


@app.post("/api/rag/query")
async def rag_query(req: Request, body: QueryBody) -> Any:
    return await proxy_request("POST", "/rag/query", token=extract_token(req), json=body.model_dump())


@app.post("/api/search")
async def search(req: Request, body: QueryBody) -> Any:
    return await proxy_request("POST", "/search", token=extract_token(req), json=body.model_dump())


@app.get("/api/settings")
async def settings(req: Request) -> Any:
    return await proxy_request("GET", "/settings", token=extract_token(req))


@app.post("/api/settings")
async def set_setting(req: Request, body: SettingBody) -> Any:
    return await proxy_request("POST", "/settings", token=extract_token(req), json=body.model_dump())


@app.get("/api/history")
async def history(req: Request) -> Any:
    return await proxy_request("GET", "/history", token=extract_token(req))


@app.post("/api/admin/backup")
async def backup(req: Request) -> Any:
    return await proxy_request("POST", "/admin/backup", token=extract_token(req))


@app.get("/api/wiki/{project_id}")
async def get_wiki(req: Request, project_id: str) -> Any:
    return await proxy_request("GET", f"/wiki/{project_id}", token=extract_token(req))


@app.post("/api/wiki/generate/{project_id}")
async def generate_wiki(req: Request, project_id: str) -> Any:
    return await proxy_request("POST", f"/wiki/generate/{project_id}", token=extract_token(req))


@app.post("/api/admin/rebuild")
async def rebuild(req: Request) -> Any:
    return await proxy_request("POST", "/admin/rebuild", token=extract_token(req))


@app.post("/api/llm/test")
async def llm_test(req: Request, body: dict) -> Any:
    if "base_url" in body and body["base_url"]:
        body["base_url"] = normalize_url(body["base_url"])
    return await proxy_request("POST", "/llm/test", token=extract_token(req), json=body)


@app.post("/api/llm/test-query")
async def llm_test_query(req: Request, body: dict) -> Any:
    if "base_url" in body and body["base_url"]:
        body["base_url"] = normalize_url(body["base_url"])
    return await proxy_request("POST", "/llm/test-query", token=extract_token(req), json=body)


class SetupBody(BaseModel):
    server_url: str
    llm_url: str = ""
    llm_model: str = ""


@app.get("/api/setup/status")
async def setup_status() -> Any:
    env_path = BASE_DIR / ".env"
    configured = False
    if env_path.exists():
        content = env_path.read_text("utf-8", errors="ignore")
        for line in content.splitlines():
            if line.startswith("SERVER_API_URL=") and "127.0.0.1" not in line.split("=", 1)[1]:
                configured = True
                break
    return {"configured": configured, "server_url": SERVER_API_URL}


@app.post("/api/setup/test-server")
async def test_server(body: SetupBody) -> Any:
    url = normalize_url(body.server_url)
    try:
        async with httpx.AsyncClient(timeout=5, verify=False) as client:
            resp = await client.get(f"{url}/health")
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "server_info": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def normalize_url(url: str) -> str:
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


@app.post("/api/setup/save")
async def save_setup(body: SetupBody) -> Any:
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text("utf-8", errors="ignore").splitlines()
    updates = {"SERVER_API_URL": normalize_url(body.server_url)}
    if body.llm_url:
        updates["LLM_BASE_URL"] = normalize_url(body.llm_url)
    if body.llm_model:
        updates["LLM_MODEL"] = body.llm_model
    new_lines = []
    updated_keys = set()
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    global SERVER_API_URL
    SERVER_API_URL = body.server_url.rstrip("/")
    return {"message": "設定已保存，請重新啟動 User 服務以生效。"}
