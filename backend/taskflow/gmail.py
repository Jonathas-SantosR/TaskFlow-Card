"""Autorização Google e envio de recuperação pela API do Gmail."""

import base64
import json
import os
import threading
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from backend.taskflow.criptografia import ErroCriptografia
from backend.taskflow.dominio import ErroDominio
from backend.taskflow.email import ErroEnvioEmail, validar_email

ESCOPO_ENVIO = "https://www.googleapis.com/auth/gmail.send"
ESCOPO_IDENTIDADE = "https://www.googleapis.com/auth/userinfo.email"
AUTORIZACAO_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
IDENTIDADE_URL = "https://openidconnect.googleapis.com/v1/userinfo"
ENVIO_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
RETORNO_LOCAL = "http://127.0.0.1:8765/gmail/retorno"


def _url_publica(valor):
    url = str(valor or "http://127.0.0.1:5000").strip().rstrip("/")
    try:
        partes = urlsplit(url)
        _ = partes.port
    except ValueError:
        raise ErroDominio("Configure uma URL válida para os links de recuperação.") from None
    if (
        not partes.hostname
        or partes.username
        or partes.password
        or partes.path
        or partes.query
        or partes.fragment
        or any(c.isspace() for c in url)
        or not (
            partes.scheme == "https"
            or (partes.scheme == "http" and partes.hostname in {"localhost", "127.0.0.1", "::1"})
        )
    ):
        raise ErroDominio("Use HTTPS na URL pública; HTTP é permitido apenas no computador local.")
    return url


