# Plano de Evolução Frontend & UX: Robo-Auto-Inst (`frontend-evolution.md`)

## 1. Diagnóstico Sênior da Interface Atual

A partir da inspeção direta dos screenshots reais do painel e da auditoria de `frontend/index.html`, `frontend/css/{tokens,styles,agenda}.css` e `frontend/js/**`:

### 1.1 Gargalos Críticos de Layout & Fluxo
1. **Bloco de Grades Programadas (`#resumo-semanal-box`) acoplado e expandido por padrão:**
   - Hoje reside dentro do mesmo `<article class="glass-card">` do **Estúdio de Criação**, colado abaixo do botão principal sem respiro nem identidade própria.
   - O `<select>` de lotes (`Semana 2026-11-16 • $0.0020 (AGUARDANDO_APROVACAO)`) **não possui botão de exclusão**, deixando planejamentos antigos ou rejeitados presos na tela indefinidamente (`PlanejamentoRepositoryPort` e `/planejamento` ainda não expõem `DELETE`).
   - Os itens da grade vêm **100% abertos**, exibindo `input` de tema, `select`, hora, dia, checkbox e dois `<textarea>` longos empilhados, empurrando a **Agenda** para baixo da dobra da tela.
2. **Bug de especificidade CSS quebrando checkboxes em 2 linhas:**
   - Em `styles.css`, `label { flex-direction: column; }` vence `.presets-chip` em `agenda.css` (que usa `display: inline-flex` sem definir `flex-direction: row`), fazendo o checkbox aparecer **acima** do texto em `"Imagem IA"`, `"Melhorar Resolução"`, `"Fotografia Profissional"`, etc.
   - Além disso, `input { padding: 0.55rem 0.8rem; }` afeta checkboxes nativos e os campos `checkbox` (`Modo Série Narrativa`, `Auto-agendar na grade`) ficam sem estilo customizado.
3. **Agenda espremida em 4 colunas (`.grid-agenda-4`):**
   - Em `1320px`, 4 colunas deixam cada card com ~290px úteis. Como resultado, `.agenda-acoes-barra` (`1fr auto auto auto`) espreme o `<input type="datetime-local">` cortando a hora (`17/11/2026...`) e comprime os botões.
   - Os botões circulares de edição exibem a letra literal `"o"` sem semântica visual clara.
4. **Oportunidades nas demais abas:**
   - **Custos:** apenas 1 barra linear; faltam KPIs escaneáveis (Empresa vs Conta Ativa vs Saldo vs Modo).
   - **Cultura (RAG) & Config:** formulários horizontais densos e `<textarea>` de JSON sem estética de editor monoespaçado/validação visual.
   - **Empty States:** mensagens de texto simples sem orientação acionável.

---

## 2. Arquitetura Visual & Diretrizes do Novo Design

- **Estética:** *SaaS Studio Dark/Light* profissional, glassmorphism sutil com hierarquia de elevação (`--bg`, `--surface`, `--surface-elevated`, `--surface-inset`), tipografia clara, espaçamentos consistentes (`4px/8px` scale) e alto contraste WCAG AA.
- **Zero dependências externas (CSP estrito):** ícones via módulo JS dedicado (`frontend/js/icones.js`, `<= 120` linhas) gerando SVG inline leve por `createElementNS` (sem `innerHTML`, sem CDN externo).
- **Separação visual em 3 zonas claras na aba `Agenda Post`:**
  1. **Estúdio de Criação (Card 1):** foco em criar 1 post ou propor 1 lote, com segmented control limpo, chips alinhados, toggles em estilo switch, dropzone de mídia e `<details>` recolhido para *Prompt Avançado*.
  2. **Grades & Lotes Programados (Card 2 — independente e minimizado por padrão):**
     - Cabeçalho compacto em 1 linha: ícone + título *"Grades Programadas"*, seletor do lote, pílula de status humanizada (*Aguardando Aprovação*, *Concluído*, *Falha*), badge de custo estimado (`$0.0020`), botão primário **`✅ Aprovar & Gerar na Agenda`** e botão **`🗑️ Excluir Lote`**.
     - Corpo em `<details>` **recolhido por padrão** (`▸ Revisar / editar itens da grade (N)` — exatamente como o `Prompt Avançado Opcional`), abrindo mini-cards estruturados (badge de formato colorido, dia/horário alinhados, switch *Imagem IA*, prévia visual/thumbnail e campos de texto compactos).
  3. **Agenda de Publicações (Card 3):**
     - Cabeçalho com filtros rápidos por status (*Todos*, *Rascunhos*, *Aguardando Mídia*, *Agendados*, *Publicados*) + botão *Atualizar*.
     - Grid responsivo de **3 colunas** em desktop (`repeat(3, minmax(0, 1fr))` acima de `1080px`, `2` colunas em tablet, `1` em mobile).
     - Card da Agenda modernizado: badge de formato no canto da mídia, botões com ícones SVG reais (lápis para editar/IA texto, câmera/varinha para foto/IA imagem), linha de meta-informação limpa e **barra inferior em 2 linhas** (Linha 1: seletor data/hora inteiro + botão Agendar; Linha 2: CTA Postar/Repostar + botão Excluir).

