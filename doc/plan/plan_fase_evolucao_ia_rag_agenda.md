# Plano em Fases: Evolução IA, RAG Híbrido, Pipeline Visual & Motor 24/7 (Robo-Auto-Inst)

## 1. Visão Geral & Contrato Arquitetural
- **Objetivo:** Evoluir o `Robo-Auto-Inst` em quatro frentes integradas:
  1. **RAG Híbrido & Busca Web Real:** Ingestão de `.pdf`, `.txt`, `.md` e URLs públicas (portando do `projeto_robo_instagram`), busca híbrida (lexical + embeddings com filtro mínimo de relevância), Brand Bible pré-compilada com Prompt Caching, Blueprints de formatos de sucesso extraídos via busca web aberta (sem scraping autenticado no Instagram) e ativação real de `templates_json`.
  2. **Pipeline Visual Inteligente (Diretor de Arte + Crítico em até 2 Loops):** Desacoplar legenda de direção visual, substituir clichês "8k/HDR/studio" por fotografia documental, suportar **Modo Série Narrativa** (sequência intencional de N posts sem vício) e **Memória Anti-Repetição**, usar fotos reais como referência (`midia_base_ids`) e validar cada imagem gerada via VLM com checklist JSON binário antes de salvar.
  3. **Visão nas Fotos Reais, Rascunho Só-Texto & Motor de Agendamento 24/7:** Analisar fotos anexadas via visão para escrever legendas, curadoria comparativa de até 5 fotos, permitir `RASCUNHO` somente texto (bloqueando `AGENDADO` sem mídia), auto-agendamento opcional na Grade Semanal e recuperação de posts travados em `PUBLICANDO` no Worker.
  4. **Estúdio Unificado Assíncrono (UX Zero-Prompt + Avançado Opcional):** Unificar "Agendamento Semanal" e "Criação Unitária" em um único gerador dinâmico flexível (Textos primeiro, Completo com IA ou Manual $0), com campo avançado opcional de prompt, jobs assíncronos e bloqueio visual contra duplo clique.
- **Stack & Padrões:** Python 3.12+, FastAPI, SQLAlchemy Async + Alembic, Pydantic, OpenRouter (texto, visão, embeddings e geração de imagem), Pillow, Worker assíncrono, JS ES Modules vanilla, Clean Architecture (`api -> aplicacao -> dominio <- infra`), SOLID e Dependency Injection.
- **Modalidade de Execução:** Agente Sequencial com Handoff entre chats (1 fase por sessão limpa via `/clean` ou novo chat).
- **Diretrizes Inegociáveis:**
  1. **Arquivos de código `<= 200` linhas** (`.py`, `.js`, `.css`, `.html`).
  2. **Isolamento Multi-Tenant & Nichos Distintos por Conta:** Zero segredos hardcoded e isolamento estrito por `(empresa_id, conta_ig_id)`. Prompts estruturais/técnicos (schema JSON, checklist visual anti-defeito, princípios fotográficos e invariantes Meta) permanecem **globais no sistema**; enquanto `persona_json`, `brand_bible_json`, `templates_json`, `fontes_rag` (chunks, resumos e **embeddings**), memórias anti-repetição e parâmetros de busca/tendência (`nicho + região`) são **100% personalizados e isolados por conta Instagram**, permitindo nichos totalmente diferentes sem contaminação cruzada.
  3. **Quality Gate obrigatório:** `pytest`, `ruff check .` e `mypy app/ testes/ --strict` 100% verdes antes de qualquer commit.
  4. **Espelhamento de Testes:** Todo módulo novo/alterado em `app/` possui teste correspondente em `testes/{unit,integration}/` (`<= 200` linhas).
  5. **Segurança & Compliance Meta:** Nunca realizar scraping autenticado dentro de `instagram.com`; nunca agendar/publicar post sem validar invariantes de mídia exigidas pela Meta Graph API.

## 2. Checklist de Fases & Status
- [x] **Fase 1: RAG Híbrido (Arquivos/URLs + Embeddings), Brand Bible & Buscador Web Real**
  - Status: Concluído
  - Commit: `feat(rag): busca hibrida com embeddings por conta, ingestao arquivos/urls, brand bible e buscador web real`
- [x] **Fase 2: Pipeline Visual (Diretor de Arte, Séries, Referência Real & Crítico em 2 Loops)**
  - Status: Concluído
  - Commit: `feat(visual): diretor de arte documental, series narrativas, referencia real e critico em 2 loops`
- [ ] **Fase 3: Visão em Fotos Anexadas, Rascunho Só-Texto, Auto-Agendamento & Worker Resiliente**
  - Status: Pendente
  - Commit: `pendente`
