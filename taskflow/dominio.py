"""Entidades e validações sem dependência de interface ou banco de dados."""

from dataclasses import asdict, dataclass
import re


PERFIL_PROFESSOR = "PROFESSOR"
PERFIL_ALUNO = "ALUNO"
PERFIS = (PERFIL_PROFESSOR, PERFIL_ALUNO)
NIVEIS_DIFICULDADE = ("FÁCIL", "MÉDIO", "DIFÍCIL")
MODOS_JOGO = ("BOT", "MULTIJOGADOR")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
IDENTIFICADOR_ALUNO = re.compile(r"^[A-Za-z0-9._-]{2,24}$")


class ErroDominio(ValueError):
    """Erro previsto que pode ser mostrado ao usuário."""


class AcessoNegado(PermissionError):
    """Operação incompatível com o perfil autenticado."""


@dataclass(frozen=True, slots=True)
class Usuario:
    id: int
    perfil: str
    identificador: str
    nome: str
    ativo: bool
    criado_em: str
    primeiro_acesso: bool = False
    anonimizado_em: str | None = None

    def para_dict(self):
        return asdict(self)

    @property
    def eh_professor(self):
        return self.perfil == PERFIL_PROFESSOR

    @property
    def eh_aluno(self):
        return self.perfil == PERFIL_ALUNO

    @property
    def anonimizado(self):
        return self.anonimizado_em is not None


@dataclass(frozen=True, slots=True)
class Questao:
    """Questão revisada pelo professor e disponível para as partidas."""

    id: int
    professor_id: int | None
    tema: str
    dificuldade: str
    enunciado: str
    alternativas: tuple[str, str, str, str]
    indice_correto: int
    explicacao: str
    feedback_acerto: str
    feedback_erro: str
    criada_em: str
    ativa: bool = True

    @property
    def alternativa_correta(self):
        return self.alternativas[self.indice_correto]

    @property
    def pontos(self):
        return {"FÁCIL": 1, "MÉDIO": 2, "DIFÍCIL": 3}[self.dificuldade]


@dataclass(frozen=True, slots=True)
class ResultadoResposta:
    correta: bool
    alternativa_correta: str
    feedback: str
    pontos_recebidos: int
    bot_acertou: bool | None = None
    pontos_bot: int = 0


@dataclass(frozen=True, slots=True)
class SalaMultijogador:
    """Sala on-line compartilhada entre estudantes autenticados."""

    id: int
    codigo: str
    nome: str
    criador_id: int | None
    questao_id: int
    rodada: int
    status: str
    criada_em: str


@dataclass(frozen=True, slots=True)
class ParticipanteSala:
    """Placar e estado de um estudante dentro da rodada atual."""

    aluno_id: int
    nome: str
    pontos: int
    respondeu: bool


@dataclass(frozen=True, slots=True)
class Desempenho:
    total: int
    acertos: int
    pontos: int

    @property
    def percentual(self):
        return round((self.acertos / self.total) * 100) if self.total else 0


def normalizar_nome(valor):
    nome = " ".join(valor.split()) if isinstance(valor, str) else ""
    if not 2 <= len(nome) <= 60:
        raise ErroDominio("Informe um nome com 2 a 60 caracteres.")
    return nome


def normalizar_identificador(perfil, valor):
    if not isinstance(valor, str):
        raise ErroDominio("Informe o e-mail ou a matrícula.")
    identificador = valor.strip()
    if perfil == PERFIL_PROFESSOR:
        if len(identificador) > 100 or EMAIL.fullmatch(identificador) is None:
            raise ErroDominio("Informe um e-mail válido para o professor.")
    elif perfil == PERFIL_ALUNO:
        identificador = "".join(identificador.split())
        if IDENTIFICADOR_ALUNO.fullmatch(identificador) is None:
            raise ErroDominio("A matrícula deve ter de 2 a 24 letras, números, pontos, traços ou sublinhados.")
    else:
        raise ErroDominio("Perfil inválido.")
    return identificador


def normalizar_questao(
    tema,
    dificuldade,
    enunciado,
    alternativas,
    indice_correto,
    explicacao,
    feedback_acerto="",
    feedback_erro="",
):
    """Valida conteúdo pedagógico antes de persistir ou enviar para o jogo."""

    tema = " ".join(str(tema or "").split())
    enunciado = " ".join(str(enunciado or "").split())
    explicacao = " ".join(str(explicacao or "").split())
    dificuldade = str(dificuldade or "").strip().upper()
    alternativas = tuple(
        " ".join(str(alternativa or "").split()) for alternativa in alternativas
    )
    try:
        indice_correto = int(indice_correto)
    except (TypeError, ValueError):
        raise ErroDominio("Selecione a alternativa correta.") from None

    if not 2 <= len(tema) <= 100:
        raise ErroDominio("O tema deve ter de 2 a 100 caracteres.")
    if dificuldade not in NIVEIS_DIFICULDADE:
        raise ErroDominio("Dificuldade inválida.")
    if not 5 <= len(enunciado) <= 500:
        raise ErroDominio("O enunciado deve ter de 5 a 500 caracteres.")
    if len(alternativas) != 4 or any(
        not 1 <= len(alternativa) <= 180 for alternativa in alternativas
    ):
        raise ErroDominio("Informe quatro alternativas com até 180 caracteres.")
    if len({alternativa.casefold() for alternativa in alternativas}) != 4:
        raise ErroDominio("As quatro alternativas devem ser diferentes.")
    if indice_correto not in range(4):
        raise ErroDominio("Selecione uma alternativa correta válida.")
    if not 3 <= len(explicacao) <= 500:
        raise ErroDominio("A explicação deve ter de 3 a 500 caracteres.")

    feedback_acerto = " ".join(str(feedback_acerto or "").split())
    feedback_erro = " ".join(str(feedback_erro or "").split())
    if not feedback_acerto:
        feedback_acerto = f"Resposta correta. {explicacao}"
    if not feedback_erro:
        feedback_erro = f"Revise este conteúdo. {explicacao}"

    return {
        "tema": tema,
        "dificuldade": dificuldade,
        "enunciado": enunciado,
        "alternativas": alternativas,
        "indice_correto": indice_correto,
        "explicacao": explicacao,
        "feedback_acerto": feedback_acerto[:500],
        "feedback_erro": feedback_erro[:500],
    }
