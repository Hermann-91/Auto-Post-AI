# Plano em Fases: Robo-Auto-Inst (SaaS Automação Instagram)

## 1. Visão Geral & Contrato Arquitetural
- **Objetivo:** Construir uma plataforma SaaS multi-empresa em Python para criação assistida por IA (OpenRouter), tratamento híbrido de mídia e publicação/agendamento oficial via Instagram Graph API, pronta para deploy via Docker em VPS com login seguro.
- **Stack & Padrões:** Python 3.12+, FastAPI, pydantic-settings, argon2-cffi, PyJWT, cryptography (Fernet), SQLAlchemy + Alembic, PostgreSQL (prod) / SQLite (dev), Redis, Worker dedicado, Caddy HTTPS, Docker Compose, Clean Architecture (`api -> aplicacao -> dominio <- infra`), SOLID e Dependency Injection.
- **Documentação Técnica Associada:**
  - `doc/plan/arq/arquitetura_saas.md`
  - `doc/plan/ia/openrouter_e_custos.md`
  - `doc/plan/meta/instagram_graph_api.md`
  - `doc/plan/drive/storage_e_drive.md`
- **Diretrizes Inegociáveis:**
  1. **Arquivos de código <= 200 linhas** (modularização estrita).
  2. **Zero segredos hardcoded** (`.env` + criptografia Fernet/AES-GCM para tokens OAuth no DB).
  3. **Isolamento Multi-Tenant:** `empresa_id` sempre extraído do usuário autenticado no servidor.
  4. **Quality Gate obrigatório:** nenhum avanço de fase sem `pytest` (e linter) 100% verdes.
  5. **Segurança na entrada:** Argon2id, Cookies `HttpOnly`/`Secure`/`SameSite=Lax`, Rate Limit (Redis) e Cloudflare Turnstile validado no back-end.
  6. **Controle de Versão:** Inicializar repositório Git (`git init`) na raiz do projeto antes do commit da Fase 1.
  7. **Espelhamento de Testes:** Todo módulo em `app/<camada>/<subpacote>/<arquivo>.py` deve possuir teste espelhado em `testes/{unit,integration}/<camada>/<subpacote>/test_<arquivo>.py` (`<= 200` linhas).

## 2. Checklist de Fases & Status
- [ ] **Fase 1: Fundação, Domínio Multi-Tenant & Segurança Base (Auth + Turnstile + Rate Limit)**
  - Status: Pendente | Commit: `-`
- [ ] **Fase 2: Persistência (SQLAlchemy/Alembic), Docker/VPS & Storage R2/S3 com Cotas**
  - Status: Pendente | Commit: `-`
- [ ] **Fase 3: Pipeline Determinístico de Mídia (Migração Refatorada de `midia/`)**
  - Status: Pendente | Commit: `-`
- [ ] **Fase 4: Gateway OpenRouter (DeepSeek + Nano Banana), Prompts/RAG por Conta, Planejamento Semanal & Orçamento ($)**
  - Status: Pendente | Commit: `-`
- [ ] **Fase 5: Meta Graph API Oficial (OAuth + Containers/Polling) & Worker de Agendamento**
  - Status: Pendente | Commit: `-`
- [ ] **Fase 6: Google Drive Opcional & Painel Web MVP (Login, Biblioteca, Planejamento Semanal & Custos)**
  - Status: Pendente | Commit: `-`
- [ ] **Fase Final: Auditoria, Revisão Geral & Hardening para VPS**
  - Status: Pendente | Commit: `-`

## 3. Detalhamento de Cada Fase

