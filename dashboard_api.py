import os
import socket
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db, init_db
from models import Item
from ffmpeg_setup import ffmpeg_path, ensure_ffmpeg

_BASE_DIR = Path(__file__).parent if not getattr(__import__('sys'), 'frozen', False) \
    else Path(__import__('sys').executable).parent

app = FastAPI(title="SisCatLaMP Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_FOTOS_DIR = Path(__file__).parent / "media" / "fotos"


# ── Schemas ──────────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    bot_token:    Optional[str] = None
    gemini_key:   Optional[str] = None
    openai_key:   Optional[str] = None
    llm_provider: Optional[str] = None   # "gemini" | "openai"


class ItemUpdate(BaseModel):
    tipo: Optional[str] = None
    descricao: Optional[str] = None
    quantidade: Optional[int] = None
    patrimonio: Optional[str] = None
    local: Optional[str] = None


class ItemCreate(BaseModel):
    tipo: str
    descricao: str
    quantidade: int = 1
    patrimonio: Optional[str] = None
    local: Optional[str] = None


# ── Rotas estáticas ───────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_dashboard():
    html_path = Path(__file__).parent / "dashboard" / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard não encontrado.")
    return FileResponse(str(html_path))


@app.get("/media/fotos/{filename}", include_in_schema=False)
def serve_photo(filename: str):
    file_path = MEDIA_FOTOS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return FileResponse(str(file_path))


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Item.id)).scalar()
    permanente = db.query(func.count(Item.id)).filter(Item.tipo == "Permanente").scalar()
    consumo = db.query(func.count(Item.id)).filter(Item.tipo == "Consumo").scalar()
    locais = db.query(func.count(func.distinct(Item.local))).scalar()
    qtd_total = db.query(func.sum(Item.quantidade)).scalar() or 0

    por_local = (
        db.query(Item.local, func.count(Item.id).label("total"))
        .filter(Item.local.isnot(None))
        .group_by(Item.local)
        .order_by(func.count(Item.id).desc())
        .limit(10)
        .all()
    )

    return {
        "total_itens": total,
        "permanente": permanente,
        "consumo": consumo,
        "locais_distintos": locais,
        "quantidade_total": qtd_total,
        "por_local": [{"local": r.local, "total": r.total} for r in por_local],
    }


# ── Locais ────────────────────────────────────────────────────────────────────

@app.get("/api/locais")
def get_locais(db: Session = Depends(get_db)):
    rows = (
        db.query(Item.local)
        .filter(Item.local.isnot(None))
        .distinct()
        .order_by(Item.local)
        .all()
    )
    return [r.local for r in rows]


# ── CRUD de Itens ─────────────────────────────────────────────────────────────

@app.get("/api/items")
def list_items(
    search: str = Query(""),
    tipo: str = Query(""),
    local: str = Query(""),
    sort: str = Query("id"),
    order: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Item)

    if search:
        pattern = f"%{search}%"
        q = q.filter(
            Item.descricao.ilike(pattern)
            | Item.patrimonio.ilike(pattern)
            | Item.local.ilike(pattern)
        )
    if tipo:
        q = q.filter(Item.tipo == tipo)
    if local:
        q = q.filter(Item.local == local)

    valid_sort = {"id", "descricao", "tipo", "quantidade", "local", "patrimonio", "data_registro"}
    sort_col = sort if sort in valid_sort else "id"
    col = getattr(Item, sort_col)
    q = q.order_by(col.desc() if order == "desc" else col.asc())

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_serialize(i) for i in items],
    }


