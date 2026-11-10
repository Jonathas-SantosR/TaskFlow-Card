from backend.taskflow.dominio import Desempenho
from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioDesempenho(RepositorioBase):
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