- [ ] **Fase 4: Jobs Assíncronos & Estúdio Unificado Zero-Prompt no Painel Web**
  - Status: Pendente
  - Commit: `pendente`
- [ ] **Fase Final: Auditoria, Revisão Geral & Hardening**
  - Status: Pendente
  - Commit: `pendente`

## 3. Detalhamento de Cada Fase

### Fase 1: RAG Híbrido (Arquivos/URLs + Embeddings), Brand Bible & Buscador Web Real
- **Arquivos:**
  - `requirements.txt` (MODIFY: adicionar `pypdf` para leitura de PDFs)
  - `app/core/config.py` (MODIFY: configurações de buscador web real, modelo de embeddings e limites de ingestão)
  - `app/dominio/objetos_valor/enums_conteudo.py` (MODIFY: adicionar `TipoFonteRAG.URL` e `TipoFonteRAG.REFERENCIA_BENCHMARK`)
  - `app/dominio/entidades/ia_rag.py` (MODIFY: `FonteRAG` com `resumo_fatos` e `embeddings_chunks`; `ConfigIAConta` com `brand_bible_json`)
  - `app/dominio/portas/ia_meta.py` (MODIFY: adicionar método/porta de embeddings `gerar_embeddings` sem quebrar implementações existentes)
  - `app/infra/db/modelos_conteudo.py` & `alembic/versions/0002_rag_hibrido_brand_bible.py` (MODIFY/NEW: persistência de embeddings/resumo e Brand Bible por conta)
  - `app/infra/db/repo_ia_rag_sql.py` (MODIFY: mapear novos campos mantendo `<= 200` linhas)
  - `app/infra/ia/cliente_openrouter.py` & `app/infra/ia/openrouter_parser.py` (MODIFY: suporte a `/embeddings` com controle de `usage.cost`)
  - `app/infra/ia/cliente_stub.py` (MODIFY: stub para `gerar_embeddings`)
  - `app/infra/ia/extrator_rag.py` (NEW: portando e evoluindo parsing de `.pdf`, `.txt`, `.md` e higienização de URL pública via `html.parser` nativo)
  - `app/infra/ia/pesquisa_tendencias.py` & `app/infra/ia/buscador_web_real.py` (MODIFY/NEW: substituir Instant Answer do DuckDuckGo por buscador web real de tendências/blueprints abertos parametrizado por `nicho + regiao`, preservando cache 24h–72h)
  - `app/aplicacao/ia/rag_texto.py` (MODIFY: busca híbrida BM25/lexical + cosseno de embeddings no escopo da conta com descarte de `score == 0`)
  - `app/aplicacao/ia/servico_prompts_rag.py` (MODIFY: combinar núcleo estrutural global com `brand_bible_json`, `persona_json` e `templates_json` personalizados da conta ativa)
  - `app/api/schemas/criacao_ia.py` & `app/api/rotas/contas_config.py` (MODIFY: endpoints de upload multipart PDF/TXT/MD e indexação de URL pública no RAG isolados por `conta_ig_id`)
  - Testes espelhados em `testes/unit/infra/ia/`, `testes/unit/aplicacao/ia/` e `testes/integration/api/rotas/`.
- **Responsabilidade & Funções:** Garantir que cada conta Instagram (mesmo de nichos opostos) tenha Brand Bible pré-compilada, RAG em PDFs/URLs com chunks e embeddings isolados por conta e buscador web real de tendências/blueprints abertos, preservando prompts estruturais globais.
- **Quality Gate:** `pytest testes/unit/aplicacao/ia testes/unit/infra/ia testes/integration/infra/db testes/integration/api/rotas -v`, `ruff check .`, `mypy app/ --strict` e `alembic upgrade head` em SQLite temporário.
- **Mensagem do Commit:** `feat(rag): busca hibrida com embeddings por conta, ingestao arquivos/urls, brand bible e buscador web real`

