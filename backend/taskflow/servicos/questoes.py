from backend.taskflow.dominio import (
    NIVEIS_DIFICULDADE,
    AcessoNegado,
    ErroDominio,
    normalizar_questao,
)
from backend.taskflow.servicos.base import ServicoBase


class ServicoQuestoes(ServicoBase):
    def _questao_do_professor(self, questao_id, professor_id):
        # Editar, ativar ou excluir exige que a questão pertença ao professor.
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is None or questao.professor_id != professor_id:
            raise ErroDominio("Questão não encontrada.")
        return questao

    def buscar_questao(self, questao_id):
        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre para consultar questões.")
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is not None and usuario.eh_professor and questao.professor_id != usuario.id:
            return None
        if (
            questao is not None
            and usuario.eh_aluno
            and (not self.repositorio.salas.questao_autorizada_aluno(usuario.id, questao.id))
        ):
            return None
        return questao

    def gerar_questao(self, tema, dificuldade):
        professor = self._professor()
        # A geração retorna um rascunho. O professor salva a questão em outra ação.
        questao = self.gemini.gerar_questao(tema, dificuldade)
        self.repositorio.registrar_evento(professor.perfil, "IA_QUESTAO", "GEMINI", professor.id)
        return questao

    def listar_questoes(self):
        professor = self._professor()
        return [
            questao for questao in self.repositorio.listar_questoes()
            if questao.professor_id == professor.id
        ]

    def questoes_sem_professor(self):
        self._professor()
        return [
            questao for questao in self.repositorio.listar_questoes()
            if questao.professor_id is None
        ]

    def aderir_questao(self, questao_id):
        professor = self._professor()
        questao = self.repositorio.aderir_questao(questao_id, professor.id)
        self.repositorio.registrar_evento(
            professor.perfil, "QUESTAO_ADERIDA", "QUESTOES", professor.id, questao.id
        )
        return questao

    def painel_questoes(self, valores=None):
        """Seleciona as questões sem alterar os dados nem a dificuldade original."""

        valores = valores or {}
        filtros = {
            campo: str(valores.get(campo, "") or "").strip()
            for campo in ("tema", "dificuldade", "situacao")
        }
        filtros["dificuldade"] = filtros["dificuldade"].upper()
        filtros["situacao"] = filtros["situacao"].upper()
        if filtros["dificuldade"] and filtros["dificuldade"] not in NIVEIS_DIFICULDADE:
            raise ErroDominio("Dificuldade inválida.")
        if filtros["situacao"] and filtros["situacao"] not in {"ATIVA", "PAUSADA"}:
            raise ErroDominio("Situação da questão inválida.")
        todas = self.listar_questoes()
        questoes = [
            questao
            for questao in todas
            if (not filtros["tema"] or filtros["tema"].casefold() in questao.tema.casefold())
            and (not filtros["dificuldade"] or questao.dificuldade == filtros["dificuldade"])
            and (not filtros["situacao"] or questao.ativa == (filtros["situacao"] == "ATIVA"))
        ]
        return {
            "questoes": questoes,
            "filtros": filtros,
            "temas": sorted({questao.tema for questao in todas}, key=str.casefold),
            "total_questoes": len(todas),
        }

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
        # A autoria vem da sessão do professor após a validação dos campos.
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
        self._questao_do_professor(questao_id, professor.id)
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
        questao = self._questao_do_professor(questao_id, professor.id)
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
        self._questao_do_professor(questao_id, professor.id)
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
        original = self._questao_do_professor(questao_id, professor.id)
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
        questao = self.buscar_questao(questao_id)
        if questao is None:
            raise ErroDominio("Questão não encontrada.")
        audio, tipo = self.gemini.gerar_narracao(questao)
        self.repositorio.registrar_evento(
            usuario.perfil, "IA_NARRACAO", "GEMINI", usuario.id, questao.id
        )
        return audio, tipo
