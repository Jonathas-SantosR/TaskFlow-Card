"""Recuperação pelo Gmail de login, com fila finita e cotas persistentes."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from backend.taskflow.dominio import ErroDominio, normalizar_gmail
from backend.taskflow.email import ORIENTACOES_ERRO, ErroEnvioEmail

MENSAGEM_RECUPERACAO = (
    "Se o Gmail corresponder a uma conta ativa e o envio estiver disponível, "
    "você receberá um link para criar uma nova senha. Confira a pasta de spam "
    "e aguarde pelo menos um minuto antes de solicitar novamente."
)


class ServicoRecuperacao:
    """Compartilhado pela aplicação; não mantém a identidade da requisição."""

    def __init__(self, repositorio, remetente, tentativas=None, envio_assincrono=True):
        self.repositorio = repositorio
        self.remetente = remetente
        self.tentativas = tentativas if tentativas is not None else {}
        self._vagas = threading.BoundedSemaphore(20)
        self._executor = ThreadPoolExecutor(max_workers=2) if envio_assincrono else None

    def fechar(self):
        if self._executor:
            self._executor.shutdown(wait=True)

    def email_do_usuario(self, usuario):
        return self.repositorio.recuperacao.email_do_usuario(usuario)

    def salvar_email(self, usuario, email, senha_atual):
        raise ErroDominio(
            "A recuperação utiliza somente o Gmail de login. Atualize o cadastro da conta."
        )

    def resumo_envios(self, limite=20):
        """Diagnóstico interno; não retorna Gmail, IP ou tokens."""
        registros = self.repositorio.recuperacao.listar_solicitacoes(limite)
        for registro in registros:
            registro["orientacao"] = ORIENTACOES_ERRO.get(registro["codigo_erro"], "")
        return registros

    def solicitar(self, perfil, identificador, origem="", chave_requisicao=""):
        try:
            gmail = normalizar_gmail(identificador)
        except ErroDominio:
            return MENSAGEM_RECUPERACAO
        if perfil not in {"PROFESSOR", "ALUNO"}:
            return MENSAGEM_RECUPERACAO
        persistencia = self.repositorio.recuperacao
        reserva = persistencia.reservar_solicitacao(gmail, origem, chave_requisicao)
        if not reserva["nova"]:
            return MENSAGEM_RECUPERACAO
        solicitacao_id = reserva["id"]
        if not self.remetente.configurada:
            persistencia.concluir_solicitacao(solicitacao_id, "FALHOU", "GMAIL_NAO_CONFIGURADO")
            return MENSAGEM_RECUPERACAO
        destinatario = persistencia.buscar_destinatario(perfil, gmail)
        if destinatario is None:
            persistencia.concluir_solicitacao(solicitacao_id, "IGNORADO", "DADOS_NAO_ELEGIVEIS")
            return MENSAGEM_RECUPERACAO
        if not self._vagas.acquire(blocking=False):
            persistencia.concluir_solicitacao(solicitacao_id, "FALHOU", "FILA_CHEIA")
            return MENSAGEM_RECUPERACAO
        usuario, email = destinatario
        try:
            token = persistencia.emitir_token(
                usuario.id,
                email_esperado=email,
                versao_esperada=usuario.versao_sessao,
                solicitacao_id=solicitacao_id,
            )
        except ErroDominio:
            self._vagas.release()
            persistencia.concluir_solicitacao(solicitacao_id, "IGNORADO", "CADASTRO_ALTERADO")
            return MENSAGEM_RECUPERACAO
        except Exception:
            self._vagas.release()
            raise
        if self._executor:
            try:
                self._executor.submit(self._enviar, solicitacao_id, usuario.id, email, token)
            except RuntimeError:
                self._vagas.release()
                persistencia.revogar_token(token)
                persistencia.concluir_solicitacao(solicitacao_id, "FALHOU", "ENVIO_INTERROMPIDO")
        else:
            self._enviar(solicitacao_id, usuario.id, email, token)
        return MENSAGEM_RECUPERACAO

    def _enviar(self, solicitacao_id, usuario_id, email, token):
        persistencia = self.repositorio.recuperacao
        enviado = False
        try:
            if not persistencia.iniciar_envio(solicitacao_id, token):
                persistencia.concluir_solicitacao(solicitacao_id, "IGNORADO", "CADASTRO_ALTERADO")
                return
            try:
                # Uma tentativa por solicitação. Não há reenvio automático.
                self.remetente.enviar_recuperacao(email, token)
            except (ErroEnvioEmail, ErroDominio, OSError) as erro:
                persistencia.revogar_token(token)
                codigo = getattr(erro, "codigo", "GMAIL_FALHOU")
                persistencia.concluir_solicitacao(solicitacao_id, "FALHOU", codigo)
                evento = "EMAIL_RECUPERACAO_FALHOU"
            else:
                enviado = True
                persistencia.concluir_solicitacao(solicitacao_id, "ENVIADO")
                evento = "EMAIL_RECUPERACAO_ENVIADO"
            self.repositorio.registrar_evento("ANONIMO", evento, "USUARIOS", None, usuario_id)
        except Exception:
            # Nunca registrar destinatário, mensagem, token ou senha no log.
            try:
                if enviado:
                    persistencia.concluir_solicitacao(solicitacao_id, "ENVIADO")
                else:
                    persistencia.revogar_token(token)
                    persistencia.concluir_solicitacao(solicitacao_id, "FALHOU", "GMAIL_FALHOU")
            except Exception:
                pass
            logging.getLogger(__name__).error(
                "Falha interna ao concluir solicitação de recuperação."
            )
        finally:
            self._vagas.release()

    def redefinir(self, token, senha, confirmacao):
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        usuario = self.repositorio.recuperacao.redefinir(token, senha)
        self.tentativas.pop(f"{usuario.perfil}|{usuario.identificador.strip().casefold()}", None)
        self.repositorio.registrar_evento(
            "ANONIMO", "SENHA_RECUPERADA_EMAIL", "USUARIOS", None, usuario.id
        )
        return usuario
