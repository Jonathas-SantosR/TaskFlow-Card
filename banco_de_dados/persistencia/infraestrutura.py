import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.taskflow.criptografia import AssinadorAuditoria, CriptografiaDados
from banco_de_dados.banco import ESQUEMA_MYSQL, conectar_mysql
from banco_de_dados.postgres import conectar_postgres
from banco_de_dados.migracao_identidade import MigradorIdentidade
from banco_de_dados.migracoes import MigradorBanco


class InfraestruturaBanco:
    """Abre a conexão, prepara o esquema e carrega as chaves locais."""

    def __init__(self, caminho, chave_dados=None, configuracao_mysql=None, postgres_url=None):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        self._bloqueio = threading.RLock()
        self.tipo_banco = "postgres" if postgres_url else ("mysql" if configuracao_mysql else "sqlite")
        if self.tipo_banco == "postgres":
            self.conexao = conectar_postgres(postgres_url)
            esquema = (Path(__file__).resolve().parents[1] / "esquema_postgres.sql").read_text(
                encoding="utf-8"
            )
        elif self.tipo_banco == "mysql":
            self.conexao = conectar_mysql(configuracao_mysql)
            esquema = ESQUEMA_MYSQL
        else:
            self.conexao = sqlite3.connect(caminho, timeout=5, check_same_thread=False)
            self.conexao.row_factory = sqlite3.Row
            esquema = """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    perfil TEXT NOT NULL CHECK(perfil IN ('PROFESSOR','ALUNO','TI')),
                    identificador TEXT NOT NULL,
                    chave_identificador TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    senha_hash TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    primeiro_acesso INTEGER NOT NULL DEFAULT 0,
                    idade INTEGER,
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
        if self.tipo_banco == "postgres":
            self._registrar_versoes_postgres()
        else:
            MigradorBanco(self).aplicar()
        possui_dados_criptografados = (
            self.conexao.execute(
                """SELECT 1 FROM usuarios
            WHERE identificador LIKE 'enc:v1:%' OR nome LIKE 'enc:v1:%'
            LIMIT 1"""
            ).fetchone()
            is not None
        )
        self.criptografia = CriptografiaDados.carregar(
            caminho.parent / ".data_key",
            chave=chave_dados,
            permitir_criar=not possui_dados_criptografados,
        )
        self.assinador_auditoria = AssinadorAuditoria.carregar(
            caminho.parent / ".audit_private.pem"
        )
        if self.tipo_banco != "postgres":
            self._migrar_dados_pessoais()
            MigradorIdentidade(self).aplicar()
            MigradorBanco(self).aplicar_academico()

    def _registrar_versoes_postgres(self):
        """Marca o esquema completo criado para a primeira instalação web."""
        with self._bloqueio, self.conexao:
            for versao in (1, 2, 3, 4, 5, 7, 8, 9, 11, 12):
                self.conexao.execute(
                    """INSERT INTO versoes_esquema (versao,descricao,aplicada_em)
                    VALUES (?,?,?) ON CONFLICT (versao) DO NOTHING""",
                    (
                        versao, "Esquema inicial PostgreSQL",
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                )

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
                for linha in self.conexao.execute("PRAGMA table_info(usuarios)").fetchall()
            }
        if "primeiro_acesso" not in colunas:
            self.conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN primeiro_acesso INTEGER NOT NULL DEFAULT 0"
            )
        if "recuperacao_hash" not in colunas:
            self.conexao.execute("ALTER TABLE usuarios ADD COLUMN recuperacao_hash TEXT")
        if "anonimizado_em" not in colunas:
            self.conexao.execute("ALTER TABLE usuarios ADD COLUMN anonimizado_em TEXT")

    def _migrar_idade_professor(self):
        if self.tipo_banco == "mysql":
            colunas = {
                linha["Field"] for linha in self.conexao.execute("SHOW COLUMNS FROM usuarios").fetchall()
            }
        else:
            colunas = {
                linha["name"] for linha in self.conexao.execute("PRAGMA table_info(usuarios)").fetchall()
            }
        if "idade" not in colunas:
            self.conexao.execute("ALTER TABLE usuarios ADD COLUMN idade INTEGER NULL")

    def _migrar_codigos_cadastro(self):
        """Guarda somente o resumo dos codigos, sem alterar contas existentes."""
        sufixo = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if self.tipo_banco == "mysql" else ""
        self.conexao.execute(
            """CREATE TABLE IF NOT EXISTS codigos_cadastro (
            perfil VARCHAR(20) NOT NULL,
            chave_email VARCHAR(80) NOT NULL,
            codigo_hash VARCHAR(80) NOT NULL,
            expira_em VARCHAR(40) NOT NULL,
            enviado_em VARCHAR(40) NOT NULL,
            janela_inicio VARCHAR(40) NOT NULL,
            envios_janela INTEGER NOT NULL DEFAULT 1,
            tentativas INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (perfil, chave_email)
            )""" + sufixo
        )

    def _migrar_salas_multijogador(self):
        """Mantém salas antigas utilizáveis após a inclusão da lista de questões."""

        if self.tipo_banco == "mysql":
            colunas = {
                linha["Field"]
                for linha in self.conexao.execute("SHOW COLUMNS FROM salas_multijogador").fetchall()
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
                "ALTER TABLE salas_multijogador ADD COLUMN nome VARCHAR(80) NOT NULL DEFAULT ''"
            )
        if self.tipo_banco == "mysql":
            self.conexao.execute(
                "UPDATE salas_multijogador SET nome=CONCAT('Sala ', codigo) WHERE nome=''"
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
                for linha in self.conexao.execute("PRAGMA table_info(auditoria)").fetchall()
            }
        if "assinatura" not in colunas:
            self.conexao.execute("ALTER TABLE auditoria ADD COLUMN assinatura TEXT")

    def _migrar_perfil_ti(self):
        """Amplia a restrição de perfis sem alterar contas, hashes ou seus IDs."""
        if self.tipo_banco == "mysql":
            existente = self.conexao.execute(
                """SELECT cc.CHECK_CLAUSE AS clausula
                FROM information_schema.CHECK_CONSTRAINTS cc
                JOIN information_schema.TABLE_CONSTRAINTS tc
                  ON tc.CONSTRAINT_SCHEMA=cc.CONSTRAINT_SCHEMA
                 AND tc.CONSTRAINT_NAME=cc.CONSTRAINT_NAME
                WHERE tc.TABLE_SCHEMA=DATABASE() AND tc.TABLE_NAME='usuarios'
                  AND tc.CONSTRAINT_NAME='ck_usuario_perfil'"""
            ).fetchone()
            if existente and re.search(r"'TI'", existente["clausula"], re.IGNORECASE):
                return
            remover = "DROP CHECK ck_usuario_perfil, " if existente else ""
            self.conexao.execute(
                f"ALTER TABLE usuarios {remover}ADD CONSTRAINT ck_usuario_perfil "
                "CHECK (perfil IN ('PROFESSOR','ALUNO','TI'))"
            )
            return

        esquema = self.conexao.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'"
        ).fetchone()["sql"]
        restricao = r"CHECK\s*\(\s*perfil\s+IN\s*\(\s*'PROFESSOR'\s*,\s*'ALUNO'\s*\)\s*\)"
        novo_esquema, alteracoes = re.subn(
            restricao,
            "CHECK(perfil IN ('PROFESSOR','ALUNO','TI'))",
            esquema,
            flags=re.IGNORECASE,
        )
        if alteracoes:
            novo_esquema = re.sub(
                r"\ACREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?usuarios[\"`\]]?",
                "CREATE TABLE usuarios_perfil_ti_migracao",
                novo_esquema,
                count=1,
                flags=re.IGNORECASE,
            )
            objetos = self.conexao.execute(
                """SELECT sql FROM sqlite_master WHERE tbl_name='usuarios'
                AND type IN ('index','trigger') AND sql IS NOT NULL"""
            ).fetchall()
            colunas = self.conexao.execute("PRAGMA table_info(usuarios)").fetchall()
            nomes = ",".join('"' + coluna["name"].replace('"', '""') + '"' for coluna in colunas)
            sequencia = self.conexao.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='usuarios'"
            ).fetchone()
            # O BEGIN explícito inclui também os DDL no rollback do SQLite.
            self.conexao.execute("BEGIN IMMEDIATE")
            try:
                self.conexao.execute(novo_esquema)
                self.conexao.execute(
                    f"INSERT INTO usuarios_perfil_ti_migracao ({nomes}) SELECT {nomes} FROM usuarios"
                )
                self.conexao.execute("DROP TABLE usuarios")
                self.conexao.execute("ALTER TABLE usuarios_perfil_ti_migracao RENAME TO usuarios")
                for objeto in objetos:
                    self.conexao.execute(objeto["sql"])
                if sequencia:
                    self.conexao.execute(
                        "UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='usuarios'",
                        (sequencia["seq"],),
                    )
                self.conexao.commit()
            except Exception:
                self.conexao.rollback()
                raise

    def _migrar_varios_professores(self):
        """Retira o limite de um professor de instalações anteriores."""
        if self.tipo_banco == "sqlite":
            self.conexao.execute("DROP INDEX IF EXISTS uq_professor_ativo")
            return

        alteracoes = []
        if self.conexao.execute(
            "SHOW INDEX FROM usuarios WHERE Key_name='uq_professor_ativo'"
        ).fetchone():
            alteracoes.append("DROP INDEX uq_professor_ativo")
        if self.conexao.execute(
            "SHOW COLUMNS FROM usuarios WHERE Field='professor_unico'"
        ).fetchone():
            alteracoes.append("DROP COLUMN professor_unico")
        if alteracoes:
            self.conexao.execute("ALTER TABLE usuarios " + ", ".join(alteracoes))

    def _migrar_recuperacao_email(self):
        """Guarda destinatários protegidos e somente resumos dos tokens de uso único."""
        if self.tipo_banco == "mysql":
            colunas = {
                linha["Field"]
                for linha in self.conexao.execute("SHOW COLUMNS FROM usuarios").fetchall()
            }
        else:
            colunas = {
                linha["name"]
                for linha in self.conexao.execute("PRAGMA table_info(usuarios)").fetchall()
            }
        if "versao_sessao" not in colunas:
            self.conexao.execute(
                "ALTER TABLE usuarios ADD COLUMN versao_sessao INTEGER NOT NULL DEFAULT 0"
            )
        sufixo = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if self.tipo_banco == "mysql" else ""
        self.conexao.execute(
            """CREATE TABLE IF NOT EXISTS emails_recuperacao (
            usuario_id BIGINT PRIMARY KEY,
            email TEXT NOT NULL
            )"""
            + sufixo
        )
        indice = (
            ", INDEX idx_tokens_recuperacao_usuario (usuario_id)"
            if self.tipo_banco == "mysql"
            else ""
        )
        self.conexao.execute(
            """CREATE TABLE IF NOT EXISTS tokens_recuperacao (
            token_hash VARCHAR(64) PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            expira_em VARCHAR(40) NOT NULL,
            usado_em VARCHAR(40) NULL"""
            + indice
            + ")"
            + sufixo
        )
        if self.tipo_banco != "mysql":
            self.conexao.execute(
                """CREATE INDEX IF NOT EXISTS idx_tokens_recuperacao_usuario
                ON tokens_recuperacao(usuario_id)"""
            )

    def _migrar_dados_pessoais(self):
        """Criptografa cadastros legados sem alterar IDs ou senhas."""

        with self._bloqueio, self.conexao:
            linhas = self.conexao.execute(
                "SELECT id, identificador, chave_identificador, nome FROM usuarios"
            ).fetchall()
            for linha in linhas:
                identificador = self.criptografia.descriptografar(linha["identificador"])
                nome = self.criptografia.descriptografar(linha["nome"])
                identificador_protegido = linha["identificador"]
                nome_protegido = linha["nome"]
                indice = self.criptografia.indice(identificador)
                if not self.criptografia.esta_criptografado(identificador_protegido):
                    identificador_protegido = self.criptografia.criptografar(identificador)
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

    def fechar(self):
        with self._bloqueio:
            self.conexao.close()
