import os
import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from ai_agent import process_user_input, process_image_for_catalog
from media_processor import process_audio, process_image
from sqlalchemy import func
from database import SessionLocal
from models import Item

router = Router()

class Form(StatesGroup):
    waiting_confirmation = State()
    waiting_description_edit = State()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "👋 Olá! Sou o bot de **Gestão de Inventário Laboratorial**.\n\n"
        "⚡ *Comandos rápidos (sem IA):*\n"
        "`/tabela` · `/buscar <termo>` · `/item <id>`\n"
        "`/editar <id>` · `/deletar <id>` · `/stats`\n"
        "`/recentes` · `/locais` · `/ajuda`\n\n"
        "🤖 *Com IA (texto livre):*\n"
        "Cadastrar: `2 cadeiras no Lab 03`\n"
        "Editar: `editar item 4`\n"
        "Consultar: `Quantos martelos tem?`\n"
        "Áudio 🎙️ e fotos 📸 também são aceitos."
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("locais"))
async def cmd_locais(message: Message):
    text = (
        "📍 **Locais Permitidos:**\n\n"
        "- `Laboratório [Nome/Número]`\n"
        "- `Paiol [Nome/Número]`\n\n"
        "Exemplos: *Laboratório 01*, *Paiol 04*, *Laboratório Quimica*"
    )
    await message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data == "edit_description", StateFilter(Form.waiting_confirmation))
async def ask_description(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "✏️ **Modo de Edição Direta:**\nPor favor, *digite* a nova descrição exata para este item no chat e me envie (ou clique no botão Cancelar atual).", 
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_description_edit)

