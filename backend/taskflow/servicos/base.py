from dataclasses import dataclass, field

from backend.taskflow.dominio import AcessoNegado, Usuario


@dataclass
class ContextoServico:
    """Identidade local; dependências e tentativas podem ser compartilhadas."""

    repositorio: object
    gemini: object
    tentativas: dict = field(default_factory=dict)
    codigo_configuracao_professor: str = ""
    usuario_atual: Usuario | None = None


class ServicoBase:
    """Identidade e dependências comuns, sem regras específicas de uma funcionalidade."""

    def __init__(self, contexto):
        self._contexto = contexto

    @property
    def repositorio(self):
        return self._contexto.repositorio

    @property
    def gemini(self):
        return self._contexto.gemini

    @property
    def usuario_atual(self):
        return self._contexto.usuario_atual

    @property
    def _tentativas(self):
        return self._contexto.tentativas

    @property
    def _codigo_configuracao_professor(self):
        return self._contexto.codigo_configuracao_professor

    @usuario_atual.setter
    def usuario_atual(self, usuario):
        self._contexto.usuario_atual = usuario

    def _professor(self):
        if not self.usuario_atual or not self.usuario_atual.eh_professor:
            raise AcessoNegado("Acesso permitido somente ao professor.")
        return self.usuario_atual

    def _aluno(self):
        if not self.usuario_atual or not self.usuario_atual.eh_aluno:
            raise AcessoNegado("Acesso permitido somente ao aluno.")
        return self.usuario_atual