### Fase 2: Pipeline Visual (Diretor de Arte, Séries, Referência Real & Crítico em 2 Loops)
- **Arquivos:**
  - `app/aplicacao/ia/dtos.py` (MODIFY: incluir `pilar_editorial`, `modo_serie`, `etapa_serie`, `qualidade_revisao` e contadores de revisão)
  - `app/aplicacao/ia/diretor_arte.py` (NEW: gera `SceneSpec` JSON estruturado combinando regras fotográficas globais + identidade visual da conta; varia ângulo, lente e iluminação documental; suporta progressão de **Modo Série** vs **Memória Anti-Repetição** dos últimos posts; proíbe clichês de estúdio/CGI)
  - `app/aplicacao/ia/avaliador_visual.py` (NEW: **Crítico Visual VLM** com Scorecard JSON binário global `PASS/FAIL`: `anatomia_correta`, `sem_texto_corrompido`, `realismo_fotografico`, `aderencia_ao_briefing`, `diagnostico_correcao`)
  - `app/aplicacao/ia/servico_prompts_rag.py` (MODIFY: `formatar_ancoras_visuais` deixa de copiar `prompt_final[:300]` como referência positiva e passa a fornecer resumo negativo anti-repetição da conta)
  - `app/aplicacao/ia/geracao_visual.py` (MODIFY: remover termos `"8k fullhd HDR studio"`, suportar múltiplas fotos de referência `midia_base_ids` e orquestrar loop `gerar -> avaliar -> corrigir` limitado a no máximo **2 iterações** com registro de custo no `ServicoOrcamentoUseCase`)
  - `app/aplicacao/ia/criar_conteudo.py` (MODIFY: separar Copywriter de Diretor de Arte; aceitar `pilar` + `prompt_avancado` opcional)
  - `app/aplicacao/ia/recriar_postagem_contexto.py` (MODIFY: corrigir bug da duplicação de `contexto_adicional` e impedir vazamento de texto RAG bruto para o gerador de imagens)
  - `app/aplicacao/ia/servico_orcamento.py` (MODIFY: estimar teto conservador considerando até 2 chamadas de crítica visual no `BudgetGuard`)
  - `app/infra/ia/openrouter_parser.py` (MODIFY: `montar_payload_imagem` aceitando lista de imagens de referência `image_url` além de edição unitária)
  - Testes espelhados em `testes/unit/aplicacao/ia/` e `test/unit/infra/ia/` (`testes/unit/infra/ia/`).
- **Responsabilidade & Funções:** Eliminar anatomia quebrada (ex.: 3 braços), textos borrados nas imagens, visual plástico artificial e repetição não intencional, mantendo coerência quando o usuário quiser séries de múltiplos posts respeitando a identidade de cada conta.
- **Quality Gate:** `pytest testes/unit/aplicacao/ia testes/unit/infra/ia -v`, `ruff check .` e `mypy app/ --strict`.
- **Mensagem do Commit:** `feat(visual): diretor de arte documental, series narrativas, referencia real e critico em 2 loops`

### Fase 3: Visão em Fotos Anexadas, Rascunho Só-Texto, Auto-Agendamento & Worker Resiliente
- **Arquivos:**
  - `app/dominio/entidades/publicacao.py` & `app/dominio/objetos_valor/maquina_estados.py` (MODIFY: permitir `midias_chaves=[]` apenas em `RASCUNHO`; exigir invariantes Meta em `agendar()` e `iniciar_publicacao()`; adicionar transição `PUBLICANDO -> FALHA/AGENDADO` para recuperação de crash)
  - `app/aplicacao/ia/servico_curadoria.py` (MODIFY: adicionar `eleger_melhor_foto` comparando até 5 mídias da Biblioteca da conta — portando do `projeto_robo_instagram`)
  - `app/aplicacao/ia/criar_conteudo.py` (MODIFY: quando houver `midia_base_ids` sem `gerar_imagem_ia`, enviar miniatura compactada via `ClienteVisaoPort` para a legenda e sugestão de horário refletirem a foto real; permitir `salvar_rascunho=True` mesmo sem mídia no modo texto-primeiro)
  - `app/aplicacao/ia/planejamento_semanal.py` & `app/aplicacao/ia/grade_semanal.py` (MODIFY: corrigir criação de rascunho em modo somente texto, suportar `composicao_formatos` dinâmica ex.: `3 IMAGE + 2 REELS`, e calcular `agendado_para` UTC real quando `auto_agendar=True` e houver mídia)
  - `app/aplicacao/ia/edicao_orcamento_semanal.py` (MODIFY: adequar recálculo de orçamento por formato/quantidade e anexos de mídia)
  - `app/aplicacao/publicacao/servico_agendamento.py` & `app/worker/executor_lotes.py` (MODIFY: recuperação automática de posts presos em `PUBLICANDO` além do TTL do lock e retry com backoff em falhas transitórias de rede)
  - `app/api/rotas/criacao.py`, `app/api/rotas/planejamento.py`, `app/api/rotas/posts.py` & `app/api/schemas/` (MODIFY: expor curadoria em lote, rascunho sem mídia, composição dinâmica e `auto_agendar`)
  - Testes espelhados em `testes/unit/dominio/`, `testes/unit/aplicacao/` e `testes/integration/worker/`.
