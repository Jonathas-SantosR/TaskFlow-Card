"""Histórico ordenado de alterações compatíveis com bancos existentes."""

from datetime import datetime, timezone


class MigradorBanco:
    def __init__(self, infraestrutura):
        self.infraestrutura = infraestrutura

    def aplicar(self):
        banco = self.infraestrutura
        banco.conexao.execute("""CREATE TABLE IF NOT EXISTS versoes_esquema (
            versao INTEGER PRIMARY KEY,
            descricao VARCHAR(120) NOT NULL,
            aplicada_em VARCHAR(40) NOT NULL
        )""")
        etapas = (
            (1, "Campos de contas e professor inicial", banco._migrar_usuarios),
            (2, "Nome e sequência de questões das salas", banco._migrar_salas_multijogador),
            (3, "Assinatura dos eventos de auditoria", banco._migrar_auditoria),
        )
        aplicadas = {
            linha["versao"]
            for linha in banco.conexao.execute("SELECT versao FROM versoes_esquema").fetchall()
        }
        for versao, descricao, executar in etapas:
            if versao in aplicadas:
                continue
            # As rotinas verificam colunas existentes: uma falha de DDL no MySQL
            # pode ser retomada sem tratar rollback como reversão do esquema.
            executar()
            with banco.conexao:
                banco.conexao.execute(
                    "INSERT INTO versoes_esquema VALUES (?,?,?)",
                    (versao, descricao, datetime.now(timezone.utc).isoformat()),
                )
