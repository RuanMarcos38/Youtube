# Overrides locais e compatíveis com a API externa.
# Mantemos o módulo original para preservar tipos/erros usados pelo restante
# da aplicação e substituímos somente a função de conexão síncrona da Kiwify.
from . import kiwify_api as _kiwify_api
from .kiwify_fast import register_webhook_fast as _register_webhook_fast

_kiwify_api.register_webhook = _register_webhook_fast
