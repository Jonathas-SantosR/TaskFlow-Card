"""Compatibilidade do repositório existente com PostgreSQL."""

import re

from banco_de_dados.banco import ErroConfiguracaoBanco, ErroIntegridadeBanco


_ID_AUTOMATICO = {"usuarios", "auditoria", "questoes", "tentativas", "salas_multijogador"}


def adaptar_sql_postgres(sql):
    consulta = str(sql).strip()
    if re.match(r"INSERT\s+OR\s+IGNORE\b", consulta, flags=re.IGNORECASE):
        consulta = re.sub(
            r"^INSERT\s+OR\s+IGNORE\b", "INSERT", consulta, count=1,
            flags=re.IGNORECASE,
        ).rstrip(" ;") + " ON CONFLICT DO NOTHING"
    return consulta.replace("?", "%s")


class CursorPostgres:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()


class ConexaoPostgres:
    """Oferece execute, transações e cursores esperados pelo repositório."""

    tipo = "postgres"

    def __init__(self, connection, integrity_error):
        self._connection = connection
        self._integrity_error = integrity_error
        self._em_transacao = False

    @property
    def in_transaction(self):
        return self._em_transacao

    def __enter__(self):
        if not self._em_transacao:
            self._connection.execute("BEGIN")
            self._em_transacao = True
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def execute(self, sql, parametros=()):
        if str(sql).strip().upper() == "BEGIN IMMEDIATE":
            if not self._em_transacao:
                self._connection.execute("BEGIN")
                self._em_transacao = True
            return CursorPostgres(self._connection.cursor())
        consulta = adaptar_sql_postgres(sql)
        insert = re.match(r"^INSERT\s+INTO\s+([a-z_]+)\b", consulta, re.IGNORECASE)
        returning_id = bool(
            insert and insert.group(1).lower() in _ID_AUTOMATICO
            and not re.search(r"\bRETURNING\b", consulta, re.IGNORECASE)
        )
        if returning_id:
            consulta = consulta.rstrip(" ;") + " RETURNING id"
        cursor = self._connection.cursor()
        try:
            cursor.execute(consulta, tuple(parametros) if parametros else None)
            lastrowid = cursor.fetchone()["id"] if returning_id else None
        except self._integrity_error as error:
            cursor.close()
            raise ErroIntegridadeBanco(str(error)) from error
        return CursorPostgres(cursor, lastrowid)

    def executemany(self, sql, parametros):
        cursor = self._connection.cursor()
        try:
            cursor.executemany(adaptar_sql_postgres(sql), list(parametros))
        except self._integrity_error as error:
            cursor.close()
            raise ErroIntegridadeBanco(str(error)) from error
        return CursorPostgres(cursor)

    def executescript(self, script):
        for statement in str(script).split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self._connection.commit()
        self._em_transacao = False

    def rollback(self):
        self._connection.rollback()
        self._em_transacao = False

    def close(self):
        self._connection.close()


def conectar_postgres(url):
    if not str(url or "").startswith(("postgresql://", "postgres://")):
        raise ErroConfiguracaoBanco("DATABASE_URL do PostgreSQL ausente ou inválida.")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise ErroConfiguracaoBanco("Instale as dependências do PostgreSQL.") from error
    try:
        connection = psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=10)
    except psycopg.Error as error:
        raise ErroConfiguracaoBanco("Não foi possível conectar ao PostgreSQL configurado.") from error
    return ConexaoPostgres(connection, psycopg.IntegrityError)
