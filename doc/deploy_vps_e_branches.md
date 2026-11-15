# 🚀 Guia de Deploy na VPS (`oracle-vps`) e Fluxo de Branches

Este documento descreve a arquitetura de deploy contínuo do **Robo-Auto-Inst** na `oracle-vps` via Git Hook (`post-receive`) e o fluxo de trabalho entre as branches `develop`, `main` e `web`.

---

## 🌿 1. Estratégia de Branches

| Branch | Ambiente | Descrição |
| :--- | :--- | :--- |
| **`develop`** | Local (Dev) | Branch de trabalho diário para implementar novas funcionalidades e rodar testes (`pytest`, `ruff`, `mypy`). |
| **`main`** | GitHub (Release) | Histórico estável das entregas homologadas. |
| **`web`** | Produção (`oracle-vps`) | Branch conectada ao deploy automático em tempo real na VPS via `git push origin web`. |

### Fluxo Diário de Desenvolvimento:
```bash
# 1. Desenvolver e testar na branch develop
git checkout develop
.venv/bin/ruff check . && .venv/bin/mypy app testes && .venv/bin/pytest

# 2. Promover para produção (branch web) e disparar deploy na VPS + GitHub
git checkout web
git merge develop
git push origin web

# 3. Voltar para develop para continuar implementando
git checkout develop
```

---

## 🖥️ 2. Arquitetura na `oracle-vps`

- **Alias SSH:** `oracle-vps` (`ubuntu@163.176.239.118`)
- **Diretório da Aplicação (Working Tree):** `/home/ubuntu/apps/robo-auto-inst`
- **Repositório Git Bare (Receptor de Push):** `/home/ubuntu/repos/robo-auto-inst.git`
- **Hook de Deploy:** `/home/ubuntu/repos/robo-auto-inst.git/hooks/post-receive`

### Como o Duplo Push Funciona (`origin`)
O remote `origin` está configurado com duas `pushurl`s:
1. `git@github.com:Hermann-91/Auto-Post-AI.git` (atualiza o GitHub)
2. `oracle-vps:/home/ubuntu/repos/robo-auto-inst.git` (dispara `docker compose up -d --build --remove-orphans` na VPS)

Para verificar as URLs configuradas localmente:
```bash
git remote -v
```

---

## 🛠️ 3. Comandos Úteis de Operação na `oracle-vps`

### Verificar status dos 6 containers na VPS:
```bash
ssh oracle-vps "cd /home/ubuntu/apps/robo-auto-inst && docker compose ps"
```

### Consultar a URL pública atual do Túnel Cloudflare (`cloudflared`) da VPS:
```bash
ssh oracle-vps "cd /home/ubuntu/apps/robo-auto-inst && docker compose logs tunnel | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1"
```

### Atualizar `STORAGE_LOCAL_BASE_URL` na VPS caso o container `tunnel` gere nova URL:
```bash
VPS_TUNNEL=$(ssh oracle-vps "cd /home/ubuntu/apps/robo-auto-inst && docker compose logs tunnel | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1")
ssh oracle-vps "cd /home/ubuntu/apps/robo-auto-inst && sed -i \"s|STORAGE_LOCAL_BASE_URL=.*|STORAGE_LOCAL_BASE_URL=${VPS_TUNNEL}/media|g\" .env && docker compose up -d api worker"
```

### Acompanhar logs do Worker e da API na VPS em tempo real:
```bash
ssh oracle-vps "cd /home/ubuntu/apps/robo-auto-inst && docker compose logs -f --tail=50 worker api"
```