@app.get("/api/items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return _serialize(item)


@app.put("/api/items/{item_id}")
def update_item(item_id: int, data: ItemUpdate, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return _serialize(item)


@app.post("/api/items", status_code=201)
def create_item(data: ItemCreate, db: Session = Depends(get_db)):
    item = Item(
        tipo=data.tipo,
        descricao=data.descricao,
        quantidade=data.quantidade,
        patrimonio=data.patrimonio,
        local=data.local,
        usuario_id=0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@app.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    db.delete(item)
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(item: Item) -> dict:
    foto_url = None
    if item.foto_path:
        filename = Path(item.foto_path).name
        foto_url = f"/media/fotos/{filename}"
    return {
        "id": item.id,
        "tipo": item.tipo,
        "descricao": item.descricao,
        "quantidade": item.quantidade,
        "patrimonio": item.patrimonio,
        "local": item.local,
        "foto_url": foto_url,
        "usuario_id": item.usuario_id,
        "data_registro": item.data_registro.isoformat() if item.data_registro else None,
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def get_health():
    # Internet
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        internet = True
    except Exception:
        internet = False

    # FFmpeg
    ff = ffmpeg_path()

    # Chaves configuradas
    _ph = {"gemini": "sua_chave_do_google_gemini_aqui",
           "openai": "sua_chave_da_openai_aqui",
           "bot":    "seu_token_aqui"}
    gemini_ok = bool(os.getenv("GEMINI_API_KEY") and
                     os.getenv("GEMINI_API_KEY") != _ph["gemini"])
    openai_ok = bool(os.getenv("OPENAI_API_KEY") and
                     os.getenv("OPENAI_API_KEY") != _ph["openai"])
    bot_ok    = bool(os.getenv("BOT_TOKEN") and
                     os.getenv("BOT_TOKEN") != _ph["bot"])

    return {
        "app_running":        True,
        "internet":           internet,
        "ffmpeg":             bool(ff),
        "ffmpeg_path":        ff or "",
        "gemini_configured":  gemini_ok,
        "openai_configured":  openai_ok,
        "bot_configured":     bot_ok,
        "llm_provider":       os.getenv("LLM_PROVIDER", "gemini"),
    }


# ── Config ────────────────────────────────────────────────────────────────────

def _mask(value: str) -> str:
    """Mascara um segredo exibindo só os últimos 4 caracteres."""
    if not value or len(value) < 8:
        return ""
    return "•" * (len(value) - 4) + value[-4:]

@app.get("/api/config")
def get_config():
    return {
        "bot_token":    _mask(os.getenv("BOT_TOKEN", "")),
        "gemini_key":   _mask(os.getenv("GEMINI_API_KEY", "")),
        "openai_key":   _mask(os.getenv("OPENAI_API_KEY", "")),
        "llm_provider": os.getenv("LLM_PROVIDER", "gemini"),
    }

@app.put("/api/config")
def update_config(data: ConfigUpdate):
    updates: dict[str, str] = {}
    if data.bot_token    and "•" not in data.bot_token:
        updates["BOT_TOKEN"]    = data.bot_token.strip()
    if data.gemini_key   and "•" not in data.gemini_key:
        updates["GEMINI_API_KEY"] = data.gemini_key.strip()
    if data.openai_key   and "•" not in data.openai_key:
        updates["OPENAI_API_KEY"] = data.openai_key.strip()
    if data.llm_provider in ("gemini", "openai"):
        updates["LLM_PROVIDER"] = data.llm_provider

    if not updates:
        return {"message": "Nenhuma alteração detectada."}

    _write_env(updates)

    # Atualiza os.environ para valer imediatamente
    for k, v in updates.items():
        os.environ[k] = v

    # Reseta o cliente Gemini para usar nova chave
    try:
        import ai_agent
        ai_agent._gemini_client = None
    except Exception:
        pass

    return {"message": "Configurações salvas. Reinicie o bot para aplicar o novo token/provider."}

@app.post("/api/ffmpeg/download")
async def download_ffmpeg():
    """Dispara o download do FFmpeg em background e retorna imediatamente."""
    import asyncio
    asyncio.create_task(_async_ensure_ffmpeg())
    return {"message": "Download iniciado. Verifique /api/health em alguns instantes."}

async def _async_ensure_ffmpeg():
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, ensure_ffmpeg)

def _write_env(updates: dict[str, str]):
    env_path = _BASE_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard_api:app", host="0.0.0.0", port=8001, reload=True)
