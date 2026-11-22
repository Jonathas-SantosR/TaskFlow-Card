import json

from backend.taskflow.dominio import ErroDominio, Questao
from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioQuestoes(RepositorioBase):
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

    def aderir_questao(self, questao_id, professor_id):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                "UPDATE questoes SET professor_id=? WHERE id=? AND professor_id IS NULL",
                (int(professor_id), int(questao_id)),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Esta questão não está disponível para adesão.")
        return self.buscar_questao(questao_id)

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
            cursor = self.conexao.execute("DELETE FROM questoes WHERE id=?", (int(questao_id),))
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
            AND EXISTS (
                SELECT 1 FROM perfil_aluno a
                JOIN usuarios u ON u.id=a.aluno_id AND u.ativo=1 AND u.perfil='ALUNO'
                JOIN salas_multijogador s ON s.chave_academica=a.chave_academica
                JOIN questoes_sala_multijogador sq ON sq.sala_id=s.id
                WHERE a.aluno_id=? AND sq.questao_id=q.id
            )
            ORDER BY
                CASE WHEN historico.ultima_tentativa IS NULL THEN 0 ELSE 1 END,
                historico.ultima_tentativa ASC,
                CASE WHEN q.dificuldade=? THEN 0 ELSE 1 END,
                RANDOM()
            LIMIT 1"""
            parametros = [int(aluno_id), int(aluno_id), dificuldade or ""]
        with self._bloqueio:
            linha = self.conexao.execute(consulta, parametros).fetchone()
        return self._questao(linha)

    def registrar_resposta_bot(self, aluno_id, questao, indice_escolhido, correta, pontos):
        """Confere a autorização na própria gravação, inclusive se a sala mudou."""

        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """INSERT INTO tentativas
                (aluno_id,questao_id,modo,dificuldade,indice_escolhido,correta,pontos,respondida_em)
                SELECT a.aluno_id,q.id,'BOT',q.dificuldade,?,?,?,?
                FROM perfil_aluno a
                JOIN usuarios u ON u.id=a.aluno_id AND u.ativo=1 AND u.perfil='ALUNO'
                JOIN salas_multijogador s ON s.chave_academica=a.chave_academica
                JOIN questoes_sala_multijogador sq ON sq.sala_id=s.id
                JOIN questoes q ON q.id=sq.questao_id AND q.ativa=1
                WHERE a.aluno_id=? AND q.id=? AND q.dificuldade=?
                AND q.indice_correto=? AND q.alternativas_json=?""",
                (
                    int(indice_escolhido),
                    1 if correta else 0,
                    int(pontos),
                    self._agora(),
                    int(aluno_id),
                    questao.id,
                    questao.dificuldade,
                    questao.indice_correto,
                    json.dumps(questao.alternativas, ensure_ascii=False),
                ),
            )
            if cursor.rowcount != 1:
                raise ErroDominio("A questão não está disponível para sua sala. Atualize o treino.")
