# 📸 Guia de Integração Meta Graph API (`@gerai.artes`)

Este guia documenta a configuração de autenticação, criptografia de tokens e entrega de mídia para publicação real no Instagram via Graph API (`v22.0`).

---

## 🔑 1. Tipos de Token e `META_GRAPH_BASE_URL`

A Meta possui dois formatos de token OAuth para Instagram, e cada um exige um host específico na variável `META_GRAPH_BASE_URL` do `.env`:

| Prefixo do Token | Origem no Painel Meta | `META_GRAPH_BASE_URL` Correta | Expiração |
| :--- | :--- | :--- | :--- |
| **`EAA...`** *(Atual)* | Login Unificado / Usuário do Sistema (`SYSTEM_USER`) | **`https://graph.facebook.com`** | Permanente (`expires_at: 0`) |
| **`IGAA...`** | Login do Instagram Legado | `https://graph.instagram.com` | 60 dias (renovável) |

> ⚠️ **Atenção ao Erro `code=190`:** Enviar um token `EAA...` para `https://graph.instagram.com` retorna `Invalid OAuth access token - Cannot parse access token (code=190)`. Certifique-se de manter `META_GRAPH_BASE_URL=https://graph.facebook.com` no `.env`.

---

## 🗄️ 2. Sincronização da Conta no PostgreSQL (`contas_instagram`)

Para publicar em uma conta Instagram, a tabela `contas_instagram` precisa conter:
- **`ig_user_id`**: ID numérico oficial da conta na Meta (para `@gerai.artes`: `17841428089794256`).
- **`access_token_enc`**: Token `EAA...` criptografado com a chave `FERNET_KEYS` do `.env`.
- **`token_expira_em`**: `2099-12-31 23:59:59+00` para tokens permanentes (`SYSTEM_USER`).

### Comando para Atualizar o Token Criptografado no Banco:
```bash
ENC_TOKEN=$(docker compose exec -T api python -c "
from app.core.config import obter_configuracoes
from cryptography.fernet import Fernet
chave = obter_configuracoes().resolver_fernet_keys()[0].encode()
print(Fernet(chave).encrypt(b'SEU_TOKEN_EAA_AQUI').decode())
" | tr -d '\r\n')

docker compose exec -T db psql -U robo_app -d robo_auto_inst -c "
UPDATE contas_instagram
SET ig_user_id = '17841428089794256',
    access_token_enc = '$ENC_TOKEN',
    token_expira_em = '2099-12-31 23:59:59+00',
    ativa = true
WHERE username = 'gerai.artes';
"
```

---

## 🌐 3. Entrega de Mídia Pública (`STORAGE_LOCAL_BASE_URL`)

Quando o `worker` publica um post (`POST /{ig_user_id}/media`), os servidores da Meta fazem um download HTTP (`GET`) da imagem gerada em `/media/{chave}?exp=...&sig=...`.

- Por isso, `STORAGE_LOCAL_BASE_URL` **não pode ser `http://localhost:8000/media`**.
- O container `tunnel` (`cloudflare/cloudflared:latest`) cria automaticamente um túnel HTTPS apontando para `http://api:8000`, cujo endereço `https://xxxx.trycloudflare.com/media` deve estar configurado em `STORAGE_LOCAL_BASE_URL` no `.env`.
