import secrets

from backend.taskflow.dominio import MODOS_JOGO, ErroDominio, ResultadoResposta
from backend.taskflow.servicos.base import ServicoBase


class ServicoJogos(ServicoBase):
    def _dificuldade_adaptativa(self, aluno_id, sala_id):
        recentes = self.repositorio.acertos_recentes(aluno_id, modo="BOT", sala_id=sala_id)
        if len(recentes) < 3:
            return "MÉDIO"
        aproveitamento = sum(recentes) / len(recentes)
        if aproveitamento < 0.5:
            return "FÁCIL"
        if aproveitamento >= 0.8:
            return "DIFÍCIL"
        return "MÉDIO"

    def proxima_questao(self, modo, codigo_sala=None):
        aluno = self._aluno()
        modo = str(modo or "").strip().upper()
        if modo not in MODOS_JOGO:
            raise ErroDominio("Modo de jogo inválido.")
        if modo != "BOT":
            raise ErroDominio("Entre em uma sala para jogar o modo multijogador.")
        sala = self.repositorio.salas.selecionar_sala_aluno(aluno.id, codigo_sala)
        if sala is None:
            return None
        dificuldade = self._dificuldade_adaptativa(aluno.id, sala.id)  # Histórico da sala.
        return self.repositorio.selecionar_questao(dificuldade, aluno_id=aluno.id, sala_id=sala.id)

    def responder_questao(self, questao_id, indice_escolhido, modo, codigo_sala=None):
        aluno = self._aluno()
        modo = str(modo or "").strip().upper()
        if modo not in MODOS_JOGO:
            raise ErroDominio("Modo de jogo inválido.")
        if modo != "BOT":
            raise ErroDominio("Entre em uma sala para responder no multijogador.")
        sala = self.repositorio.salas.selecionar_sala_aluno(aluno.id, codigo_sala)
        questao = self.repositorio.buscar_questao(questao_id)  # O ID não comprova acesso.
        if sala is None or questao is None or not self.repositorio.salas.questao_autorizada_aluno(
            aluno.id, questao.id, sala.id
        ):
            raise ErroDominio("Esta questão não está disponível para sua sala.")
        try:
            indice_escolhido = int(indice_escolhido)
        except (TypeError, ValueError):
            raise ErroDominio("Escolha uma alternativa.") from None
        if indice_escolhido not in range(4):
            raise ErroDominio("Escolha uma alternativa válida.")
        correta = indice_escolhido == questao.indice_correto
        pontos = questao.pontos if correta else 0
        feedback = questao.feedback_acerto if correta else questao.feedback_erro
        chance_bot = {"FÁCIL": 75, "MÉDIO": 60, "DIFÍCIL": 45}[questao.dificuldade]
        bot_acertou = secrets.randbelow(100) < chance_bot
        pontos_bot = questao.pontos if bot_acertou else 0
        self.repositorio.questoes.registrar_resposta_bot(
            aluno.id,
            questao,
            indice_escolhido,
            correta,
            pontos,
            sala.id,
        )
        self.repositorio.registrar_evento(
            aluno.perfil,
            "RESPOSTA_REGISTRADA",
            "PARTIDA",
            aluno.id,
            questao.id,
        )
        return ResultadoResposta(
            correta=correta,
            alternativa_correta=questao.alternativa_correta,
            feedback=feedback,
            pontos_recebidos=pontos,
            bot_acertou=bot_acertou,
            pontos_bot=pontos_bot,
        )