- **Responsabilidade & Funções:** Devolver a inteligência visual sobre fotos reais do `projeto_robo_instagram` dentro do motor oficial 24/7, habilitar o fluxo "planejar só texto primeiro e anexar/gerar imagem depois" e automatizar o agendamento no calendário sem trabalho manual repetitivo.
- **Quality Gate:** `pytest testes/unit/dominio testes/unit/aplicacao testes/integration/worker -v`, `ruff check .` e `mypy app/ --strict`.
- **Mensagem do Commit:** `feat(agenda): visao em fotos anexadas, rascunho texto-primeiro, auto-agendamento e worker resiliente`

### Fase 4: Jobs Assíncronos & Estúdio Unificado Zero-Prompt no Painel Web
- **Arquivos:**
  - `app/dominio/entidades/job_ia.py` & `app/aplicacao/ia/servico_jobs.py` (NEW: rastreamento de jobs assíncronos com etapas, progresso `X/Y`, erro e resultado para evitar timeout HTTP e duplo clique)
  - `app/api/rotas/jobs_ia.py` & `app/api/dependencias/provedores_ia.py` (NEW/MODIFY: endpoints `POST /ia/jobs` e `GET /ia/jobs/{job_id}`)
  - `frontend/index.html` (MODIFY mantendo `<= 200` linhas: substituir os 2 cards redundantes por um único **Estúdio de Criação & Agenda**, atualizar aba `Cultura (RAG)` com upload de arquivo e URL, e expor configuração de `templates_json`/`brand_bible_json` por conta em `Config`)
  - `frontend/js/planejamento.js`, `frontend/js/componentes/estudio_unificado.js` (MODIFY/NEW `<= 200` linhas: construtor dinâmico de lote ex. `N` posts / `M` reels / `K` stories, seleção de modo **Só Texto**, **IA Completa** ou **Manual $0**, Pilares + Modo Série + bloco recolhível **Prompt Avançado Opcional**, polling de job com barra de status e bloqueio de duplo clique)
  - `frontend/js/componentes/card_agenda.js` & `frontend/js/componentes/modal_recriacao.js` (MODIFY mantendo `<= 200` linhas: badge "Aguardando mídia" nos rascunhos só-texto com ação direta "Gerar Imagem IA" ou "Anexar Foto", botões rápidos de 1 clique `"Mais natural"`, `"Sem pessoas"`, `"Trocar ângulo"` e bloqueio de agendamento sem mídia)
  - `frontend/js/rag.js` (NEW `<= 200` linhas: upload multipart PDF/TXT/MD, indexação de URL e visualização por conta)
  - Testes de integração de API/frontend em `testes/integration/api/rotas/test_jobs_ia.py` e `testes/integration/api/rotas/test_painel_frontend.py`.
- **Responsabilidade & Funções:** Entregar UX unificada, intuitiva e à prova de duplo clique para todo o fluxo: planejamento somente texto, geração visual com progresso assíncrono, anexo de fotos prontas sem IA e agendamento programado 24/7.
- **Quality Gate:** `pytest testes/ -v`, `ruff check .`, `mypy app/ --strict` e checagem de contagem `<= 200` linhas em todos os arquivos `.py`, `.js`, `.css` e `.html`.
- **Mensagem do Commit:** `feat(ui): jobs assincronos e estudio unificado zero-prompt com rag de arquivos/urls`

### Fase Final: Auditoria, Revisão Geral & Hardening
- **Escopo da Revisão:**
  1. Verificar 100% dos arquivos criados/alterados no limite `<= 200` linhas, zero código morto, imports órfãos ou duplicação (DRY).
  2. Auditoria de segurança: validação de arquivos PDF/URL contra SSRF e Path Traversal, isolamento multi-conta em RAG/embeddings/Brand Bible, zero vazamento de chaves em logs, invariantes Meta preservadas.
  3. Checagem estrita: `ruff check .`, `mypy app/ testes/ --strict` e regressão completa `pytest testes/ -v`.
  4. Validação `docker compose config -q` (e build/subida se disponível no ambiente).
- **Quality Gate:** 100% dos testes, `ruff` e `mypy` verdes sem warnings.
- **Mensagem do Commit:** `refactor(audit): revisao geral, limpeza de codigo e hardening final`

