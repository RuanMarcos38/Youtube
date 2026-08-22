# Diagnóstico de rede do YouTube

O diagnóstico de produção agora distingue duas situações que antes podiam aparecer misturadas no mesmo cartão:

- `youtube_ip_challenge`: a VPS conseguiu alcançar o YouTube em pelo menos uma estratégia, mas o IP/sessão de saída recebeu desafio anti-bot. Se uma tentativa IPv6 secundária terminar com `Network is unreachable`, essa mensagem não substitui a causa principal.
- `network_unreachable`: nenhuma evidência de desafio anti-bot foi detectada e a falha reportada é de conectividade/rota da VPS.

Essa alteração não troca cookies, OAuth, proxy, secrets ou credenciais existentes. O upload local e o Editor IA permanecem independentes do downloader remoto do YouTube.
