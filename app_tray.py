"""
SisCatLaMP — Tray Application
Ponto de entrada para o executável (.exe).
Gerencia o bot e o dashboard em threads separadas e
exibe o status em tempo real no ícone da bandeja do Windows.
Abre o dashboard automaticamente no browser ao iniciar.
"""
import sys
import os
import threading
import asyncio
import webbrowser
import time
import urllib.request
from pathlib import Path
from datetime import datetime

# ── Caminho base (funciona tanto em .py quanto em .exe empacotado) ─────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

os.chdir(str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR))

# Carrega .env antes de qualquer import do projeto
from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

import pystray
from PIL import Image, ImageDraw
from ffmpeg_setup import ensure_ffmpeg

# ── Estado compartilhado entre threads ────────────────────────────────────────
_lock = threading.Lock()
_status = {
    "state":      "starting",   # starting | ok | warning | error
    "telegram":   "Aguardando…",
    "gemini":     "Aguardando…",
    "openai":     "Aguardando…",
    "bot_handle": "",
    "detail":     "Inicializando serviços…",
    "checked_at": "—",
}

def set_status(**kw):
    with _lock:
        _status.update(kw)
        _status["checked_at"] = datetime.now().strftime("%H:%M:%S")

def get_status():
    with _lock:
        return dict(_status)

# ── Ícone da bandeja com logo real + dot de status ────────────────────────────
_DOT_COLORS = {
    "starting": (99,  102, 241, 255),   # índigo
    "ok":       (34,  197,  94, 255),   # verde
    "warning":  (234, 179,   8, 255),   # âmbar
    "error":    (239,  68,  68, 255),   # vermelho
}

_logo_base: Image.Image | None = None

def _load_logo_base() -> Image.Image:
    """Carrega e redimensiona a logo para 64×64 (cache na primeira chamada)."""
    global _logo_base
    if _logo_base is not None:
        return _logo_base
    logo_path = BASE_DIR / "image.png"
    if logo_path.exists():
        img = Image.open(logo_path).convert("RGBA").resize((64, 64), Image.LANCZOS)
        _logo_base = img
        return img
    # Fallback: círculo cinza
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([4, 4, 60, 60], fill=(99, 102, 241, 255))
    _logo_base = img
    return img

def _make_icon(state: str) -> Image.Image:
    """Logo com pequeno dot colorido no canto inferior-direito indicando status."""
    base = _load_logo_base().copy()
    d = ImageDraw.Draw(base)
    dot_color = _DOT_COLORS.get(state, _DOT_COLORS["starting"])
    # Sombra do dot
    d.ellipse([44, 44, 62, 62], fill=(0, 0, 0, 80))
    # Dot colorido
    d.ellipse([43, 43, 61, 61], fill=dot_color)
    # Borda branca
    d.ellipse([43, 43, 61, 61], outline=(255, 255, 255, 200), width=2)
    return base

# ── Loop asyncio do bot + dashboard ──────────────────────────────────────────
_async_loop: asyncio.AbstractEventLoop | None = None
_dp_ref = None
_bot_ref = None

async def _check_services_loop():
    """Verifica conectividade a cada 60 segundos."""
    await asyncio.sleep(15)          # aguarda o bot inicializar
    while True:
        # Telegram
        try:
            await _bot_ref.get_me()
            tg = "✅ Online"
            new_state = "ok"
        except Exception as e:
            tg = f"❌ {str(e)[:40]}"
            new_state = "error"

        # Gemini
        g_key = os.getenv("GEMINI_API_KEY", "")
        if g_key and g_key != "sua_chave_do_google_gemini_aqui":
            gm = "✅ Chave configurada"
        else:
            gm = "⚠️ Chave não configurada"
            if new_state == "ok":
                new_state = "warning"

        # OpenAI
        o_key = os.getenv("OPENAI_API_KEY", "")
        if o_key and o_key != "sua_chave_da_openai_aqui":
            oai = "✅ Chave configurada"
        else:
            oai = "⚠️ Não configurada (fallback inativo)"
            if new_state == "ok":
                new_state = "warning"

        set_status(state=new_state, telegram=tg, gemini=gm, openai=oai,
                   detail="Operacional" if new_state == "ok" else "Verifique as chaves no .env")
        await asyncio.sleep(60)


