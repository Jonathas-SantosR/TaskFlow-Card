import sqlite3
import threading
from pathlib import Path

from backend.taskflow.criptografia import AssinadorAuditoria, CriptografiaDados
from banco_de_dados.banco import ESQUEMA_MYSQL, conectar_mysql
from banco_de_dados.migracoes import MigradorBanco


class InfraestruturaBanco:
    """Abre a conexão, prepara o esquema e carrega as chaves locais."""

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
            self.conexao = sqlite3.connect(caminho, timeout=5, check_same_thread=False)
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
