import os
import sys
import asyncio
import logging
import tempfile
import atexit
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from database import init_db
from bot_handlers import router

# Configure logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

# --- Proteção contra múltiplas instâncias via arquivo de lock ---
_LOCK_PATH = os.path.join(tempfile.gettempdir(), "siscatlamp.lock")
_lock_file = None

def _acquire_lock():
    global _lock_file
    import msvcrt
    try:
        _lock_file = open(_LOCK_PATH, "w")
        msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
    except OSError:
        logging.error("Outra instância do bot já está rodando. Encerrando.")
        sys.exit(1)

def _release_lock():
    global _lock_file
    if _lock_file:
        import msvcrt
        try:
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        _lock_file.close()
        try:
            os.remove(_LOCK_PATH)
        except Exception:
            pass

atexit.register(_release_lock)
_acquire_lock()
# ---------------------------------------------------------------

async def main():
    # Initialize SQLite Database (creates tables if they don't exist)
    init_db()
    
    token = os.getenv("BOT_TOKEN")
    if not token or token == "seu_token_aqui":
        logging.error("BOT_TOKEN não configurado. Por favor, edite o arquivo .env e insira o tokn.")
        return

    # Use default bot properties to set parsing mode globally
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode='Markdown'))
    dp = Dispatcher()
    
    dp.include_router(router)
    
    await bot.set_my_commands([
        BotCommand(command="inserir",  description="Cadastrar item: /inserir <desc> <tipo> <qtd> <pat> <local>"),
        BotCommand(command="ajuda",    description="Lista todos os comandos"),
        BotCommand(command="tabela",   description="Listar todos os itens"),
        BotCommand(command="buscar",   description="Buscar item por termo"),
        BotCommand(command="item",     description="Ver detalhes de um item"),
        BotCommand(command="editar",   description="Editar item por ID"),
        BotCommand(command="deletar",  description="Excluir item por ID"),
        BotCommand(command="recentes", description="Últimos 10 itens cadastrados"),
        BotCommand(command="stats",    description="Estatísticas do inventário"),
        BotCommand(command="locais",   description="Locais permitidos"),
        BotCommand(command="start",    description="Reiniciar / mensagem de boas-vindas"),
    ])
    logging.info("Iniciando bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot finalizado com sucesso.")
