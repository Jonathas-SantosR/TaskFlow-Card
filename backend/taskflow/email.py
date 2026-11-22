"""Validação e diagnóstico seguro do envio de recuperação pelo Gmail."""

from backend.taskflow.dominio import EMAIL, ErroDominio


ORIENTACOES_ERRO = {
    "GMAIL_NAO_CONFIGURADO": "O envio pela API do Gmail ainda não foi configurado nesta instalação.",
    "GMAIL_AUTORIZACAO": "A autorização da conta Gmail expirou ou falhou. Atualize a configuração privada.",
    "GMAIL_FALHOU": "A API do Gmail não confirmou o envio. Verifique a conexão e a autorização da conta.",
    "FILA_CHEIA": "Há muitos envios em andamento. Aguarde antes de solicitar novamente.",
    "ENVIO_INTERROMPIDO": "O sistema foi interrompido durante o envio. Não houve reenvio automático.",
    "DADOS_NAO_ELEGIVEIS": "A solicitação não correspondeu a uma conta ativa elegível.",
    "CADASTRO_ALTERADO": "O cadastro ou a senha mudou durante a solicitação. O link anterior foi cancelado.",
}


class ErroEnvioEmail(RuntimeError):
    """Falha de transporte sem incluir credenciais ou a resposta do provedor."""

    def __init__(self, mensagem=None, codigo="GMAIL_FALHOU"):
        self.codigo = codigo if codigo in ORIENTACOES_ERRO else "GMAIL_FALHOU"
        super().__init__(mensagem or ORIENTACOES_ERRO[self.codigo])


def validar_email(valor):
    email = str(valor or "").strip()
    if len(email) > 254 or EMAIL.fullmatch(email) is None:
        raise ErroDominio("Informe um e-mail válido.")
    return email
