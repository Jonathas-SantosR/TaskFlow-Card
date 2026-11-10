from datetime import datetime, timezone


class RepositorioBase:
    def __init__(self, infraestrutura):
        self._infraestrutura = infraestrutura

    @property
    def conexao(self):
        return self._infraestrutura.conexao

    @property
    def _bloqueio(self):
        return self._infraestrutura._bloqueio

    @property
    def criptografia(self):
        return self._infraestrutura.criptografia

    @property
    def assinador_auditoria(self):
        return self._infraestrutura.assinador_auditoria

    @property
    def tipo_banco(self):
        return self._infraestrutura.tipo_banco

    @property
    def caminho(self):
        return self._infraestrutura.caminho

    @staticmethod
    def _agora():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