## 4. Log de Decisões e Handoff
- **Planejamento inicial (2026-11-16):**
  - Diagnosticado que `projeto_robo_instagram` possuía ingestão `.pdf`/`.txt`/`.md`/URL e análise visual de fotos anexadas (além de sugestão de horário), enquanto `Robo-Auto-Inst` já possui a base arquitetural SaaS, orçamento USD, chunking/ranking lexical, cache de tendências 24h–72h e Worker oficial Meta Graph API.
  - Reforçada a arquitetura multi-conta/multi-nicho: prompts estruturais técnicos (contratos JSON, fotografia documental, checklist do Crítico Visual e regras Meta) permanecem **globais**, enquanto `persona_json`, `brand_bible_json`, `templates_json`, `fontes_rag` (chunks, resumos e embeddings), memórias visuais e buscas de tendência são **100% isolados e personalizados por `(empresa_id, conta_ig_id)`**.
  - Decidido **não** realizar scraping autenticado em `instagram.com` por risco de bloqueio/ToS; benchmarks de formatos serão obtidos via busca web aberta + fontes `REFERENCIA_BENCHMARK` no RAG.
  - Decidido unificar os cards de criação unitária e planejamento semanal em um único Estúdio Dinâmico com 3 modos (Somente Texto/Estratégia primeiro, Completo com IA, Manual $0), mantendo campo avançado opcional de prompt, suporte a Séries Narrativas e loop de Crítico Visual (máx. 2 iterações).
  - Identificada necessidade de flexibilizar `Postagem.validar_invariantes()` para aceitar `midias_chaves=[]` apenas em `StatusPostagem.RASCUNHO`, mantendo validação estrita da Meta em `agendar()` e `iniciar_publicacao()`.
- **Fase 1 concluída em 2026-11-16 17:30:**
  - Portas segregadas `ClienteEmbeddingsPort` e `ExtratorConteudoRagPort` criadas (ISP/DIP) preservando compatibilidade com todos os mocks de `ClienteIAPort`.
  - `ExtratorConteudoRag` + `extrator_html_ssrf.py` implementados com `pypdf`, `HTMLParser` nativo, bloqueio anti-Path Traversal e bloqueio anti-SSRF (IPs privados, loopback, link-local, portas não-HTTP e redirects).
  - `BuscadorWebReal` (DuckDuckGo HTML + fallback RSS seguro anti-XXE parametrizado por `nicho + regiao`) substituiu o Instant Answer mantendo cache de 24h–72h e bloqueio a domínios `instagram.com`/`facebook.com`.
  - `rag_texto.py` atualizado para busca híbrida BM25 + cosseno com descarte de `score == 0`; `prompts_brand_bible.py` pré-compila `brand_bible_json` por conta e ativa `templates_json` no núcleo cacheável do `system_prompt`.
  - Endpoints `POST /contas/{conta_ig_id}/rag/arquivo`, `POST /contas/{conta_ig_id}/rag/url` e `POST /contas/{conta_ig_id}/brand-bible/compilar` adicionados em `contas_rag.py`; migração `0002_rag_hibrido_brand_bible` aplicada e testada. Quality Gate: 48/48 Fase 1 e 141/141 suíte completa verdes.
- **Fase 2 concluída em 2026-11-16 17:55:**
  - Porta segregada `ClienteImagemMultireferenciaPort` adicionada em `ia_meta.py` (ISP) e implementada em `ClienteOpenRouter`/`ClienteIANaoConfigurado` via `montar_payload_imagem` multi-referência com validação anti-SSRF.
  - `dtos_visuais.py` e `persistencia_visual.py` criados para manter 100% dos módulos `<= 200` linhas (`SceneSpec`, `VereditoCriticoVisual`, `QualidadeRevisaoVisual`, I/O de referências reais e Pillow `$0`).
  - `DiretorArteService` (`diretor_arte.py`) desacoplado do Copywriter em `criar_conteudo.py`: aplica regras documentais globais + identidade visual isolada da conta, remove clichês `"8k/fullhd/HDR/studio"`, suporta `pilar_editorial`, `prompt_avancado`, **Modo Série** (`modo_serie` + `etapa_serie`) e **Memória Anti-Repetição** (`prompts_brand_bible.py` / `servico_prompts_rag.py`).
  - `AvaliadorVisualCritico` (`avaliador_visual.py`) + `GeradorVisualHibrido` (`geracao_visual.py`) executam loop `gerar -> avaliar VLM -> corrigir` limitado a no máximo **2 iterações**, com teto conservador em `estimar_pipeline_visual` (`servico_orcamento.py`) e registro de custos por iteração.
  - Bugfix em `recriar_postagem_contexto.py` eliminou duplicação de `contexto_adicional` e vazamento de RAG bruto ao gerador de imagens; campos opcionais expostos em `criacao_ia.py`/`criacao.py` e ligados em `provedores_ia.py`. Quality Gate: 34/34 Fase 2 e 151/151 suíte completa verdes.