async def _run_all():
    """Executa bot e dashboard no mesmo loop asyncio."""
    global _bot_ref, _dp_ref

    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.types import BotCommand
    from database import init_db
    from bot_handlers import router
    import uvicorn
    from dashboard_api import app as dashboard_app

    token = os.getenv("BOT_TOKEN", "")
    if not token or token == "seu_token_aqui":
        set_status(state="error",
                   telegram="❌ BOT_TOKEN ausente",
                   detail="Configure o arquivo .env e reinicie.")
        return

    init_db()

    # Garante FFmpeg disponível (baixa se necessário)
    set_status(detail="Verificando FFmpeg…")
    ff_ok, ff_msg = await asyncio.get_event_loop().run_in_executor(None, ensure_ffmpeg)
    if not ff_ok:
        print(f"[FFmpeg] {ff_msg}")

    _bot_ref = Bot(token=token, default=DefaultBotProperties(parse_mode="Markdown"))
    _dp_ref  = Dispatcher()
    _dp_ref.include_router(router)

    # Registra comandos no menu do Telegram
    try:
        await _bot_ref.set_my_commands([
            BotCommand(command="ajuda",    description="Lista todos os comandos"),
            BotCommand(command="tabela",   description="Listar todos os itens"),
            BotCommand(command="buscar",   description="Buscar item por termo"),
            BotCommand(command="item",     description="Ver detalhes de um item"),
            BotCommand(command="editar",   description="Editar item por ID"),
            BotCommand(command="deletar",  description="Excluir item por ID"),
            BotCommand(command="recentes", description="Últimos 10 itens cadastrados"),
            BotCommand(command="stats",    description="Estatísticas do inventário"),
            BotCommand(command="locais",   description="Locais permitidos"),
            BotCommand(command="start",    description="Boas-vindas"),
        ])
    except Exception:
        pass

    # Verifica conexão inicial com o Telegram
    try:
        me = await _bot_ref.get_me()
        set_status(
            state="ok",
            telegram="✅ Conectado",
            bot_handle=f"@{me.username}",
            detail=f"Bot @{me.username} online",
        )
    except Exception as e:
        set_status(state="error", telegram=f"❌ {e}", detail=str(e))
        return

    # Inicia dashboard uvicorn
    uv_config = uvicorn.Config(
        dashboard_app,
        host="0.0.0.0",
        port=8001,
        log_level="warning",
    )
    uv_server = uvicorn.Server(uv_config)

    await _bot_ref.delete_webhook(drop_pending_updates=True)

    # Tudo junto no mesmo loop
    await asyncio.gather(
        _dp_ref.start_polling(_bot_ref),
        uv_server.serve(),
        _check_services_loop(),
    )


def _bot_thread_main():
    """Thread que roda o loop asyncio do bot."""
    global _async_loop
    _async_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_async_loop)
    try:
        _async_loop.run_until_complete(_run_all())
    except Exception as e:
        set_status(state="error", detail=str(e))


# ── Abertura automática do dashboard no browser ───────────────────────────────
def _open_browser_when_ready():
    """Aguarda o servidor subir (até 30s) e abre o dashboard no browser padrão."""
    url = "http://localhost:8001"
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(1)
    # Se não conseguiu, tenta abrir mesmo assim
    webbrowser.open(url)


# ── Bandeja do sistema ────────────────────────────────────────────────────────
_tray: pystray.Icon | None = None

_STATE_LABEL = {
    "starting": "Iniciando…",
    "ok":       "Operacional ✅",
    "warning":  "Parcial ⚠️",
    "error":    "Erro ❌",
}

def _build_menu():
    s = get_status()
    label = _STATE_LABEL.get(s["state"], "?")
    handle = s.get("bot_handle") or "—"
    return (
        pystray.MenuItem(f"SisCatLaMP  —  {label}",    None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Bot: {handle}",               None, enabled=False),
        pystray.MenuItem(f"Telegram : {s['telegram']}",  None, enabled=False),
        pystray.MenuItem(f"Gemini   : {s['gemini']}",    None, enabled=False),
        pystray.MenuItem(f"OpenAI   : {s['openai']}",    None, enabled=False),
        pystray.MenuItem(f"Checado às {s['checked_at']}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🌐  Abrir Dashboard",
                         lambda icon, item: webbrowser.open("http://localhost:8001")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌  Sair", _quit),
    )


def _quit(icon, item):
    icon.stop()
    if _async_loop and _async_loop.is_running():
        _async_loop.call_soon_threadsafe(_async_loop.stop)
    os._exit(0)


def _icon_updater():
    """Atualiza ícone e tooltip a cada 5 segundos."""
    while True:
        time.sleep(5)
        if _tray is None:
            continue
        s = get_status()
        _tray.icon  = _make_icon(s["state"])
        _tray.title = f"SisCatLaMP — {_STATE_LABEL.get(s['state'], '?')}"


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global _tray

    # Bot + servidor em thread separada
    t = threading.Thread(target=_bot_thread_main, daemon=True)
    t.start()

    # Abre o dashboard no browser quando o servidor estiver pronto
    b = threading.Thread(target=_open_browser_when_ready, daemon=True)
    b.start()

    # Atualiza ícone em background
    u = threading.Thread(target=_icon_updater, daemon=True)
    u.start()

    # Tray roda na thread principal (obrigatório no Windows)
    _tray = pystray.Icon(
        name="SisCatLaMP",
        icon=_make_icon("starting"),
        title="SisCatLaMP — Iniciando…",
        menu=pystray.Menu(_build_menu),
    )
    _tray.run()


if __name__ == "__main__":
    main()
