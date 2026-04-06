# SisCatLaMP

Bot de Telegram para gestão de inventário laboratorial com IA (Google Gemini + OpenAI), dashboard web e suporte a áudio, texto e fotos.

---

## Funcionalidades

- **Bot do Telegram** com comandos diretos e linguagem natural via IA
- **Dashboard web** em `http://localhost:8001` com tabela de itens, filtros, busca e estatísticas
- **Cadastro por voz** — áudios OGG transcritos automaticamente via Whisper
- **Cadastro por foto** — imagens comprimidas e vinculadas ao item
- **IA dual** — Google Gemini como principal, OpenAI como fallback automático
- **Ícone na bandeja do Windows** com status de conexão em tempo real
- **FFmpeg baixado automaticamente** na primeira execução
- **Configuração pelo dashboard** — chaves de API, provedor de IA e importação de `.env`

---

## Pré-requisitos

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- Um **Bot do Telegram** criado via [@BotFather](https://t.me/BotFather)
- Chave da API **Google Gemini** — [aistudio.google.com](https://aistudio.google.com/app/apikey)
- Chave da API **OpenAI** (opcional, fallback) — [platform.openai.com](https://platform.openai.com/api-keys)
- **FFmpeg** — baixado automaticamente, ou instale via [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)

---

## Instalação local

### 1. Clone o repositório

```bash
git clone <url-do-repositorio>
cd SisCatLaMP
```

### 2. Crie e ative o ambiente virtual

```bash
python -m venv venv

# Windows
venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

```bash
copy .env.example .env
```

Edite o `.env` e preencha:

```env
BOT_TOKEN=seu_token_do_botfather_aqui
GEMINI_API_KEY=sua_chave_do_google_gemini_aqui
OPENAI_API_KEY=sua_chave_da_openai_aqui   # opcional
LLM_PROVIDER=gemini                        # gemini | openai
```

> Alternativamente, configure as chaves pelo próprio Dashboard após subir o app (Configurações → Importar `.env` ou preencha os campos manualmente).

---

## Como rodar

O projeto tem três modos de execução. Use apenas **um por vez**.

### Modo 1 — Aplicativo completo com bandeja (recomendado)

Sobe o bot + dashboard + monitoramento de status em um único processo.

```bash
python app_tray.py
```

Um ícone aparece na bandeja do Windows. Clique com botão direito para:
- Ver o status de cada serviço (Telegram, Gemini, OpenAI)
- Abrir o dashboard no navegador
- Encerrar o aplicativo

### Modo 2 — Somente o Bot

```bash
python main.py
```

### Modo 3 — Somente o Dashboard

```bash
python dashboard_api.py
```

Acesse em: **http://localhost:8001**

---

## Dashboard

Interface web completa acessível em `http://localhost:8001`.

### Barra de status
Exibida no topo da página, atualizada a cada 30 segundos:

| Indicador | Verde | Amarelo | Vermelho |
|---|---|---|---|
| Internet | Conectado | — | Sem conexão |
| FFmpeg | Disponível | — | Não encontrado |
| Gemini | Chave configurada | Sem chave | — |
| OpenAI | Chave configurada | Sem chave | — |

### Configurações (ícone ⚙ no cabeçalho)

- **Importar `.env`** — arraste o arquivo ou clique para selecionar; as chaves são identificadas automaticamente e preenchidas nos campos correspondentes
- **Provedor de IA** — alterne entre Gemini (com fallback OpenAI) e OpenAI exclusivo
- **Chaves de API** — edite Bot Token, Gemini Key e OpenAI Key com campo mascarado e botão de revelar
- **FFmpeg** — status e botão de download automático caso não esteja instalado

---

## Comandos do Bot

### Cadastro direto (sem IA)

```
/inserir <descrição> <tipo> <qtd> <patrimônio> <local>
```

| Campo | Valores | Exemplo |
|---|---|---|
| `descrição` | Texto livre (antes do tipo) | `Furadeira de Impacto` |
| `tipo` | `Permanente` ou `Consumo` | `Permanente` |
| `qtd` | Número inteiro | `2` |
| `patrimônio` | Código ou `-` se não houver | `12345` |
| `local` | Texto livre (último campo) | `Laboratório 1` |

```
/inserir Furadeira de Impacto Permanente 1 12345 Laboratório 1
/inserir Papel A4 Consumo 10 - Paiol 2
```

Após o comando, o bot aguarda o envio de uma foto para anexar ao item.

### Todos os comandos

| Comando | Descrição |
|---|---|
| `/inserir <desc> <tipo> <qtd> <pat> <local>` | Cadastrar item diretamente |
| `/tabela` | Listar todos os itens (paginado, 10 por página) |
| `/item <id>` | Ver detalhes completos de um item |
| `/editar <id>` | Editar item por ID |
| `/deletar <id>` | Excluir item por ID com confirmação |
| `/buscar <termo>` | Buscar por descrição, local ou patrimônio |
| `/recentes` | Últimos 10 itens cadastrados |
| `/stats` | Estatísticas: total, por tipo, top 5 locais |
| `/locais` | Lista de locais permitidos |
| `/ajuda` | Lista todos os comandos |

### Com linguagem natural (IA)

| Intenção | Exemplo |
|---|---|
| Cadastrar | `"2 cadeiras no Laboratório 3"` |
| Editar item do banco | `"editar item 4"` ou `"modificar a furadeira"` |
| Corrigir item em edição | `"muda a quantidade para 5"` |
| Consultar estoque | `"Quantos martelos têm no estoque?"` |

Áudio 🎙️ e fotos 📸 também são aceitos em qualquer momento.

---

## Instalação como executável (.exe)

Para distribuir para outras máquinas Windows sem precisar instalar Python:

```bat
# Com o venv ativo, na pasta do projeto:
build_exe.bat
```

O executável é gerado em `dist\SisCatLaMP\SisCatLaMP.exe`.

### Checklist antes de instalar na máquina destino

1. Copie o arquivo `.env` preenchido para `dist\SisCatLaMP\`
   - Ou configure as chaves pelo Dashboard após a primeira execução
2. **FFmpeg** é baixado automaticamente na primeira execução (requer internet)
   - Sem internet: copie `ffmpeg.exe` para dentro de `dist\SisCatLaMP\`
3. **Modelo Whisper** (~74 MB) é baixado automaticamente na primeira execução
   - Sem internet: copie a pasta `models\whisper\` para dentro de `dist\SisCatLaMP\`

---

## Estrutura do projeto

```
SisCatLaMP/
├── app_tray.py          # Ponto de entrada completo (bot + dashboard + bandeja)
├── main.py              # Ponto de entrada somente do bot
├── dashboard_api.py     # API REST (FastAPI) — itens, health, config
├── bot_handlers.py      # Handlers do Telegram: comandos e fluxo IA
├── ai_agent.py          # Integração Gemini / OpenAI com seleção de provedor
├── media_processor.py   # Áudio (Whisper) e imagens (FFmpeg)
├── ffmpeg_setup.py      # Download automático do FFmpeg
├── database.py          # Configuração SQLAlchemy + SQLite
├── models.py            # Modelo ORM — tabela itens
├── dashboard/
│   └── index.html       # Dashboard SPA (HTML + CSS + JS)
├── media/
│   ├── fotos/           # Fotos comprimidas dos itens
│   └── audio_tmp/       # Áudios temporários
├── models/
│   └── whisper/         # Modelo Whisper armazenado localmente
├── .env                 # Variáveis de ambiente — NÃO versionar
├── .env.example         # Template de configuração
├── requirements.txt     # Dependências Python
└── build_exe.bat        # Script de build do executável Windows
```

---

## Solução de problemas

**Conflito "only one bot instance is running"**
- Outra instância do bot já está rodando (outro terminal ou processo em background)
- Encerre todos os processos Python e reinicie: `taskkill /F /IM python.exe`

**Erro 429 no Gemini (cota excedida)**
- O free tier permite 1.500 req/dia com `gemini-2.0-flash`
- Acesse o Dashboard → Configurações → mude o Provedor para **OpenAI**

**OpenAI 401 Unauthorized**
- A `OPENAI_API_KEY` está incorreta ou não configurada
- Acesse o Dashboard → Configurações → atualize a chave

**FFmpeg não encontrado**
- Dashboard → Configurações → clique em **Baixar automaticamente**
- Ou instale manualmente e adicione ao PATH do Windows

**Áudio não transcrito**
- O modelo Whisper é baixado na primeira execução (~74 MB)
- Se a máquina não tiver internet, copie a pasta `models\whisper\` manualmente
