"""Conexões de banco usadas pelo repositório, sem expor segredos à interface."""

from __future__ import annotations

import re


class ErroConfiguracaoBanco(RuntimeError):
    """Indica configuração ausente ou conexão indisponível."""


class ErroIntegridadeBanco(Exception):
    """Uniformiza violações de chave única entre SQLite e MySQL."""


def adaptar_sql_mysql(sql):
    """Converte apenas as diferenças usadas pelas consultas do projeto."""

    convertido = str(sql)
    convertido = re.sub(
        r"\bINSERT\s+OR\s+IGNORE\b",
        "INSERT IGNORE",
        convertido,
        flags=re.IGNORECASE,
    )
    convertido = re.sub(
        r"\bRANDOM\s*\(\s*\)",
        "RAND()",
        convertido,
        flags=re.IGNORECASE,
    )
    return convertido.replace("?", "%s")


ESQUEMA_MYSQL = """
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    perfil VARCHAR(20) NOT NULL,
    identificador VARCHAR(1024) NOT NULL,
    chave_identificador VARCHAR(128) NOT NULL,
    nome VARCHAR(1024) NOT NULL,
    senha_hash VARCHAR(512) NOT NULL,
    ativo TINYINT(1) NOT NULL DEFAULT 1,
    criado_em VARCHAR(40) NOT NULL,
    primeiro_acesso TINYINT(1) NOT NULL DEFAULT 0,
    recuperacao_hash VARCHAR(512) NULL,
    anonimizado_em VARCHAR(40) NULL,
    professor_unico TINYINT GENERATED ALWAYS AS (
        CASE WHEN perfil='PROFESSOR' AND anonimizado_em IS NULL THEN 1 ELSE NULL END
    ) STORED,
    CONSTRAINT uq_usuario_identificador UNIQUE (perfil, chave_identificador),
    CONSTRAINT uq_professor_ativo UNIQUE (professor_unico),
    CONSTRAINT ck_usuario_perfil CHECK (perfil IN ('PROFESSOR','ALUNO'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auditoria (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ocorrido_em VARCHAR(40) NOT NULL,
    ator_id BIGINT NULL,
    perfil VARCHAR(20) NOT NULL,
    evento VARCHAR(80) NOT NULL,
    recurso VARCHAR(80) NOT NULL,
    alvo_id BIGINT NULL,
    assinatura VARCHAR(255) NULL,
    INDEX idx_auditoria_ocorrido_em (ocorrido_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS aceites (
    usuario_id BIGINT PRIMARY KEY,
    termos_versao VARCHAR(40) NOT NULL,
    privacidade_versao VARCHAR(40) NOT NULL,
    aceito_em VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS questoes (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    professor_id BIGINT NULL,
    tema VARCHAR(255) NOT NULL,
    dificuldade VARCHAR(20) NOT NULL,
    enunciado TEXT NOT NULL,
    alternativas_json TEXT NOT NULL,
    indice_correto INT NOT NULL,
    explicacao TEXT NOT NULL,
    feedback_acerto TEXT NOT NULL,
    feedback_erro TEXT NOT NULL,
    criada_em VARCHAR(40) NOT NULL,
    ativa TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_questoes_ativas (ativa, dificuldade)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tentativas (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    aluno_id BIGINT NULL,
    questao_id BIGINT NULL,
    modo VARCHAR(30) NOT NULL,
    dificuldade VARCHAR(20) NOT NULL,
    indice_escolhido INT NOT NULL,
    correta TINYINT(1) NOT NULL,
    pontos INT NOT NULL,
    respondida_em VARCHAR(40) NOT NULL,
    INDEX idx_tentativas_aluno (aluno_id, respondida_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS salas_multijogador (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    nome VARCHAR(80) NOT NULL,
    criador_id BIGINT NULL,
    questao_id BIGINT NOT NULL,
    rodada INT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'ABERTA',
    criada_em VARCHAR(40) NOT NULL,
    INDEX idx_salas_codigo_status (codigo, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS questoes_sala_multijogador (
    sala_id BIGINT NOT NULL,
    ordem INT NOT NULL,
    questao_id BIGINT NOT NULL,
    PRIMARY KEY (sala_id, ordem),
    CONSTRAINT uq_sala_questao UNIQUE (sala_id, questao_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS participantes_multijogador (
    sala_id BIGINT NOT NULL,
    aluno_id BIGINT NOT NULL,
    pontos INT NOT NULL DEFAULT 0,
    entrou_em VARCHAR(40) NOT NULL,
    PRIMARY KEY (sala_id, aluno_id),
    INDEX idx_participantes_aluno (aluno_id, sala_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS respostas_multijogador (
    sala_id BIGINT NOT NULL,
    rodada INT NOT NULL,
    aluno_id BIGINT NOT NULL,
    questao_id BIGINT NOT NULL,
    indice_escolhido INT NOT NULL,
    correta TINYINT(1) NOT NULL,
    pontos INT NOT NULL,
    respondida_em VARCHAR(40) NOT NULL,
    PRIMARY KEY (sala_id, rodada, aluno_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def _validar_nome_banco(nome):
    nome = str(nome or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", nome):
        raise ErroConfiguracaoBanco(
            "TASKFLOW_MYSQL_DATABASE deve conter somente letras, números e sublinhado."
        )
    return nome


class CursorMySQL:
    """Mantém a pequena interface de cursor usada pelo repositório."""

    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()


class ConexaoMySQL:
    """Adapta PyMySQL à interface já utilizada por RepositorioTaskFlow."""

    tipo = "mysql"

    def __init__(self, conexao, erro_integridade):
        self._conexao = conexao
        self._erro_integridade = erro_integridade
        self._em_transacao = False

    @property
    def in_transaction(self):
        return self._em_transacao

    def __enter__(self):
        if not self._em_transacao:
            self._conexao.begin()
            self._em_transacao = True
        return self

    def __exit__(self, tipo_erro, erro, rastreamento):
        if tipo_erro is None:
            self.commit()
        else:
            self.rollback()
        return False

    def execute(self, sql, parametros=()):
        if str(sql).strip().upper() == "BEGIN IMMEDIATE":
            if not self._em_transacao:
                self._conexao.begin()
                self._em_transacao = True
            return CursorMySQL(self._conexao.cursor())
        cursor = self._conexao.cursor()
        try:
            consulta = adaptar_sql_mysql(sql)
            valores = tuple(parametros or ())
            if valores:
                cursor.execute(consulta, valores)
            else:
                # Sem argumentos, o PyMySQL não deve aplicar a formatação `%`.
                # Isso preserva curingas literais de LIKE, como `enc:v1:%`.
                cursor.execute(consulta)
        except self._erro_integridade as erro:
            cursor.close()
            raise ErroIntegridadeBanco(str(erro)) from erro
        return CursorMySQL(cursor)

    def executemany(self, sql, parametros):
        cursor = self._conexao.cursor()
        try:
            cursor.executemany(adaptar_sql_mysql(sql), list(parametros))
        except self._erro_integridade as erro:
            cursor.close()
            raise ErroIntegridadeBanco(str(erro)) from erro
        return CursorMySQL(cursor)

    def executescript(self, roteiro):
        for instrucao in str(roteiro).split(";"):
            if instrucao.strip():
                self.execute(instrucao)

    def commit(self):
        self._conexao.commit()
        self._em_transacao = False

    def rollback(self):
        self._conexao.rollback()
        self._em_transacao = False

    def close(self):
        self._conexao.close()


def conectar_mysql(configuracao, criar_banco=True):
    """Abre MySQL com DictCursor e cria o banco vazio quando autorizado."""

    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as erro:
        raise ErroConfiguracaoBanco(
            "PyMySQL não está instalado. Execute: pip install -r requirements.txt"
        ) from erro

    config = dict(configuracao or {})
    banco = _validar_nome_banco(config.pop("database", "taskflowcards"))
    ssl_ca = str(config.pop("ssl_ca", "") or "").strip()
    parametros = {
        "host": str(config.pop("host", "127.0.0.1")),
        "port": int(config.pop("port", 3306)),
        "user": str(config.pop("user", "")),
        "password": str(config.pop("password", "")),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": True,
        "connect_timeout": int(config.pop("connect_timeout", 10)),
    }
    if not parametros["user"]:
        raise ErroConfiguracaoBanco("Defina TASKFLOW_MYSQL_USER.")
    if ssl_ca:
        parametros["ssl"] = {"ca": ssl_ca, "check_hostname": True}

    try:
        try:
            conexao = pymysql.connect(database=banco, **parametros)
        except pymysql.err.OperationalError as erro_conexao:
            banco_inexistente = bool(erro_conexao.args and int(erro_conexao.args[0]) == 1049)
            if not criar_banco or not banco_inexistente:
                raise
            inicial = pymysql.connect(**parametros)
            try:
                with inicial.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE `{banco}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
            finally:
                inicial.close()
            conexao = pymysql.connect(database=banco, **parametros)
    except pymysql.MySQLError as erro:
        raise ErroConfiguracaoBanco(
            "Não foi possível conectar ao MySQL. Confira servidor, banco e credenciais."
        ) from erro

    return ConexaoMySQL(conexao, pymysql.err.IntegrityError)
