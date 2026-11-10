from datetime import datetime, timedelta, timezone

from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioAuditoria(RepositorioBase):
    @staticmethod
    def _campos_assinatura_evento(ocorrido_em, perfil, evento, recurso, ator_id=None, alvo_id=None):
        return {
            "ocorrido_em": ocorrido_em,
            "ator_id": ator_id,
            "perfil": perfil,
            "evento": evento,
            "recurso": recurso,
            "alvo_id": alvo_id,
        }

    def reassinar_eventos(self, eventos_ids):
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
            "PRIMEIRO_PROFESSOR",
            "CONTA_CRIADA",
            "LOGIN_OK",
            "LOGIN_FALHOU",
            "LOGOUT",
            "ALUNO_CRIADO",
            "ALUNO_BLOQUEADO",
            "ALUNO_ATIVADO",
            "ALUNO_EXCLUIDO",
            "IA_QUESTAO",
            "SENHA_PRIMEIRO_ACESSO",
            "SENHA_ALUNO_REDEFINIDA",
            "RECUPERACAO_CONFIGURADA",
            "SENHA_PROFESSOR_RECUPERADA",
            "CONTA_ANONIMIZADA",
            "CONTA_EXCLUIDA",
            "QUESTAO_CRIADA",
            "QUESTAO_ATUALIZADA",
            "QUESTAO_EXCLUIDA",
            "IA_QUESTAO_ADAPTADA",
            "IA_NARRACAO",
            "RESPOSTA_REGISTRADA",
            "SALA_MULTIJOGADOR_CRIADA",
            "SALA_MULTIJOGADOR_EDITADA",
            "SALA_MULTIJOGADOR_EXCLUIDA",
            "SALA_MULTIJOGADOR_ENTRADA",
            "RESPOSTA_MULTIJOGADOR",
            "RODADA_MULTIJOGADOR_AVANCADA",
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
            evento["integridade"] = self.assinador_auditoria.verificar(campos, linha["assinatura"])
            eventos.append(evento)
        return eventos
