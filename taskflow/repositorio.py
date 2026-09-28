"""Persistência do TaskFlowCards compatível com SQLite e MySQL."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import threading

from taskflow.banco import (
    ESQUEMA_MYSQL,
    ErroIntegridadeBanco,
    conectar_mysql,
)
from taskflow.criptografia import AssinadorAuditoria, CriptografiaDados
from taskflow.dominio import (
    ErroDominio,
    PERFIL_ALUNO,
    PERFIL_PROFESSOR,
    Desempenho,
    Questao,
    SalaMultijogador,
    Usuario,
    normalizar_identificador,
    normalizar_nome,
)
from taskflow.seguranca import conferir_senha, criar_hash


class ProfessorJaExiste(ErroDominio):
    pass


class RepositorioTaskFlow:
    """Centraliza SQL para que a interface nunca acesse tabelas diretamente."""

    def __init__(self, caminho, chave_dados=None, configuracao_mysql=None):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        self._bloqueio = threading.RLock()
        self.tipo_banco = "mysql" if configuracao_mysql else "sqlite"
        if self.tipo_banco == "mysql":
            self.conexao = conectar_mysql(configuracao_mysql)
            esquema = ESQUEMA_MYSQL
        else:
            self.conexao = sqlite3.connect(
                caminho, timeout=5, check_same_thread=False
            )
            self.conexao.row_factory = sqlite3.Row
            esquema = """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    perfil TEXT NOT NULL CHECK(perfil IN ('PROFESSOR','ALUNO')),
                    identificador TEXT NOT NULL,
                    chave_identificador TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    senha_hash TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    primeiro_acesso INTEGER NOT NULL DEFAULT 0,
                    recuperacao_hash TEXT,
                    UNIQUE(perfil, chave_identificador)
                );
                CREATE TABLE IF NOT EXISTS auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ocorrido_em TEXT NOT NULL,
                    ator_id INTEGER,
                    perfil TEXT NOT NULL,
                    evento TEXT NOT NULL,
                    recurso TEXT NOT NULL,
                    alvo_id INTEGER,
                    assinatura TEXT
                );
                CREATE TABLE IF NOT EXISTS aceites (
                    usuario_id INTEGER PRIMARY KEY,
                    termos_versao TEXT NOT NULL,
                    privacidade_versao TEXT NOT NULL,
                    aceito_em TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    professor_id INTEGER,
                    tema TEXT NOT NULL,
                    dificuldade TEXT NOT NULL,
                    enunciado TEXT NOT NULL,
                    alternativas_json TEXT NOT NULL,
                    indice_correto INTEGER NOT NULL,
                    explicacao TEXT NOT NULL,
                    feedback_acerto TEXT NOT NULL,
                    feedback_erro TEXT NOT NULL,
                    criada_em TEXT NOT NULL,
                    ativa INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS tentativas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER,
                    questao_id INTEGER,
                    modo TEXT NOT NULL,
                    dificuldade TEXT NOT NULL,
                    indice_escolhido INTEGER NOT NULL,
                    correta INTEGER NOT NULL,
                    pontos INTEGER NOT NULL,
                    respondida_em TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS salas_multijogador (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    criador_id INTEGER,
                    questao_id INTEGER NOT NULL,
                    rodada INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'ABERTA',
                    criada_em TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questoes_sala_multijogador (
                    sala_id INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    questao_id INTEGER NOT NULL,
                    PRIMARY KEY (sala_id, ordem),
                    UNIQUE (sala_id, questao_id)
                );
                CREATE TABLE IF NOT EXISTS participantes_multijogador (
                    sala_id INTEGER NOT NULL,
                    aluno_id INTEGER NOT NULL,
                    pontos INTEGER NOT NULL DEFAULT 0,
                    entrou_em TEXT NOT NULL,
                    PRIMARY KEY (sala_id, aluno_id)
                );
                CREATE TABLE IF NOT EXISTS respostas_multijogador (
                    sala_id INTEGER NOT NULL,
                    rodada INTEGER NOT NULL,
                    aluno_id INTEGER NOT NULL,
                    questao_id INTEGER NOT NULL,
                    indice_escolhido INTEGER NOT NULL,
                    correta INTEGER NOT NULL,
                    pontos INTEGER NOT NULL,
                    respondida_em TEXT NOT NULL,
                    PRIMARY KEY (sala_id, rodada, aluno_id)
                );
                CREATE INDEX IF NOT EXISTS idx_questoes_ativas
                ON questoes(ativa, dificuldade);
                CREATE INDEX IF NOT EXISTS idx_tentativas_aluno
                ON tentativas(aluno_id, respondida_em);
                CREATE INDEX IF NOT EXISTS idx_salas_multijogador_codigo
                ON salas_multijogador(codigo, status);
                CREATE INDEX IF NOT EXISTS idx_participantes_multijogador_aluno
                ON participantes_multijogador(aluno_id, sala_id);
            """
        with self.conexao:
            self.conexao.executescript(esquema)
            self._migrar_usuarios()
            self._migrar_salas_multijogador()
            self._migrar_auditoria()
        possui_dados_criptografados = self.conexao.execute(
            """SELECT 1 FROM usuarios
            WHERE identificador LIKE 'enc:v1:%' OR nome LIKE 'enc:v1:%'
            LIMIT 1"""
        ).fetchone() is not None
        self.criptografia = CriptografiaDados.carregar(
            caminho.parent / ".data_key",
            chave=chave_dados,
            permitir_criar=not possui_dados_criptografados,
        )
        self.assinador_auditoria = AssinadorAuditoria.carregar(
            caminho.parent / ".audit_private.pem"
        )
        self._migrar_dados_pessoais()

    def _migrar_usuarios(self):
        """Acrescenta recursos novos sem apagar contas de versões anteriores."""
        if self.tipo_banco == "mysql":
            colunas = {
                linha["Field"]
                for linha in self.conexao.execute("SHOW COLUMNS FROM usuarios").fetchall()
            }
        else:
            colunas = {
                linha["name"]
                for linha in self.conexao.execute(
                    "PRAGMA table_info(usuarios)"
                ).fetchall()
            }
        if "primeiro_acesso" not in colunas:
            self.conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN primeiro_acesso INTEGER NOT NULL DEFAULT 0"
            )
        if "recuperacao_hash" not in colunas:
            self.conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN recuperacao_hash TEXT"
            )
        if "anonimizado_em" not in colunas:
            self.conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN anonimizado_em TEXT"
            )
        if self.tipo_banco == "mysql" and "professor_unico" not in colunas:
            self.conexao.execute(
                """ALTER TABLE usuarios ADD COLUMN professor_unico TINYINT
                GENERATED ALWAYS AS (
                    CASE WHEN perfil='PROFESSOR' AND anonimizado_em IS NULL
                    THEN 1 ELSE NULL END
                ) STORED"""
            )
            self.conexao.execute(
                "CREATE UNIQUE INDEX uq_professor_ativo ON usuarios(professor_unico)"
            )

    def _migrar_salas_multijogador(self):
        """Mantém salas antigas utilizáveis após a inclusão da lista de questões."""

        if self.tipo_banco == "mysql":
            colunas = {
                linha["Field"]
                for linha in self.conexao.execute(
                    "SHOW COLUMNS FROM salas_multijogador"
                ).fetchall()
            }
        else:
            colunas = {
                linha["name"]
                for linha in self.conexao.execute(
                    "PRAGMA table_info(salas_multijogador)"
                ).fetchall()
            }
        if "nome" not in colunas:
            self.conexao.execute(
                "ALTER TABLE salas_multijogador "
                "ADD COLUMN nome VARCHAR(80) NOT NULL DEFAULT ''"
            )
        if self.tipo_banco == "mysql":
            self.conexao.execute(
                "UPDATE salas_multijogador SET nome=CONCAT('Sala ', codigo) "
                "WHERE nome=''"
            )
        else:
            self.conexao.execute(
                "UPDATE salas_multijogador SET nome='Sala ' || codigo WHERE nome=''"
            )

        self.conexao.execute(
            """INSERT OR IGNORE INTO questoes_sala_multijogador
            (sala_id,ordem,questao_id)
            SELECT id,rodada,questao_id FROM salas_multijogador"""
        )

    def _migrar_auditoria(self):
        """Acrescenta assinatura aos bancos criados antes da segunda versão."""
        if self.tipo_banco == "mysql":
            colunas = {
                linha["Field"]
                for linha in self.conexao.execute("SHOW COLUMNS FROM auditoria").fetchall()
            }
        else:
            colunas = {
                linha["name"]
                for linha in self.conexao.execute(
                    "PRAGMA table_info(auditoria)"
                ).fetchall()
            }
        if "assinatura" not in colunas:
            self.conexao.execute("ALTER TABLE auditoria ADD COLUMN assinatura TEXT")

    def _migrar_dados_pessoais(self):
        """Criptografa cadastros legados sem alterar IDs ou senhas."""

        with self._bloqueio, self.conexao:
            linhas = self.conexao.execute(
                "SELECT id, identificador, chave_identificador, nome FROM usuarios"
            ).fetchall()
            for linha in linhas:
                identificador = self.criptografia.descriptografar(
                    linha["identificador"]
                )
                nome = self.criptografia.descriptografar(linha["nome"])
                identificador_protegido = linha["identificador"]
                nome_protegido = linha["nome"]
                indice = self.criptografia.indice(identificador)
                if not self.criptografia.esta_criptografado(identificador_protegido):
                    identificador_protegido = self.criptografia.criptografar(
                        identificador
                    )
                if not self.criptografia.esta_criptografado(nome_protegido):
                    nome_protegido = self.criptografia.criptografar(nome)
                if (
                    identificador_protegido == linha["identificador"]
                    and nome_protegido == linha["nome"]
                    and indice == linha["chave_identificador"]
                ):
                    continue
                self.conexao.execute(
                    """UPDATE usuarios
                    SET identificador=?, chave_identificador=?, nome=?
                    WHERE id=?""",
                    (
                        identificador_protegido,
                        indice,
                        nome_protegido,
                        linha["id"],
                    ),
                )

    @staticmethod
    def _agora():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

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
            return self.conexao.execute(
                """SELECT 1 FROM usuarios
                WHERE perfil='PROFESSOR' AND anonimizado_em IS NULL LIMIT 1"""
            ).fetchone() is not None

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
                raise ProfessorJaExiste(
                    "O primeiro professor já foi cadastrado."
                ) from erro
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
        return self.criar_usuario(
            PERFIL_ALUNO, nome, matricula, senha, primeiro_acesso=True
        )

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
        self.conexao.execute(
            "DELETE FROM aceites WHERE usuario_id=?", (usuario_id,)
        )
        self.conexao.execute(
            """UPDATE auditoria SET
            ator_id=CASE WHEN ator_id=? THEN NULL ELSE ator_id END,
            alvo_id=CASE WHEN alvo_id=? THEN NULL ELSE alvo_id END""",
            (usuario_id, usuario_id),
        )
        self._reassinar_eventos(eventos_afetados)
        self.conexao.execute(
            "UPDATE tentativas SET aluno_id=NULL WHERE aluno_id=?", (usuario_id,)
        )
        self.conexao.execute(
            "UPDATE questoes SET professor_id=NULL WHERE professor_id=?", (usuario_id,)
        )
        self.conexao.execute(
            "UPDATE salas_multijogador SET criador_id=NULL WHERE criador_id=?",
            (usuario_id,),
        )
        self.conexao.execute(
            "DELETE FROM respostas_multijogador WHERE aluno_id=?", (usuario_id,)
        )
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
            self.conexao.execute(
                consulta, (int(usuario_id), termos, privacidade, self._agora())
            )

    @staticmethod
    def _campos_assinatura_evento(
        ocorrido_em, perfil, evento, recurso, ator_id=None, alvo_id=None
    ):
        return {
            "ocorrido_em": ocorrido_em,
            "ator_id": ator_id,
            "perfil": perfil,
            "evento": evento,
            "recurso": recurso,
            "alvo_id": alvo_id,
        }

    def _reassinar_eventos(self, eventos_ids):
        for evento_id in eventos_ids:
            linha = self.conexao.execute(
                """SELECT ocorrido_em,ator_id,perfil,evento,recurso,alvo_id
                FROM auditoria WHERE id=?""",
                (int(evento_id),),
            ).fetchone()
            if linha is None:
                continue
            campos = self._campos_assinatura_evento(
                linha["ocorrido_em"],
                linha["perfil"],
                linha["evento"],
                linha["recurso"],
                linha["ator_id"],
                linha["alvo_id"],
            )
            self.conexao.execute(
                "UPDATE auditoria SET assinatura=? WHERE id=?",
                (self.assinador_auditoria.assinar(campos), int(evento_id)),
            )

    def registrar_evento(self, perfil, evento, recurso, ator_id=None, alvo_id=None):
        permitidos = {
            "PRIMEIRO_PROFESSOR", "CONTA_CRIADA", "LOGIN_OK", "LOGIN_FALHOU", "LOGOUT",
            "ALUNO_CRIADO", "ALUNO_BLOQUEADO", "ALUNO_ATIVADO", "ALUNO_EXCLUIDO",
            "IA_QUESTAO", "SENHA_PRIMEIRO_ACESSO", "SENHA_ALUNO_REDEFINIDA",
            "RECUPERACAO_CONFIGURADA", "SENHA_PROFESSOR_RECUPERADA",
            "CONTA_ANONIMIZADA", "CONTA_EXCLUIDA",
            "QUESTAO_CRIADA", "QUESTAO_ATUALIZADA", "QUESTAO_EXCLUIDA",
            "IA_QUESTAO_ADAPTADA", "IA_NARRACAO", "RESPOSTA_REGISTRADA",
            "SALA_MULTIJOGADOR_CRIADA", "SALA_MULTIJOGADOR_EDITADA",
            "SALA_MULTIJOGADOR_EXCLUIDA", "SALA_MULTIJOGADOR_ENTRADA",
            "RESPOSTA_MULTIJOGADOR", "RODADA_MULTIJOGADOR_AVANCADA",
        }
        if evento not in permitidos:
            raise ValueError("Evento de auditoria inválido.")
        corte = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        ocorrido_em = self._agora()
        campos = self._campos_assinatura_evento(
            ocorrido_em, perfil, evento, recurso, ator_id, alvo_id
        )
        assinatura = self.assinador_auditoria.assinar(campos)
        with self._bloqueio, self.conexao:
            self.conexao.execute("DELETE FROM auditoria WHERE ocorrido_em < ?", (corte,))
            self.conexao.execute(
                """INSERT INTO auditoria
                (ocorrido_em,ator_id,perfil,evento,recurso,alvo_id,assinatura)
                VALUES(?,?,?,?,?,?,?)""",
                (ocorrido_em, ator_id, perfil, evento, recurso, alvo_id, assinatura),
            )

    def listar_eventos(self, limite=100):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT ocorrido_em,ator_id,perfil,evento,recurso,alvo_id,assinatura
                FROM auditoria ORDER BY id DESC LIMIT ?""",
                (min(max(int(limite), 1), 100),),
            ).fetchall()
        eventos = []
        for linha in linhas:
            campos = self._campos_assinatura_evento(
                linha["ocorrido_em"],
                linha["perfil"],
                linha["evento"],
                linha["recurso"],
                linha["ator_id"],
                linha["alvo_id"],
            )
            evento = dict(linha)
            evento.pop("assinatura", None)
            evento["integridade"] = self.assinador_auditoria.verificar(
                campos, linha["assinatura"]
            )
            eventos.append(evento)
        return eventos

    def conferir_senha_usuario(self, usuario_id, senha):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT senha_hash FROM usuarios
                WHERE id=? AND ativo=1 AND anonimizado_em IS NULL""",
                (int(usuario_id),),
            ).fetchone()
        return bool(linha and conferir_senha(senha, linha["senha_hash"]))

    @staticmethod
    def _questao(linha):
        if linha is None:
            return None
        alternativas = tuple(json.loads(linha["alternativas_json"]))
        return Questao(
            id=linha["id"],
            professor_id=linha["professor_id"],
            tema=linha["tema"],
            dificuldade=linha["dificuldade"],
            enunciado=linha["enunciado"],
            alternativas=alternativas,
            indice_correto=linha["indice_correto"],
            explicacao=linha["explicacao"],
            feedback_acerto=linha["feedback_acerto"],
            feedback_erro=linha["feedback_erro"],
            criada_em=linha["criada_em"],
            ativa=bool(linha["ativa"]),
        )

    @staticmethod
    def _sala_multijogador(linha):
        if linha is None:
            return None
        return SalaMultijogador(
            id=linha["id"],
            codigo=linha["codigo"],
            nome=linha["nome"],
            criador_id=linha["criador_id"],
            questao_id=linha["questao_id"],
            rodada=linha["rodada"],
            status=linha["status"],
            criada_em=linha["criada_em"],
        )

    def criar_questao(self, professor_id, dados):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """INSERT INTO questoes (
                    professor_id,tema,dificuldade,enunciado,alternativas_json,
                    indice_correto,explicacao,feedback_acerto,feedback_erro,
                    criada_em,ativa
                ) VALUES(?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    int(professor_id),
                    dados["tema"],
                    dados["dificuldade"],
                    dados["enunciado"],
                    json.dumps(dados["alternativas"], ensure_ascii=False),
                    dados["indice_correto"],
                    dados["explicacao"],
                    dados["feedback_acerto"],
                    dados["feedback_erro"],
                    self._agora(),
                ),
            )
        return self.buscar_questao(cursor.lastrowid)

    def buscar_questao(self, questao_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                "SELECT * FROM questoes WHERE id=?", (int(questao_id),)
            ).fetchone()
        return self._questao(linha)

    def listar_questoes(self, somente_ativas=False):
        consulta = "SELECT * FROM questoes"
        if somente_ativas:
            consulta += " WHERE ativa=1"
        consulta += " ORDER BY id DESC"
        with self._bloqueio:
            linhas = self.conexao.execute(consulta).fetchall()
        return [self._questao(linha) for linha in linhas]

    def atualizar_questao(self, questao_id, dados):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """UPDATE questoes SET
                    tema=?, dificuldade=?, enunciado=?, alternativas_json=?,
                    indice_correto=?, explicacao=?, feedback_acerto=?,
                    feedback_erro=?
                WHERE id=?""",
                (
                    dados["tema"],
                    dados["dificuldade"],
                    dados["enunciado"],
                    json.dumps(dados["alternativas"], ensure_ascii=False),
                    dados["indice_correto"],
                    dados["explicacao"],
                    dados["feedback_acerto"],
                    dados["feedback_erro"],
                    int(questao_id),
                ),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Questão não encontrada.")
        return self.buscar_questao(questao_id)

    def definir_questao_ativa(self, questao_id, ativa):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                "UPDATE questoes SET ativa=? WHERE id=?",
                (1 if ativa else 0, int(questao_id)),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Questão não encontrada.")
        return self.buscar_questao(questao_id)

    def excluir_questao(self, questao_id):
        with self._bloqueio, self.conexao:
            self.conexao.execute(
                """UPDATE salas_multijogador SET status='ENCERRADA'
                WHERE status='ABERTA' AND id IN (
                    SELECT sala_id FROM questoes_sala_multijogador
                    WHERE questao_id=?
                )""",
                (int(questao_id),),
            )
            self.conexao.execute(
                "DELETE FROM questoes_sala_multijogador WHERE questao_id=?",
                (int(questao_id),),
            )
            self.conexao.execute(
                "UPDATE tentativas SET questao_id=NULL WHERE questao_id=?",
                (int(questao_id),),
            )
            cursor = self.conexao.execute(
                "DELETE FROM questoes WHERE id=?", (int(questao_id),)
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Questão não encontrada.")

    def selecionar_questao(self, dificuldade=None, aluno_id=None):
        """Escolhe a questão menos recente, sem repetir enquanto houver outra."""

        if aluno_id is None:
            consulta = "SELECT * FROM questoes WHERE ativa=1"
            parametros = []
            if dificuldade:
                consulta += " AND dificuldade=?"
                parametros.append(dificuldade)
            consulta += " ORDER BY RANDOM() LIMIT 1"
        else:
            consulta = """SELECT q.* FROM questoes q
            LEFT JOIN (
                SELECT questao_id, MAX(id) AS ultima_tentativa
                FROM tentativas
                WHERE aluno_id=? AND modo='BOT' AND questao_id IS NOT NULL
                GROUP BY questao_id
            ) historico ON historico.questao_id=q.id
            WHERE q.ativa=1
            ORDER BY
                CASE WHEN historico.ultima_tentativa IS NULL THEN 0 ELSE 1 END,
                historico.ultima_tentativa ASC,
                CASE WHEN q.dificuldade=? THEN 0 ELSE 1 END,
                RANDOM()
            LIMIT 1"""
            parametros = [int(aluno_id), dificuldade or ""]
        with self._bloqueio:
            linha = self.conexao.execute(consulta, parametros).fetchone()
        return self._questao(linha)

    def registrar_tentativa(
        self,
        aluno_id,
        questao,
        modo,
        indice_escolhido,
        correta,
        pontos,
    ):
        with self._bloqueio, self.conexao:
            self.conexao.execute(
                """INSERT INTO tentativas (
                    aluno_id,questao_id,modo,dificuldade,indice_escolhido,
                    correta,pontos,respondida_em
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    int(aluno_id),
                    questao.id,
                    modo,
                    questao.dificuldade,
                    int(indice_escolhido),
                    1 if correta else 0,
                    int(pontos),
                    self._agora(),
                ),
            )

    def desempenho_aluno(self, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT COUNT(*) AS total, COALESCE(SUM(correta),0) AS acertos,
                COALESCE(SUM(pontos),0) AS pontos
                FROM tentativas WHERE aluno_id=?""",
                (int(aluno_id),),
            ).fetchone()
        return Desempenho(
            total=int(linha["total"]),
            acertos=int(linha["acertos"]),
            pontos=int(linha["pontos"]),
        )

    def acertos_recentes(self, aluno_id, limite=6):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT correta FROM tentativas WHERE aluno_id=?
                ORDER BY id DESC LIMIT ?""",
                (int(aluno_id), int(limite)),
            ).fetchall()
        return [bool(linha["correta"]) for linha in linhas]

    def listar_desempenho_turma(self):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT aluno_id, COUNT(*) AS total,
                COALESCE(SUM(correta),0) AS acertos,
                COALESCE(SUM(pontos),0) AS pontos
                FROM tentativas WHERE aluno_id IS NOT NULL
                GROUP BY aluno_id ORDER BY pontos DESC, acertos DESC"""
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def criar_sala_multijogador(self, codigo, nome, criador_id, questoes_ids):
        """Cria uma sala do professor com a sequência escolhida de questões."""

        questoes_ids = [int(questao_id) for questao_id in questoes_ids]
        if not questoes_ids:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        try:
            with self._bloqueio, self.conexao:
                cursor = self.conexao.execute(
                    """INSERT INTO salas_multijogador
                    (codigo,nome,criador_id,questao_id,rodada,status,criada_em)
                    VALUES(?,?,?,?,1,'ABERTA',?)""",
                    (codigo, nome, int(criador_id), questoes_ids[0], self._agora()),
                )
                self.conexao.executemany(
                    """INSERT INTO questoes_sala_multijogador
                    (sala_id,ordem,questao_id) VALUES(?,?,?)""",
                    [
                        (cursor.lastrowid, ordem, questao_id)
                        for ordem, questao_id in enumerate(questoes_ids, start=1)
                    ],
                )
        except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
            raise ErroDominio("Não foi possível criar a sala. Tente novamente.") from erro
        return self.buscar_sala_multijogador(codigo)

    def listar_salas_professor(self, professor_id):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT s.*,
                COUNT(DISTINCT q.ordem) AS total_questoes,
                COUNT(DISTINCT p.aluno_id) AS total_alunos
                FROM salas_multijogador s
                LEFT JOIN questoes_sala_multijogador q ON q.sala_id=s.id
                LEFT JOIN participantes_multijogador p ON p.sala_id=s.id
                WHERE s.criador_id=?
                GROUP BY s.id ORDER BY s.id DESC""",
                (int(professor_id),),
            ).fetchall()
        return [
            {
                "sala": self._sala_multijogador(linha),
                "total_questoes": int(linha["total_questoes"]),
                "total_alunos": int(linha["total_alunos"]),
            }
            for linha in linhas
        ]

    def questoes_ids_sala_multijogador(self, sala_id):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT questao_id FROM questoes_sala_multijogador
                WHERE sala_id=? ORDER BY ordem""",
                (int(sala_id),),
            ).fetchall()
        return [int(linha["questao_id"]) for linha in linhas]

    def atualizar_sala_multijogador(self, sala_id, nome, questoes_ids):
        """Troca a sequência e reinicia rodada, respostas e placar da sala."""

        sala_id = int(sala_id)
        questoes_ids = [int(questao_id) for questao_id in questoes_ids]
        if not questoes_ids:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        with self._bloqueio:
            self.conexao.execute("BEGIN IMMEDIATE")
            try:
                cursor = self.conexao.execute(
                    """UPDATE salas_multijogador
                    SET nome=?,questao_id=?,rodada=1,status='ABERTA' WHERE id=?""",
                    (nome, questoes_ids[0], sala_id),
                )
                if cursor.rowcount != 1:
                    raise ErroDominio("Sala não encontrada.")
                self.conexao.execute(
                    "DELETE FROM respostas_multijogador WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.execute(
                    "UPDATE participantes_multijogador SET pontos=0 WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.execute(
                    "DELETE FROM questoes_sala_multijogador WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.executemany(
                    """INSERT INTO questoes_sala_multijogador
                    (sala_id,ordem,questao_id) VALUES(?,?,?)""",
                    [
                        (sala_id, ordem, questao_id)
                        for ordem, questao_id in enumerate(questoes_ids, start=1)
                    ],
                )
                self.conexao.commit()
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise

    def excluir_sala_multijogador(self, sala_id):
        """Exclui definitivamente uma sala e seus dados operacionais."""

        sala_id = int(sala_id)
        with self._bloqueio, self.conexao:
            self.conexao.execute(
                "DELETE FROM respostas_multijogador WHERE sala_id=?", (sala_id,)
            )
            self.conexao.execute(
                "DELETE FROM participantes_multijogador WHERE sala_id=?", (sala_id,)
            )
            self.conexao.execute(
                "DELETE FROM questoes_sala_multijogador WHERE sala_id=?", (sala_id,)
            )
            cursor = self.conexao.execute(
                "DELETE FROM salas_multijogador WHERE id=?", (sala_id,)
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Sala não encontrada.")

    def buscar_sala_multijogador(self, codigo):
        with self._bloqueio:
            linha = self.conexao.execute(
                "SELECT * FROM salas_multijogador WHERE codigo=?",
                (str(codigo).upper(),),
            ).fetchone()
        return self._sala_multijogador(linha)

    def entrar_sala_multijogador(self, sala_id, aluno_id):
        with self._bloqueio, self.conexao:
            sala = self.conexao.execute(
                "SELECT status FROM salas_multijogador WHERE id=?",
                (int(sala_id),),
            ).fetchone()
            if sala is None or sala["status"] != "ABERTA":
                raise ErroDominio("Esta sala não está disponível.")
            self.conexao.execute(
                """INSERT OR IGNORE INTO participantes_multijogador
                (sala_id,aluno_id,pontos,entrou_em) VALUES(?,?,0,?)""",
                (int(sala_id), int(aluno_id), self._agora()),
            )

    def participante_na_sala(self, sala_id, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT 1 FROM participantes_multijogador
                WHERE sala_id=? AND aluno_id=?""",
                (int(sala_id), int(aluno_id)),
            ).fetchone()
        return linha is not None

    def participantes_multijogador(self, sala):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT p.aluno_id, p.pontos,
                CASE WHEN r.aluno_id IS NULL THEN 0 ELSE 1 END AS respondeu
                FROM participantes_multijogador p
                LEFT JOIN respostas_multijogador r
                  ON r.sala_id=p.sala_id AND r.aluno_id=p.aluno_id
                 AND r.rodada=?
                WHERE p.sala_id=? ORDER BY p.entrou_em, p.aluno_id""",
                (int(sala.rodada), int(sala.id)),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def resposta_multijogador(self, sala, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT indice_escolhido,correta,pontos
                FROM respostas_multijogador
                WHERE sala_id=? AND rodada=? AND aluno_id=?""",
                (int(sala.id), int(sala.rodada), int(aluno_id)),
            ).fetchone()
        return dict(linha) if linha else None

    def registrar_resposta_multijogador(
        self, sala, aluno_id, questao, indice_escolhido, correta, pontos
    ):
        """Registra uma única resposta por estudante e rodada."""

        try:
            with self._bloqueio:
                self.conexao.execute("BEGIN IMMEDIATE")
                atual = self.conexao.execute(
                    "SELECT * FROM salas_multijogador WHERE id=?",
                    (int(sala.id),),
                ).fetchone()
                participa = self.conexao.execute(
                    """SELECT 1 FROM participantes_multijogador
                    WHERE sala_id=? AND aluno_id=?""",
                    (int(sala.id), int(aluno_id)),
                ).fetchone()
                if (
                    atual is None
                    or atual["status"] != "ABERTA"
                    or atual["rodada"] != sala.rodada
                    or atual["questao_id"] != questao.id
                    or participa is None
                ):
                    raise ErroDominio("A rodada foi atualizada. Recarregue a sala.")
                total = self.conexao.execute(
                    """SELECT COUNT(*) AS total FROM participantes_multijogador
                    WHERE sala_id=?""",
                    (int(sala.id),),
                ).fetchone()["total"]
                if total < 2:
                    raise ErroDominio("Aguarde outro aluno entrar na sala.")
                self.conexao.execute(
                    """INSERT INTO respostas_multijogador
                    (sala_id,rodada,aluno_id,questao_id,indice_escolhido,
                    correta,pontos,respondida_em) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        sala.id, sala.rodada, int(aluno_id), questao.id,
                        int(indice_escolhido), 1 if correta else 0,
                        int(pontos), self._agora(),
                    ),
                )
                self.conexao.execute(
                    """UPDATE participantes_multijogador SET pontos=pontos+?
                    WHERE sala_id=? AND aluno_id=?""",
                    (int(pontos), sala.id, int(aluno_id)),
                )
                self.conexao.execute(
                    """INSERT INTO tentativas (
                    aluno_id,questao_id,modo,dificuldade,indice_escolhido,
                    correta,pontos,respondida_em
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        int(aluno_id), questao.id, "MULTIJOGADOR",
                        questao.dificuldade, int(indice_escolhido),
                        1 if correta else 0, int(pontos), self._agora(),
                    ),
                )
                self.conexao.commit()
        except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
            if self.conexao.in_transaction:
                self.conexao.rollback()
            raise ErroDominio("Você já respondeu nesta rodada.") from erro
        except Exception:
            if self.conexao.in_transaction:
                self.conexao.rollback()
            raise

    def avancar_rodada_multijogador(self, sala):
        """Avança com segurança quando todos responderam ou encerra a sequência."""

        with self._bloqueio:
            self.conexao.execute("BEGIN IMMEDIATE")
            atual = self.conexao.execute(
                "SELECT * FROM salas_multijogador WHERE id=?", (int(sala.id),)
            ).fetchone()
            if (
                atual is None
                or atual["status"] != "ABERTA"
                or int(atual["rodada"]) != int(sala.rodada)
            ):
                self.conexao.rollback()
                return self.buscar_sala_multijogador(sala.codigo)
            contagens = self.conexao.execute(
                """SELECT
                (SELECT COUNT(*) FROM participantes_multijogador WHERE sala_id=?) participantes,
                (SELECT COUNT(*) FROM respostas_multijogador
                 WHERE sala_id=? AND rodada=?) respostas""",
                (sala.id, sala.id, sala.rodada),
            ).fetchone()
            if contagens["participantes"] < 2 or contagens["respostas"] < contagens["participantes"]:
                self.conexao.rollback()
                raise ErroDominio("Aguarde todos os participantes responderem.")
            proxima = self.conexao.execute(
                """SELECT questao_id FROM questoes_sala_multijogador
                WHERE sala_id=? AND ordem=?""",
                (sala.id, sala.rodada + 1),
            ).fetchone()
            if proxima is None:
                self.conexao.execute(
                    """UPDATE salas_multijogador SET status='ENCERRADA'
                    WHERE id=? AND rodada=? AND status='ABERTA'""",
                    (sala.id, sala.rodada),
                )
            else:
                self.conexao.execute(
                    """UPDATE salas_multijogador
                    SET questao_id=?, rodada=rodada+1
                    WHERE id=? AND rodada=? AND status='ABERTA'""",
                    (int(proxima["questao_id"]), sala.id, sala.rodada),
                )
            self.conexao.commit()
        return self.buscar_sala_multijogador(sala.codigo)

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
            cursor = self.conexao.execute(
                "DELETE FROM usuarios WHERE id=?", (usuario_id,)
            )
            if cursor.rowcount != 1:
                raise ErroDominio("Usuário não encontrado.")

    def fechar(self):
        with self._bloqueio:
            self.conexao.close()
