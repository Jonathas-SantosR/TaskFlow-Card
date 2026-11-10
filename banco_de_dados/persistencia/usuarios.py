import secrets
import sqlite3

from backend.taskflow.dominio import (
    PERFIL_ALUNO,
    PERFIL_PROFESSOR,
    ErroDominio,
    Usuario,
    normalizar_identificador,
    normalizar_nome,
)
from backend.taskflow.seguranca import conferir_senha, criar_hash
from banco_de_dados.banco import ErroIntegridadeBanco
from banco_de_dados.persistencia.base import RepositorioBase
from banco_de_dados.persistencia.erros import ProfessorJaExiste


class RepositorioUsuarios(RepositorioBase):
    def __init__(self, infraestrutura, auditoria):
        super().__init__(infraestrutura)
        self._auditoria = auditoria

    def _usuario(self, linha):
        return Usuario(
            id=linha["id"],
            perfil=linha["perfil"],
            identificador=self.criptografia.descriptografar(linha["identificador"]),
            nome=self.criptografia.descriptografar(linha["nome"]),
            ativo=bool(linha["ativo"]),
            criado_em=linha["criado_em"],
            primeiro_acesso=bool(linha["primeiro_acesso"]),
            anonimizado_em=linha["anonimizado_em"],
        )

    def possui_professor(self):
        with self._bloqueio:
            return (
                self.conexao.execute(
                    """SELECT 1 FROM usuarios
                WHERE perfil='PROFESSOR' AND anonimizado_em IS NULL LIMIT 1"""
                ).fetchone()
                is not None
            )

    def criar_primeiro_professor(self, nome, email, senha):
        nome = normalizar_nome(nome)
        email = normalizar_identificador(PERFIL_PROFESSOR, email)
        senha_hash = criar_hash(senha)
        with self._bloqueio:
            try:
                self.conexao.execute("BEGIN IMMEDIATE")
                if self.conexao.execute(
                    """SELECT 1 FROM usuarios
                    WHERE perfil='PROFESSOR' AND anonimizado_em IS NULL LIMIT 1"""
                ).fetchone():
                    raise ProfessorJaExiste("O primeiro professor já foi cadastrado.")
                cursor = self.conexao.execute(
                    """INSERT INTO usuarios
                    (perfil,identificador,chave_identificador,nome,senha_hash,criado_em)
                    VALUES(?,?,?,?,?,?)""",
                    (
                        PERFIL_PROFESSOR,
                        self.criptografia.criptografar(email),
                        self.criptografia.indice(email),
                        self.criptografia.criptografar(nome),
                        senha_hash,
                        self._agora(),
                    ),
                )
                self.conexao.commit()
            except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise ProfessorJaExiste("O primeiro professor já foi cadastrado.") from erro
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise
        return self.buscar_usuario(cursor.lastrowid)

    def criar_usuario(self, perfil, nome, identificador, senha, primeiro_acesso=False):
        """Cria uma conta individual para professor ou aluno."""

        if perfil not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            raise ErroDominio("Perfil inválido.")
        nome = normalizar_nome(nome)
        identificador = normalizar_identificador(perfil, identificador)
        try:
            with self._bloqueio, self.conexao:
                cursor = self.conexao.execute(
                    """INSERT INTO usuarios
                    (perfil,identificador,chave_identificador,nome,senha_hash,
                    criado_em,primeiro_acesso) VALUES(?,?,?,?,?,?,?)""",
                    (
                        perfil,
                        self.criptografia.criptografar(identificador),
                        self.criptografia.indice(identificador),
                        self.criptografia.criptografar(nome),
                        criar_hash(senha),
                        self._agora(),
                        1 if primeiro_acesso else 0,
                    ),
                )
        except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
            mensagem = (
                "Já existe um professor com esse e-mail."
                if perfil == PERFIL_PROFESSOR
                else "Já existe um aluno com essa matrícula."
            )
            raise ErroDominio(mensagem) from erro
        return self.buscar_usuario(cursor.lastrowid)

    def criar_aluno(self, nome, matricula, senha):
        return self.criar_usuario(PERFIL_ALUNO, nome, matricula, senha, primeiro_acesso=True)

    def buscar_usuario(self, usuario_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                "SELECT * FROM usuarios WHERE id=?", (int(usuario_id),)
            ).fetchone()
        return self._usuario(linha) if linha else None

    def autenticar(self, perfil, identificador, senha):
        try:
            identificador = normalizar_identificador(perfil, identificador)
        except ErroDominio:
            return None
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT * FROM usuarios
                WHERE perfil=? AND chave_identificador=? AND ativo=1
                AND anonimizado_em IS NULL""",
                (perfil, self.criptografia.indice(identificador)),
            ).fetchone()
        if linha is None or not conferir_senha(senha, linha["senha_hash"]):
            return None
        return self._usuario(linha)

    def listar_alunos(self):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT * FROM usuarios
                WHERE perfil='ALUNO' AND anonimizado_em IS NULL ORDER BY id DESC"""
            ).fetchall()
        return [self._usuario(linha) for linha in linhas]

    def definir_ativo(self, aluno_id, ativo):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """UPDATE usuarios SET ativo=?
                WHERE id=? AND perfil='ALUNO' AND anonimizado_em IS NULL""",
                (1 if ativo else 0, int(aluno_id)),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Aluno não encontrado.")
        return self.buscar_usuario(aluno_id)

    def _remover_vinculos_pessoais(self, usuario_id):
        """Desvincula dados pessoais antes de anonimizar ou excluir uma conta."""

        usuario_id = int(usuario_id)
        eventos_afetados = [
            linha["id"]
            for linha in self.conexao.execute(
                "SELECT id FROM auditoria WHERE ator_id=? OR alvo_id=?",
                (usuario_id, usuario_id),
            ).fetchall()
        ]
        self.conexao.execute("DELETE FROM aceites WHERE usuario_id=?", (usuario_id,))
        self.conexao.execute(
            """UPDATE auditoria SET
            ator_id=CASE WHEN ator_id=? THEN NULL ELSE ator_id END,
            alvo_id=CASE WHEN alvo_id=? THEN NULL ELSE alvo_id END""",
            (usuario_id, usuario_id),
        )
        self._auditoria.reassinar_eventos(eventos_afetados)
        self.conexao.execute("UPDATE tentativas SET aluno_id=NULL WHERE aluno_id=?", (usuario_id,))
        self.conexao.execute(
            "UPDATE questoes SET professor_id=NULL WHERE professor_id=?", (usuario_id,)
        )
        self.conexao.execute(
            "UPDATE salas_multijogador SET criador_id=NULL WHERE criador_id=?",
            (usuario_id,),
        )
        self.conexao.execute("DELETE FROM respostas_multijogador WHERE aluno_id=?", (usuario_id,))
        self.conexao.execute(
            "DELETE FROM participantes_multijogador WHERE aluno_id=?", (usuario_id,)
        )

    def excluir_aluno(self, aluno_id):
        with self._bloqueio, self.conexao:
            linha = self.conexao.execute(
                "SELECT id FROM usuarios WHERE id=? AND perfil='ALUNO'",
                (int(aluno_id),),
            ).fetchone()
            if linha is None:
                raise ErroDominio("Aluno não encontrado.")
            self._remover_vinculos_pessoais(aluno_id)
            cursor = self.conexao.execute(
                "DELETE FROM usuarios WHERE id=? AND perfil='ALUNO'", (int(aluno_id),)
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Aluno não encontrado.")

    def definir_senha(self, usuario_id, senha, primeiro_acesso=False):
        senha_hash = criar_hash(senha)
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                "UPDATE usuarios SET senha_hash=?, primeiro_acesso=? WHERE id=?",
                (senha_hash, 1 if primeiro_acesso else 0, int(usuario_id)),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Usuário não encontrado.")
        return self.buscar_usuario(usuario_id)

    def configurar_recuperacao_professor(self, professor_id, codigo):
        codigo_hash = criar_hash(codigo)
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """UPDATE usuarios SET recuperacao_hash=?
                WHERE id=? AND perfil='PROFESSOR'""",
                (codigo_hash, int(professor_id)),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Professor não encontrado.")

    def professor_possui_recuperacao(self, professor_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT recuperacao_hash FROM usuarios
                WHERE id=? AND perfil='PROFESSOR'""",
                (int(professor_id),),
            ).fetchone()
        return bool(linha and linha["recuperacao_hash"])

    def recuperar_senha_professor(self, email, codigo, nova_senha):
        email = normalizar_identificador(PERFIL_PROFESSOR, email)
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT id, recuperacao_hash FROM usuarios
                WHERE perfil='PROFESSOR' AND chave_identificador=? AND ativo=1
                AND anonimizado_em IS NULL""",
                (self.criptografia.indice(email),),
            ).fetchone()
        if linha is None or not linha["recuperacao_hash"]:
            raise ErroDominio("Recuperação ainda não configurada para este professor.")
        if not conferir_senha(codigo, linha["recuperacao_hash"]):
            raise ErroDominio("E-mail ou código de recuperação inválido.")
        return self.definir_senha(linha["id"], nova_senha)

    def registrar_aceite(
        self,
        usuario_id,
        termos="2026-09-v2",
        privacidade="2026-09-v2",
    ):
        if self.tipo_banco == "mysql":
            consulta = """INSERT INTO aceites
                (usuario_id,termos_versao,privacidade_versao,aceito_em)
                VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE
                termos_versao=VALUES(termos_versao),
                privacidade_versao=VALUES(privacidade_versao),
                aceito_em=VALUES(aceito_em)"""
        else:
            consulta = """INSERT INTO aceites
                (usuario_id,termos_versao,privacidade_versao,aceito_em)
                VALUES(?,?,?,?) ON CONFLICT(usuario_id) DO UPDATE SET
                termos_versao=excluded.termos_versao,
                privacidade_versao=excluded.privacidade_versao,
                aceito_em=excluded.aceito_em"""
        with self._bloqueio, self.conexao:
            self.conexao.execute(consulta, (int(usuario_id), termos, privacidade, self._agora()))

    def conferir_senha_usuario(self, usuario_id, senha):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT senha_hash FROM usuarios
                WHERE id=? AND ativo=1 AND anonimizado_em IS NULL""",
                (int(usuario_id),),
            ).fetchone()
        return bool(linha and conferir_senha(senha, linha["senha_hash"]))

    def anonimizar_usuario(self, usuario_id):
        """Remove irreversivelmente os identificadores, mantendo só a conta anônima."""

        usuario_id = int(usuario_id)
        marcador = f"anonimo-{secrets.token_urlsafe(18)}"
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """UPDATE usuarios SET
                identificador=?, chave_identificador=?, nome=?, senha_hash=?,
                ativo=0, primeiro_acesso=0, recuperacao_hash=NULL, anonimizado_em=?
                WHERE id=? AND anonimizado_em IS NULL""",
                (
                    self.criptografia.criptografar(marcador),
                    self.criptografia.indice(marcador),
                    self.criptografia.criptografar("Usuário anonimizado"),
                    criar_hash(secrets.token_urlsafe(48)),
                    self._agora(),
                    usuario_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ErroDominio("Usuário não encontrado.")
            self._remover_vinculos_pessoais(usuario_id)

    def excluir_usuario_definitivamente(self, usuario_id):
        """Apaga cadastro e aceite, retirando vínculos restantes da auditoria."""

        usuario_id = int(usuario_id)
        with self._bloqueio, self.conexao:
            self._remover_vinculos_pessoais(usuario_id)
            cursor = self.conexao.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
            if cursor.rowcount != 1:
                raise ErroDominio("Usuário não encontrado.")