---

## 3. Contrato Técnico & Fases de Implementação (`<= 200` linhas/arquivo)

### Fase 1: Exclusão de Planejamento no Backend + Design Tokens & Ícones SVG
- **Backend:**
  - `app/dominio/portas/repositorios_conteudo.py` (`PlanejamentoRepositoryPort.remover`), `app/infra/db/repo_ia_rag_sql.py` (`SqlPlanejamentoRepository.remover`), `app/infra/memoria/repo_publicacao_mem.py` (`remover`).
  - `app/aplicacao/ia/planejamento_semanal.py` (`remover_plano` isolado por `empresa_id, conta_ig_id`) e `app/api/rotas/planejamento.py` (`DELETE /planejamento/{conta_ig_id}/{plano_id}`, `204 No Content`).
  - Testes unitários e de integração (`test_criacao_planejamento.py`, `test_repo_ia_rag_sql.py`) garantindo isolamento multi-tenant.
- **Frontend Base:**
  - `frontend/css/tokens.css`: adicionar tokens de elevação (`--surface-inset`, `--border-strong`, `--ring`, raios e estados semânticos).
  - `frontend/css/styles.css`: corrigir `input[type="checkbox"]`, `label.check`, `.presets-chip` (`flex-direction: row`), switches customizados e estados `:focus-visible`.
  - `frontend/js/icones.js` (NEW): biblioteca enxuta de ícones SVG inline seguros (`createElementNS`).

### Fase 2: Card Independente & Minimizado de "Grades Programadas"
- **Arquivos:** `frontend/index.html`, `frontend/js/componentes/resumo_orcamento.js`, `frontend/js/planejamento.js`, `frontend/css/agenda.css`.
- **Entregas:**
  - Mover `#resumo-semanal-box` para um `<article class="glass-card">` próprio entre o Estúdio e a Agenda (oculto quando não houver grades).
  - Transformar o conteúdo da grade selecionada em `<details class="grade-detalhes">` **fechado por padrão** (abrindo apenas sob demanda), mantendo seletor de lote, status legível, custo estimado, botão **Aprovar & Gerar** e botão **🗑️ Excluir Lote** (`DELETE /planejamento/{contaId}/{planoId}`) visíveis no resumo fechado.
  - Reestruturar cada item dentro do acordeão em mini-card visual de 2 colunas com badges de formato (`IMAGE`, `CAROUSEL`, `REELS`, `STORIES`), switch `Imagem IA` alinhado e prévia organizada.

### Fase 3: Estúdio Refinado & Cards da Agenda Profissionais (3 Colunas)
- **Arquivos:** `frontend/js/componentes/card_agenda.js`, `frontend/js/componentes/estudio_unificado.js`, `frontend/js/planejamento.js`, `frontend/css/agenda.css`.
- **Entregas:**
  - Substituir `.grid-agenda-4` por `.grid-agenda-3` (`repeat(3, minmax(0, 1fr))`), ajustando `.agenda-acoes-barra` para 2 linhas sem corte no `datetime-local`.
  - Substituir os botões `"o"` por ícones SVG claros (`✏️ Editar / IA`, `✨ Arte IA`) com tooltip e contraste refinado.
  - Adicionar barra de filtros por status no cabeçalho da Agenda (*Todos*, *Rascunhos*, *Agendados*, *Publicados*) e contadores numéricos.

### Fase 4: Polimento das Abas Secundárias, Responsividade & Auditoria
- **Arquivos:** `frontend/js/config_custos.js`, `frontend/js/rag.js`, `frontend/js/biblioteca.js`, `frontend/index.html`, `testes/integration/api/rotas/test_painel_frontend.py`.
- **Entregas:**
  - Cards de KPIs na aba `Custos`, fonte monoespaçada e feedback JSON na aba `Config`, lista de fontes RAG em cards limpos e estados vazios padronizados.
  - Quality Gate obrigatório: 100% dos arquivos `<= 200` linhas, `ruff check .`, `mypy app/ testes/ --strict`, `pytest testes/ -v` e inspeção visual via `/chrome-control`.

