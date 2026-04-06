import os
import json
import sqlite3
import openai
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class ItemSchema(BaseModel):
    tipo: str = Field(description="Deve ser 'Permanente' ou 'Consumo'")
    descricao: str = Field(description="Nome ou descrição do item")
    quantidade: int = Field(description="Valor numérico", default=1)
    patrimonio: str | None = Field(description="Código patrimonial, null se não houver", default=None)
    local: str | None = Field(description="Local exato formatado como 'Laboratório X' ou 'Paiol X', null se não houver", default=None)

class EdicaoSchema(BaseModel):
    item_id: int | None = Field(description="ID numérico do item a editar, se mencionado", default=None)
    item_descricao: str | None = Field(description="Descrição/nome do item a editar, se não houver ID", default=None)

def consultar_estoque(consulta_sql: str) -> str:
    """Ferramenta para ajudar o LLM a consultar o banco de dados. Executa uma instrução SQL na tabela 'itens' e retorna os resultados.
    Tabela: itens (id, tipo, descricao, quantidade, patrimonio, local, usuario_id, data_registro).
    """
    if any(palavra in consulta_sql.lower() for palavra in ["drop", "delete", "update", "insert", "alter"]):
        return "Erro: Apenas consultas SELECT são permitidas."
        
    db_path = os.path.join(os.path.dirname(__file__), 'inventory.db')
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(consulta_sql)
        cols = [description[0] for description in cursor.description] if cursor.description else []
        results = cursor.fetchall()
        conn.close()
        str_res = str(results)[:2000]
        return f"Colunas: {cols}\nResultados: {str_res}"
    except Exception as e:
        return f"Erro na consulta SQL: {e}"

_gemini_client: genai.Client | None = None

def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "sua_chave_do_google_gemini_aqui":
            raise ValueError("GEMINI_API_KEY não configurada.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client

def process_with_gemini(text: str, current_item: dict, intent_prompt: str) -> dict:
    c = _get_gemini_client()

    response_intent = c.models.generate_content(
        model='gemini-2.0-flash',
        contents=intent_prompt,
    )
    intent = response_intent.text.strip().upper()
    
    if "PERGUNTA" in intent:
        question_prompt = f"""
        O usuário perguntou ou falou: "{text}"
        Você é um assistente de gestão de inventário. Responda de forma clara e amigável.
        Se ele perguntou sobre algo no estoque, use a ferramenta `consultar_estoque` para montar uma query SQL e ver a tabela 'itens', depois responda com a conclusão.
        ATENÇÃO: Responda usando TEXTO PURO. NÃO utilize formatação Markdown (como negrito, itálico, ou listas com asteriscos), pois isso causa erro de sintaxe no servidor do chat.
        """
        chat = c.chats.create(
            model='gemini-2.0-flash',
            config=types.GenerateContentConfig(tools=[consultar_estoque])
        )
        response_qa = chat.send_message(question_prompt)
        return {"intent": "PERGUNTA", "resposta": response_qa.text}
        
    elif "EDICAO" in intent:
        edicao_prompt = f"""
        O usuário quer editar um item existente no banco. Mensagem: "{text}"
        Extraia o ID numérico do item (se mencionado) ou a descrição/nome do item para localizá-lo.
        """
        response_edicao = c.models.generate_content(
            model='gemini-2.0-flash',
            contents=edicao_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EdicaoSchema,
            )
        )
        return {"intent": "EDICAO", **json.loads(response_edicao.text)}

    elif "CORRECAO" in intent:
        update_prompt = f"""
        O usuário enviou uma correção: "{text}"
        O item atual estava assim: {json.dumps(current_item, ensure_ascii=False) if current_item else "Nenhum (crie do zero)"}

        Aplique a correção pedida ao item e retorne os dados no formato atualizado com JSON Exato obedecendo ao schema.
        Mantenha as regras do sistema: tipo='Permanente' ou 'Consumo', local deve ter prefixo 'Laboratório' ou 'Paiol'.
        """
        response_item = c.models.generate_content(
            model='gemini-2.0-flash',
            contents=update_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ItemSchema,
            )
        )
        return {"intent": "CORRECAO", "item": json.loads(response_item.text)}

    else:
        extract_prompt = f"""
        Extraia as informações do seguinte texto do inventário: "{text}"
        Regras de Negócio:
        tipo: 'Permanente' ou 'Consumo' (se não falar, defina como 'Consumo').
        quantidade: Número inteiro (padrão 1).
        local: Formate como 'Laboratório X' ou 'Paiol X' (Ex: 'lab 4' vira 'Laboratório 04').
        patrimonio: O número do patrimônio se mencionado.
        descricao: O nome limpo do item, capitalizado.
        """
        response_item = c.models.generate_content(
            model='gemini-2.0-flash',
            contents=extract_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ItemSchema,
            )
        )
        return {"intent": "CADASTRO", "item": json.loads(response_item.text)}


