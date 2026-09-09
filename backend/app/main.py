from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS
from app.routers import evaluation, report, upload

app = FastAPI(title="AIDA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(report.router)
app.include_router(upload.router)
app.include_router(evaluation.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# 빌드된 프론트가 옆에 있으면 같이 서빙한다 (Dockerfile이 /app/static에 넣는다).
#
# **로컬 개발에는 영향이 없다.** 그때는 이 폴더가 없어서 아래가 통째로
# 건너뛰어지고, 프론트는 vite 개발 서버(5173)가 따로 띄운다.
#
# 라우터를 먼저 등록하고 이걸 나중에 붙이는 순서가 중요하다 — 반대로 하면
# "/" 마운트가 /api/* 를 통째로 삼킨다.
_STATIC = Path(__file__).resolve().parent.parent / "static"
if _STATIC.is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        """SPA 폴백. 라우팅은 브라우저가 하므로 어느 경로든 index.html을 준다.

        실제 파일이 있으면 그걸 준다 — favicon 같은 것이 index.html로 나가면
        안 된다.
        """
        candidate = (_STATIC / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_STATIC):
            return FileResponse(candidate)
        return FileResponse(_STATIC / "index.html")
