# Deploy no EasyPanel

Este repositório foi preparado para ser implantado como **Compose Service** no EasyPanel. O Compose sobe três serviços: `frontend` (Next.js), `backend` (FastAPI) e `worker` (processamento yt-dlp/FFmpeg/OpenAI/upload), compartilhando o volume persistente `shorts_data`.

## 1. Criar o serviço

No EasyPanel: `Project > New Service > Compose > Git`.

- Repository URL: `https://github.com/RuanMarcos38/Youtube.git`
- Branch: `main`
- Build Path: `/`
- Docker Compose File: `docker-compose.yml`

Não publique portas no host. O domínio do EasyPanel deve apontar para o serviço interno `frontend`, porta `3000`.

## 2. Variáveis de ambiente

Cole o conteúdo de `.env.easypanel.example` no Environment e preencha os campos vazios. O EasyPanel substitui `$(PRIMARY_DOMAIN)` pelo domínio principal configurado.

Obrigatórias para operação completa:

- `OPENAI_API_KEY`
- `YOUTUBE_API_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_PROJECT_ID`

## 3. Google Cloud / YouTube

No OAuth Client do Google Cloud, cadastre exatamente a URI exibida por `/api/health` em `oauth_redirect_uri`. Em produção ela deve ser:

`https://SEU_DOMINIO/api/youtube/oauth/callback`

Habilite YouTube Data API v3 e use um OAuth Client do tipo Web Application. Depois do deploy, abra o site e clique em **Conectar YouTube**. O refresh token fica salvo no volume persistente, não no GitHub.

## 4. Domínio

Crie um domínio no Compose apontando para:

- Internal service: `frontend`
- Port: `3000`
- Protocol: HTTP
- HTTPS/certificado: habilitado no EasyPanel

O frontend encaminha `/api/*` e `/media/*` internamente para o FastAPI; portanto somente um domínio público é necessário.

## 5. Validação

Após o deploy:

- `/` deve abrir o dashboard.
- `/api/health` deve retornar os checks do backend/worker/API.
- `worker_alive` deve ficar `true`.
- `ffmpeg_available` e `ffprobe_available` devem ficar `true`.
- Após preencher as credenciais, `openai_configured`, `youtube_api_configured` e `google_oauth_configured` devem ficar `true`.
- Depois do OAuth, `youtube_channel_connected` deve ficar `true`.

## 6. Persistência

`shorts_data` guarda SQLite, vídeos gerados, transcrições e tokens OAuth. Não remova esse volume em atualizações normais.
