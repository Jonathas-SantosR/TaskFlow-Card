import secrets

from backend.taskflow.dominio import AcessoNegado, ErroDominio, ParticipanteSala, ResultadoResposta
from backend.taskflow.servicos.base import ServicoBase


class ServicoSalas(ServicoBase):
    @staticmethod
    def _normalizar_codigo_sala(codigo):
        codigo = "".join(
            caractere for caractere in str(codigo or "").upper() if caractere.isalnum()
        )
        if len(codigo) != 6:
            raise ErroDominio("Informe o código de seis caracteres da sala.")
        return codigo

    def _normalizar_questoes_sala(self, questoes_ids):
        ids_normalizados = []
        for valor in questoes_ids:
            try:
                questao_id = int(valor)
            except (TypeError, ValueError):
                continue
            if questao_id not in ids_normalizados:
                ids_normalizados.append(questao_id)
        if not ids_normalizados:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        for questao_id in ids_normalizados:
            questao = self.repositorio.buscar_questao(questao_id)
            if questao is None or not questao.ativa:
                raise ErroDominio("Uma das questões selecionadas não está disponível.")
        return ids_normalizados

    @staticmethod
    def _normalizar_nome_sala(nome):
        nome = " ".join(str(nome or "").split())
        if len(nome) < 3:
            raise ErroDominio("Informe um nome para a sala com pelo menos 3 caracteres.")
        if len(nome) > 80:
            raise ErroDominio("O nome da sala deve ter no máximo 80 caracteres.")
        return nome

    def criar_sala_multijogador(self, nome, questoes_ids):
        professor = self._professor()
        nome = self._normalizar_nome_sala(nome)
        ids_normalizados = self._normalizar_questoes_sala(questoes_ids)
        alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        codigo = "".join(secrets.choice(alfabeto) for _ in range(6))
        sala = self.repositorio.criar_sala_multijogador(
            codigo, nome, professor.id, ids_normalizados
        )
        self.repositorio.registrar_evento(
            professor.perfil,
            "SALA_MULTIJOGADOR_CRIADA",
            "PARTIDA",
            professor.id,
            sala.id,
        )
        return sala

    def listar_salas_professor(self):
        professor = self._professor()
        return self.repositorio.listar_salas_professor(professor.id)

    def _sala_do_professor(self, codigo):
        professor = self._professor()
        sala = self.repositorio.buscar_sala_multijogador(self._normalizar_codigo_sala(codigo))
        if sala is None or sala.criador_id != professor.id:
            raise ErroDominio("Sala não encontrada.")
        return professor, sala

    def dados_sala_professor(self, codigo):
        _, sala = self._sala_do_professor(codigo)
        return {
            "sala": sala,
            "questoes_ids": self.repositorio.questoes_ids_sala_multijogador(sala.id),
        }

    def atualizar_sala_multijogador(self, codigo, nome, questoes_ids):
        professor, sala = self._sala_do_professor(codigo)
        nome = self._normalizar_nome_sala(nome)
        ids_normalizados = self._normalizar_questoes_sala(questoes_ids)
        self.repositorio.atualizar_sala_multijogador(sala.id, nome, ids_normalizados)
        self.repositorio.registrar_evento(
            professor.perfil,
            "SALA_MULTIJOGADOR_EDITADA",
            "PARTIDA",
            professor.id,
            sala.id,
        )
        return self.repositorio.buscar_sala_multijogador(sala.codigo)

    def excluir_sala_multijogador(self, codigo):
        professor, sala = self._sala_do_professor(codigo)
        self.repositorio.excluir_sala_multijogador(sala.id)
        self.repositorio.registrar_evento(
            professor.perfil,
            "SALA_MULTIJOGADOR_EXCLUIDA",
            "PARTIDA",
            professor.id,
            sala.id,
        )

    def entrar_sala_multijogador(self, codigo):
        aluno = self._aluno()
        codigo = self._normalizar_codigo_sala(codigo)
        sala = self.repositorio.buscar_sala_multijogador(codigo)
        if sala is None or sala.status != "ABERTA":
            raise ErroDominio("Sala não encontrada ou encerrada.")
        self.repositorio.entrar_sala_multijogador(sala.id, aluno.id)
        self.repositorio.registrar_evento(
            aluno.perfil,
            "SALA_MULTIJOGADOR_ENTRADA",
            "PARTIDA",
            aluno.id,
            sala.id,
        )
        return sala

    def estado_sala_multijogador(self, codigo):
        aluno = self._aluno()
        sala = self.repositorio.buscar_sala_multijogador(self._normalizar_codigo_sala(codigo))
        if sala is None:
            raise ErroDominio("Sala não encontrada.")
        if not self.repositorio.participante_na_sala(sala.id, aluno.id):
            raise AcessoNegado("Entre na sala antes de acessar a partida.")
        questao = self.repositorio.buscar_questao(sala.questao_id)
        if questao is None or not questao.ativa:
            raise ErroDominio("A questão desta rodada não está disponível.")

        participantes = []
        for linha in self.repositorio.participantes_multijogador(sala):
            usuario = self.repositorio.buscar_usuario(linha["aluno_id"])
            if usuario is None or not usuario.ativo:
                continue
            participantes.append(
                ParticipanteSala(
                    aluno_id=usuario.id,
                    nome=usuario.nome,
                    pontos=int(linha["pontos"]),
                    respondeu=bool(linha["respondeu"]),
                )
            )

        linha_resposta = self.repositorio.resposta_multijogador(sala, aluno.id)
        minha_resposta = None
        if linha_resposta:
            correta = bool(linha_resposta["correta"])
            minha_resposta = ResultadoResposta(
                correta=correta,
                alternativa_correta=questao.alternativa_correta,
                feedback=(questao.feedback_acerto if correta else questao.feedback_erro),
                pontos_recebidos=int(linha_resposta["pontos"]),
            )
        return {
            "sala": sala,
            "questao": questao,
            "participantes": participantes,
            "minha_resposta": minha_resposta,
            "pode_responder": (
                sala.status == "ABERTA" and len(participantes) >= 2 and minha_resposta is None
            ),
            "todos_responderam": (
                len(participantes) >= 2
                and all(participante.respondeu for participante in participantes)
            ),
            "sou_criador": sala.criador_id == aluno.id,
            "partida_encerrada": sala.status == "ENCERRADA",
        }

    def responder_sala_multijogador(self, codigo, indice_escolhido):
        aluno = self._aluno()
        estado = self.estado_sala_multijogador(codigo)
        sala = estado["sala"]
        questao = estado["questao"]
        try:
            indice_escolhido = int(indice_escolhido)
        except (TypeError, ValueError):
            raise ErroDominio("Escolha uma alternativa.") from None
        if indice_escolhido not in range(4):
            raise ErroDominio("Escolha uma alternativa válida.")
        correta = indice_escolhido == questao.indice_correto
        pontos = questao.pontos if correta else 0
        self.repositorio.registrar_resposta_multijogador(
            sala, aluno.id, questao, indice_escolhido, correta, pontos
        )
        self.repositorio.registrar_evento(
            aluno.perfil,
            "RESPOSTA_MULTIJOGADOR",
            "PARTIDA",
            aluno.id,
            sala.id,
        )
        return ResultadoResposta(
            correta=correta,
            alternativa_correta=questao.alternativa_correta,
            feedback=questao.feedback_acerto if correta else questao.feedback_erro,
            pontos_recebidos=pontos,
        )

    def avancar_rodada_multijogador(self, codigo):
        aluno = self._aluno()
        estado = self.estado_sala_multijogador(codigo)
        sala = estado["sala"]
        if sala.status == "ENCERRADA":
            return sala
        if not estado["todos_responderam"]:
            raise ErroDominio("Aguarde todos os participantes responderem.")
        atualizada = self.repositorio.avancar_rodada_multijogador(sala)
        self.repositorio.registrar_evento(
            aluno.perfil,
            "RODADA_MULTIJOGADOR_AVANCADA",
            "PARTIDA",
            aluno.id,
            sala.id,
        )
        return atualizada
