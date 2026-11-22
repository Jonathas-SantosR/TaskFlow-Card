import secrets
import sqlite3

from backend.taskflow.dominio import (
    EMAIL,
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
            versao_sessao=int(linha["versao_sessao"]),
            gmail_vinculado=bool(linha["chave_login_global"]),
            idade=int(linha["idade"]) if linha["idade"] is not None else None,
        )

    def _validar_gmail_disponivel(self, gmail, usuario_id=None):
        chave = self.criptografia.indice(gmail)
        conflito = self.conexao.execute(
            "SELECT 1 FROM conflitos_identidade WHERE chave_email=?", (chave,)
        ).fetchone()
        existente = self.conexao.execute(
            "SELECT id FROM usuarios WHERE chave_login_global=?", (chave,)
        ).fetchone()
        if conflito or (existente and existente["id"] != usuario_id):
            raise ErroDominio(
                "Este Gmail já está vinculado a uma conta. Entre nela ou recupere a senha."
            )
        return chave

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
        return self._criar_usuario(
            PERFIL_PROFESSOR, nome, email, senha, False, somente_primeiro=True
        )

    def criar_usuario(self, perfil, nome, identificador, senha, primeiro_acesso=False):
        """Persiste uma conta; a autorização para criá-la pertence ao serviço."""

        if perfil not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            raise ErroDominio("Perfil inválido.")
        return self._criar_usuario(perfil, nome, identificador, senha, primeiro_acesso)

    def _criar_usuario(
        self, perfil, nome, identificador, senha, primeiro_acesso, *, somente_primeiro=False
    ):
        nome = normalizar_nome(nome)
        identificador = normalizar_identificador(perfil, identificador)
        senha_hash = criar_hash(senha)
        try:
            with self._bloqueio, self.conexao:
                if perfil == PERFIL_PROFESSOR:
                    # Serializa o cadastro com a operação legada de criar só o primeiro.
                    if self.tipo_banco in {"mysql", "postgres"}:
                        self.conexao.execute(
                            "SELECT versao FROM versoes_esquema WHERE versao=1 FOR UPDATE"
                        ).fetchone()
                    elif not self.conexao.in_transaction:
                        self.conexao.execute("BEGIN IMMEDIATE")
                    if somente_primeiro and self.possui_professor():
                        raise ProfessorJaExiste("O primeiro professor já foi cadastrado.")
                chave_global = self._validar_gmail_disponivel(identificador)
                cursor = self.conexao.execute(
                    """INSERT INTO usuarios
                    (perfil,identificador,chave_identificador,nome,senha_hash,
                    criado_em,primeiro_acesso,chave_login_global) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        perfil,
                        self.criptografia.criptografar(identificador),
                        self.criptografia.indice(identificador),
                        self.criptografia.criptografar(nome),
                        senha_hash,
                        self._agora(),
                        1 if primeiro_acesso else 0,
                        chave_global,
                    ),
                )
        except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
            raise ErroDominio("Este Gmail já está vinculado a uma conta.") from erro
        return self.buscar_usuario(cursor.lastrowid)

    def criar_aluno(self, nome, gmail, senha):
        return self.criar_usuario(PERFIL_ALUNO, nome, gmail, senha, primeiro_acesso=True)

    def buscar_usuario(self, usuario_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                "SELECT * FROM usuarios WHERE id=?", (int(usuario_id),)
            ).fetchone()
        return self._usuario(linha) if linha else None

    def _linha_por_login(self, perfil, identificador):
        if perfil not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            return None
        try:
            identificador = normalizar_identificador(perfil, identificador)
        except ErroDominio:
            # Compatibilidade limitada ao professor anterior à exigência de Gmail.
            # Matrículas de aluno e perfis descontinuados nunca são aceitos aqui.
            if (
                perfil != PERFIL_PROFESSOR
                or not isinstance(identificador, str)
                or len(identificador.strip()) > 254
                or EMAIL.fullmatch(identificador.strip()) is None
            ):
                return None
            consulta = """SELECT * FROM usuarios
                WHERE perfil='PROFESSOR' AND chave_identificador=?
                AND chave_login_global IS NULL AND ativo=1 AND anonimizado_em IS NULL"""
        else:
            consulta = """SELECT * FROM usuarios
                WHERE perfil=? AND chave_login_global=? AND ativo=1
                AND anonimizado_em IS NULL"""
            with self._bloqueio:
                return self.conexao.execute(
                    consulta, (perfil, self.criptografia.indice(identificador))
                ).fetchone()
        with self._bloqueio:
            return self.conexao.execute(
                consulta, (self.criptografia.indice(identificador),)
            ).fetchone()

    def buscar_por_login(self, perfil, identificador):
        linha = self._linha_por_login(perfil, identificador)
        return self._usuario(linha) if linha else None

    def autenticar(self, perfil, identificador, senha):
        # A busca da conta ativa pelo perfil precede a verificação da senha pelo hash.
        linha = self._linha_por_login(perfil, identificador)
        if linha is None or not conferir_senha(senha, linha["senha_hash"]):
            return None
        return self._usuario(linha)

    def vincular_gmail(self, usuario_id, email, senha_atual):
        """Migra a própria conta após conferir sua senha, preservando ID e progresso."""
        with self._bloqueio:
            try:
                self.conexao.execute("BEGIN IMMEDIATE")
                consulta = """SELECT * FROM usuarios WHERE id=? AND ativo=1
                    AND anonimizado_em IS NULL AND perfil IN ('PROFESSOR','ALUNO')"""
                if self.tipo_banco in {"mysql", "postgres"}:
                    consulta += " FOR UPDATE"
                linha = self.conexao.execute(consulta, (int(usuario_id),)).fetchone()
                if linha is None or not conferir_senha(senha_atual, linha["senha_hash"]):
                    raise ErroDominio("Conta ou senha atual inválida.")
                gmail = normalizar_identificador(linha["perfil"], email)
                chave = self._validar_gmail_disponivel(gmail, int(usuario_id))
                if linha["chave_login_global"] != chave:
                    self.conexao.execute(
                        """UPDATE usuarios SET identificador_legado=COALESCE(identificador_legado,identificador),
                        identificador=?,chave_identificador=?,chave_login_global=?,
                        versao_sessao=versao_sessao+1 WHERE id=?""",
                        (self.criptografia.criptografar(gmail), chave, chave, int(usuario_id)),
                    )
                    self.conexao.execute(
                        """UPDATE tokens_recuperacao SET usado_em=?
                        WHERE usuario_id=? AND usado_em IS NULL""",
                        (self._agora(), int(usuario_id)),
                    )
                self.conexao.commit()
            except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise ErroDominio("Este Gmail já está vinculado a uma conta.") from erro
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise
        return self.buscar_usuario(usuario_id)

    def listar_alunos(self, professor_id=None):
        consulta = """SELECT u.* FROM usuarios u
            WHERE u.perfil='ALUNO' AND u.anonimizado_em IS NULL"""
        parametros = ()
        if professor_id is not None:
            consulta += """ AND EXISTS (
                SELECT 1 FROM perfil_aluno p
                JOIN salas_multijogador s ON s.chave_academica=p.chave_academica
                WHERE p.aluno_id=u.id AND s.criador_id=?
            )"""
            parametros = (int(professor_id),)
        consulta += " ORDER BY u.id DESC"
        with self._bloqueio:
            linhas = self.conexao.execute(consulta, parametros).fetchall()
        return [self._usuario(linha) for linha in linhas]

    def definir_ativo(self, aluno_id, ativo):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """UPDATE usuarios SET ativo=?, versao_sessao=versao_sessao+1
                WHERE id=? AND perfil='ALUNO' AND anonimizado_em IS NULL""",
                (1 if ativo else 0, int(aluno_id)),
            )
            if cursor.rowcount == 1:
                self.conexao.execute(
                    """UPDATE tokens_recuperacao SET usado_em=?
                    WHERE usuario_id=? AND usado_em IS NULL""",
                    (self._agora(), int(aluno_id)),
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
        self.conexao.execute("DELETE FROM emails_recuperacao WHERE usuario_id=?", (usuario_id,))
        self.conexao.execute("DELETE FROM tokens_recuperacao WHERE usuario_id=?", (usuario_id,))
        self.conexao.execute("DELETE FROM perfil_aluno WHERE aluno_id=?", (usuario_id,))
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
                """UPDATE usuarios SET senha_hash=?, primeiro_acesso=?,
                versao_sessao=versao_sessao+1 WHERE id=?""",
                (senha_hash, 1 if primeiro_acesso else 0, int(usuario_id)),
            )
            if cursor.rowcount == 1:
                self.conexao.execute(
                    """UPDATE tokens_recuperacao SET usado_em=?
                    WHERE usuario_id=? AND usado_em IS NULL""",
                    (self._agora(), int(usuario_id)),
                )
        if cursor.rowcount != 1:
            raise ErroDominio("Usuário não encontrado.")
        return self.buscar_usuario(usuario_id)

    def alterar_senha_titular(self, usuario_id, senha_atual, nova_senha):
        senha_hash = criar_hash(nova_senha)
        with self._bloqueio:
            self.conexao.execute("BEGIN IMMEDIATE")
            try:
                consulta = """SELECT senha_hash FROM usuarios WHERE id=? AND ativo=1
                    AND anonimizado_em IS NULL AND perfil IN ('PROFESSOR','ALUNO')"""
                if self.tipo_banco in {"mysql", "postgres"}:
                    consulta += " FOR UPDATE"
                linha = self.conexao.execute(consulta, (int(usuario_id),)).fetchone()
                if linha is None or not conferir_senha(senha_atual, linha["senha_hash"]):
                    raise ErroDominio("Senha atual incorreta.")
                if conferir_senha(nova_senha, linha["senha_hash"]):
                    raise ErroDominio("Escolha uma senha diferente da atual.")
                self.conexao.execute(
                    """UPDATE usuarios SET senha_hash=?,versao_sessao=versao_sessao+1
                    WHERE id=?""",
                    (senha_hash, int(usuario_id)),
                )
                self.conexao.execute(
                    """UPDATE tokens_recuperacao SET usado_em=?
                    WHERE usuario_id=? AND usado_em IS NULL""",
                    (self._agora(), int(usuario_id)),
                )
                self.conexao.commit()
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise
        return self.buscar_usuario(usuario_id)

    def definir_idade_professor(self, professor_id, idade):
        with self._bloqueio, self.conexao:
            self.conexao.execute(
                """UPDATE usuarios SET idade=? WHERE id=? AND perfil='PROFESSOR'
                AND ativo=1 AND anonimizado_em IS NULL""",
                (int(idade), int(professor_id)),
            )
        professor = self.buscar_usuario(professor_id)
        if professor is None or not professor.eh_professor or not professor.ativo:
            raise ErroDominio("Professor não encontrado.")
        return professor

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
                ativo=0, primeiro_acesso=0, recuperacao_hash=NULL, idade=NULL, anonimizado_em=?,
                chave_login_global=NULL, identificador_legado=NULL,
                versao_sessao=versao_sessao+1
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
        # Os vínculos pessoais e a conta são removidos na mesma transação.
        usuario_id = int(usuario_id)
        with self._bloqueio, self.conexao:
            self._remover_vinculos_pessoais(usuario_id)
            cursor = self.conexao.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
            if cursor.rowcount != 1:
                raise ErroDominio("Usuário não encontrado.")