### Fase Final: Auditoria, Revisão Geral & Hardening
- **Escopo:** Varredura de código morto/duplicado (DRY), verificação de `<= 200` linhas em todo o diff contra `7b49632`, `ruff check .`, `mypy app/ testes/ --strict`, suíte completa `pytest testes/ -v` e inspeção visual final via `/chrome-control`.

---

## 4. Checklist de Fases & Status
- [x] **Fase 1: Exclusão de Planejamento no Backend + Design Tokens & Ícones SVG**
  - Status: Concluído
  - Commit: `a7bd80e`
- [x] **Fase 2: Card Independente & Minimizado de "Grades Programadas"**
  - Status: Concluído
  - Commit: `22ab9e3`
- [x] **Fase 3: Estúdio Refinado & Cards da Agenda Profissionais (3 Colunas)**
  - Status: Concluído
  - Commit: `414d364`
- [x] **Fase 4: Polimento das Abas Secundárias, Responsividade & Auditoria**
  - Status: Concluído
  - Commit: `c82b93a`
- [ ] **Fase Final: Auditoria, Revisão Geral & Hardening**
  - Status: Pendente
  - Commit: `-`

## 5. Log de Decisões e Handoff
- **Fase 1 concluída em 2026-11-17 (`a7bd80e`):**
  - Extraído `SqlPlanejamentoRepository` + helper compartilhado `remover_por_conta` para `app/infra/db/repo_planejamento_sql.py` (com re-exportação em `repo_ia_rag_sql.py`), preservando `<= 200` linhas e evitando duplicação com `SqlRagRepository.remover`.
  - Extraído `preparar_reexecucao_plano` para `app/aplicacao/ia/agendamento_grade.py`, permitindo incluir `remover_plano` em `PlanejamentoSemanalUseCase` (190 linhas) com bloqueio HTTP `422` quando `status == EM_EXECUCAO`.
  - Rota `DELETE /planejamento/{conta_ig_id}/{plano_id}` retorna `204` ou `404` isolado por `(empresa_id, conta_ig_id)`; suíte de testes dedicada criada em `testes/integration/api/rotas/test_exclusao_planejamento.py`.
  - Adicionados design tokens de elevação/semântica (`frontend/css/tokens.css`), correção de especificidade de checkboxes/switches e `:focus-visible` (`frontend/css/styles.css`), e módulo SVG seguro via `createElementNS` sem `innerHTML` (`frontend/js/icones.js`).
  - Quality Gate: 14/14 arquivos `<= 190` linhas, `ruff check .` limpo, `mypy app/ testes/ --strict` limpo em 253 arquivos, `pytest testes/ -v` com `168 passed`.
- **Fase 2 concluída em 2026-11-17 (`22ab9e3`):**
  - Desacoplado `#resumo-semanal-box` em `<article class="glass-card stack-sm grades-card hidden">` independente entre o Estúdio e a Agenda (`frontend/index.html`), oculto automaticamente quando não há lotes.
  - Refatorado `frontend/js/componentes/resumo_orcamento.js` (154 linhas) com cabeçalho compacto (seletor de lote, status humanizado, botão **Aprovar & Gerar na Agenda** e botão **Excluir Lote** via `DELETE /planejamento/{contaId}/{planoId}` bloqueado quando `EM_EXECUCAO`), além de acordeão `<details class="grade-detalhes">` fechado por padrão com resumo de formatos.
  - Extraído `frontend/js/componentes/item_grade.js` (106 linhas, SRP) para renderizar cada item em mini-card de 2 colunas com badges coloridos (`IMAGE`, `CAROUSEL`, `REELS`, `STORIES`), prévia visual/placeholder e switch `Imagem IA` alinhado; sincronizada troca de lote em `frontend/js/planejamento.js` (`aoSelecionarPlano`).
  - Removidas classes legadas/mortas (`.resumo-*`, `.previa-unitaria-*`) e adicionados estilos responsivos em `frontend/css/agenda.css` (123 linhas); cobertura ampliada em `testes/integration/api/rotas/test_painel_frontend.py` (196 linhas).
  - Quality Gate: 6/6 arquivos `<= 196` linhas, zero `innerHTML`, `node --check OK`, `ruff check .` limpo, `mypy app/ testes/ --strict` limpo em 253 arquivos, `pytest testes/ -v` com `168 passed`.
