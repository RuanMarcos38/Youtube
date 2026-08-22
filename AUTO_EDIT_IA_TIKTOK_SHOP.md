# Auto-Edit IA — TikTok Shop

## Objetivo

Adicionar edição automatizada por IA ao ShortsFlow AI sem redesenhar o produto existente, sem alterar credenciais e sem substituir o fluxo atual de YouTube. A nova experiência entra como complemento: um botão flutuante **Auto-Edit IA** para usuários autenticados abre um workspace dedicado em `/editor-ia`.

## 1. Fluxo do usuário

1. O usuário entra normalmente no ShortsFlow AI com o login já existente.
2. O dashboard atual permanece com a mesma estrutura. Um botão discreto **Auto-Edit IA** é exibido como camada complementar.
3. Ao abrir `/editor-ia`, o usuário escolhe um preset de edição.
4. O usuário anexa um vídeo próprio em MP4, MOV, M4V, MPEG/MPG ou WEBM, com limite inicial de 500 MB.
5. Antes do envio, confirma que possui direitos/licença/autorização para editar e publicar o material.
6. Após o upload, clica em **Auto-Edit IA**.
7. A interface acompanha o processamento por status/progresso sem bloquear o restante do sistema.
8. A IA entrega um preview vertical pronto para revisão.
9. A timeline permanece estruturada em camadas: vídeo, áudio, legendas e efeitos. O usuário pode desativar cortes e solicitar nova renderização.
10. Quando aprovado, o usuário aciona **Exportar para TikTok Shop** e recebe um MP4 1080x1920 pronto para download/importação.

## 2. Pipeline técnico de back-end

### Upload e isolamento

- Endpoint multipart autenticado.
- Validação de extensão e tamanho.
- Armazenamento isolado por usuário em `data/users/{user_id}/editor-projects/{project_id}`.
- Nenhuma nova credencial é necessária.
- O projeto usa as configurações OpenAI e FFmpeg que já existem no runtime.

### Processamento

1. **Probe de mídia** — FFprobe obtém duração e características do arquivo.
2. **Áudio** — FFmpeg extrai áudio para transcrição.
3. **Transcrição** — usa o serviço de transcrição já existente no projeto.
4. **Detecção de silêncio** — FFmpeg `silencedetect` identifica pausas removíveis.
5. **Planejamento por IA** — o modelo recebe a transcrição com timestamps e pode marcar apenas retomadas, repetições, erros de gravação, frases abandonadas e enrolação removível, além de palavras-chave para legenda.
6. **Proteção de conteúdo** — intervalos são normalizados e a remoção excessiva é limitada para reduzir o risco de destruir a mensagem principal.
7. **Ritmo** — trechos mantidos são segmentados preferencialmente em limites naturais da transcrição, conforme o preset escolhido.
8. **Legendas** — timestamps são remapeados para a nova timeline e gerados em ASS, com animação, alto contraste e destaque de palavras-chave.
9. **Tratamento visual** — escala/crop vertical, Lanczos, redução de ruído e correções leves de contraste/saturação.
10. **Tratamento de áudio** — high-pass, limiter e normalização para alvo de -14 LUFS.
11. **Render** — H.264, 1080x1920, 30 fps, `yuv420p`, AAC 192 kbps/48 kHz e `faststart`.
12. **Timeline editável** — um JSON versionado é salvo com trilhas separadas de vídeo, áudio, captions e efeitos.
13. **Reedição** — mudanças na timeline voltam para a fila e são renderizadas novamente.
14. **Exportação TikTok Shop** — gera `tiktok-shop-export.mp4` em preset vertical compatível com importação/publicação.

### Execução assíncrona interna

O worker atual recebe um pool adicional exclusivo para o editor IA. Os jobs atuais de criação de Shorts, upload para YouTube e diagnóstico continuam independentes. Em reinício do worker, tarefas de edição interrompidas voltam automaticamente para a fila.

## 3. Presets sem poluir a interface

Os presets aparecem em um único seletor no workspace do Auto-Edit IA. Nenhum painel permanente é adicionado ao dashboard principal.

### TikTok Shop Vendas

- Cortes rápidos.
- Silêncios mais agressivos.
- Legendas de impacto.
- Foco em gancho, benefício, demonstração e CTA.

### UGC Conversão

- Ritmo humano e natural.
- Menos cortes por segundo.
- Legendas diretas.
- Adequado para depoimento, review e demonstração pessoal.

### Produto Cinematográfico

- Ritmo mais elegante.
- Tratamento visual suave.
- Legendas discretas.
- Adequado para produtos premium e detalhes de acabamento.

### Retenção Máxima

- Jump cuts mais rápidos.
- Alto contraste nas legendas.
- Indicado para criativos curtos e diretos.

## Arquitetura de UI

A regra é **progressive disclosure**:

- Dashboard original: somente o launcher flutuante `Auto-Edit IA`.
- Workspace de IA: upload + preset + progresso + preview.
- Timeline: só aparece depois que existe uma edição pronta.
- Exportação: só aparece quando o projeto está pronto.

Assim, o usuário iniciante vê apenas o necessário, enquanto o usuário mais experiente pode ajustar a timeline sem perder a edição automática.

## Segurança e compatibilidade

- Credenciais existentes não são modificadas.
- Nenhuma chave é escrita no código da funcionalidade.
- Acesso depende da autenticação já existente.
- Arquivos ficam segregados pelo `user_id`.
- O endpoint de mídia existente continua validando o diretório raiz do usuário.
- O fluxo atual de YouTube permanece disponível e não é substituído.

## Observação sobre upscaling

A primeira versão implementa **upscaling de alta qualidade por Lanczos + limpeza/redução de ruído**, preservando compatibilidade com CPU e EasyPanel. Super-resolution neural (por exemplo Real-ESRGAN) deve ser ativada como etapa opcional quando o ambiente possuir GPU/modelo adequado, para não tornar o deploy atual instável ou exigir novas credenciais.

## Critérios de aceite

- O layout atual não é redesenhado.
- Login, cobrança, YouTube e credenciais atuais continuam intactos.
- Usuário autenticado consegue anexar vídeo próprio.
- Auto-Edit IA gera preview vertical.
- Cortes, áudio, captions e efeitos são representados em trilhas separadas.
- Timeline pode ser ajustada e renderizada novamente.
- Exportação final é MP4 1080x1920 H.264/AAC.
- Cada usuário só acessa seus próprios projetos/mídias.
