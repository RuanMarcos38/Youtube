# Auto-Edit IA — Acabamento avançado em produção

Esta evolução complementa o Auto-Edit IA já implementado sem redesenhar o dashboard, sem substituir autenticação/cobrança e sem alterar credenciais existentes.

## Recursos acrescentados

- **Auto-reframe 9:16 por tomada:** OpenCV analisa o quadro central de cada corte, detecta o rosto dominante e suaviza o centro de enquadramento. Quando não há rosto detectável, aplica fallback central seguro.
- **Adaptação social:** o master 1080x1920 é compatível com TikTok Shop, Instagram Reels e YouTube Shorts.
- **B-roll contextual:** a IA extrai conceitos da transcrição e cria inserções visuais usando somente o próprio material enviado pelo usuário, com punch-in/contextual cutaway. Nenhum banco externo é baixado sem licença ou nova credencial.
- **Sound design:** gera uma cama sonora original procedural, escolhe mood automaticamente e sincroniza acentos sonoros com pontos de corte. A voz continua normalizada para -14 LUFS.
- **Ganchos A/B:** gera três variações fiéis ao conteúdo para os primeiros 3 segundos, com texto e acento sonoro próprios. As versões A, B e C ficam disponíveis no workspace.
- **Timeline separada:** adiciona trilhas `broll-contextual`, `sound-design` e `hook-variants` ao JSON editável já existente.

## Segurança de direitos

O B-roll usa somente o arquivo do próprio usuário, cuja autorização é confirmada no upload. A trilha é gerada proceduralmente pelo sistema e não baixa música comercial ou conteúdo de terceiros.

## Fallback de produção

O acabamento avançado roda depois da edição base. Se OpenCV, planejamento criativo ou alguma etapa extra falhar, o preview base já renderizado é preservado e o projeto continua disponível para revisão/exportação.

## Infraestrutura

A funcionalidade reutiliza OpenAI, FFmpeg, autenticação, armazenamento por `user_id` e worker existentes. A única dependência adicional é `opencv-python-headless`, usada apenas para análise de enquadramento. Nenhuma nova chave, senha ou variável secreta é necessária.