- **Fase 3 concluída em 2026-11-17 (`414d364`):**
  - Extraído `frontend/js/componentes/agenda_filtros.js` (54 linhas, SRP) para renderizar os filtros de status (`Todos`, `Rascunhos`, `Aguardando Mídia`, `Agendados`, `Publicados` e `Falhas` condicional) com contadores numéricos em cache local e empty states acionáveis; integrado em `frontend/js/planejamento.js` (173 linhas).
  - Refatorado `frontend/js/componentes/card_agenda.js` (174 linhas): removidos os botões literais `"o"` (substituídos por `wand` na mídia e `pencil` na legenda via `frontend/js/icones.js`, 115 linhas com `+send` e `+alertCircle`), adicionados badge de formato `.badge-fmt`, badges semânticos por status e barra de ações em 2 linhas (linha 1: `datetime-local` completo + agendar; linha 2: CTA `Postar Agora`/`Repostar` + lixeira).
  - Refinado `frontend/js/componentes/estudio_unificado.js` (193 linhas) com barra superior única de modos + atalhos destacados, switches (`switch small`) para Série/Auto-agendar, `Pilar Editorial` alinhado e ícones SVG sem emojis.
  - Atualizados `frontend/index.html` (195 linhas) e `frontend/css/agenda.css` (132 linhas) migrando `.grid-agenda-4` para `.grid-agenda-3` (`repeat(3, minmax(0, 1fr))` acima de `1080px`, `2` colunas em tablet, `1` em mobile) e removendo `.btn-circular-recriar`.
  - Cobertura ampliada em `testes/integration/api/rotas/test_painel_frontend.py` (199 linhas) validando ausência de `grid-agenda-4`, `btn-circular-recriar` e `text: "o"`, além de zero `innerHTML` em todos os assets JS/CSS.
  - Quality Gate: 8/8 arquivos `<= 199` linhas, zero `innerHTML`, `node --check OK`, `ruff check .` limpo, `mypy app/ testes/ --strict` limpo em 253 arquivos, `pytest testes/ -v` com `168 passed`.
- **Fase 4 concluída em 2026-11-17 (`c82b93a`):**
  - Criado componente compartilhado `frontend/js/componentes/estado_vazio.js` (29 linhas, DRY/SRP) reutilizado por `agenda_filtros.js` (51 linhas), `biblioteca.js` (163 linhas) e `rag.js` (193 linhas).
  - Criado `frontend/js/componentes/custos_kpi.js` (87 linhas) com 4 cards de KPIs escaneáveis (*Gasto da Empresa*, *Conta Ativa*, *Saldo Disponível*, *Modo de Proteção*) + barra semântica (`progress-warn`/`progress-danger`) reutilizada também pela cota da Biblioteca.
  - Criado `frontend/js/componentes/editor_json_config.js` (90 linhas) com fonte monoespaçada, botão *Formatar* e validação visual em tempo real (`JSON válido` / `JSON inválido`), integrado a `frontend/js/config_custos.js` (160 linhas).
  - Reorganizada aba `Cultura (RAG)` (`frontend/js/rag.js`) em grid de 3 cards de ingestão + cards limpos de fontes indexadas; aprimorada `frontend/js/biblioteca.js` e `frontend/js/auth.js` (126 linhas, ícones `sun`/`moon`/`logout`); ampliada biblioteca `frontend/js/icones.js` (152 linhas).
  - Estruturado `frontend/index.html` (194 linhas) + `frontend/css/paineis.css` (132 linhas) + ajustes responsivos em `styles.css` (117 linhas) e `agenda.css` (132 linhas) eliminando overflow horizontal em mobile (`390x844`) e desktop (`1366x900`) nos temas dark e light.
  - Inspeção visual via `/chrome-control` (15 capturas em dark/light, desktop/mobile, estado vazio e erro JSON) com `0` overflows e `erros_runtime: []`; adicionada suíte `testes/integration/api/rotas/test_painel_secundarias.py` (89 linhas).
  - Quality Gate: 100% dos arquivos `<= 199` linhas, zero `innerHTML`, `node --check OK`, `ruff check .` limpo, `mypy app/ testes/ --strict` limpo em 254 arquivos, `pytest testes/ -v` com `169 passed`.
