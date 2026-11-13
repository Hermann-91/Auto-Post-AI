# Integração Oficial Meta (Instagram Graph API)

## 1. Estratégia de Autenticação (SaaS + Conta Própria no Dev)
- **Abstração (`ProvedorAuthMetaPort`):**
  - **Implementação Padrão V1 — Instagram API with Instagram Login** (`graph.instagram.com`):
    - Scopes: `instagram_business_basic`, `instagram_business_content_publish`.
    - **Motivo:** Não exige que o cliente tenha uma Página do Facebook vinculada (menor atrito no onboarding SaaS).
  - **Extensão Futura:** Adaptador para **Facebook Login** (`graph.facebook.com`) caso o SaaS passe a oferecer tagueamento de produtos ou busca avançada de hashtags.
- **Gestão de Tokens:** Trocar código OAuth por *Long-Lived Token* (60 dias), criptografar com Fernet no DB e manter tarefa periódica de renovação antes da expiração.

## 2. Fluxo Obrigatório de Publicação (Assíncrono)
**Regra de Ouro:** Containers da Meta expiram (`EXPIRED`) em **24 horas**. Nunca criar containers na hora em que o usuário agenda; o **Worker** cria apenas no horário de publicar.

### Passo a passo no Worker:
0. **Resolução por Conta (`conta_ig_id`) & Strategy:** Selecionar as credenciais criptografadas da conta alvo e instanciar via DI a estratégia de publicação (`FotoStrategy`, `CarrosselStrategy`, `ReelsStrategy`, `StoriesStrategy` — extensível para novos formatos de vídeo).
1. **Checagem de Cota:** `GET /{ig-user-id}/content_publishing_limit?fields=quota_usage,config` — abortar/reagendar se atingiu o teto móvel de 24h (50–100 posts; carrossel conta como 1).
2. **Criar Container(s):**
   - **Foto Única:** `POST /{ig-user-id}/media` com `image_url` (JPEG público HTTPS no R2/S3) e `caption`.
   - **Carrossel (2 a 10 itens):** criar cada item com `is_carousel_item=true` (sem legenda) -> criar container pai com `media_type=CAROUSEL`, `children=[ids]` e `caption`.
   - **Reels:** `POST /{ig-user-id}/media` com `media_type=REELS`, `video_url` (MP4/MOV H.264+AAC, 9:16) e `caption`.
   - **Stories:** `POST /{ig-user-id}/media` com `media_type=STORIES` e `image_url`/`video_url` (`9:16` `1080x1920`, sem legenda textual).
3. **Polling Obrigatório de Status:**
   - Consultar `GET /{container-id}?fields=status_code,status` com backoff (ex.: 3s, 5s, 10s até timeout configurável).
   - Avançar **apenas** quando `status_code == "FINISHED"`. Se `ERROR` ou `EXPIRED`, registrar erro detalhado e marcar post como `FALHA`.
4. **Publicar (`media_publish`):**
   - `POST /{ig-user-id}/media_publish` com `creation_id`.
   - **Idempotência:** Se der timeout ou erro 5xx na resposta, consultar o container antes de qualquer retry (se já constar `PUBLISHED`, marcar como `PUBLICADO` sem duplicar).

## 3. Roteiro Dev -> Produção SaaS (App Review)
- **Fase Dev (Imediato):** Criar App no Meta Developers, adicionar sua própria conta do Instagram como **Testador** no painel do app. Isso permite testar OAuth e publicação real sem esperar App Review.
- **Fase Produção SaaS:** Publicar URLs reais de **Política de Privacidade** e **Termos de Uso** no domínio da VPS, gravar vídeo demonstrando o fluxo completo (login -> conexão IG -> criação -> publicação) e submeter para o **Meta App Review** das permissões `instagram_business_basic` e `instagram_business_content_publish`.
