# Armazenamento em Nuvem (R2/S3), Pastas, Cotas e Google Drive Opcional

## 1. Por que NÃO enviar links do Google Drive direto para a Meta
A Instagram Graph API exige que `image_url` e `video_url` apontem para arquivos diretos acessíveis publicamente via HTTPS (especialmente **JPEG** para imagens), sem cookies, telas de preview HTML, redirects de autenticação ou bloqueio de crawler. Links compartilhados do Google Drive falham com frequência nesse download pelo servidor da Meta.

## 2. Arquitetura de Fluxo de Mídia (`StorageMidiaPort`)
```text
[Upload UI] ou [Google Drive API (Importação Opcional)]
        │
        ▼
[Pipeline Pillow / FFmpeg] -> Compacta e padroniza (JPEG 4:5 / 9:16 ou MP4)
        │
        ▼
[StorageMidiaPort -> Cloudflare R2 / S3 (Principal na Nuvem)]
   └── /{empresa_id}/{conta_ig_id}/
        ├── originais/      (mídias enviadas, compactadas para economizar cota)
        ├── processadas/    (prontas para publicação/agendamento na Meta)
        ├── IA-Cria/        (artes criadas do zero via IA)
        └── IA-Edita/       (artes editadas via IA)
        │
        ▼
[Meta Graph API] -> Faz download direto da URL HTTPS do R2/S3 e publica
```

## 3. Storage Principal na Nuvem, Cotas e Limpeza Pós-Postagem
- **Cloudflare R2 (Padrão Recomendado) / AWS S3:** Zero armazenamento pesado no disco da VPS, configuração mínima via credenciais S3 no `.env`, CDN/HTTPS nativo compatível com a Meta e isolamento por prefixo de conta. *(Para testes locais sem internet, manter adaptador `FakeStorage/Local` apenas em ambiente `dev/test`)*.
- **Cotas por Conta/Plano (`midias_biblioteca`):**
  - Limite padrão configurável (ex.: **máximo 250 mídias [fotos + vídeos] OU teto de armazenamento em GB por conta/plano**), validado via consulta SQL (`COUNT` / `SUM(tamanho_bytes)`) antes de aceitar novo upload ou geração IA.
  - **Compactação na Entrada:** Fotos originais são normalizadas (ex.: até 2048px JPEG otimizado) ao salvar em `originais/` para maximizar a capacidade dentro da cota e reduzir custos de visão multimodal.
- **Botão de Curtida (`curtida_favorita`) & Limpeza Pós-Postagens:**
  - Qualquer imagem em `originais/`, `IA-Cria/` ou `IA-Edita/` pode ser **curtida/fixada** pelo usuário.
  - **Botão "Limpar Mídias Pós-Postagem"** (e política automática opcional): remove do R2/S3 e da fila apenas arquivos vinculados a posts já `PUBLICADO`, **protegendo obrigatoriamente** mídias marcadas com `curtida_favorita = true` ou vinculadas a posts `AGENDADO`/`RASCUNHO`.

## 4. Integração Opcional com Google Drive API
- Fluxo OAuth `drive.readonly` (ou `drive.file` se for salvar backup de artes tratadas de volta na pasta do cliente).
- O usuário escolhe imagens da sua pasta no Drive pelo painel -> o Back-end baixa os bytes -> compacta/processa e salva no `StorageMidiaPort` (R2/S3) dentro da cota da conta.
