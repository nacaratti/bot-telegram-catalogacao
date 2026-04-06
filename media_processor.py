import os
import sys
import uuid
import ffmpeg
import whisper
from pathlib import Path

# Quando empacotado como .exe, usa a pasta ao lado do executável;
# caso contrário usa a pasta do próprio script.
if getattr(sys, 'frozen', False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent

# Diretório onde o modelo Whisper será salvo/carregado
_WHISPER_MODEL_DIR = str(_BASE / "models" / "whisper")
os.makedirs(_WHISPER_MODEL_DIR, exist_ok=True)

os.makedirs(str(_BASE / 'media' / 'fotos'),     exist_ok=True)
os.makedirs(str(_BASE / 'media' / 'audio_tmp'), exist_ok=True)

# Garante que os caminhos relativos usados pelo bot ainda funcionem
os.makedirs(os.path.join('media', 'fotos'),     exist_ok=True)
os.makedirs(os.path.join('media', 'audio_tmp'), exist_ok=True)

# Carrega modelo Whisper (faz download automático se ainda não existir)
try:
    print("Carregando modelo Whisper...")
    whisper_model = whisper.load_model("base", download_root=_WHISPER_MODEL_DIR)
    print("Modelo carregado.")
except Exception as e:
    whisper_model = None
    print(f"Aviso: Não foi possível carregar o Whisper: {e}")

def process_audio(ogg_path: str) -> str:
    """Transcreve áudio usando Whisper."""
    if not whisper_model:
        return ""
    try:
        result = whisper_model.transcribe(ogg_path, language="pt")
        return result["text"].strip()
    except Exception as e:
        print(f"Erro na transcrição: {e}")
        return ""

def process_image(input_image_path: str) -> str:
    """Redimensiona e converte foto para WebP com compressão."""
    filename = f"{uuid.uuid4()}.webp"
    output_path = os.path.join('media', 'fotos', filename)
    
    try:
        (
            ffmpeg
            .input(input_image_path)
            .filter('scale', 'trunc(min(800,iw)/2)*2', '-1')
            .output(output_path, vcodec='libwebp', **{'q:v': 70})
            .overwrite_output()
            .run(quiet=True)
        )
        return output_path
    except Exception as e:
        print(f"Erro no ffmpeg: {e}")
        return None
