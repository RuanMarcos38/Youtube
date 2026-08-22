# Deploy no EasyPanel

O projeto suporta agora **dois modos** de implantação no EasyPanel:

1. **APP único** — recomendado para o serviço `shortsia` que já existe no painel. O `Dockerfile` da raiz sobe frontend Next.js, backend FastAPI e worker no mesmo container usando Supervisor.
2. **Compose Service** — alternativa avançada, mantendo frontend/backend/worker em containers separados.

---

# Opção A — usar o APP `shortsia` existente

## Fonte

No serviço `r2rmarketingdigital / shortsia`, abra **Fonte**:

- Source: `GitHub`
- Repository: `RuanMarcos38/Youtube`
- Branch: `main`
- Build Path: `/`

## Build

Em **Build** selecione:

- Builder: `Dockerfile`
- Dockerfile: `Dockerfile`

Não use Nixpacks/Railpack na raiz para este projeto monorepo.

O Dockerfile da raiz executa:

- Next.js na porta pública `3000`
- FastAPI internamente na porta `8000`
- Worker de yt-dlp/FFmpeg/OpenAI em processo separado

## Ambiente

Em **Ambiente**, use como base `.env.example` e configure:

```env
APP_NAME=ShortsFlow AI
FRONTEND_URL=https://$(PRIMARY_DOMAIN)
OPENAI_API_KEY=
OPENAI_TEXT_MODEL=gpt-5
OPENAI_TRANSCRIPTION_MODEL=whisper-1
YOUTUBE_API_KEY=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_PROJECT_ID=
YOUTUBE_OAUTH_REDIRECT_URI=https://$(PRIMARY_DOMAIN)/api/youtube/oauth/callback
YOUTUBE_DEFAULT_REGION=BR
YOUTUBE_DEFAULT_PRIVACY=private
WORKER_POLL_SECONDS=2
```

### Autenticação do download do YouTube na VPS

O botão **YouTube conectado** confirma o OAuth usado para a API/upload, mas esse OAuth não substitui a sessão necessária ao `yt-dlp` quando o IP da VPS recebe o desafio **Sign in to confirm you're not a bot**.

Para esse cenário, o backend aceita de forma opcional:

```env
YTDLP_COOKIES_B64=
YTDLP_PROXY_URL=
```

No Windows, versões atuais do Chrome podem impedir `yt-dlp --cookies-from-browser chrome` com `Failed to decrypt with DPAPI` por causa do App-Bound Encryption do Chromium. Não desative a proteção do Chrome para contornar isso.

Use o utilitário da raiz do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File .\CONFIGURAR-YOUTUBE-AUTH.ps1
```

O utilitário:

- prefere Firefox quando houver uma sessão local disponível;
- não tenta quebrar/desativar a proteção DPAPI/App-Bound do Chrome;
- permite selecionar um `cookies.txt` Netscape exportado somente do `youtube.com`;
- valida o arquivo e copia o valor de `YTDLP_COOKIES_B64` para a área de transferência sem exibi-lo no terminal;
- não altera senhas, OAuth, domínio, banco ou outros projetos.

Depois de colar **somente** o valor em `YTDLP_COOKIES_B64`, salve o ambiente do serviço `r2rmarketingdigital/shortsia` e faça um novo deploy/Force Rebuild. Em `/api/health`, `youtube_download_mode` deve aparecer como `cookies` ou `cookies+proxy`.

Trate `cookies.txt` e o Base64 como credenciais: não envie em chat, issue, commit, print ou log.

## Persistência

Em **Storage/Volumes**, adicione armazenamento persistente montado em:

`/app/data`

É onde ficam SQLite, vídeos, transcrições, cortes e tokens OAuth.

## Domínio

Em **Domínios**, o domínio deve apontar para:

- Porta: `3000`
- Protocolo interno: `HTTP`
- HTTPS: habilitado pelo EasyPanel

Não aponte o domínio para `8000`: essa porta é apenas do FastAPI interno.

## Implantar

Clique em **Implantar**. Nos logs de runtime devem aparecer três processos iniciados pelo Supervisor:

- `backend`
- `worker`
- `frontend`

Depois valide:

- `/` abre o dashboard
- `/api/health` retorna o diagnóstico
- `worker_alive` = `true`
- `ffmpeg_available` = `true`
- `ffprobe_available` = `true`

---

# Opção B — Compose Service

No EasyPanel: `Project > New Service > Compose > Git`.

- Repository URL: `https://github.com/RuanMarcos38/Youtube.git`
- Branch: `main`
- Build Path: `/`
- Docker Compose File: `docker-compose.yml`

O Compose sobe `frontend`, `backend` e `worker` separadamente e compartilha o volume `shorts_data`.

O domínio deve apontar para:

- Internal service: `frontend`
- Port: `3000`
- Protocol: HTTP

---

# Google Cloud / YouTube

No OAuth Client do Google Cloud, cadastre exatamente:

`https://SEU_DOMINIO/api/youtube/oauth/callback`

Habilite a **YouTube Data API v3** e crie um OAuth Client do tipo **Web Application**.

Depois do deploy, clique em **Conectar YouTube**. O refresh token é armazenado no volume persistente e não é enviado ao GitHub.

# Validação final

Após preencher as credenciais e concluir o OAuth:

- `openai_configured` = `true`
- `youtube_api_configured` = `true`
- `google_oauth_configured` = `true`
- `youtube_channel_connected` = `true`

A aplicação poderá então executar o fluxo real de download autorizado, transcrição, seleção dos melhores momentos, renderização vertical, legendas, metadata por IA e upload para o YouTube.
