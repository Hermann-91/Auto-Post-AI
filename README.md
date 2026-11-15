# 🤖 Robo-Auto-Inst — SaaS Multi-Tenant de Automação para Instagram

Plataforma SaaS multi-empresa construída em **Python 3.12+ / FastAPI** para criação assistida por IA (**OpenRouter**: DeepSeek + Visão Multimodal + Nano Banana), processamento determinístico de mídia (imagens `4:5`/`1:1`/`9:16`, carrosséis e vídeos MP4 via **Pillow** e **FFmpeg**), biblioteca com controle de cota e publicação/agendamento oficial via **Instagram Graph API (Instagram Login)**.

---

## 🏗️ Arquitetura e Diretrizes Técnicas

O projeto segue **Clean Architecture (Ports & Adapters)**, **SOLID** e **Dependency Injection**, com isolamento estrito por tenant (`empresa_id`) e por conta Instagram (`(empresa_id, conta_ig_id)`):

```text
app/api  -->  app/aplicacao  -->  app/dominio  <--  app/infra
```

- **Modularidade Estrita:** Todos os módulos `.py`, `.js` e `.css` possuem `<= 200` linhas.
- **Segurança por Padrão:**
  - Hash de senhas com **Argon2id** (`argon2-cffi` em thread pool + *dummy hash* anti-enumeração/timing attack).
  - Sessão com **Access Token JWT** curto (15 min) + **Refresh Token rotativo** com revogação automática de toda a família (`familia_id`) em caso de reuso.
  - Cookies `HttpOnly`, `SameSite=Lax`, `Secure` + proteção **CSRF Double-Submit** (`X-CSRF-Token`) e validação de `Origin`/`Sec-Fetch-Site`.
  - Proteção de entrada com **Rate Limit** (`IP + sha256(email)`) e **Cloudflare Turnstile** validado no servidor antes do Argon2id.
  - Tokens OAuth da Meta criptografados em repouso no banco com **Fernet (AES-128-CBC + HMAC-SHA256)** e suporte a rotação (`MultiFernet`).
  - Logging estruturado em JSON com filtro anti-vazamento (`[REDIGIDO]`) para tokens Bearer, JWT, Fernet, chaves OpenRouter e credenciais de banco/Redis.

---

## 📂 Estrutura do Projeto

```text
Robo-Auto-Inst/
├── alembic/                  # Migrações de banco de dados (SQLAlchemy 2.0 Async)
├── app/
│   ├── api/                  # FastAPI: rotas, schemas Pydantic, middlewares CSRF/CSP e containers DI
│   ├── aplicacao/            # Casos de uso puros: auth/, biblioteca/, ia/, publicacao/
│   ├── core/                 # Configurações (pydantic-settings), logging seguro e criptografia/JWT/Argon2
│   ├── dominio/              # Entidades, Objetos de Valor, Máquina de Estados, Exceções e Portas (Protocols)
│   ├── infra/                # Adaptadores: db/, storage/ (Local HMAC e R2/S3), midia/, ia/, meta/, seguranca/
│   ├── worker/               # Processo assíncrono de publicação agendada e renovação preventiva de tokens Meta
│   └── main.py               # Entrypoint e fábrica da aplicação FastAPI
├── doc/plan/                 # Documentação arquitetural e plano de fases
├── doc/                      # Guias de Deploy VPS (branch web) e Integração Meta Graph API
├── frontend/                 # Painel Web SPA desacoplado (HTML5, CSS Glassmorphic e JS ES Modules)
├── testes/                   # Suíte espelhada de testes unitários e de integração (129 testes)
├── Caddyfile                 # Proxy reverso HTTPS automático (Caddy 2)
├── Dockerfile                # Build multi-stage com Python 3.12-slim, FFmpeg e usuário não-root (appuser)
├── docker-compose.yml        # Orquestração: proxy, api, worker, db (Postgres 16), redis e tunnel (cloudflared)
├── pyproject.toml            # Configuração de pytest, ruff e mypy --strict
└── requirements.txt          # Dependências pinadas do projeto
```

---

## ⚙️ Configuração do Ambiente (`.env`)

1. Copie o arquivo de exemplo ou edite o `.env` na raiz do projeto:
   ```bash
   cp .env.example .env
   ```
2. Gere chaves criptográficas exclusivas para `JWT_SECRET_KEY` e `FERNET_KEYS`:
   ```bash
   .venv/bin/python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
   .venv/bin/python -c "from cryptography.fernet import Fernet; print('FERNET_KEYS=' + Fernet.generate_key().decode())"
   ```
3. Principais variáveis para **teste local (`APP_ENV=dev`)**:
   - `APP_ENV=dev` e `COOKIE_SECURE=false` (permite cookies sobre `http://localhost:8000`).
   - `CAPTCHA_ENABLED=false` (usa stub de Turnstile localmente).
   - `DATABASE_URL=sqlite+aiosqlite:///./robo_auto_inst_dev.db` (ou PostgreSQL).
   - `STORAGE_BACKEND=local`, `STORAGE_LOCAL_DIR=./data/storage` e `STORAGE_LOCAL_BASE_URL=https://<seu-tunel>.trycloudflare.com/media` (URL HTTPS pública exigida pela Meta para baixar mídias).
   - `META_GRAPH_BASE_URL=https://graph.facebook.com` (para tokens `EAA...` do Login Unificado / `SYSTEM_USER`) ou `https://graph.instagram.com` (para tokens `IGAA...`).
   - `OPENROUTER_API_KEY=sk-or-v1-...` (sua chave da OpenRouter para geração de legendas, curadoria visual e imagens).

