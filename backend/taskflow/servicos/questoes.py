from backend.taskflow.dominio import AcessoNegado, ErroDominio, normalizar_questao
from backend.taskflow.servicos.base import ServicoBase


class ServicoQuestoes(ServicoBase):
    def buscar_questao(self, questao_id):
        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre para consultar questões.")
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is not None and usuario.eh_aluno and not questao.ativa:
            return None
        return questao

    def gerar_questao(self, tema, dificuldade):
        professor = self._professor()
        questao = self.gemini.gerar_questao(tema, dificuldade)
        self.repositorio.registrar_evento(professor.perfil, "IA_QUESTAO", "GEMINI", professor.id)
        return questao

    def listar_questoes(self):
        self._professor()
        return self.repositorio.listar_questoes()

    def criar_questao(
        self,
        tema,
        dificuldade,
        enunciado,
        alternativas,
        indice_correto,
        explicacao,
        feedback_acerto="",
        feedback_erro="",
    ):
        professor = self._professor()
        dados = normalizar_questao(
            tema,
            dificuldade,
            enunciado,
            alternativas,
            indice_correto,
            explicacao,
            feedback_acerto,
            feedback_erro,
        )
        questao = self.repositorio.criar_questao(professor.id, dados)
        self.repositorio.registrar_evento(
            professor.perfil, "QUESTAO_CRIADA", "QUESTOES", professor.id, questao.id
        )
        return questao

    def salvar_questao_gerada(self, tema, dificuldade, questao):
        if not isinstance(questao, dict):
            raise ErroDominio("O rascunho da IA não está disponível.")
        return self.criar_questao(
            tema,
            dificuldade,
            questao.get("enunciado", ""),
            questao.get("alternativas", []),
            questao.get("indice_correto", ""),
            questao.get("explicacao", ""),
            questao.get("feedback_acerto", ""),
            questao.get("feedback_erro", ""),
        )

    def atualizar_questao(
        self,
        questao_id,
        tema,
        dificuldade,
        enunciado,
        alternativas,
        indice_correto,
        explicacao,
        feedback_acerto="",
        feedback_erro="",
    ):
        professor = self._professor()
        dados = normalizar_questao(
            tema,
            dificuldade,
            enunciado,
            alternativas,
            indice_correto,
            explicacao,
            feedback_acerto,
            feedback_erro,
        )
        questao = self.repositorio.atualizar_questao(questao_id, dados)
        self.repositorio.registrar_evento(
            professor.perfil,
            "QUESTAO_ATUALIZADA",
            "QUESTOES",
            professor.id,
            questao.id,
        )
        return questao

    def alternar_questao(self, questao_id):
        professor = self._professor()
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is None:
            raise ErroDominio("Questão não encontrada.")
        questao = self.repositorio.definir_questao_ativa(questao.id, not questao.ativa)
        self.repositorio.registrar_evento(
            professor.perfil,
            "QUESTAO_ATUALIZADA",
            "QUESTOES",
            professor.id,
            questao.id,
        )
        return questao

    def excluir_questao(self, questao_id):
        professor = self._professor()
        self.repositorio.excluir_questao(questao_id)
        self.repositorio.registrar_evento(
            professor.perfil,
            "QUESTAO_EXCLUIDA",
            "QUESTOES",
            professor.id,
            int(questao_id),
        )

    def adaptar_questao(self, questao_id, dificuldade):
        professor = self._professor()
        original = self.repositorio.buscar_questao(questao_id)
        if original is None:
            raise ErroDominio("Questão não encontrada.")
        dados = self.gemini.adaptar_questao(original, dificuldade)
        adaptada = self.salvar_questao_gerada(original.tema, dificuldade, dados)
        self.repositorio.registrar_evento(
            professor.perfil,
            "IA_QUESTAO_ADAPTADA",
            "GEMINI",
            professor.id,
            adaptada.id,
        )
        return adaptada

    def gerar_narracao(self, questao_id):
        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre para utilizar a narração.")
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is None or (usuario.eh_aluno and not questao.ativa):
            raise ErroDominio("Questão não encontrada.")
        audio, tipo = self.gemini.gerar_narracao(questao)
        self.repositorio.registrar_evento(
            usuario.perfil, "IA_NARRACAO", "GEMINI", usuario.id, questao.id
        )
        return audio, tipo
