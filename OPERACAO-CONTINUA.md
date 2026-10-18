# Operacao continua sem depender do computador

A producao atual usa o ramo `fix/ytdlp-chrome-api-target` no EasyPanel.
Preserve esse ramo como base: a versao principal nao inclui todas as integracoes publicadas.

A conexao residencial do computador e temporaria (seis horas) e exige computador ligado, internet e cliente aberto. Ela nao atende processamento com computador desligado.

Para operar continuamente, configure um proxy residencial/estatico permanente no servidor, no campo **Configuracoes > Download YouTube > Proxy residencial/estatico**. Insira as credenciais apenas no painel autenticado; nunca em commits, logs ou mensagens. Essa configuracao tem prioridade sobre o pareamento temporario, sem apagar cookies, contas ou codigos existentes. Sem proxy configurado, o comportamento do cliente temporario permanece igual.

A configuracao de um proxy nao garante que o YouTube aceite a sessao/IP. Execute **Testar download**, confirme um resultado aprovado e depois repita um processamento com o cliente do computador fechado. Confira a geracao de um corte completo. Os processamentos anteriores que falharam precisam ser reenviados por **Tentar novamente**, apos a validacao.

O servidor e o worker ja possuem reinicio automatico via Supervisor. Reiniciar a hospedagem ou manter a pagina aberta nao restaura uma saida residencial offline. Nao substitua o ambiente nem os volumes para corrigir esse problema.

Diagnostico em 17/10/2026: worker e ferramentas de video ativos; cliente residencial offline; nenhum proxy permanente configurado; teste direto do servidor recusado pelo mecanismo anti-bot do YouTube. A disponibilidade dos downloads depende da configuracao e validacao da conexao permanente.
