"""Fachada de persistência que compõe repositórios especializados."""

from backend.taskflow.dominio import ErroDominio
from backend.taskflow.seguranca import criar_hash
from banco_de_dados.persistencia.auditoria import RepositorioAuditoria
from banco_de_dados.persistencia.base import RepositorioBase
from banco_de_dados.persistencia.desempenho import RepositorioDesempenho
from banco_de_dados.persistencia.erros import ProfessorJaExiste
from banco_de_dados.persistencia.infraestrutura import InfraestruturaBanco
from banco_de_dados.persistencia.questoes import RepositorioQuestoes
from banco_de_dados.persistencia.recuperacao import RepositorioRecuperacao
from banco_de_dados.persistencia.salas import RepositorioSalas
from banco_de_dados.persistencia.usuarios import RepositorioUsuarios
from banco_de_dados.persistencia.verificacao_cadastro import RepositorioVerificacaoCadastro


VERSAO_DOCUMENTOS_LEGAIS = "2026-11-v6"


class RepositorioTaskFlow(RepositorioBase):
    def __init__(self, caminho, chave_dados=None, configuracao_mysql=None, postgres_url=None):
        super().__init__(InfraestruturaBanco(
            caminho, chave_dados, configuracao_mysql, postgres_url
        ))
        self.auditoria = RepositorioAuditoria(self._infraestrutura)
        self.auditoria.limpar_eventos_expirados()
        self.usuarios = RepositorioUsuarios(self._infraestrutura, self.auditoria)
        self.verificacao_cadastro = RepositorioVerificacaoCadastro(self._infraestrutura, self.usuarios)
        self.recuperacao = RepositorioRecuperacao(self._infraestrutura, self.usuarios)
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

    def criar_aluno(self, nome, gmail, senha):
        return self.usuarios.criar_aluno(nome, gmail, senha)

    def buscar_usuario(self, usuario_id):
        return self.usuarios.buscar_usuario(usuario_id)

    def autenticar(self, perfil, identificador, senha):
        return self.usuarios.autenticar(perfil, identificador, senha)

    def listar_alunos(self, professor_id=None):
        return self.usuarios.listar_alunos(professor_id)

    def concluir_perfil_aluno(self, aluno_id, versao, nome, idade, codigo_sala, senha=None):
        """Compatibilidade com chamadas antigas que ainda informam um código de sala."""
        sala = self.salas.buscar_sala_multijogador(codigo_sala)
        if sala is None or not sala.chave_academica:
            raise ErroDominio("Sala não encontrada para esse código.")
        return self.concluir_perfil_aluno_classificacao(
            aluno_id, versao, nome, idade,
            sala.ano_escolar, sala.turma, sala.sala_escolar, senha,
        )

    def concluir_perfil_aluno_classificacao(
        self, aluno_id, versao, nome, idade, ano_escolar, turma, periodo, senha=None
    ):
        """Salva o perfil e o aceite em uma única transação."""
        senha_hash = criar_hash(senha) if senha is not None else None
        with self._bloqueio:
            self.conexao.execute("BEGIN IMMEDIATE")
            try:
                consulta = """SELECT id FROM usuarios WHERE id=? AND perfil='ALUNO'
                    AND ativo=1 AND versao_sessao=? AND anonimizado_em IS NULL"""
                if self.tipo_banco in {"mysql", "postgres"}:
                    consulta += " FOR UPDATE"
                if not self.conexao.execute(consulta, (aluno_id, versao)).fetchone():
                    raise ErroDominio("A sessão foi alterada. Entre novamente.")
                if self.salas.buscar_perfil_aluno(aluno_id):
                    raise ErroDominio("Seu perfil escolar já foi preenchido.")
                self.salas.salvar_perfil_aluno(
                    aluno_id,
                    idade,
                    ano_escolar,
                    turma,
                    periodo,
                    na_transacao=True,
                )
                self.conexao.execute(
                    """UPDATE usuarios SET nome=?, primeiro_acesso=0,
                    senha_hash=COALESCE(?, senha_hash), versao_sessao=versao_sessao+1
                    WHERE id=?""",
                    (self.criptografia.criptografar(nome), senha_hash, aluno_id),
                )
                if senha_hash is not None:
                    self.conexao.execute(
                        "DELETE FROM tokens_recuperacao WHERE usuario_id=?", (aluno_id,)
                    )
                self.conexao.execute("DELETE FROM aceites WHERE usuario_id=?", (aluno_id,))
                self.conexao.execute(
                    """INSERT INTO aceites(usuario_id,termos_versao,privacidade_versao,aceito_em)
                    VALUES(?,?,?,?)""",
                    (aluno_id, VERSAO_DOCUMENTOS_LEGAIS, VERSAO_DOCUMENTOS_LEGAIS, self._agora()),
                )
                self.conexao.commit()
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise
        return self.buscar_usuario(aluno_id)

    def definir_ativo(self, aluno_id, ativo):
        return self.usuarios.definir_ativo(aluno_id, ativo)

    def excluir_aluno(self, aluno_id):
        return self.usuarios.excluir_aluno(aluno_id)

    def definir_senha(self, usuario_id, senha, primeiro_acesso=False):
        return self.usuarios.definir_senha(usuario_id, senha, primeiro_acesso)

    def alterar_senha_titular(self, usuario_id, senha_atual, nova_senha):
        return self.usuarios.alterar_senha_titular(usuario_id, senha_atual, nova_senha)

    def definir_idade_professor(self, professor_id, idade):
        return self.usuarios.definir_idade_professor(professor_id, idade)

    def configurar_recuperacao_professor(self, professor_id, codigo):
        return self.usuarios.configurar_recuperacao_professor(professor_id, codigo)

    def professor_possui_recuperacao(self, professor_id):
        return self.usuarios.professor_possui_recuperacao(professor_id)

    def recuperar_senha_professor(self, email, codigo, nova_senha):
        return self.usuarios.recuperar_senha_professor(email, codigo, nova_senha)

    def registrar_aceite(
        self, usuario_id, termos=VERSAO_DOCUMENTOS_LEGAIS, privacidade=VERSAO_DOCUMENTOS_LEGAIS,
    ):
        return self.usuarios.registrar_aceite(usuario_id, termos, privacidade)

    def conferir_senha_usuario(self, usuario_id, senha):
        return self.usuarios.conferir_senha_usuario(usuario_id, senha)

    def anonimizar_usuario(self, usuario_id):
        return self.usuarios.anonimizar_usuario(usuario_id)

    def excluir_usuario_definitivamente(self, usuario_id):
        return self.usuarios.excluir_usuario_definitivamente(usuario_id)

    def registrar_evento(self, perfil, evento, recurso, ator_id=None, alvo_id=None):
        return self.auditoria.registrar_evento(perfil, evento, recurso, ator_id, alvo_id)

    def listar_eventos(self, limite=100, ator_id=None, *, incluir_sessoes_alunos=False):
        return self.auditoria.listar_eventos(
            limite, ator_id, incluir_sessoes_alunos=incluir_sessoes_alunos
        )

    def criar_questao(self, professor_id, dados):
        return self.questoes.criar_questao(professor_id, dados)

    def buscar_questao(self, questao_id):
        return self.questoes.buscar_questao(questao_id)

    def listar_questoes(self, somente_ativas=False):
        return self.questoes.listar_questoes(somente_ativas)

    def aderir_questao(self, questao_id, professor_id):
        return self.questoes.aderir_questao(questao_id, professor_id)

    def atualizar_questao(self, questao_id, dados):
        return self.questoes.atualizar_questao(questao_id, dados)

    def definir_questao_ativa(self, questao_id, ativa):
        return self.questoes.definir_questao_ativa(questao_id, ativa)

    def excluir_questao(self, questao_id):
        return self.questoes.excluir_questao(questao_id)

    def selecionar_questao(self, dificuldade=None, aluno_id=None, sala_id=None):
        return self.questoes.selecionar_questao(dificuldade, aluno_id, sala_id)

    def registrar_tentativa(self, aluno_id, questao, modo, indice_escolhido, correta, pontos):
        return self.desempenho.registrar_tentativa(
            aluno_id, questao, modo, indice_escolhido, correta, pontos
        )

    def desempenho_aluno(self, aluno_id, modo=None, sala_id=None):
        return self.desempenho.desempenho_aluno(aluno_id, modo, sala_id)

    def reiniciar_treino_bot(self, aluno_id):
        return self.desempenho.reiniciar_treino_bot(aluno_id)

    def acertos_recentes(self, aluno_id, limite=6, modo=None, sala_id=None):
        return self.desempenho.acertos_recentes(aluno_id, limite, modo, sala_id)

    def listar_desempenho_turma(self, filtros=None, professor_id=None):
        return self.desempenho.listar_desempenho_turma(filtros, professor_id)

    def listar_escolaridade_alunos(self):
        return self.desempenho.listar_escolaridade_alunos()

    def criar_sala_multijogador(self, codigo, nome, criador_id, questoes_ids, *classificacao):
        return self.salas.criar_sala_multijogador(
            codigo, nome, criador_id, questoes_ids, *classificacao
        )

    def listar_salas_professor(self, professor_id):
        return self.salas.listar_salas_professor(professor_id)

    def aderir_sala_multijogador(self, codigo, professor_id):
        return self.salas.aderir_sala_multijogador(codigo, professor_id)

    def questoes_ids_sala_multijogador(self, sala_id):
        return self.salas.questoes_ids_sala_multijogador(sala_id)

    def atualizar_sala_multijogador(self, sala_id, nome, questoes_ids, *classificacao):
        return self.salas.atualizar_sala_multijogador(sala_id, nome, questoes_ids, *classificacao)

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