---

## 🚀 Como Executar Localmente (Modo Desenvolvimento)

### 1. Ativar o ambiente virtual e aplicar migrações:
```bash
source .venv/bin/activate
alembic upgrade head
```

### 2. Iniciar a API + Painel Web:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **Painel Web:** [http://localhost:8000/painel/](http://localhost:8000/painel/)
- **Documentação Interativa (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Healthchecks:** [http://localhost:8000/healthz](http://localhost:8000/healthz) e [http://localhost:8000/readyz](http://localhost:8000/readyz)

### 3. Iniciar o Worker de Agendamento (opcional em segundo terminal):
```bash
python -m app.worker
```

---

## 🐳 Como Executar com Docker Compose (VPS / Produção)

Para subir toda a infraestrutura (6 containers: `db` PostgreSQL 16, `redis` Redis 7, `api` FastAPI, `worker`, `proxy` Caddy e `tunnel` Cloudflare HTTPS):

```bash
docker compose up -d --build --wait
docker compose ps
```

> **Captura da URL HTTPS do Túnel (`cloudflared`):**
> ```bash
> docker compose logs tunnel | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com'
> ```

> **Dica para teste local com Docker:** Caso as portas `80` e `443` da sua máquina já estejam ocupadas por outro serviço, parametrize `HTTP_PORT` e `HTTPS_PORT`:
> ```bash
> HTTP_PORT=8080 HTTPS_PORT=8443 docker compose up -d --build --wait
> ```

Para encerrar os containers:
```bash
docker compose down
```

---

## 🌿 Fluxo de Branches e Deploy Automático (`oracle-vps`)

| Branch | Finalidade |
| :--- | :--- |
| **`develop`** | Branch padrão de desenvolvimento local para novas features e experimentos. |
| **`main`** | Branch estável consolidada no GitHub. |
| **`web`** | Branch de produção vinculada ao deploy automático em tempo real na **`oracle-vps`**. |

Ao executar `git push origin web`, o Git envia os commits simultaneamente para o **GitHub** e para o repositório bare na **`oracle-vps`** (`oracle-vps:/home/ubuntu/repos/robo-auto-inst.git`), disparando o hook `post-receive` que reconstrói e reinicia os containers Docker em `/home/ubuntu/apps/robo-auto-inst`.

- Consulte [doc/deploy_vps_e_branches.md](doc/deploy_vps_e_branches.md) e [doc/guia_meta_graph_api.md](doc/guia_meta_graph_api.md) para detalhes operacionais.

---

## 🔌 Principais Endpoints da API

| Grupo | Método & Rota | Descrição |
| :--- | :--- | :--- |
| **Saúde** | `GET /healthz`, `GET /readyz` | Liveness da API e readiness de Banco/Redis |
| **Auth** | `GET /auth/config` | Configuração pública do Cloudflare Turnstile |
| **Auth** | `POST /auth/register`, `POST /auth/login` | Cadastro multi-tenant e login com cookies `HttpOnly` |
| **Auth** | `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | Rotação de sessão, logout e perfil do usuário |
| **Contas & RAG** | `POST /contas`, `GET /contas` | Cadastro e listagem de contas Instagram da empresa |
| **Contas & RAG** | `PUT /contas/{id}/config-ia`, `POST /contas/{id}/rag` | Persona, modelos preferidos e fontes RAG por conta |
| **Biblioteca** | `GET /biblioteca/{id}`, `GET /biblioteca/{id}/cota` | Listagem por pasta (`originais`, `processadas`, `IA-Cria`, `IA-Edita`) e uso da cota (`X/250`) |
| **Biblioteca** | `POST /biblioteca/{id}/upload` | Upload (`<= 100MB`) com compactação automática de imagens |
| **Biblioteca** | `PATCH /biblioteca/{id}/{midia_id}/curtida` | Marca/desmarca mídia favorita (protegida contra limpeza) |
| **Biblioteca** | `POST /biblioteca/{id}/limpar-pos-postagem` | Remove mídias de posts já publicados preservando favoritas |
| **Mídia Assinada** | `GET /media/{chave}?exp=...&sig=...` | Entrega pública assinada via HMAC para a Meta Graph API |
| **IA & Custos** | `POST /ia/criar-conteudo`, `POST /ia/curadoria-visual` | Criação individual de postagem com IA e resumo visual |
| **IA & Custos** | `GET /ia/orcamento/{conta_id}` | Consulta de consumo e saldo mensal em USD (`$`) |
| **Planejamento** | `POST /planejamento/gerar-grade`, `POST /planejamento/executar` | Planejamento Semanal Automatizado em 2 etapas (estimativa `$` + geração) |
| **Meta & Posts** | `POST /meta/oauth/url`, `POST /meta/oauth/callback` | Fluxo OAuth oficial Instagram Login |
| **Meta & Posts** | `POST /posts`, `GET /posts/{conta_id}`, `POST /posts/{conta_id}/{post_id}/publicar` | Agendamento, listagem e publicação imediata na Meta |

---

## 🧪 Qualidade de Código e Testes

O projeto conta com **129 testes automatizados** (unitários e de integração), linter **Ruff** e checagem estrita de tipos com **Mypy (`--strict`)**:

```bash
# Executar linter
.venv/bin/ruff check .

# Executar verificação estrita de tipos (app + testes)
.venv/bin/mypy app testes

# Executar suíte completa de testes
.venv/bin/pytest -v
```
