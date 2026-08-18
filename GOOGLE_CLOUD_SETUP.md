# Google Cloud + YouTube Data API v3

## Objetivo
Habilitar busca e upload real de YouTube Shorts pelo backend FastAPI.

## 1. Projeto Google Cloud
1. Crie ou selecione o projeto da plataforma.
2. Em APIs & Services > Library, ative **YouTube Data API v3**.

## 2. OAuth consent screen
Configure a marca/aplicação e os usuários de teste enquanto o app estiver em modo de teste.

Escopos usados pelo backend:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`

## 3. OAuth Client
Em APIs & Services > Credentials, crie um **OAuth client ID** do tipo **Web application**.

Cadastre como Authorized redirect URI exatamente:

`https://SEU_BACKEND_PUBLICO/api/youtube/oauth/callback`

O valor precisa ser idêntico ao `YOUTUBE_OAUTH_REDIRECT_URI` do backend, incluindo `https`, hostname, path e barra final (se houver).

Baixe o JSON e salve como:

`backend/client_secret.json`

Nunca faça commit desse arquivo.

## 4. API key para descoberta de vídeos
Crie uma API key para o YouTube Data API v3, restrinja a chave ao YouTube Data API v3 e coloque o valor em:

`YOUTUBE_API_KEY=...`

## 5. Backend
Crie `backend/.env` a partir de `.env.example` e configure pelo menos:

```env
OPENAI_API_KEY=...
YOUTUBE_API_KEY=...
GOOGLE_OAUTH_CLIENT_SECRETS_FILE=client_secret.json
YOUTUBE_OAUTH_REDIRECT_URI=https://SEU_BACKEND_PUBLICO/api/youtube/oauth/callback
FRONTEND_URL=https://SEU_FRONTEND_PUBLICO
CORS_ORIGINS=https://SEU_FRONTEND_PUBLICO
```

## 6. Verificação
Com backend online:

- `GET /api/health` — deve mostrar FFmpeg, FFprobe, OpenAI, YouTube API e OAuth configurados.
- `GET /api/youtube/oauth/status` — deve mostrar `configured: true`.
- `GET /api/youtube/oauth/start` — abra `authorization_url` retornada.
- Após consentir, o Google retorna ao callback e o backend salva o refresh token.
- `GET /api/youtube/oauth/status` — deve mostrar `connected: true` e o canal conectado.

## 7. Upload
O upload usa `videos.insert` com sessão resumable e retry exponencial para erros 5xx.

Por segurança, a plataforma exige aprovação do corte antes de permitir o upload.

## Observação de produção
Projetos de API não verificados podem ter restrições de publicação definidas pelo YouTube. Faça a verificação/auditoria do projeto do Google quando for disponibilizar o SaaS para usuários reais.