def _json_google(url, dados=None, token=None):
    cabecalhos = {"Accept": "application/json"}
    corpo = None
    if dados is not None:
        corpo = urlencode(dados).encode("utf-8")
        cabecalhos["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, data=corpo, headers=cabecalhos), timeout=15) as resposta:
            return json.loads(resposta.read(65537))
    except (HTTPError, URLError, OSError, ValueError, TimeoutError):
        raise ErroEnvioEmail(
            "Não foi possível concluir a comunicação com o Google.", codigo="GMAIL_FALHOU"
        ) from None


class RemetenteGmail:
    """Guarda credenciais OAuth criptografadas e usa somente o escopo de envio."""

    def __init__(self, caminho, criptografia=None, base_url=None):
        self.caminho = Path(caminho)
        self.criptografia = criptografia
        self.base_url = _url_publica(base_url or os.getenv("TASKFLOW_PUBLIC_URL"))
        self._bloqueio = threading.RLock()

    def _carregar(self):
        variaveis = {
            "client_id": os.getenv("TASKFLOW_GMAIL_CLIENT_ID", "").strip(),
            "client_secret": os.getenv("TASKFLOW_GMAIL_CLIENT_SECRET", "").strip(),
            "refresh_token": os.getenv("TASKFLOW_GMAIL_REFRESH_TOKEN", "").strip(),
            "email": os.getenv("TASKFLOW_GMAIL_SENDER", "").strip(),
        }
        if any(variaveis.values()):
            if not all(variaveis.values()):
                raise ErroDominio("A configuração privada da API do Gmail está incompleta.")
            return variaveis
        if not self.caminho.exists():
            return {}
        if self.criptografia is None:
            raise ErroDominio("A chave da configuração privada do Gmail não foi encontrada.")
        try:
            return json.loads(self.criptografia.descriptografar(
                self.caminho.read_text(encoding="utf-8")
            ))
        except (OSError, ValueError, TypeError, ErroCriptografia):
            raise ErroDominio("Não foi possível ler a configuração do Gmail.") from None

    def _salvar(self, dados):
        if self.criptografia is None:
            raise ErroDominio("Configure a chave privada do Gmail antes de salvar credenciais.")
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        temporario.write_text(
            self.criptografia.criptografar(json.dumps(dados)), encoding="utf-8"
        )
        try:
            temporario.chmod(0o600)
        except OSError:
            pass
        os.replace(temporario, self.caminho)

    def publico(self):
        with self._bloqueio:
            dados = self._carregar()
            return {
                "cliente_configurado": bool(dados.get("client_id") and dados.get("client_secret")),
                "conectada": bool(dados.get("refresh_token")),
                "email": dados.get("email", ""),
            }

    @property
    def configurada(self):
        try:
            return self.publico()["conectada"]
        except ErroDominio:
            return False

    def importar_cliente(self, conteudo):
        try:
            if len(conteudo) > 16384:
                raise ValueError
            web = json.loads(conteudo)["web"]
            client_id = web["client_id"]
            client_secret = web["client_secret"]
            retornos = web["redirect_uris"]
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            raise ErroDominio(
                "Envie o JSON de um cliente OAuth do tipo aplicativo da Web."
            ) from None
        if (
            not isinstance(client_id, str)
            or not client_id.endswith(".apps.googleusercontent.com")
            or not isinstance(client_secret, str)
            or not client_secret
            or not isinstance(retornos, list)
            or RETORNO_LOCAL not in retornos
        ):
            raise ErroDominio(
                f"No Google Cloud, cadastre a URI de redirecionamento {RETORNO_LOCAL}."
            )
        with self._bloqueio:
            self._salvar({"client_id": client_id, "client_secret": client_secret})

    def iniciar(self, estado):
        with self._bloqueio:
            dados = self._carregar()
        if not dados.get("client_id"):
            raise ErroDominio("Envie primeiro as credenciais OAuth do Google.")
        return AUTORIZACAO_URL + "?" + urlencode({
            "client_id": dados["client_id"],
            "redirect_uri": RETORNO_LOCAL,
            "response_type": "code",
            "scope": f"{ESCOPO_ENVIO} {ESCOPO_IDENTIDADE}",
            "access_type": "offline",
            "prompt": "consent",
            "state": estado,
        })

    def concluir(self, codigo):
        if not codigo or len(codigo) > 4096:
            raise ErroDominio("A autorização do Google não foi concluída.")
        with self._bloqueio:
            dados = self._carregar()
            resposta = _json_google(TOKEN_URL, {
                "code": codigo,
                "client_id": dados["client_id"],
                "client_secret": dados["client_secret"],
                "redirect_uri": RETORNO_LOCAL,
                "grant_type": "authorization_code",
            })
            if not resposta.get("refresh_token") or not resposta.get("access_token"):
                raise ErroDominio("O Google não concedeu acesso contínuo. Autorize novamente.")
            escopos = set(resposta.get("scope", "").split())
            if ESCOPO_ENVIO not in escopos or ESCOPO_IDENTIDADE not in escopos:
                raise ErroDominio("Autorize o envio e a identificação da conta Google.")
            identidade = _json_google(IDENTIDADE_URL, token=resposta["access_token"])
            if not identidade.get("email_verified"):
                raise ErroDominio("A conta Google precisa ter e-mail verificado.")
            dados["email"] = validar_email(identidade.get("email"))
            dados["refresh_token"] = resposta["refresh_token"]
            self._salvar(dados)
            return dados["email"]

    def desconectar(self):
        with self._bloqueio:
            dados = self._carregar()
            dados.pop("refresh_token", None)
            dados.pop("email", None)
            self._salvar(dados)

    def enviar_recuperacao(self, destinatario, token):
        destinatario = validar_email(destinatario)
        mensagem = EmailMessage()
        mensagem["Subject"] = "TaskFlowCards — recuperação de senha"
        mensagem["To"] = destinatario
        mensagem.set_content(
            "Recebemos um pedido de recuperação de senha da sua conta TaskFlowCards.\n\n"
            "Abra o link para escolher uma nova senha:\n"
            f"{self.base_url}/redefinir-senha#token={token}\n\n"
            "Este link pode ser usado uma vez e expira em 30 minutos.\n"
            "Se você não solicitou a recuperação, ignore esta mensagem.\n"
            "Não compartilhe o link. Sua senha atual continua válida até a redefinição.\n"
        )
        self._enviar_mensagem(mensagem, destinatario)

    def enviar_codigo_cadastro(self, destinatario, codigo, perfil):
        destinatario = validar_email(destinatario)
        mensagem = EmailMessage()
        mensagem["Subject"] = "TaskFlowCards — código de confirmação"
        mensagem["To"] = destinatario
        mensagem.set_content(
            f"Seu código de confirmação para a conta de {perfil.lower()} no TaskFlowCards é: {codigo}\n\n"
            "Digite o código na tela de cadastro. Ele expira em 10 minutos e pode ser usado uma vez.\n"
            "Se você não solicitou este cadastro, ignore a mensagem. Não compartilhe o código.\n"
        )
        self._enviar_mensagem(mensagem, destinatario)

    def _enviar_mensagem(self, mensagem, destinatario):
        with self._bloqueio:
            dados = self._carregar()
            if not dados.get("refresh_token"):
                raise ErroEnvioEmail("O envio de recuperação pelo Gmail ainda não foi configurado.", codigo="GMAIL_NAO_CONFIGURADO")
            try:
                credencial = _json_google(TOKEN_URL, {
                    "client_id": dados["client_id"],
                    "client_secret": dados["client_secret"],
                    "refresh_token": dados["refresh_token"],
                    "grant_type": "refresh_token",
                })
                acesso = credencial["access_token"]
            except (ErroEnvioEmail, KeyError):
                raise ErroEnvioEmail(
                    "A autorização Gmail expirou ou falhou. Reconecte a conta na configuração privada.",
                    codigo="GMAIL_AUTORIZACAO",
                ) from None
            mensagem["From"] = dados["email"]
            corpo = json.dumps({
                "raw": base64.urlsafe_b64encode(mensagem.as_bytes()).decode("ascii")
            }).encode("utf-8")
            try:
                requisicao = Request(ENVIO_URL, data=corpo, headers={
                    "Authorization": f"Bearer {acesso}",
                    "Content-Type": "application/json",
                })
                with urlopen(requisicao, timeout=15) as resposta:
                    if resposta.status != 200:
                        raise ErroEnvioEmail("O Gmail não confirmou o envio da mensagem.", codigo="GMAIL_FALHOU")
            except (HTTPError, URLError, OSError, ValueError, TimeoutError):
                raise ErroEnvioEmail("Não foi possível enviar o e-mail pelo Gmail.", codigo="GMAIL_FALHOU") from None
