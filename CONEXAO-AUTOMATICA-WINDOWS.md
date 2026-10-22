# Conexao automatica no Windows

O modo automatico inicia ao entrar na conta do Windows e reconecta apos quedas de internet. O computador precisa permanecer ligado e conectado. Nenhuma senha de conta ou chave Google/YouTube e alterada.

## Ativar uma vez

1. Com a atualizacao do servidor publicada, entre como administrador em `https://shorts.r2rmarketingdigital.com.br/conexao-automatica`.
2. Clique em **Autorizar conexao automatica deste computador** e depois em **Copiar codigo para o instalador**. Se houver cliente antigo aberto, desconecte-o primeiro.
3. Na pasta do pacote Windows, abra `ATIVAR-AUTOMATICO.bat`, cole o codigo no campo protegido e clique em **Ativar inicio automatico**.
4. Confirme no painel que o computador esta conectado. Para verificar a inicializacao automatica, saia e entre novamente no Windows.

O instalador copia os arquivos para `%LOCALAPPDATA%\ShortsFlow-Automatico` e registra `ShortsFlow-Automatico.vbs` na pasta Inicializar do usuario atual. A autorizacao e cifrada com DPAPI, vinculada ao usuario Windows; a pasta fica restrita ao usuario e SYSTEM. O segredo nao aparece em argumentos de processos, logs ou no GitHub. O servidor guarda apenas o hash verificador, em volume privado.

O codigo temporario antigo continua expirando em seis horas. Gere o codigo na pagina de conexao automatica para usar o modo persistente. A autorizacao persistente sobrevive a reinicios do servidor e permanece valida ate revogacao. Gerar outra autorizacao automatica substitui a anterior. **Configuracoes > Desativar conexao residencial** revoga a autorizacao do computador.

`Desativar-ShortsFlow.ps1` remove somente a inicializacao automatica local. Para encerrar e revogar a conexao atual, use o painel. O arquivo `connection.log`, na pasta de instalacao, contem apenas estados de conexao e tem tamanho limitado. Caso a autorizacao seja recusada/revogada, o cliente para em vez de tentar indefinidamente.

O cliente continua limitado a destinos HTTPS do YouTube, com bloqueio de enderecos privados e limite de canais. Ele nao abre portas na rede local nem permite acesso geral pela conexao residencial.