@router.message(F.text, StateFilter(Form.waiting_description_edit))
async def process_description_edit(message: Message, state: FSMContext, bot: Bot):
    current_state_data = await state.get_data()
    
    last_msg_id = current_state_data.get('last_summary_msg_id')
    if last_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=last_msg_id, reply_markup=None)
        except Exception:
            pass

    parsed_data = current_state_data.get('parsed_data')
    final_photo = current_state_data.get('photo_path')
    
    if not parsed_data:
        await message.answer("❌ Erro: Nenhum item em edição.")
        await state.clear()
        return
        
    parsed_data['descricao'] = message.text.strip()
    await state.update_data(parsed_data=parsed_data)
    
    tipo_intent = "✏️ **Descrição Atualizada**"
    alerta_local = ""
    if not parsed_data.get('local'):
        alerta_local = "\n⚠️ *Aviso: Local não identificado.*"

    tem_foto = "🖼️ Anexada" if final_photo else "❌ Nenhuma"

    resumo = (
        f"{tipo_intent}\n\n"
        f"**Descrição:** {parsed_data.get('descricao', 'N/A')}\n"
        f"**Tipo:** {parsed_data.get('tipo', 'N/A')}\n"
        f"**Qtd:** {parsed_data.get('quantidade', 1)}\n"
        f"**Patrimônio:** {parsed_data.get('patrimonio') or 'N/A'}\n"
        f"**Local:** {parsed_data.get('local') or 'N/A'}\n"
        f"**Foto:** {tem_foto}"
        f"{alerta_local}\n\n"
        f"_(Você ainda pode pedir para o Agente IA ajustar outras coisas enviando aqui.)_"
    )
    
    keyboard = []
    keyboard.append([InlineKeyboardButton(text="✅ Confirmar e Salvar", callback_data="confirm_save")])
    keyboard.append([InlineKeyboardButton(text="✏️ Editar Descrição", callback_data="edit_description")])
    if not final_photo:
        keyboard.append([InlineKeyboardButton(text="📸 Adicionar Foto", callback_data="ask_photo")])
    keyboard.append([InlineKeyboardButton(text="❌ Cancelar/Descartar", callback_data="cancel_save")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    sent_msg = await message.answer(resumo, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Form.waiting_confirmation)
    await state.update_data(last_summary_msg_id=sent_msg.message_id)

@router.message(StateFilter(Form.waiting_description_edit))
async def invalid_description_input(message: Message, state: FSMContext):
    await message.answer("❌ Por favor, envie em formato de **texto** a nova descrição.")

@router.message((F.text & ~F.text.startswith("/")) | F.voice | F.photo, StateFilter(None, Form.waiting_confirmation))
async def process_entry(message: Message, state: FSMContext, bot: Bot):
    current_state_data = await state.get_data()
    
    last_msg_id = current_state_data.get('last_summary_msg_id')
    if last_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=last_msg_id, reply_markup=None)
        except Exception:
            pass
            
    current_item = current_state_data.get('parsed_data')
    
    # Fast path: user is just attaching a photo to an existing item pending confirmation
    if message.photo and not message.caption and current_item:
        agent_msg = await message.answer("🖼 Anexando foto ao item atual...")
        
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        img_temp_path = os.path.join('media', 'fotos', f"temp_{file_id}.jpg")
        await bot.download_file(file.file_path, img_temp_path)
        
        processed_path = process_image(img_temp_path)
        photo_path_db = processed_path or img_temp_path
        if processed_path:
            try: os.remove(img_temp_path)
            except: pass
            
        await state.update_data(photo_path=photo_path_db)
        
        parsed_data = current_item
        tipo_intent = "✏️ **Foto Anexada com Sucesso**"
        
        alerta_local = ""
        if not parsed_data.get('local'):
            alerta_local = "\n⚠️ *Aviso: Local não identificado.*"

        resumo = (
            f"{tipo_intent}\n\n"
            f"**Descrição:** {parsed_data.get('descricao', 'N/A')}\n"
            f"**Tipo:** {parsed_data.get('tipo', 'N/A')}\n"
            f"**Qtd:** {parsed_data.get('quantidade', 1)}\n"
            f"**Patrimônio:** {parsed_data.get('patrimonio') or 'N/A'}\n"
            f"**Local:** {parsed_data.get('local') or 'N/A'}\n"
            f"**Foto:** 🖼️ Adicionada"
            f"{alerta_local}\n\n"
            f"_(Para fazer edições no texto enviado, basta me enviar uma mensagem ex: 'Altere a qtd para 5')_"
        )
        
        keyboard = []
        keyboard.append([InlineKeyboardButton(text="✅ Confirmar e Salvar", callback_data="confirm_save")])
        keyboard.append([InlineKeyboardButton(text="✏️ Editar Descrição", callback_data="edit_description")])
        keyboard.append([InlineKeyboardButton(text="❌ Cancelar/Descartar", callback_data="cancel_save")])
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await agent_msg.edit_text(resumo, reply_markup=kb, parse_mode="Markdown")
        await state.set_state(Form.waiting_confirmation)
        await state.update_data(last_summary_msg_id=agent_msg.message_id)
        return

    text_to_parse = ""
    photo_path_db = None
    result = None

    if message.text:
        text_to_parse = message.text
        agent_msg = await message.answer("🧠 Analisando processamento com IA...")

    elif message.voice:
        agent_msg = await message.answer("🎙 Ouvindo e transcrevendo áudio...")
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        ogg_path = os.path.join('media', 'audio_tmp', f"{file_id}.ogg")
        await bot.download_file(file.file_path, ogg_path)

        transcrito = await asyncio.to_thread(process_audio, ogg_path)
        try:
            os.remove(ogg_path)
        except:
            pass

        if not transcrito:
            await agent_msg.edit_text("❌ Erro ao transcrever áudio ou áudio vazio.")
            return

        text_to_parse = transcrito
        await agent_msg.edit_text(f"📝 **Transcrição:** {transcrito}\n🧠 Analisando intenção...", parse_mode="Markdown")

    elif message.photo:
        agent_msg = await message.answer("🖼 Recebendo e processando imagem...")

        file_id = message.photo[-1].file_id  # Last item in array is highest resolution
        file = await bot.get_file(file_id)
        img_temp_path = os.path.join('media', 'fotos', f"temp_{file_id}.jpg")
        await bot.download_file(file.file_path, img_temp_path)

        processed_path = process_image(img_temp_path)
        if processed_path:
            photo_path_db = processed_path
            try:
                os.remove(img_temp_path)
            except:
                pass
        else:
            photo_path_db = img_temp_path  # Fallback

        if message.caption:
            text_to_parse = message.caption
            await agent_msg.edit_text("🖼 Imagem recebida. 🧠 Analisando legenda para extrair dados...")
        else:
            # Sem legenda e sem item pendente: analisa a imagem diretamente com visão da IA
            await agent_msg.edit_text("🔍 Analisando imagem com visão computacional da IA...")
            result = await asyncio.to_thread(process_image_for_catalog, photo_path_db or img_temp_path)

    # Chamada para o Agente LLM de texto (apenas se a visão não produziu resultado)
    if result is None:
        result = await asyncio.to_thread(process_user_input, text_to_parse, current_item)
    
    if result["intent"] == "ERROR":
        await agent_msg.edit_text(result["resposta"], parse_mode="")
        return

    if result["intent"] == "PERGUNTA":
        await agent_msg.edit_text(f"🤖 Resposta da IA:\n\n{result['resposta']}", parse_mode="")
        return

    if result["intent"] == "EDICAO":
        item_id = result.get("item_id")
        item_desc = result.get("item_descricao")
        db = SessionLocal()
        try:
            if item_id:
                db_item = db.query(Item).filter(Item.id == item_id).first()
            elif item_desc:
                db_item = db.query(Item).filter(
                    func.lower(Item.descricao).contains(item_desc.lower())
                ).first()
            else:
                db_item = None

            if not db_item:
                ref = f"ID {item_id}" if item_id else f'"{item_desc}"'
                await agent_msg.edit_text(
                    f"❌ Item {ref} não encontrado no banco de dados.\n"
                    "Verifique o ID ou o nome e tente novamente.",
                    parse_mode=""
                )
                return

            parsed_data = {
                "id": db_item.id,
                "tipo": db_item.tipo,
                "descricao": db_item.descricao,
                "quantidade": db_item.quantidade,
                "patrimonio": db_item.patrimonio,
                "local": db_item.local,
            }
            final_photo = db_item.foto_path
        finally:
            db.close()

        await state.update_data(parsed_data=parsed_data, photo_path=final_photo, editing_db_id=db_item.id)

        alerta_local = "\n⚠️ *Aviso: Local não identificado.*" if not parsed_data.get('local') else ""
        tem_foto = "🖼️ Anexada" if final_photo else "❌ Nenhuma"
        resumo = (
            f"✏️ **Editando Item #{db_item.id} do banco**\n\n"
            f"**Descrição:** {parsed_data.get('descricao', 'N/A')}\n"
            f"**Tipo:** {parsed_data.get('tipo', 'N/A')}\n"
            f"**Qtd:** {parsed_data.get('quantidade', 1)}\n"
            f"**Patrimônio:** {parsed_data.get('patrimonio') or 'N/A'}\n"
            f"**Local:** {parsed_data.get('local') or 'N/A'}\n"
            f"**Foto:** {tem_foto}"
            f"{alerta_local}\n\n"
            f"_Envie uma mensagem com as alterações desejadas (ex: 'muda a qtd para 5') ou confirme para salvar._"
        )
        keyboard = [
            [InlineKeyboardButton(text="✅ Confirmar e Salvar", callback_data="confirm_save")],
            [InlineKeyboardButton(text="✏️ Editar Descrição", callback_data="edit_description")],
            [InlineKeyboardButton(text="❌ Cancelar/Descartar", callback_data="cancel_save")],
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
        sent_msg = await agent_msg.edit_text(resumo, reply_markup=kb, parse_mode="Markdown")
        await state.set_state(Form.waiting_confirmation)
        await state.update_data(last_summary_msg_id=sent_msg.message_id)
        return

    parsed_data = result.get("item")
    if not parsed_data:
         await agent_msg.edit_text("❌ Falha na resposta da IA. Não extraiu os dados.", parse_mode="Markdown")
         return
         
    # Preserva a foto se houver uma correção que não envia nova foto
    final_photo = photo_path_db or current_state_data.get('photo_path')

    await state.update_data(
        parsed_data=parsed_data,
        photo_path=final_photo
    )
    
    tipo_intent = "📋 **Novo Cadastro Extraído**" if result["intent"] == "CADASTRO" else "✏️ **Item Atualizado/Corrigido**"
    
    alerta_local = ""
    if not parsed_data.get('local'):
        alerta_local = "\n⚠️ *Aviso: Local não identificado. Tente informar um formato válido (Laboratório X ou Paiol X).* "

    tem_foto = "🖼️ Anexada" if final_photo else "❌ Nenhuma"

    resumo = (
        f"{tipo_intent}\n\n"
        f"**Descrição:** {parsed_data.get('descricao', 'N/A')}\n"
        f"**Tipo:** {parsed_data.get('tipo', 'N/A')}\n"
        f"**Qtd:** {parsed_data.get('quantidade', 1)}\n"
        f"**Patrimônio:** {parsed_data.get('patrimonio') or 'N/A'}\n"
        f"**Local:** {parsed_data.get('local') or 'N/A'}\n"
        f"**Foto:** {tem_foto}"
        f"{alerta_local}\n\n"
        f"_(Se houver erro do Whisper, basta me enviar outro texto com a correção. Ex: 'Altere a qtd para 5')_"
    )
    
    keyboard = []
    keyboard.append([InlineKeyboardButton(text="✅ Confirmar e Salvar", callback_data="confirm_save")])
    keyboard.append([InlineKeyboardButton(text="✏️ Editar Descrição", callback_data="edit_description")])
    if not final_photo:
        keyboard.append([InlineKeyboardButton(text="📸 Adicionar Foto", callback_data="ask_photo")])
    keyboard.append([InlineKeyboardButton(text="❌ Cancelar/Descartar", callback_data="cancel_save")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await agent_msg.edit_text(resumo, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Form.waiting_confirmation)
    await state.update_data(last_summary_msg_id=agent_msg.message_id)

@router.callback_query(F.data == "confirm_save", Form.waiting_confirmation)
async def confirm_save(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    parsed = data.get('parsed_data')
    photo = data.get('photo_path')
    
    if not parsed:
        await callback.message.edit_text("❌ Erro: Dados ausentes na memória de estado.")
        return
        
    editing_db_id = data.get('editing_db_id')
    db = SessionLocal()
    try:
        if editing_db_id:
            item = db.query(Item).filter(Item.id == editing_db_id).first()
            if not item:
                await callback.message.edit_text(f"❌ **Item #{editing_db_id} não encontrado.**", parse_mode="Markdown")
                return
            item.tipo = parsed.get('tipo', item.tipo)
            item.descricao = parsed.get('descricao', item.descricao)
            item.quantidade = parsed.get('quantidade', item.quantidade)
            item.patrimonio = parsed.get('patrimonio', item.patrimonio)
            item.local = parsed.get('local', item.local)
            if photo:
                item.foto_path = photo
            db.commit()
            await callback.message.edit_text(f"✅ **Item #{editing_db_id} atualizado com sucesso!**", parse_mode="Markdown")
        else:
            user_id = callback.from_user.id
            item = Item(
                tipo=parsed.get('tipo', 'Consumo'),
                descricao=parsed.get('descricao', ''),
                quantidade=parsed.get('quantidade', 1),
                patrimonio=parsed.get('patrimonio'),
                local=parsed.get('local'),
                foto_path=photo,
                usuario_id=user_id
            )
            db.add(item)
            db.commit()
            await callback.message.edit_text("✅ **Item salvo com sucesso no banco de dados!**", parse_mode="Markdown")
    except Exception as e:
        db.rollback()
        await callback.message.edit_text(f"❌ **Erro ao salvar no banco:** {str(e)}", parse_mode="Markdown")
    finally:
        db.close()
        
    await state.clear()

@router.callback_query(F.data == "cancel_save", Form.waiting_confirmation)
async def cancel_save(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("❌ **Análise descartada.** Você pode recomeçar um cadastro.", parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data == "ask_photo", Form.waiting_confirmation)
async def ask_photo(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📸 **Aguardando Foto:**\nPor favor, envie a foto agora utilizando o botão de clipe/câmera do Telegram (ou clique em Cancelar para abortar o cadastro atual).",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _fmt_item(item: Item) -> str:
    """Formata os detalhes completos de um item em Markdown."""
    tipo_emoji = "🔵" if item.tipo == "Permanente" else "🟡"
    data = item.data_registro.strftime("%d/%m/%Y %H:%M") if item.data_registro else "N/A"
    tem_foto = "🖼️ Sim" if item.foto_path else "❌ Não"
    alerta = "\n⚠️ *Local não informado*" if not item.local else ""
    return (
        f"📋 **Item #{item.id}**\n\n"
        f"{tipo_emoji} **Tipo:** {item.tipo}\n"
        f"**Descrição:** {item.descricao}\n"
        f"**Qtd:** {item.quantidade}\n"
        f"**Patrimônio:** {item.patrimonio or 'N/A'}\n"
        f"**Local:** {item.local or 'N/A'}\n"
        f"**Foto:** {tem_foto}\n"
        f"**Registrado em:** {data}"
        f"{alerta}"
    )

async def _open_item_for_edit(db_item: Item, message: Message, state: FSMContext):
    """Carrega item do banco no estado FSM e exibe resumo de edição."""
    parsed_data = {
        "tipo": db_item.tipo,
        "descricao": db_item.descricao,
        "quantidade": db_item.quantidade,
        "patrimonio": db_item.patrimonio,
        "local": db_item.local,
    }
    await state.clear()
    await state.update_data(
        parsed_data=parsed_data,
        photo_path=db_item.foto_path,
        editing_db_id=db_item.id,
    )
    alerta = "\n⚠️ *Local não informado.*" if not db_item.local else ""
    tem_foto = "🖼️ Anexada" if db_item.foto_path else "❌ Nenhuma"
    resumo = (
        f"✏️ **Editando Item #{db_item.id}**\n\n"
        f"**Descrição:** {db_item.descricao}\n"
        f"**Tipo:** {db_item.tipo}\n"
        f"**Qtd:** {db_item.quantidade}\n"
        f"**Patrimônio:** {db_item.patrimonio or 'N/A'}\n"
        f"**Local:** {db_item.local or 'N/A'}\n"
        f"**Foto:** {tem_foto}"
        f"{alerta}\n\n"
        f"_Envie uma mensagem com as alterações desejadas ou confirme para salvar._"
    )
    kb = []
    kb.append([InlineKeyboardButton(text="✅ Confirmar e Salvar", callback_data="confirm_save")])
    kb.append([InlineKeyboardButton(text="✏️ Editar Descrição", callback_data="edit_description")])
    if not db_item.foto_path:
        kb.append([InlineKeyboardButton(text="📸 Adicionar Foto", callback_data="ask_photo")])
    kb.append([InlineKeyboardButton(text="❌ Cancelar/Descartar", callback_data="cancel_save")])
    sent = await message.answer(resumo, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await state.set_state(Form.waiting_confirmation)
    await state.update_data(last_summary_msg_id=sent.message_id)


# ═══════════════════════════════════════════════════════════════
#  COMANDOS SEM IA
# ═══════════════════════════════════════════════════════════════

@router.message(Command("ajuda"))
async def cmd_ajuda(message: Message):
    text = (
        "📚 **Comandos disponíveis**\n\n"
        "➕ *Cadastro direto*\n"
        "`/inserir <descrição> <tipo> <qtd> <patrimônio> <local>`\n"
        "  _Tipo: Permanente ou Consumo_\n"
        "  _Patrimônio: use `-` se não houver_\n"
        "  _Ex: `/inserir Furadeira Permanente 1 12345 Laboratório 1`_\n\n"
        "🔍 *Consulta*\n"
        "`/item <id>` — Detalhes de um item\n"
        "`/tabela` — Listar todos os itens\n"
        "`/buscar <termo>` — Buscar por descrição ou local\n"
        "`/recentes` — Últimos 10 itens cadastrados\n"
        "`/stats` — Estatísticas do inventário\n"
        "`/locais` — Locais cadastrados\n\n"
        "✏️ *Edição direta*\n"
        "`/editar <id>` — Editar item por ID\n"
        "`/deletar <id>` — Excluir item por ID\n\n"
        "🤖 *Com IA (linguagem natural)*\n"
        "Cadastrar → `2 cadeiras no Lab 03`\n"
        "Editar → `editar item 4`\n"
        "Consultar → `Quantos martelos tem?`\n"
        "Áudio 🎙️ e fotos 📸 também são aceitos."
    )
    await message.answer(text, parse_mode="Markdown")


def _parse_inserir(raw: str):
    """
    Faz o parse dos argumentos do /inserir.
    Formato: <descrição> <Permanente|Consumo> <qtd> <patrimônio> <local>
    Retorna (parsed_data: dict, erro: str | None).
    """
    content = raw.strip()
    if not content:
        return None, "nenhum_argumento"

    # Localiza o tipo (Permanente / Consumo) — tudo antes é a descrição
    tipo = None
    tipo_start = -1
    lower = content.lower()
    for kw, canonical in [("permanente", "Permanente"), ("consumo", "Consumo"),
                           ("perm", "Permanente"),       ("cons", "Consumo")]:
        idx = lower.find(kw)
        if idx != -1:
            # Confirma que é uma palavra isolada (não substring de outra)
            after = idx + len(kw)
            ok_before = idx == 0 or not lower[idx - 1].isalpha()
            ok_after  = after >= len(lower) or not lower[after].isalpha()
            if ok_before and ok_after:
                tipo = canonical
                tipo_start = idx
                tipo_end   = after
                break

    if tipo is None:
        return None, (
            "❌ *Tipo não identificado.*\n"
            "Use `Permanente` ou `Consumo` no comando.\n"
            "Ex: `/inserir Furadeira Permanente 1 12345 Laboratório 1`"
        )

    descricao = content[:tipo_start].strip()
    remainder = content[tipo_end:].strip()

    if not descricao:
        return None, (
            "❌ *Descrição não pode ser vazia.*\n"
            "Ex: `/inserir Furadeira Permanente 1 12345 Laboratório 1`"
        )

    # remainder: <qtd> <patrimônio> <local...>
    parts = remainder.split(maxsplit=2)

    quantidade = 1
    patrimonio = None
    local = None

    if len(parts) >= 1:
        try:
            quantidade = int(parts[0])
        except ValueError:
            return None, f"❌ Quantidade inválida: `{parts[0]}`. Use um número inteiro."

    if len(parts) >= 2:
        p = parts[1].strip()
        patrimonio = None if p in ("-", "0", "nenhum", "n/a", "") else p

    if len(parts) >= 3:
        local = parts[2].strip() or None

    return {
        "tipo":       tipo,
        "descricao":  descricao,
        "quantidade": quantidade,
        "patrimonio": patrimonio,
        "local":      local,
    }, None


@router.message(Command("inserir"))
async def cmd_inserir(message: Message, state: FSMContext):
    raw = message.text.split(maxsplit=1)
    args = raw[1] if len(raw) > 1 else ""

    if not args.strip():
        await message.answer(
            "ℹ️ *Como usar:*\n"
            "`/inserir <descrição> <tipo> <qtd> <patrimônio> <local>`\n\n"
            "*Exemplos:*\n"
            "`/inserir Furadeira Permanente 1 12345 Laboratório 1`\n"
            "`/inserir Papel A4 Consumo 10 - Paiol 2`\n\n"
            "_Patrimônio: use `-` se não houver._\n"
            "_Local: pode conter espaços (é o último campo)._",
            parse_mode="Markdown"
        )
        return

    parsed, erro = _parse_inserir(args)
    if erro == "nenhum_argumento":
        await message.answer(
            "ℹ️ Uso: `/inserir <descrição> <tipo> <qtd> <patrimônio> <local>`",
            parse_mode="Markdown"
        )
        return
    if erro:
        await message.answer(erro, parse_mode="Markdown")
        return

    # Limpa estado anterior e carrega dados
    await state.clear()
    await state.update_data(parsed_data=parsed, photo_path=None, editing_db_id=None)

    alerta_local = "\n⚠️ *Local não informado.*" if not parsed.get("local") else ""
    resumo = (
        f"📋 **Novo item pronto para cadastro**\n\n"
        f"**Descrição:** {parsed['descricao']}\n"
        f"**Tipo:** {parsed['tipo']}\n"
        f"**Qtd:** {parsed['quantidade']}\n"
        f"**Patrimônio:** {parsed.get('patrimonio') or 'N/A'}\n"
        f"**Local:** {parsed.get('local') or 'N/A'}\n"
        f"**Foto:** ❌ Nenhuma"
        f"{alerta_local}\n\n"
        f"📸 *Envie uma foto agora para anexá-la, ou use os botões abaixo.*"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Salvar sem foto",       callback_data="confirm_save")],
        [InlineKeyboardButton(text="✏️ Editar Descrição",      callback_data="edit_description")],
        [InlineKeyboardButton(text="❌ Cancelar/Descartar",    callback_data="cancel_save")],
    ])
    sent = await message.answer(resumo, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Form.waiting_confirmation)
    await state.update_data(last_summary_msg_id=sent.message_id)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    db = SessionLocal()
    try:
        total       = db.query(func.count(Item.id)).scalar() or 0
        permanente  = db.query(func.count(Item.id)).filter(Item.tipo == "Permanente").scalar() or 0
        consumo     = db.query(func.count(Item.id)).filter(Item.tipo == "Consumo").scalar() or 0
        qtd_total   = db.query(func.sum(Item.quantidade)).scalar() or 0
        n_locais    = db.query(func.count(func.distinct(Item.local))).scalar() or 0
        sem_local   = db.query(func.count(Item.id)).filter(Item.local == None).scalar() or 0
        por_local   = (
            db.query(Item.local, func.count(Item.id).label("n"))
            .filter(Item.local != None)
            .group_by(Item.local)
            .order_by(func.count(Item.id).desc())
            .limit(5).all()
        )
    finally:
        db.close()

    top = "\n".join(f"  `{r.local}`: {r.n} item(s)" for r in por_local) or "  _nenhum_"
    text = (
        "📊 **Estatísticas do Inventário**\n\n"
        f"📦 Total de itens: **{total}**\n"
        f"🔢 Total de unidades: **{qtd_total}**\n"
        f"🔵 Permanentes: **{permanente}**\n"
        f"🟡 Consumo: **{consumo}**\n"
        f"📍 Locais distintos: **{n_locais}**\n"
        f"⚠️ Sem local definido: **{sem_local}**\n\n"
        f"🏆 *Top 5 locais:*\n{top}"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("item"))
async def cmd_item(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("ℹ️ Uso: `/item <id>` — Ex: `/item 4`", parse_mode="Markdown")
        return

    item_id = int(args[1].strip())
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            await message.answer(f"❌ Item #{item_id} não encontrado.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✏️ Editar", callback_data=f"cmd_edit:{item_id}"),
            InlineKeyboardButton(text="🗑️ Deletar", callback_data=f"cmd_del_ask:{item_id}"),
        ]])
        await message.answer(_fmt_item(item), reply_markup=kb, parse_mode="Markdown")
    finally:
        db.close()


@router.message(Command("editar"))
async def cmd_editar(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("ℹ️ Uso: `/editar <id>` — Ex: `/editar 4`", parse_mode="Markdown")
        return

    item_id = int(args[1].strip())
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            await message.answer(f"❌ Item #{item_id} não encontrado.")
            return
        await _open_item_for_edit(item, message, state)
    finally:
        db.close()


@router.message(Command("deletar"))
async def cmd_deletar(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("ℹ️ Uso: `/deletar <id>` — Ex: `/deletar 4`", parse_mode="Markdown")
        return

    item_id = int(args[1].strip())
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            await message.answer(f"❌ Item #{item_id} não encontrado.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Sim, excluir", callback_data=f"cmd_del_ok:{item_id}"),
            InlineKeyboardButton(text="❌ Cancelar",     callback_data="cmd_del_no"),
        ]])
        await message.answer(
            f"⚠️ Confirmar exclusão de **#{item.id} — {item.descricao}**?\n"
            f"Tipo: {item.tipo} | Qtd: {item.quantidade} | Local: {item.local or 'N/A'}",
            reply_markup=kb, parse_mode="Markdown"
        )
    finally:
        db.close()


@router.message(Command("buscar"))
async def cmd_buscar(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("ℹ️ Uso: `/buscar <termo>` — Ex: `/buscar martelo`", parse_mode="Markdown")
        return

    termo = args[1].strip()
    db = SessionLocal()
    try:
        pattern = f"%{termo}%"
        items = (
            db.query(Item)
            .filter(Item.descricao.ilike(pattern) | Item.local.ilike(pattern) | Item.patrimonio.ilike(pattern))
            .order_by(Item.id.desc())
            .limit(20).all()
        )
    finally:
        db.close()

    if not items:
        await message.answer(f"🔍 Nenhum resultado para `{termo}`.", parse_mode="Markdown")
        return

    linhas = [f"🔍 *{len(items)} resultado(s) para \"{termo}\":*\n"]
    for it in items:
        emoji = "🔵" if it.tipo == "Permanente" else "🟡"
        linhas.append(f"{emoji} `#{it.id}` *{it.descricao}* — {it.quantidade} un. | {it.local or 'sem local'}")
    linhas.append("\n_/item <id> para detalhes · /editar <id> para editar_")
    await message.answer("\n".join(linhas), parse_mode="Markdown")


@router.message(Command("recentes"))
async def cmd_recentes(message: Message):
    db = SessionLocal()
    try:
        items = db.query(Item).order_by(Item.data_registro.desc()).limit(10).all()
    finally:
        db.close()

    if not items:
        await message.answer("📭 Nenhum item cadastrado ainda.")
        return

    linhas = ["🕐 *Últimos 10 itens cadastrados:*\n"]
    for it in items:
        emoji = "🔵" if it.tipo == "Permanente" else "🟡"
        data  = it.data_registro.strftime("%d/%m %H:%M") if it.data_registro else "?"
        linhas.append(f"{emoji} `#{it.id}` *{it.descricao}* — {it.quantidade} un. | {data}")
    await message.answer("\n".join(linhas), parse_mode="Markdown")


@router.message(Command("tabela"))
async def cmd_tabela(message: Message):
    await _send_tabela(message, page=1)


async def _send_tabela(target, page: int, edit: bool = False):
    per_page = 10
    db = SessionLocal()
    try:
        total = db.query(func.count(Item.id)).scalar() or 0
        items = (
            db.query(Item)
            .order_by(Item.id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page).all()
        )
    finally:
        db.close()

    if not items:
        txt = "📭 Nenhum item cadastrado ainda."
        if edit:
            await target.edit_text(txt)
        else:
            await target.answer(txt)
        return

    total_pags = max(1, (total + per_page - 1) // per_page)
    linhas = [f"📦 *Inventário — Pág. {page}/{total_pags} ({total} itens)*\n"]
    linhas.append("`ID    Descrição           Tp   Qtd  Local`")
    linhas.append("`" + "─" * 44 + "`")
    for it in items:
        desc  = (it.descricao or "")[:17].ljust(17)
        tp    = "Perm" if it.tipo == "Permanente" else "Cons"
        qtd   = str(it.quantidade or 0).rjust(4)
        local = (it.local or "—")[:11]
        linhas.append(f"`#{str(it.id).ljust(5)}{desc} {tp} {qtd}  {local}`")
    linhas.append("\n_/item <id> · /editar <id> · /deletar <id>_")

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀ Anterior", callback_data=f"tabela_pg:{page - 1}"))
    if page < total_pags:
        nav.append(InlineKeyboardButton(text="Próximo ▶", callback_data=f"tabela_pg:{page + 1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[nav]) if nav else None
    txt = "\n".join(linhas)

    if edit:
        await target.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
    else:
        await target.answer(txt, reply_markup=kb, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════
#  CALLBACKS DOS COMANDOS DIRETOS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("tabela_pg:"))
async def cb_tabela_pg(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.split(":")[1])
    await _send_tabela(callback.message, page=page, edit=True)


@router.callback_query(F.data.startswith("cmd_edit:"))
async def cb_cmd_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    item_id = int(callback.data.split(":")[1])
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            await callback.message.edit_text(f"❌ Item #{item_id} não encontrado.")
            return
        await callback.message.delete()
        await _open_item_for_edit(item, callback.message, state)
    finally:
        db.close()


@router.callback_query(F.data.startswith("cmd_del_ask:"))
async def cb_cmd_del_ask(callback: CallbackQuery):
    await callback.answer()
    item_id = int(callback.data.split(":")[1])
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            await callback.message.edit_text(f"❌ Item #{item_id} não encontrado.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Sim, excluir", callback_data=f"cmd_del_ok:{item_id}"),
            InlineKeyboardButton(text="❌ Cancelar",     callback_data="cmd_del_no"),
        ]])
        await callback.message.edit_text(
            f"⚠️ Confirmar exclusão de **#{item.id} — {item.descricao}**?",
            reply_markup=kb, parse_mode="Markdown"
        )
    finally:
        db.close()


@router.callback_query(F.data.startswith("cmd_del_ok:"))
async def cb_cmd_del_ok(callback: CallbackQuery):
    await callback.answer()
    item_id = int(callback.data.split(":")[1])
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            await callback.message.edit_text(f"❌ Item #{item_id} não encontrado.")
            return
        desc = item.descricao
        db.delete(item)
        db.commit()
        await callback.message.edit_text(
            f"✅ Item **#{item_id} — {desc}** excluído com sucesso.", parse_mode="Markdown"
        )
    except Exception as e:
        db.rollback()
        await callback.message.edit_text(f"❌ Erro ao excluir: {e}")
    finally:
        db.close()


@router.callback_query(F.data == "cmd_del_no")
async def cb_cmd_del_no(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("❌ Exclusão cancelada.")