### Fase 1: Fundação, Domínio Multi-Tenant & Segurança Base
- **Arquivos (NEW):**
  - `pyproject.toml`, `requirements.txt`, `app/main.py`
  - `app/core/config.py`, `app/core/logging_config.py`, `app/core/seguranca/` (`senha_argon2.py`, `token_jwt.py`, `criptografia_fernet.py`)
  - `app/dominio/excecoes.py`, `app/dominio/objetos_valor/` (`enums_tenant.py`, `enums_conteudo.py`, `cota_midia.py`, `maquina_estados.py`)
  - `app/dominio/entidades/` (`tenant.py`, `ia_rag.py`, `midia.py`, `publicacao.py`)
  - `app/dominio/portas/` (`seguranca.py`, `repositorios_tenant.py`, `repositorios_conteudo.py`, `midia_storage.py`, `ia_meta.py` — incluindo `RefreshTokenRepositoryPort`, `ProvedorAuthMetaPort`, `DriveImportPort`, `ClienteIAPort`)
  - `app/aplicacao/auth/` (`dtos.py`, `protecao_entrada.py`, `emissao_sessao.py`, `registrar_usuario.py`, `autenticar_usuario.py`, `gerenciar_sessao.py`)
  - `app/infra/seguranca/` (`turnstile_adapter.py`, `rate_limiter_redis.py`, `rate_limiter_mem.py`) e `app/infra/memoria/` (`repo_tenant_mem.py`, `repo_refresh_mem.py`)
  - `app/api/dependencias/` (`container_auth.py`, `usuario_atual.py`), `app/api/schemas/auth.py`, `app/api/middlewares/seguranca_http.py`, `app/api/rotas/` (`health.py`, `auth.py`)
  - `testes/conftest.py`
  - `testes/unit/core/` (`test_config.py`, `seguranca/test_{senha_argon2,token_jwt,criptografia_fernet}.py`)
  - `testes/unit/dominio/` (`objetos_valor/test_{cota_midia,maquina_estados}.py`, `entidades/test_{tenant,ia_rag,midia,publicacao}.py`)
  - `testes/unit/aplicacao/auth/` (`test_{protecao_entrada,registrar_usuario,autenticar_usuario,gerenciar_sessao}.py`)
  - `testes/unit/infra/seguranca/` (`test_{turnstile_adapter,rate_limiter_mem,rate_limiter_redis}.py`)
  - `testes/integration/api/rotas/` (`test_health.py`, `test_auth.py`)
- **Responsabilidade & Funções:** Entidades multi-Instagram por empresa (`ConfigIAConta`, `FonteRAG`, `MidiaBiblioteca`, `Postagem`, `PlanejamentoSemanal`, `RegistroCustoIA`) com máquina de estados validada e invariantes Meta (`CAROUSEL` 2–10 itens, `STORIES` sem legenda), cotas de mídia (250 itens/GB), proteção anti-timing no Argon2id, rotação/revogação de refresh token por família, Turnstile antes do Argon2id e rate limit por `IP + sha256(email)`.
- **Quality Gate:** `pytest testes/unit/core testes/unit/dominio testes/unit/aplicacao/auth testes/unit/infra/seguranca testes/integration/api/rotas -v`
- **Mensagem do Commit:** `feat(core): dominio multi-tenant, auth argon2/jwt, rate limit e turnstile`

