from datetime import datetime, timedelta, timezone

from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioAuditoria(RepositorioBase):
    RETENCAO_DIAS = 14  # A limpeza ocorre ao iniciar, registrar ou consultar a auditoria.

    def _remover_eventos_expirados(self):
        corte = datetime.now(timezone.utc) - timedelta(days=self.RETENCAO_DIAS)
        self.conexao.execute(
            "DELETE FROM auditoria WHERE ocorrido_em < ?",
            (corte.isoformat(timespec="seconds"),),
        )

    def limpar_eventos_expirados(self):
        with self._bloqueio, self.conexao:
            self._remover_eventos_expirados()

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
            "PERFIL_ESCOLAR_CONCLUIDO",
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
            "SENHA_ALTERADA",
            "IDADE_PROFESSOR_ATUALIZADA",
            "TREINO_BOT_REINICIADO",
            "SENHA_ALUNO_REDEFINIDA",
            "RECUPERACAO_CONFIGURADA",
            "EMAIL_RECUPERACAO_CONFIGURADO",
            "EMAIL_RECUPERACAO_ENVIADO",
            "EMAIL_RECUPERACAO_FALHOU",
            "SENHA_RECUPERADA_EMAIL",
            "TI_CRIADO",
            "SMTP_CONFIGURADO",
            "SENHA_PROFESSOR_RECUPERADA",
            "CONTA_ANONIMIZADA",
            "CONTA_EXCLUIDA",
            "QUESTAO_CRIADA",
            "QUESTAO_ADERIDA",
            "QUESTAO_ATUALIZADA",
            "QUESTAO_EXCLUIDA",
            "IA_QUESTAO_ADAPTADA",
            "IA_NARRACAO",
            "RESPOSTA_REGISTRADA",
            "SALA_MULTIJOGADOR_CRIADA",
            "SALA_MULTIJOGADOR_ADERIDA",
            "SALA_MULTIJOGADOR_EDITADA",
            "SALA_MULTIJOGADOR_EXCLUIDA",
            "SALA_MULTIJOGADOR_ENTRADA",
            "RESPOSTA_MULTIJOGADOR",
            "RODADA_MULTIJOGADOR_AVANCADA",
        }
        if evento not in permitidos:
            raise ValueError("Evento de auditoria inválido.")
        ocorrido_em = self._agora()
        campos = self._campos_assinatura_evento(
            ocorrido_em, perfil, evento, recurso, ator_id, alvo_id
        )
        assinatura = self.assinador_auditoria.assinar(campos)
        with self._bloqueio, self.conexao:
            self._remover_eventos_expirados()
            self.conexao.execute(
                """INSERT INTO auditoria
                (ocorrido_em,ator_id,perfil,evento,recurso,alvo_id,assinatura)
                VALUES(?,?,?,?,?,?,?)""",
                (ocorrido_em, ator_id, perfil, evento, recurso, alvo_id, assinatura),
            )

    def listar_eventos(self, limite=100, ator_id=None, *, incluir_sessoes_alunos=False):
        consulta = """SELECT log.ocorrido_em,log.ator_id,log.perfil,log.evento,log.recurso,
                            log.alvo_id,log.assinatura
                FROM auditoria log"""
        parametros = []
        if ator_id is not None:
            consulta += " WHERE log.ator_id=?"
            parametros.append(int(ator_id))
            if incluir_sessoes_alunos:
                # O vínculo usa a mesma classificação escolar da lista de alunos.
                consulta += """ OR (
                    log.perfil='ALUNO' AND log.recurso='SESSAO'
                    AND log.evento IN ('LOGIN_OK', 'LOGOUT')
                    AND EXISTS (
                        SELECT 1 FROM perfil_aluno p
                        JOIN usuarios u ON u.id=p.aluno_id AND u.ativo=1
                            AND u.perfil='ALUNO' AND u.anonimizado_em IS NULL
                        JOIN salas_multijogador s ON s.chave_academica=p.chave_academica
                        WHERE p.aluno_id=log.ator_id AND s.criador_id=?
                    )
                )"""
                parametros.append(int(ator_id))
        consulta += " ORDER BY log.id DESC LIMIT ?"
        parametros.append(min(max(int(limite), 1), 100))
        with self._bloqueio, self.conexao:
            self._remover_eventos_expirados()
            linhas = self.conexao.execute(consulta, parametros).fetchall()
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

    def resumo_uso_gemini(self):
        """Conta chamadas bem-sucedidas registradas nesta instalação nas últimas 24 horas."""
        corte = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        eventos = {
            "IA_QUESTAO": "questoes",
            "IA_QUESTAO_ADAPTADA": "adaptacoes",
            "IA_NARRACAO": "narracoes",
        }
        resumo = {nome: 0 for nome in eventos.values()}
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT evento, COUNT(*) AS total FROM auditoria
                WHERE recurso='GEMINI' AND ocorrido_em>=?
                AND evento IN ('IA_QUESTAO','IA_QUESTAO_ADAPTADA','IA_NARRACAO')
                GROUP BY evento""",
                (corte,),
            ).fetchall()
        for linha in linhas:
            resumo[eventos[linha["evento"]]] = int(linha["total"])
        return resumo
