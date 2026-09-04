# TikTok — cadastro de produção do ShortsFlow AI

Este arquivo contém somente os dados públicos necessários para registrar o app no TikTok for Developers. Nenhuma credencial secreta deve ser salva no repositório.

## App

- Nome: `ShortsFlow AI`
- Plataforma: `Web`
- Website: `https://shorts.r2rmarketingdigital.com.br/`
- Redirect URI do Login Kit: `https://shorts.r2rmarketingdigital.com.br/api/tiktok/oauth/callback`
- Privacy Policy: `https://shorts.r2rmarketingdigital.com.br/privacidade`
- Terms of Service: `https://shorts.r2rmarketingdigital.com.br/termos`
- Exclusão de dados: `https://shorts.r2rmarketingdigital.com.br/exclusao-de-dados`
- Trusted domain: `https://shorts.r2rmarketingdigital.com.br`

## Produtos e escopos

Adicionar no app do TikTok:

1. Login Kit
2. Content Posting API
3. `user.info.basic`
4. `video.publish`

O ShortsFlow usa Direct Post com upload do arquivo (`FILE_UPLOAD`), então não depende de URL pública do vídeo para a transferência.

## Texto sugerido para revisão

> ShortsFlow AI permite que usuários conectem sua própria conta TikTok por OAuth, revisem cortes de vídeos que possuem direito de utilizar e publiquem esses vídeos diretamente em seu próprio perfil. O Login Kit é usado exclusivamente para autenticação e identificação básica da conta. O escopo video.publish é usado somente após ação explícita do usuário, respeitando as opções de privacidade e permissões retornadas pelo TikTok.

## Configuração do servidor

Depois de o TikTok fornecer as credenciais do app aprovado, cadastrar no ambiente do serviço ShortsFlow no EasyPanel:

- `TIKTOK_CLIENT_KEY=<client key do TikTok>`
- `TIKTOK_CLIENT_SECRET=<client secret do TikTok>`

O callback de produção é derivado automaticamente do `FRONTEND_URL` quando o ambiente ainda contém o callback local padrão. Se quiser fixá-lo explicitamente, usar:

- `TIKTOK_OAUTH_REDIRECT_URI=https://shorts.r2rmarketingdigital.com.br/api/tiktok/oauth/callback`

Nunca salvar o Client Secret no GitHub, em código-fonte, documentação, logs ou frontend.

## Aprovação

Para publicação direta em modo público, o app precisa ser aprovado para `video.publish`. Clientes não auditados pelo TikTok podem ter restrições de visibilidade até a conclusão da auditoria/revisão do Content Posting API.