def process_with_openai(text: str, current_item: dict, intent_prompt: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "sua_chave_da_openai_aqui":
        raise ValueError("OPENAI_API_KEY não configurada.")
        
    client_oai = openai.OpenAI(api_key=api_key)
    
    # 1. Intent Detection
    res_intent = client_oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": intent_prompt}],
        temperature=0.0
    )
    intent = res_intent.choices[0].message.content.strip().upper()
    
    if "PERGUNTA" in intent:
        question_prompt = f"""
        O usuário perguntou ou falou: "{text}"
        Você é um assistente de gestão de inventário. Responda de forma clara e amigável.
        Se ele perguntou sobre algo no estoque, use a ferramenta `consultar_estoque` para montar uma query SQL e ver a tabela 'itens', depois responda com a conclusão.
        ATENÇÃO: Responda usando TEXTO PURO. NÃO utilize formatação Markdown.
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "consultar_estoque",
                    "description": "Executa comando SQL na tabela 'itens' (id, tipo, descricao, quantidade, patrimonio, local, usuario_id, data_registro).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "consulta_sql": {
                                "type": "string",
                                "description": "Consulta SELECT pronta para rodar."
                            }
                        },
                        "required": ["consulta_sql"]
                    }
                }
            }
        ]
        messages = [{"role": "user", "content": question_prompt}]
        response = client_oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            temperature=0.3
        )
        msg_out = response.choices[0].message
        
        # Automatic Tool Execution Fallback equivalent
        if msg_out.tool_calls:
            messages.append(msg_out)
            for tool_call in msg_out.tool_calls:
                if tool_call.function.name == "consultar_estoque":
                    args = json.loads(tool_call.function.arguments)
                    sql_res = consultar_estoque(args["consulta_sql"])
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": sql_res
                    })
            response2 = client_oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3
            )
            return {"intent": "PERGUNTA", "resposta": response2.choices[0].message.content}
            
        return {"intent": "PERGUNTA", "resposta": msg_out.content}
        
    elif "EDICAO" in intent:
        edicao_prompt = f"""
        O usuário quer editar um item existente no banco. Mensagem: "{text}"
        Extraia o ID numérico do item (se mencionado) ou a descrição/nome do item para localizá-lo.
        """
        response_edicao = client_oai.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": edicao_prompt}],
            response_format=EdicaoSchema,
        )
        return {"intent": "EDICAO", **json.loads(response_edicao.choices[0].message.content)}

    elif "CORRECAO" in intent:
        update_prompt = f"""
        O usuário enviou uma correção: "{text}"
        O item atual estava assim: {json.dumps(current_item, ensure_ascii=False) if current_item else "Nenhum (crie do zero)"}

        Aplique a correção pedida ao item e retorne os dados no formato Exato do JSON Schema.
        """
        response_item = client_oai.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": update_prompt}],
            response_format=ItemSchema,
        )
        return {"intent": "CORRECAO", "item": json.loads(response_item.choices[0].message.content)}

    else:
        extract_prompt = f"""
        Extraia as informações do seguinte texto do inventário: "{text}"
        Regras de Negócio:
        tipo: 'Permanente' ou 'Consumo' (se não falar, presuma 'Consumo').
        quantidade: Número (padrão 1).
        local: Formate como 'Laboratório X' ou 'Paiol X' (Ex: 'lab 4' vira 'Laboratório 04').
        descricao: Nome limpo do objeto.
        """
        response_item = client_oai.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extract_prompt}],
            response_format=ItemSchema,
        )
        return {"intent": "CADASTRO", "item": json.loads(response_item.choices[0].message.content)}

def _process_image_with_openai_vision(image_bytes: bytes, mime_type: str) -> dict:
    import base64
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "sua_chave_da_openai_aqui":
        raise ValueError("OPENAI_API_KEY não configurada.")

    client_oai = openai.OpenAI(api_key=api_key)
    b64 = base64.b64encode(image_bytes).decode()

    prompt = (
        "Você é um assistente de gestão de inventário laboratorial/almoxarifado. "
        "Analise esta imagem (etiqueta de patrimônio ou foto do objeto) e extraia as informações disponíveis. "
        "descricao: nome do item (ex: 'Microscópio Óptico', 'Béquer 500ml'). "
        "tipo: 'Permanente' para equipamentos duráveis; 'Consumo' para materiais descartáveis. "
        "quantidade: número indicado ou 1. "
        "patrimonio: código/número de tombamento visível na etiqueta (null se não houver). "
        "local: local indicado na etiqueta no formato 'Laboratório X' ou 'Paiol X' (null se não visível)."
    )

    response = client_oai.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
            ]
        }],
        response_format=ItemSchema,
    )
    return {"intent": "CADASTRO", "item": json.loads(response.choices[0].message.content)}


def process_image_for_catalog(image_path: str) -> dict:
    """Analisa foto de etiqueta ou objeto com Gemini Vision para extrair dados do item."""
    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
    except Exception as e:
        return {"intent": "ERROR", "resposta": f"❌ Erro ao ler imagem: {e}"}

    mime_type = "image/jpeg"
    if image_path.lower().endswith('.webp'):
        mime_type = "image/webp"
    elif image_path.lower().endswith('.png'):
        mime_type = "image/png"

    extraction_prompt = (
        "Você é um assistente de gestão de inventário laboratorial/almoxarifado. "
        "Analise esta imagem — pode ser uma etiqueta de patrimônio/identificação ou foto direta do objeto. "
        "Extraia as informações disponíveis:\n"
        "- descricao: nome do item (ex: 'Microscópio Óptico', 'Béquer 500ml', 'Cadeira Giratória').\n"
        "- tipo: 'Permanente' para equipamentos e bens duráveis; 'Consumo' para materiais descartáveis.\n"
        "- quantidade: quantidade indicada (padrão 1).\n"
        "- patrimonio: número/código de tombamento ou patrimônio visível na etiqueta (null se não houver).\n"
        "- local: local indicado na etiqueta no formato 'Laboratório X' ou 'Paiol X' (null se não visível).\n"
        "Se for etiqueta: priorize patrimônio, descrição e local. "
        "Se for foto do objeto: identifique o equipamento/material e classifique adequadamente."
    )

    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "openai":
        try:
            return _process_image_with_openai_vision(image_bytes, mime_type)
        except Exception as e:
            return {"intent": "ERROR", "resposta": f"❌ OpenAI Vision Erro: {e}"}

    try:
        c = _get_gemini_client()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = c.models.generate_content(
            model='gemini-2.0-flash',
            contents=[extraction_prompt, image_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ItemSchema,
            )
        )
        return {"intent": "CADASTRO", "item": json.loads(response.text)}
    except Exception as e_gemini:
        print(f"[Warning] Gemini Vision falhou: {e_gemini}. Tentando OpenAI Vision Fallback...")
        try:
            return _process_image_with_openai_vision(image_bytes, mime_type)
        except Exception as e_openai:
            return {
                "intent": "ERROR",
                "resposta": (
                    f"❌ Falha nos serviços de visão computacional.\n\n"
                    f"🌐 Gemini: {e_gemini}\n"
                    f"🧠 OpenAI: {e_openai}"
                )
            }


def process_user_input(text: str, current_item: dict = None) -> dict:
    """
    Processa a entrada usando Gemini. Se falhar (ex: Rate limit quota), tenta OpenAI fallback automaticamente.
    """
    intent_prompt = f"""
    Analise a seguinte mensagem do usuário: "{text}"
    O contexto atual na memória (item sendo editado) é: {current_item}

    Regras estritas de classificação:
    - EDICAO: o usuário quer abrir um item JÁ EXISTENTE no banco para editar, referenciando-o por ID (ex: "editar item 4", "alterar item ID 7", "quero mudar o item 12") ou por nome (ex: "editar a furadeira", "modificar o martelo"). Use esta intenção quando o usuário quer carregar um item do banco — independente de haver contexto atual.
    - CORRECAO: 'contexto atual' existe (não é None) e o usuário envia uma mudança pontual no item em memória (ex: "muda pra 3", "o local é Lab 02", "tipo Permanente"). NÃO use se o usuário mencionar ID de banco.
    - CADASTRO: o usuário está ditando um novo item para registrar (ex: "2 martelos no Lab 3", "cadastrar cadeira permanente").
    - PERGUNTA: o usuário faz uma pergunta sobre o estoque ou conversa livremente.

    Classifique em exatamente UMA categoria (EDICAO, CADASTRO, CORRECAO, PERGUNTA).
    Responda APENAS com a palavra da intenção.
    """
    
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "openai":
        # Usa exclusivamente OpenAI (sem fallback)
        try:
            return process_with_openai(text, current_item, intent_prompt)
        except Exception as e:
            return {"intent": "ERROR",
                    "resposta": f"❌ **OpenAI Erro:** {e}\n\nVerifique sua OPENAI_API_KEY nas configurações."}

    # Padrão: Gemini com fallback para OpenAI
    try:
        return process_with_gemini(text, current_item, intent_prompt)
    except Exception as e_gemini:
        print(f"[Warning] Gemini falhou: {e_gemini}. Tentando OpenAI Fallback...")
        try:
            return process_with_openai(text, current_item, intent_prompt)
        except Exception as e_openai:
            return {
                "intent": "ERROR",
                "resposta": (
                    f"❌ Falha nos serviços de IA.\n\n"
                    f"🌐 **Gemini:** {e_gemini}\n"
                    f"🧠 **OpenAI:** {e_openai}\n\n"
                    "Verifique as chaves de API nas configurações do Dashboard."
                )
            }
