@echo off
chcp 65001 > nul
setlocal

echo ============================================================
echo  SisCatLaMP — Build do Executavel
echo ============================================================
echo.

REM ── Verifica se o venv esta ativo ────────────────────────────
where python > nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Ative o venv antes de rodar este script.
    pause & exit /b 1
)

REM ── Instala dependencias de build ─────────────────────────────
echo [1/5] Instalando dependencias...
pip install pyinstaller pystray pillow --quiet
if errorlevel 1 ( echo [ERRO] Falha ao instalar dependencias. & pause & exit /b 1 )

REM ── Pre-baixa o modelo Whisper (necessario para maquinas sem internet) ──
echo [2/5] Baixando modelo Whisper "base" (74 MB)...
python -c "import whisper, os; os.makedirs('models/whisper', exist_ok=True); whisper.load_model('base', download_root='models/whisper'); print('Modelo pronto.')"
if errorlevel 1 ( echo [AVISO] Falha ao baixar modelo Whisper. Continuando... )

REM ── Limpa builds anteriores ───────────────────────────────────
echo [3/5] Limpando builds anteriores...
if exist dist\SisCatLaMP rmdir /s /q dist\SisCatLaMP
if exist build\SisCatLaMP rmdir /s /q build\SisCatLaMP

REM ── Roda o PyInstaller ───────────────────────────────────────
echo [4/5] Empacotando com PyInstaller...
pyinstaller ^
  --name SisCatLaMP ^
  --onedir ^
  --windowed ^
  --icon NONE ^
  --add-data "dashboard;dashboard" ^
  --add-data "models;models" ^
  --add-data ".env.example;." ^
  --hidden-import "whisper" ^
  --hidden-import "whisper.audio" ^
  --hidden-import "whisper.decoding" ^
  --hidden-import "whisper.model" ^
  --hidden-import "whisper.tokenizer" ^
  --hidden-import "tiktoken" ^
  --hidden-import "tiktoken_ext" ^
  --hidden-import "tiktoken_ext.openai_public" ^
  --hidden-import "aiogram" ^
  --hidden-import "aiogram.fsm.storage.memory" ^
  --hidden-import "sqlalchemy.dialects.sqlite" ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols" ^
  --hidden-import "uvicorn.protocols.http" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.lifespan" ^
  --hidden-import "uvicorn.lifespan.on" ^
  --hidden-import "pystray._win32" ^
  --collect-submodules "google.genai" ^
  --collect-submodules "openai" ^
  --noconfirm ^
  app_tray.py

if errorlevel 1 (
    echo.
    echo [ERRO] Falha no PyInstaller. Veja o log acima.
    pause & exit /b 1
)

REM ── Copia arquivos adicionais para dist ───────────────────────
echo [5/5] Copiando arquivos extras...
set DIST=dist\SisCatLaMP

REM Copia .env.example como referencia (NAO copiar .env com segredos)
copy /y .env.example "%DIST%\.env.example" > nul

REM Cria pastas de midia vazias na distribuicao
if not exist "%DIST%\media\fotos"     mkdir "%DIST%\media\fotos"
if not exist "%DIST%\media\audio_tmp" mkdir "%DIST%\media\audio_tmp"

REM Instrucoes pos-build
echo.
echo ============================================================
echo  BUILD CONCLUIDO com sucesso!
echo ============================================================
echo.
echo  Pasta gerada: dist\SisCatLaMP\
echo.
echo  ANTES DE INSTALAR NA MAQUINA DESTINO:
echo   1. Copie o arquivo .env para dentro de dist\SisCatLaMP\
echo      (preencha BOT_TOKEN, GEMINI_API_KEY, OPENAI_API_KEY)
echo   2. Se a maquina destino tiver internet restrita, copie tambem
echo      a pasta models\whisper\ (modelo ja baixado)
echo   3. Instale o FFmpeg na maquina destino e adicione ao PATH,
echo      ou copie ffmpeg.exe para dentro de dist\SisCatLaMP\
echo.
echo  Para iniciar: execute dist\SisCatLaMP\SisCatLaMP.exe
echo ============================================================
echo.
pause
