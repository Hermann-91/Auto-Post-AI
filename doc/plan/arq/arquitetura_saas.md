# Arquitetura SaaS, Segurança e Deploy VPS

## 1. Estilo Arquitetural (Clean Architecture / Ports & Adapters)
Regra de dependência estrita: `app/api` -> `app/aplicacao` -> `app/dominio` <- `app/infra` (com todos os arquivos de código `<= 200` linhas via subpacotes coesos).
- **`app/core/`**: Configurações (`pydantic-settings` + `SecretStr`), logging mascarado e subpacote `seguranca/` (`senha_argon2.py`, `token_jwt.py`, `criptografia_fernet.py`).
- **`app/dominio/`**: Subpacotes `objetos_valor/`, `entidades/` (`Empresa`, `Usuario`, `ContaInstagram`, `ConfigIAConta`, `FonteRAG`, `MidiaBiblioteca`, `PlanejamentoSemanal`, `Postagem`, `RegistroCustoIA`), `excecoes.py` e `portas/` (`Port`s segregados por ISP + `Strategy` para `IMAGE`, `CAROUSEL`, `REELS`, `STORIES` e autenticação Meta). Zero dependência de FastAPI, SQLAlchemy, Redis ou HTTP.
- **`app/aplicacao/`**: Subpacotes por domínio funcional (`auth/`, `biblioteca/`, `ia/`, `publicacao/`) com casos de uso puros.
- **`app/infra/`**: Subpacotes de adaptadores concretos (`seguranca/`, `memoria/` na Fase 1, `db/`, `storage/`, `midia/`, `ia/`, `meta/`, `drive/`).
- **`app/api/` & `frontend/`**: Subpacotes `dependencias/`, `schemas/`, `middlewares/`, `rotas/` + Front-end desacoplado (comunicação exclusiva via API HTTP).

## 2. Modelagem Multi-Tenant (Banco Relacional)
`empresa_id` isola o tenant raiz (usuários, faturamento e orçamento); cada `Empresa` pode gerenciar **N `contas_instagram`**, e os ativos de conteúdo/IA são escopados por **`(empresa_id, conta_ig_id)`**:
- `empresas`: `id`, `nome`, `plano`, `limite_mensal_usd`, `bloqueio_orcamento`
- `usuarios`: `id`, `empresa_id`, `email` (unique), `senha_hash` (Argon2id), `papel` (`ADMIN`/`EDITOR`), `ativo`
- `refresh_tokens`: `id`, `usuario_id`, `empresa_id`, `familia_id`, `token_hash` (SHA-256), `substituido_por`, `revogado`, `expira_em`, `criado_em`
- `contas_instagram`: `id`, `empresa_id`, `ig_user_id`, `username`, `access_token_enc` (Fernet), `token_expira_em`, `provedor` (`instagram_login`)
- `configs_ia_conta`: `id`, `empresa_id`, `conta_ig_id`, `persona_json`, `templates_json`, `aplicar_logo_padrao`, `modelo_texto_pref`, `modelo_img_pref`
- `fontes_rag`: `id`, `empresa_id`, `conta_ig_id`, `tipo`, `titulo`, `conteudo_limpo`, `chunks_json`
- `midias_biblioteca`: `id`, `empresa_id`, `conta_ig_id`, `pasta` (`originais`/`processadas`/`IA-Cria`/`IA-Edita`), `chave_storage`, `tipo_arquivo`, `tamanho_bytes`, `curtida_favorita`, `resumo_visual`, `criado_em`
- `planejamentos_semanais`: `id`, `empresa_id`, `conta_ig_id`, `semana_inicio`, `tendencias_cache_json`, `custo_estimado_usd`, `status`
- `postagens`: `id`, `empresa_id`, `conta_ig_id`, `planejamento_id`, `tipo_midia` (`IMAGE`/`CAROUSEL`/`REELS`/`STORIES`), `midias_json`, `legenda`, `status`, `agendado_para`, `idempotency_key`, `meta_container_id`, `meta_media_id`, `erro_detalhe`
- `registros_custo_ia`: `id`, `empresa_id`, `conta_ig_id`, `postagem_id`, `openrouter_gen_id`, `modelo`, `tokens_in`, `tokens_out`, `custo_usd`, `criado_em`

## 3. Segurança do Login, Rate Limit e Cloudflare Turnstile
1. **Ordem rígida no `POST /auth/login` (e proteção equivalente de entrada no `POST /auth/register`):**
   1. **Rate Limit (Redis / Memória em dev):** Máximo de 5 tentativas por `IP + sha256(email)` em janela de 15 min (HTTP 429 com `Retry-After`).
   2. **Cloudflare Turnstile (Server-Side via DI):** Em produção, validar `cf-turnstile-response` via `POST https://challenges.cloudflare.com/turnstile/v0/siteverify` (com `secret` + `remoteip`) **antes** do Argon2id (protege CPU contra floods). Em dev/testes, injetar `StubCaptchaAdapter` quando `CAPTCHA_ENABLED=false` (ou usar chaves de teste oficiais da Cloudflare).
   3. **Verificação Argon2id (`argon2-cffi` em `asyncio.to_thread`):** Checar hash (executando *dummy hash* quando o e-mail não existir para evitar *timing attack* / enumeração) e sempre retornar mensagem genérica (`"E-mail ou senha inválidos"`).
   4. **Emissão e Rotação de Sessão:** Access Token JWT curto (15 min) + Refresh Token rotativo com estado (`refresh_tokens`), revogando toda a `familia_id` em caso de reuso; cookies `HttpOnly`, `Secure` (configurável apenas em `APP_ENV=dev`), `SameSite=Lax` + validação de `Origin` contra CSRF em `POST /auth/refresh` e `/auth/logout`.
2. **Proteção de segredos:** Tokens Meta/Drive criptografados com `FERNET_KEY` antes do `INSERT/UPDATE`.

## 4. Deploy em VPS com Docker (`Dockerfile` + `docker-compose.yml`)
- **`Dockerfile` (Multi-stage):** Base `python:3.12-slim`, instala `ffmpeg` e libs mínimas no stage final, executa sob usuário não-root (`appuser`).
- **Serviços no `docker-compose.yml`:**
  - `proxy` (**Caddy 2**): TLS automático (Let's Encrypt) obrigatório para OAuth da Meta e painel web (mídias pesadas servidas via Cloudflare R2/S3).
  - `api`: FastAPI + Uvicorn (múltiplos workers se necessário, sem threads de agendamento internas).
  - `worker`: Processo único/coordenado rodando o agendador e consumo assíncrono de mídia.
  - `db`: `postgres:16-alpine` com volume persistente.
  - `redis`: `redis:7-alpine` para rate limit distribuído e fila/locks.

## 5. Mapa de Reaproveitamento de `projeto_robo_instagram`
- **Reaproveitar (refatorado):** `midia/*` (`ProcessadorImagem`, `CompositorCapa`, `GeradorCarrossel`, `EditorVideo`) e o conceito de `RepositorioPrompts` + `ServicoRAG`.
- **Substituir:** `ServicoGemini` (quebrar em OpenRouter + Orçamento), `RepositorioJSON` (trocar por SQLAlchemy), `AgendadorPostagem` (trocar thread no Streamlit por Worker transacional).
- **Descartar:** `automacao/*` (Chrome CDP e Google Fotos via atalho `Shift+D`).