### Fase 2: Persistência, Docker/VPS & Storage R2/S3 com Cotas
- **Arquivos (NEW):**
  - `app/infra/db/` (`sessao.py`, `modelos_tenant.py`, `modelos_conteudo.py`, `repo_tenant_sql.py`, `repo_midia_sql.py`, `repo_post_custo_sql.py`), `alembic.ini`, `alembic/`
  - `app/infra/storage/` (`s3_r2_adapter.py`, `local_storage_adapter.py`), `app/aplicacao/biblioteca/` (`servico_upload_cota.py`, `servico_limpeza.py`)
  - `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `.env.example`, `.dockerignore`
  - `testes/unit/aplicacao/biblioteca/` (`test_servico_upload_cota.py`, `test_servico_limpeza.py`)
  - `testes/integration/infra/db/` (`test_repo_tenant_sql.py`, `test_repo_midia_sql.py`, `test_repo_post_custo_sql.py`) e `testes/integration/infra/storage/test_s3_r2_adapter.py`
- **Responsabilidade & Funções:** Persistência multi-conta, upload na nuvem R2/S3 organizado em `originais/`, `processadas/`, `IA-Cria/`, `IA-Edita/`, validação de cota (250 mídias / GB), botão de curtida (`curtida_favorita`) e limpeza pós-postagem preservando favoritas.
- **Quality Gate:** `pytest testes/unit/aplicacao/biblioteca testes/integration/infra/db testes/integration/infra/storage -v` e `docker compose config`
- **Mensagem do Commit:** `feat(infra): persistencia multi-conta, storage r2/s3 com cotas e docker vps`

### Fase 3: Pipeline Determinístico de Mídia (Reaproveitamento `projeto_robo_instagram/midia`)
- **Arquivos (NEW - refatorados de `projeto_robo_instagram/midia/`):**
  - `app/infra/midia/processador_imagem.py` (compactação no upload + corte `4:5` e `9:16` + conversão JPEG RGB)
  - `app/infra/midia/compositor_capa.py` (logo/gradiente opcional parametrizado por conta)
  - `app/infra/midia/gerador_carrossel.py` (slides sem strings/logos fixas)
  - `app/infra/midia/editor_video.py` (`ffmpeg` 4:5 / 9:16 com timeout e validação de erro)
  - `app/infra/midia/estrategias_midia.py` (Strategy + DI por tipo: `IMAGE`, `CAROUSEL`, `REELS`, `STORIES`)
  - `testes/unit/infra/midia/` (`test_processador_imagem.py`, `test_compositor_capa.py`, `test_gerador_carrossel.py`, `test_editor_video.py`, `test_estrategias_midia.py`)
- **Responsabilidade & Funções:** Compactar ativos para economizar cota e garantir 100% de compatibilidade com a Meta (JPEG, MP4, aspect ratios) a custo $0 de IA.
- **Quality Gate:** `pytest testes/unit/infra/midia -v`
- **Mensagem do Commit:** `feat(midia): pipeline deterministico multi-formato via strategy e di`

### Fase 4: Gateway OpenRouter, Prompts/RAG & Controle de Orçamento ($)
- **Arquivos (NEW):**
  - `app/infra/ia/cliente_openrouter.py` (texto `deepseek/deepseek-v4-flash`, imagem Nano Banana `modalities=["image","text"]`, extração `usage.cost`)
  - `app/infra/ia/pesquisa_tendencias.py` (busca web de tendências com cache 24h–72h no Redis/DB)
  - `app/aplicacao/ia/` (`servico_orcamento.py`, `servico_prompts_rag.py`, `criar_conteudo.py`, `planejamento_semanal.py`)
  - `app/api/schemas/criacao_ia.py`, `app/api/rotas/` (`contas_config.py`, `criacao.py`, `planejamento.py`)
  - `testes/unit/aplicacao/ia/` (`test_{servico_orcamento,servico_prompts_rag,criar_conteudo,planejamento_semanal}.py`), `testes/unit/infra/ia/` (`test_cliente_openrouter.py`, `test_pesquisa_tendencias.py`), `testes/integration/api/rotas/test_criacao_planejamento.py`
- **Responsabilidade & Funções:** Gerar conteúdo individual e executar o **Planejamento Semanal Automatizado** em 2 etapas (grade + estimativa `$` -> geração assíncrona no Worker baseada no RAG, web e fotos curtidas, salvando em `IA-Cria`/`IA-Edita`).
- **Quality Gate:** `pytest testes/unit/aplicacao/ia testes/unit/infra/ia testes/integration/api/rotas/test_criacao_planejamento.py -v`
- **Mensagem do Commit:** `feat(ia): gateway openrouter, rag por conta, planejamento semanal e orcamento`

### Fase 5: Meta Graph API Oficial & Worker de Agendamento
- **Arquivos (NEW):**
  - `app/infra/meta/auth_instagram_login.py` (`graph.instagram.com` OAuth + refresh long-lived token)
  - `app/infra/meta/cliente_meta_http.py` + `app/infra/meta/estrategias_publicacao.py` (Strategy + DI para `IMAGE`, `CAROUSEL`, `REELS`, `STORIES`; polling `FINISHED`; `content_publishing_limit`; idempotência)
  - `app/aplicacao/publicacao/servico_agendamento.py`, `app/worker/` (`agendador.py`, `executor_lotes.py`)
  - `app/api/schemas/postagens_meta.py`, `app/api/rotas/` (`meta_oauth.py`, `posts.py`)
  - `testes/unit/aplicacao/publicacao/test_servico_agendamento.py`, `testes/integration/infra/meta/` (`test_auth_instagram_login.py`, `test_estrategias_publicacao.py`), `testes/integration/worker/` (`test_agendador.py`, `test_executor_lotes.py`)
- **Responsabilidade & Funções:** Publicação oficial multi-conta e multi-formato com agendamento resiliente sem duplicação, pronto para testar com sua conta dev.
- **Quality Gate:** `pytest testes/unit/aplicacao/publicacao testes/integration/infra/meta testes/integration/worker -v`
- **Mensagem do Commit:** `feat(meta): oauth instagram login, publicacao em 2 etapas e worker agendador`

### Fase 6: Google Drive Opcional & Painel Web MVP
- **Arquivos (NEW):**
  - `app/infra/drive/cliente_google_drive.py` (OAuth read-only para importar fotos -> storage local/pipeline)
  - `app/api/schemas/biblioteca.py`, `app/api/dependencias/container_servicos.py`, `app/api/rotas/` (`drive.py`, `biblioteca.py`)
  - `frontend/` (login com Turnstile, seletor de conta Instagram ativa, **Biblioteca na Nuvem** com pastas `originais`/`processadas`/`IA-Cria`/`IA-Edita`, **botão de curtida**, cota `X/250` e **botão de limpeza pós-postagem**, **Aba de Planejamento Semanal Automatizado**, prompts/RAG e custos `$`)
  - `testes/integration/infra/drive/test_cliente_google_drive.py`, `testes/integration/api/rotas/` (`test_drive.py`, `test_biblioteca.py`)
- **Responsabilidade & Funções:** Entregar interface desacoplada consumindo apenas a API REST via cookies seguros, cobrindo todo o ciclo de gestão multi-conta.
- **Quality Gate:** `pytest testes/ -v`
- **Mensagem do Commit:** `feat(web): integracao google drive e frontend desacoplado com login turnstile`

### Fase Final: Auditoria, Revisão Geral & Hardening
- **Escopo da Revisão:**
  1. Verificar todos os arquivos de código `<= 200` linhas, zero código morto ou imports órfãos.
  2. Checagem de segurança (headers CORS/CSP, cookies `HttpOnly`, validação de uploads, zero vazamento de tokens em logs).
  3. Análise estática (`ruff check .`, `mypy app/`) e regressão total (`pytest`).
  4. Build e subida completa via `docker compose up --build` simulando VPS.
- **Quality Gate:** 100% da suíte `pytest`, `ruff` e `docker compose` sem erros.
- **Mensagem do Commit:** `refactor(audit): hardening de seguranca, limpeza e validacao final`

## 4. Log de Decisões e Handoff
- **Planejamento inicial (2026-11-13):** Definida stack Python/FastAPI + PostgreSQL + Redis + Worker + Caddy HTTPS em Docker para VPS; Cloudflare Turnstile no login; OpenRouter (`deepseek/deepseek-v4-flash` + Nano Banana); Instagram Login API com porta extensível; Storage HTTPS assinado no MVP com porta para R2/S3.
- **Revisão de Escopo (2026-11-13):** Adicionado suporte a N contas Instagram por empresa com Persona/RAG/Biblioteca independentes; Strategy+DI para `IMAGE`/`CAROUSEL`/`REELS`/`STORIES`; storage principal em nuvem (Cloudflare R2/S3) com pastas `originais`, `processadas`, `IA-Cria`, `IA-Edita`, cota (250 itens/GB), `curtida_favorita` e limpeza pós-postagens protegendo favoritas; adicionada Aba de Planejamento Semanal Automatizado (busca web em cache + 2 etapas com estimativa `$`).
- **Refatoração Modular Pré-Fase 1 (2026-11-13):** Estrutura quebrada em subpacotes (`core/seguranca/`, `dominio/{objetos_valor,entidades,portas}/`, `aplicacao/{auth,biblioteca,ia,publicacao}/`, `infra/{seguranca,memoria,db,storage,midia,ia,meta,drive}/`, `api/{dependencias,schemas,middlewares,rotas}/`) para garantir todos os arquivos `<= 200` linhas; explicitados casos de uso de auth, rotação/revogação de refresh tokens, dummy hash anti-timing no Argon2id, proteção Turnstile no registro e padronização com `ia/`, `meta/` e `drive/`.
