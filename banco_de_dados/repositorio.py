"""Fachada de persistência que compõe repositórios especializados."""

from banco_de_dados.persistencia.auditoria import RepositorioAuditoria
from banco_de_dados.persistencia.base import RepositorioBase
from banco_de_dados.persistencia.desempenho import RepositorioDesempenho
from banco_de_dados.persistencia.erros import ProfessorJaExiste
from banco_de_dados.persistencia.infraestrutura import InfraestruturaBanco
from banco_de_dados.persistencia.questoes import RepositorioQuestoes
from banco_de_dados.persistencia.salas import RepositorioSalas
from banco_de_dados.persistencia.usuarios import RepositorioUsuarios


class RepositorioTaskFlow(RepositorioBase):
    def __init__(self, caminho, chave_dados=None, configuracao_mysql=None):
        super().__init__(InfraestruturaBanco(caminho, chave_dados, configuracao_mysql))
        self.auditoria = RepositorioAuditoria(self._infraestrutura)
        self.usuarios = RepositorioUsuarios(self._infraestrutura, self.auditoria)
        self.questoes = RepositorioQuestoes(self._infraestrutura)
        self.desempenho = RepositorioDesempenho(self._infraestrutura)
        self.salas = RepositorioSalas(self._infraestrutura)

    def fechar(self):
        self._infraestrutura.fechar()

    def possui_professor(self):
        return self.usuarios.possui_professor()

    def criar_primeiro_professor(self, nome, email, senha):
        return self.usuarios.criar_primeiro_professor(nome, email, senha)

    def criar_usuario(self, perfil, nome, identificador, senha, primeiro_acesso=False):
        return self.usuarios.criar_usuario(perfil, nome, identificador, senha, primeiro_acesso)

    def criar_aluno(self, nome, matricula, senha):
        return self.usuarios.criar_aluno(nome, matricula, senha)

    def buscar_usuario(self, usuario_id):
        return self.usuarios.buscar_usuario(usuario_id)

    def autenticar(self, perfil, identificador, senha):
        return self.usuarios.autenticar(perfil, identificador, senha)

    def listar_alunos(self):
        return self.usuarios.listar_alunos()

    def definir_ativo(self, aluno_id, ativo):
        return self.usuarios.definir_ativo(aluno_id, ativo)

    def excluir_aluno(self, aluno_id):
        return self.usuarios.excluir_aluno(aluno_id)

    def definir_senha(self, usuario_id, senha, primeiro_acesso=False):
        return self.usuarios.definir_senha(usuario_id, senha, primeiro_acesso)

    def configurar_recuperacao_professor(self, professor_id, codigo):
        return self.usuarios.configurar_recuperacao_professor(professor_id, codigo)

    def professor_possui_recuperacao(self, professor_id):
        return self.usuarios.professor_possui_recuperacao(professor_id)

    def recuperar_senha_professor(self, email, codigo, nova_senha):
        return self.usuarios.recuperar_senha_professor(email, codigo, nova_senha)

    def registrar_aceite(self, usuario_id, termos="2026-09-v2", privacidade="2026-09-v2"):
        return self.usuarios.registrar_aceite(usuario_id, termos, privacidade)

    def conferir_senha_usuario(self, usuario_id, senha):
        return self.usuarios.conferir_senha_usuario(usuario_id, senha)

    def anonimizar_usuario(self, usuario_id):
        return self.usuarios.anonimizar_usuario(usuario_id)

    def excluir_usuario_definitivamente(self, usuario_id):
        return self.usuarios.excluir_usuario_definitivamente(usuario_id)

    def registrar_evento(self, perfil, evento, recurso, ator_id=None, alvo_id=None):
        return self.auditoria.registrar_evento(perfil, evento, recurso, ator_id, alvo_id)

    def listar_eventos(self, limite=100):
        return self.auditoria.listar_eventos(limite)

    def criar_questao(self, professor_id, dados):
        return self.questoes.criar_questao(professor_id, dados)

    def buscar_questao(self, questao_id):
        return self.questoes.buscar_questao(questao_id)

    def listar_questoes(self, somente_ativas=False):
        return self.questoes.listar_questoes(somente_ativas)

    def atualizar_questao(self, questao_id, dados):
        return self.questoes.atualizar_questao(questao_id, dados)

    def definir_questao_ativa(self, questao_id, ativa):
        return self.questoes.definir_questao_ativa(questao_id, ativa)

    def excluir_questao(self, questao_id):
        return self.questoes.excluir_questao(questao_id)

    def selecionar_questao(self, dificuldade=None, aluno_id=None):
        return self.questoes.selecionar_questao(dificuldade, aluno_id)

    def registrar_tentativa(self, aluno_id, questao, modo, indice_escolhido, correta, pontos):
        return self.desempenho.registrar_tentativa(
            aluno_id, questao, modo, indice_escolhido, correta, pontos
        )

    def desempenho_aluno(self, aluno_id):
        return self.desempenho.desempenho_aluno(aluno_id)

    def acertos_recentes(self, aluno_id, limite=6):
        return self.desempenho.acertos_recentes(aluno_id, limite)

    def listar_desempenho_turma(self):
        return self.desempenho.listar_desempenho_turma()

    def criar_sala_multijogador(self, codigo, nome, criador_id, questoes_ids):
        return self.salas.criar_sala_multijogador(codigo, nome, criador_id, questoes_ids)

    def listar_salas_professor(self, professor_id):
        return self.salas.listar_salas_professor(professor_id)

    def questoes_ids_sala_multijogador(self, sala_id):
        return self.salas.questoes_ids_sala_multijogador(sala_id)

    def atualizar_sala_multijogador(self, sala_id, nome, questoes_ids):
        return self.salas.atualizar_sala_multijogador(sala_id, nome, questoes_ids)

    def excluir_sala_multijogador(self, sala_id):
        return self.salas.excluir_sala_multijogador(sala_id)

    def buscar_sala_multijogador(self, codigo):
        return self.salas.buscar_sala_multijogador(codigo)

    def entrar_sala_multijogador(self, sala_id, aluno_id):
        return self.salas.entrar_sala_multijogador(sala_id, aluno_id)

    def participante_na_sala(self, sala_id, aluno_id):
        return self.salas.participante_na_sala(sala_id, aluno_id)

    def participantes_multijogador(self, sala):
        return self.salas.participantes_multijogador(sala)

    def resposta_multijogador(self, sala, aluno_id):
        return self.salas.resposta_multijogador(sala, aluno_id)

    def registrar_resposta_multijogador(
        self, sala, aluno_id, questao, indice_escolhido, correta, pontos
    ):
        return self.salas.registrar_resposta_multijogador(
            sala, aluno_id, questao, indice_escolhido, correta, pontos
        )

    def avancar_rodada_multijogador(self, sala):
        return self.salas.avancar_rodada_multijogador(sala)


__all__ = ["RepositorioTaskFlow", "ProfessorJaExiste"]
