# ShortsFlow AI — YouTube Shorts Automation SaaS

SaaS para descobrir vídeos do YouTube, baixar conteúdo autorizado, transcrever, selecionar momentos com IA, renderizar Shorts 9:16 com FFmpeg, gerar título/descrição/copy/tags e publicar no YouTube após aprovação.

## Stack

- Frontend: Next.js + React + Tailwind CSS
- Backend API: FastAPI + SQLAlchemy + SQLite
- Worker: Python separado para jobs longos
- Vídeo: yt-dlp + FFmpeg/FFprobe
- IA: OpenAI Responses API + `whisper-1` para timestamps
- YouTube: YouTube Data API v3 + OAuth 2.0
- Deploy: Docker Compose / EasyPanel

## Produção no EasyPanel

Veja [`EASYPANEL.md`](EASYPANEL.md). O repositório possui `docker-compose.yml`, Dockerfiles para frontend/backend, health checks e volume persistente.

## Desenvolvimento local

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Worker em outro terminal:

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Variáveis principais

Consulte `backend/.env.example` e `.env.easypanel.example`. Nunca faça commit de chaves ou tokens.

## Segurança e direitos

O sistema exige confirmação de direitos/licença antes de processar um vídeo. Use apenas conteúdo próprio, licenciado ou com autorização de reutilização.
