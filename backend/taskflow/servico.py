"""Fachada de compatibilidade; os casos de uso vivem em servicos/."""

from backend.taskflow.servicos.base import ContextoServico, ServicoBase
from backend.taskflow.servicos.contas import ServicoContas
from backend.taskflow.servicos.desempenho import ServicoDesempenho
from backend.taskflow.servicos.jogos import ServicoJogos
from backend.taskflow.servicos.questoes import ServicoQuestoes
from backend.taskflow.servicos.salas import ServicoSalas


class ServicoTaskFlow(ServicoBase):
    """Compõe serviços especializados e preserva a API utilizada pelas telas."""

    def __init__(self, repositorio, gemini, tentativas=None, codigo_configuracao_professor=""):
        super().__init__(
            ContextoServico(
                repositorio,
                gemini,
                tentativas if tentativas is not None else {},
                str(codigo_configuracao_professor or "").strip(),
            )
        )
        self.contas = ServicoContas(self._contexto)
        self.questoes = ServicoQuestoes(self._contexto)
        self.jogos = ServicoJogos(self._contexto)
        self.salas = ServicoSalas(self._contexto)
        self.desempenho = ServicoDesempenho(self._contexto)

    def buscar_aluno(self, aluno_id):
        return self.contas.buscar_aluno(aluno_id)

    def buscar_questao(self, questao_id):
        return self.questoes.buscar_questao(questao_id)

    @property
    def primeiro_acesso(self):
        return self.contas.primeiro_acesso

    def criar_primeiro_professor(
        self, nome, email, senha, confirmacao, aceitou, codigo_configuracao=""
    ):
        return self.contas.criar_primeiro_professor(
            nome, email, senha, confirmacao, aceitou, codigo_configuracao
        )

    def criar_conta(
        self, perfil, nome, identificador, senha, confirmacao, aceitou, codigo_configuracao=""
    ):
        return self.contas.criar_conta(
            perfil, nome, identificador, senha, confirmacao, aceitou, codigo_configuracao
        )

    def login(self, perfil, identificador, senha):
        return self.contas.login(perfil, identificador, senha)

    def logout(self):
        return self.contas.logout()

    def alterar_senha_primeiro_acesso(self, senha, confirmacao, aceitou):
        return self.contas.alterar_senha_primeiro_acesso(senha, confirmacao, aceitou)

    def configurar_recuperacao(self, codigo, confirmacao):
        return self.contas.configurar_recuperacao(codigo, confirmacao)

    def recuperacao_configurada(self):
        return self.contas.recuperacao_configurada()

    def recuperar_senha_professor(self, email, codigo, senha, confirmacao):
        return self.contas.recuperar_senha_professor(email, codigo, senha, confirmacao)

    def listar_alunos(self):
        return self.contas.listar_alunos()

    def criar_aluno(self, nome, matricula, senha, confirmacao):
        return self.contas.criar_aluno(nome, matricula, senha, confirmacao)

    def alternar_aluno(self, aluno_id):
        return self.contas.alternar_aluno(aluno_id)

    def excluir_aluno(self, aluno_id):
        return self.contas.excluir_aluno(aluno_id)

    def redefinir_senha_aluno(self, aluno_id, senha, confirmacao):
        return self.contas.redefinir_senha_aluno(aluno_id, senha, confirmacao)

    def listar_auditoria(self):
        return self.contas.listar_auditoria()

    def encerrar_conta(self, modo, senha, confirmacao):
        return self.contas.encerrar_conta(modo, senha, confirmacao)

    def gerar_questao(self, tema, dificuldade):
        return self.questoes.gerar_questao(tema, dificuldade)

    def listar_questoes(self):
        return self.questoes.listar_questoes()

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
        return self.questoes.criar_questao(
            tema,
            dificuldade,
            enunciado,
            alternativas,
            indice_correto,
            explicacao,
            feedback_acerto,
            feedback_erro,
        )

    def salvar_questao_gerada(self, tema, dificuldade, questao):
        return self.questoes.salvar_questao_gerada(tema, dificuldade, questao)

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
        return self.questoes.atualizar_questao(
            questao_id,
            tema,
            dificuldade,
            enunciado,
            alternativas,
            indice_correto,
            explicacao,
            feedback_acerto,
            feedback_erro,
        )

    def alternar_questao(self, questao_id):
        return self.questoes.alternar_questao(questao_id)

    def excluir_questao(self, questao_id):
        return self.questoes.excluir_questao(questao_id)

    def adaptar_questao(self, questao_id, dificuldade):
        return self.questoes.adaptar_questao(questao_id, dificuldade)

    def gerar_narracao(self, questao_id):
        return self.questoes.gerar_narracao(questao_id)

    def proxima_questao(self, modo):
        return self.jogos.proxima_questao(modo)

    def responder_questao(self, questao_id, indice_escolhido, modo):
        return self.jogos.responder_questao(questao_id, indice_escolhido, modo)

    def criar_sala_multijogador(self, nome, questoes_ids):
        return self.salas.criar_sala_multijogador(nome, questoes_ids)

    def listar_salas_professor(self):
        return self.salas.listar_salas_professor()

    def dados_sala_professor(self, codigo):
        return self.salas.dados_sala_professor(codigo)

    def atualizar_sala_multijogador(self, codigo, nome, questoes_ids):
        return self.salas.atualizar_sala_multijogador(codigo, nome, questoes_ids)

    def excluir_sala_multijogador(self, codigo):
        return self.salas.excluir_sala_multijogador(codigo)

    def entrar_sala_multijogador(self, codigo):
        return self.salas.entrar_sala_multijogador(codigo)

    def estado_sala_multijogador(self, codigo):
        return self.salas.estado_sala_multijogador(codigo)

    def responder_sala_multijogador(self, codigo, indice_escolhido):
        return self.salas.responder_sala_multijogador(codigo, indice_escolhido)

    def avancar_rodada_multijogador(self, codigo):
        return self.salas.avancar_rodada_multijogador(codigo)

    def meu_desempenho(self):
        return self.desempenho.meu_desempenho()

    def desempenho_turma(self):
        return self.desempenho.desempenho_turma()

    def dashboard_pedagogica(self):
        return self.desempenho.dashboard_pedagogica()
