"""
ffmpeg_setup.py
Verifica se o FFmpeg está disponível e faz download automático se necessário.
Suporta execução como .py ou como .exe empacotado (PyInstaller).
"""
import os
import sys
import shutil
import zipfile
import io
from pathlib import Path

# URL do build mínimo oficial (BtbN – ~30 MB comprimido, apenas ffmpeg.exe)
_FFMPEG_ZIP_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

def _base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def ffmpeg_path() -> str | None:
    """Retorna o caminho do executável ffmpeg, ou None se não encontrado."""
    # 1. Na variável PATH do sistema
    found = shutil.which("ffmpeg")
    if found:
        return found
    # 2. Ao lado do executável / script
    local = _base_dir() / "ffmpeg.exe"
    if local.exists():
        return str(local)
    return None


def ensure_ffmpeg(progress_cb=None) -> tuple[bool, str]:
    """
    Garante que o FFmpeg está disponível.
    Se não estiver, tenta baixar automaticamente.

    Args:
        progress_cb: callable(str) chamado com mensagens de progresso

    Returns:
        (sucesso: bool, mensagem: str)
    """
    def _log(msg: str):
        if progress_cb:
            progress_cb(msg)
        print(f"[FFmpeg] {msg}")

    # Já disponível?
    p = ffmpeg_path()
    if p:
        _log(f"FFmpeg encontrado em: {p}")
        # Garante que o diretório local está no PATH do processo
        _add_to_path(_base_dir())
        return True, f"FFmpeg disponível: {p}"

    _log("FFmpeg não encontrado. Iniciando download automático…")

    try:
        import urllib.request

        dest = _base_dir() / "ffmpeg.exe"

        _log("Conectando ao GitHub Releases…")
        req = urllib.request.Request(
            _FFMPEG_ZIP_URL,
            headers={"User-Agent": "SisCatLaMP/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            _log("Baixando arquivo ZIP…")
            data = resp.read()

        _log("Extraindo ffmpeg.exe…")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            target_entry = next(
                (n for n in z.namelist() if n.endswith("/bin/ffmpeg.exe")),
                None,
            )
            if not target_entry:
                return False, "ffmpeg.exe não encontrado dentro do ZIP."

            with z.open(target_entry) as src, open(dest, "wb") as dst:
                dst.write(src.read())

        _add_to_path(_base_dir())
        _log(f"FFmpeg instalado com sucesso em {dest}")
        return True, f"FFmpeg baixado e instalado em {dest}"

    except Exception as exc:
        msg = f"Não foi possível baixar o FFmpeg: {exc}"
        _log(msg)
        return False, msg


def _add_to_path(directory: Path):
    """Adiciona diretório ao PATH do processo atual."""
    d = str(directory)
    path_env = os.environ.get("PATH", "")
    if d not in path_env.split(os.pathsep):
        os.environ["PATH"] = d + os.pathsep + path_env
