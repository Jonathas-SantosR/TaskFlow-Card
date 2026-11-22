from backend.taskflow.dominio import Desempenho
from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioDesempenho(RepositorioBase):
    def reiniciar_treino_bot(self, aluno_id):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                "DELETE FROM tentativas WHERE aluno_id=? AND modo='BOT'", (int(aluno_id),)
            )
        return cursor.rowcount

    def listar_escolaridade_alunos(self):
        with self._bloqueio:
            linhas = self.conexao.execute(
                "SELECT aluno_id,ano_escolar,turma,sala_escolar,chave_academica "
                "FROM perfil_aluno"
            ).fetchall()
        return {int(linha["aluno_id"]): dict(linha) for linha in linhas}

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

    def desempenho_aluno(self, aluno_id, modo=None, sala_id=None):
        consulta = """SELECT COUNT(*) AS total, COALESCE(SUM(correta),0) AS acertos,
            COALESCE(SUM(pontos),0) AS pontos FROM tentativas WHERE aluno_id=?"""
        parametros = [int(aluno_id)]
        if modo:
            consulta += " AND modo=?"
            parametros.append(modo)
        if sala_id is not None:
            consulta += " AND sala_id=?"
            parametros.append(int(sala_id))
        with self._bloqueio:
            linha = self.conexao.execute(consulta, parametros).fetchone()
        return Desempenho(
            total=int(linha["total"]),
            acertos=int(linha["acertos"]),
            pontos=int(linha["pontos"]),
        )

    def acertos_recentes(self, aluno_id, limite=6, modo=None, sala_id=None):
        consulta = "SELECT correta FROM tentativas WHERE aluno_id=?"
        parametros = [int(aluno_id)]
        if modo:
            consulta += " AND modo=?"
            parametros.append(modo)
        if sala_id is not None:
            consulta += " AND sala_id=?"
            parametros.append(int(sala_id))
        consulta += " ORDER BY id DESC LIMIT ?"
        parametros.append(int(limite))
        with self._bloqueio:
            linhas = self.conexao.execute(consulta, parametros).fetchall()
        return [bool(linha["correta"]) for linha in linhas]

    def listar_desempenho_turma(self, filtros=None, professor_id=None):
        filtros = filtros or {}
        condicoes = ["aluno_id IS NOT NULL"]
        parametros = []
        for campo in ("aluno_id", "modo", "dificuldade", "sala_id"):
            if filtros.get(campo):
                condicoes.append(f"{campo}=?")
                parametros.append(filtros[campo])
        if professor_id is not None:  # O filtro restringe as tentativas às salas do professor.
            condicoes.append("""EXISTS (
                SELECT 1 FROM salas_multijogador s
                WHERE s.id=tentativas.sala_id AND s.criador_id=?
            )""")
            parametros.append(int(professor_id))
        for campo, operador in (("inicio_utc", ">="), ("fim_utc", "<")):
            if filtros.get(campo):
                condicoes.append(f"respondida_em {operador} ?")
                parametros.append(filtros[campo])
        with self._bloqueio:
            linhas = self.conexao.execute(
                f"""SELECT aluno_id, COUNT(*) AS total,
                COALESCE(SUM(correta),0) AS acertos,
                COALESCE(SUM(pontos),0) AS pontos
                FROM tentativas WHERE {" AND ".join(condicoes)}
                GROUP BY aluno_id ORDER BY pontos DESC, acertos DESC""",
                parametros,
            ).fetchall()
        return [dict(linha) for linha in linhas]
