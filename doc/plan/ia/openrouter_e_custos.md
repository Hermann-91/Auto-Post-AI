# Estratégia de IA (OpenRouter), Mídia Híbrida e Orçamento ($)

## 1. Roteamento de Modelos via OpenRouter
Todas as chamadas passam por um único `ClienteOpenRouter` compatível com OpenAI (`POST https://openrouter.ai/api/v1/chat/completions`), separando `role: "system"` (persona/regras da empresa) e `role: "user"` (tarefa).

| Função | Modelo Primário Sugerido | Estratégia de Economia / Fallback |
| :--- | :--- | :--- |
| **Texto & JSON Estruturado** (legendas, hashtags, roteiros) | `deepseek/deepseek-v4-flash` | Usar `response_format` JSON; fallback para `:floor` ou `:free` (ex.: `openrouter/free`) se o teto de custo for atingido |
| **Visão / Curadoria** (analisar fotos, sugerir legenda) | Modelo multimodal flash econômico | Redimensionar miniatura para max 1024px antes de enviar em base64 (reduz tokens de visão) |
| **Geração / Edição de Imagem** (sob demanda) | **Nano Banana 2** (`google/gemini-3.1-flash-image`) ou **Lite** (`google/gemini-3.1-flash-lite-image`) | Acionar somente quando o usuário pedir edição/criação IA; consultar catálogo em `GET /api/v1/images/models` |

## 2. Chamada ao Nano Banana (Imagem) & Pós-Processamento Obrigatório
- **Payload:** Enviar `modalities: ["image", "text"]` no `/chat/completions` (com `image_url` em base64/URL quando for edição `image-to-image`).
- **Extração:** Ler a imagem gerada em `choices[0].message.images[0].image_url.url` (`data:image/png;base64,...`).
- **Regra Crítica (Custo + Meta API):**
  - Modelos Gemini Flash Image cobram **por tokens** (tokens de saída de imagem têm custo elevado).
  - **Pipeline Híbrido em 2 estágios:**
    1. **Opcional (IA - Pago):** Geração de fundo/cena ou reiluminação no Nano Banana.
    2. **Obrigatório (Local Pillow/FFmpeg - Custo $0):** Redimensionar conforme o formato (`4:5` `1080x1350` para feed/carrossel ou `9:16` `1080x1920` para Reels/Stories), montar carrossel, aplicar logo **opcionalmente** (se habilitado na conta/post) e **converter obrigatoriamente para JPEG RGB** (ou MP4 H.264/AAC).

## 3. Controle Rigoroso de Orçamento (`$`)
1. **Pré-cheque (`BudgetGuard`):** Antes de chamar qualquer modelo pago (e antes de disparar planos semanais), somar `registros_custo_ia` da `empresa_id` no mês corrente (com rastreamento detalhado por `conta_ig_id`). Se `gasto_atual >= limite_mensal_usd`:
   - Modo estrito: bloqueia modelos pagos e retorna aviso claro.
   - Modo econômico: força fallback para modelos `:free` (para texto/visão) e bloqueia geração de imagem paga.
2. **Contabilização Real:**
   - Capturar `usage.prompt_tokens`, `usage.completion_tokens` e **`usage.cost`** diretamente do JSON de resposta do OpenRouter.
   - Salvar o `id` da geração (`gen-...`) permitindo auditoria assíncrona via `GET /api/v1/generation?id=<gen_id>` (`total_cost`, `provider_name`, `native_tokens_cached`).
   - Habilitar header de cache quando aplicável para zerar custo em chamadas idênticas repetidas.

## 4. Prompts Dinâmicos & RAG por Conta Instagram
- Acabar com o padrão fixo `"Pé da Mata"` e o corte bruto `[:600]` de `projeto_robo_instagram`.
- Cada **conta do Instagram** (`conta_ig_id`) dentro da empresa possui:
  - `persona` estruturada (marca, nicho, região, tom de voz, CTA, restrições).
  - `base_conhecimento` indexada em chunks por `(empresa_id, conta_ig_id)` (selecionando apenas os trechos mais relevantes ao tema do post).

## 5. Planejamento Semanal Automatizado (2 Etapas + Cache Web)
- **Âncora Visual (`curtida_favorita`):** Imagens originais, `IA-Cria` e `IA-Edita` recebem descrição visual curta na entrada; imagens **curtidas/fixadas** têm prioridade máxima como referência estética sem enviar dezenas de arquivos brutos no prompt.
- **Pesquisa Web (`PesquisaTendenciasPort`):** Consulta tendências do nicho/região com **cache de 24h–72h no Redis/DB** (1 busca por semana/nicho, evitando custo recorrente por post).
- **Fluxo em 2 Etapas:** (1) IA gera grade semanal em JSON (texto/hashtags/ideia visual + **estimativa de custo `$`**) -> (2) Após confirmação do usuário, o **Worker** executa a criação/edição de mídias (`IA-Cria` / `IA-Edita`) e textos, enviando para revisão ou auto-agendamento opcional.
