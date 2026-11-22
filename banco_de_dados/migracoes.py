"""Histórico ordenado de alterações compatíveis com bancos existentes."""

from datetime import datetime, timezone

from banco_de_dados.migracao_academica import migrar_academico
from banco_de_dados.persistencia.recuperacao import migrar_controle_recuperacao


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
            (4, "Perfil TI e permissões administrativas", banco._migrar_perfil_ti),
            (5, "Recuperação por e-mail e revogação de sessões", banco._migrar_recuperacao_email),
        )
        self._aplicar_etapas(etapas)

    def aplicar_academico(self):
        self._aplicar_etapas(
            (
                (
                    7,
                    "Perfil escolar e salas por turma",
                    lambda: migrar_academico(self.infraestrutura),
                ),
                (
                    8,
                    "Controle persistente de e-mails",
                    lambda: migrar_controle_recuperacao(self.infraestrutura),
                ),
                (
                    9,
                    "Cadastro de vários professores",
                    self.infraestrutura._migrar_varios_professores,
                ),
                (11, "Idade opcional do professor", self.infraestrutura._migrar_idade_professor),
                (12, "Codigos temporarios para confirmar Gmail no cadastro", self.infraestrutura._migrar_codigos_cadastro),
            )
        )

    def _aplicar_etapas(self, etapas):
        banco = self.infraestrutura
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
