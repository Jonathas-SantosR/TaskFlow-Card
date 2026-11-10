import sqlite3

from backend.taskflow.dominio import ErroDominio, SalaMultijogador
from banco_de_dados.banco import ErroIntegridadeBanco
from banco_de_dados.persistencia.base import RepositorioBase


class RepositorioSalas(RepositorioBase):
    @staticmethod
    def _sala_multijogador(linha):
        if linha is None:
            return None
        return SalaMultijogador(
            id=linha["id"],
            codigo=linha["codigo"],
            nome=linha["nome"],
            criador_id=linha["criador_id"],
            questao_id=linha["questao_id"],
            rodada=linha["rodada"],
            status=linha["status"],
            criada_em=linha["criada_em"],
        )

    def criar_sala_multijogador(self, codigo, nome, criador_id, questoes_ids):
        """Cria uma sala do professor com a sequência escolhida de questões."""

        questoes_ids = [int(questao_id) for questao_id in questoes_ids]
        if not questoes_ids:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        try:
            with self._bloqueio, self.conexao:
                cursor = self.conexao.execute(
                    """INSERT INTO salas_multijogador
                    (codigo,nome,criador_id,questao_id,rodada,status,criada_em)
                    VALUES(?,?,?,?,1,'ABERTA',?)""",
                    (codigo, nome, int(criador_id), questoes_ids[0], self._agora()),
                )
                self.conexao.executemany(
                    """INSERT INTO questoes_sala_multijogador
                    (sala_id,ordem,questao_id) VALUES(?,?,?)""",
                    [
                        (cursor.lastrowid, ordem, questao_id)
                        for ordem, questao_id in enumerate(questoes_ids, start=1)
                    ],
                )
        except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
            raise ErroDominio("Não foi possível criar a sala. Tente novamente.") from erro
        return self.buscar_sala_multijogador(codigo)

    def listar_salas_professor(self, professor_id):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT s.*,
                COUNT(DISTINCT q.ordem) AS total_questoes,
                COUNT(DISTINCT p.aluno_id) AS total_alunos
                FROM salas_multijogador s
                LEFT JOIN questoes_sala_multijogador q ON q.sala_id=s.id
                LEFT JOIN participantes_multijogador p ON p.sala_id=s.id
                WHERE s.criador_id=?
                GROUP BY s.id ORDER BY s.id DESC""",
                (int(professor_id),),
            ).fetchall()
        return [
            {
                "sala": self._sala_multijogador(linha),
                "total_questoes": int(linha["total_questoes"]),
                "total_alunos": int(linha["total_alunos"]),
            }
            for linha in linhas
        ]

    def questoes_ids_sala_multijogador(self, sala_id):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT questao_id FROM questoes_sala_multijogador
                WHERE sala_id=? ORDER BY ordem""",
                (int(sala_id),),
            ).fetchall()
        return [int(linha["questao_id"]) for linha in linhas]

    def atualizar_sala_multijogador(self, sala_id, nome, questoes_ids):
        """Troca a sequência e reinicia rodada, respostas e placar da sala."""

        sala_id = int(sala_id)
        questoes_ids = [int(questao_id) for questao_id in questoes_ids]
        if not questoes_ids:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        with self._bloqueio:
            self.conexao.execute("BEGIN IMMEDIATE")
            try:
                cursor = self.conexao.execute(
                    """UPDATE salas_multijogador
                    SET nome=?,questao_id=?,rodada=1,status='ABERTA' WHERE id=?""",
                    (nome, questoes_ids[0], sala_id),
                )
                if cursor.rowcount != 1:
                    raise ErroDominio("Sala não encontrada.")
                self.conexao.execute(
                    "DELETE FROM respostas_multijogador WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.execute(
                    "UPDATE participantes_multijogador SET pontos=0 WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.execute(
                    "DELETE FROM questoes_sala_multijogador WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.executemany(
                    """INSERT INTO questoes_sala_multijogador
                    (sala_id,ordem,questao_id) VALUES(?,?,?)""",
                    [
                        (sala_id, ordem, questao_id)
                        for ordem, questao_id in enumerate(questoes_ids, start=1)
                    ],
                )
                self.conexao.commit()
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise

    def excluir_sala_multijogador(self, sala_id):
        """Exclui definitivamente uma sala e seus dados operacionais."""

        sala_id = int(sala_id)
        with self._bloqueio, self.conexao:
            self.conexao.execute("DELETE FROM respostas_multijogador WHERE sala_id=?", (sala_id,))
            self.conexao.execute(
                "DELETE FROM participantes_multijogador WHERE sala_id=?", (sala_id,)
            )
            self.conexao.execute(
                "DELETE FROM questoes_sala_multijogador WHERE sala_id=?", (sala_id,)
            )
            cursor = self.conexao.execute("DELETE FROM salas_multijogador WHERE id=?", (sala_id,))
        if cursor.rowcount != 1:
            raise ErroDominio("Sala não encontrada.")

    def buscar_sala_multijogador(self, codigo):
        with self._bloqueio:
            linha = self.conexao.execute(
                "SELECT * FROM salas_multijogador WHERE codigo=?",
                (str(codigo).upper(),),
            ).fetchone()
        return self._sala_multijogador(linha)

    def entrar_sala_multijogador(self, sala_id, aluno_id):
        with self._bloqueio, self.conexao:
            sala = self.conexao.execute(
                "SELECT status FROM salas_multijogador WHERE id=?",
                (int(sala_id),),
            ).fetchone()
            if sala is None or sala["status"] != "ABERTA":
                raise ErroDominio("Esta sala não está disponível.")
            self.conexao.execute(
                """INSERT OR IGNORE INTO participantes_multijogador
                (sala_id,aluno_id,pontos,entrou_em) VALUES(?,?,0,?)""",
                (int(sala_id), int(aluno_id), self._agora()),
            )

    def participante_na_sala(self, sala_id, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT 1 FROM participantes_multijogador
                WHERE sala_id=? AND aluno_id=?""",
                (int(sala_id), int(aluno_id)),
            ).fetchone()
        return linha is not None

    def participantes_multijogador(self, sala):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT p.aluno_id, p.pontos,
                CASE WHEN r.aluno_id IS NULL THEN 0 ELSE 1 END AS respondeu
                FROM participantes_multijogador p
                LEFT JOIN respostas_multijogador r
                  ON r.sala_id=p.sala_id AND r.aluno_id=p.aluno_id
                 AND r.rodada=?
                WHERE p.sala_id=? ORDER BY p.entrou_em, p.aluno_id""",
                (int(sala.rodada), int(sala.id)),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def resposta_multijogador(self, sala, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT indice_escolhido,correta,pontos
                FROM respostas_multijogador
                WHERE sala_id=? AND rodada=? AND aluno_id=?""",
                (int(sala.id), int(sala.rodada), int(aluno_id)),
            ).fetchone()
        return dict(linha) if linha else None

    def registrar_resposta_multijogador(
        self, sala, aluno_id, questao, indice_escolhido, correta, pontos
    ):
        """Registra uma única resposta por estudante e rodada."""

        try:
            with self._bloqueio, self.conexao:
                self.conexao.execute("BEGIN IMMEDIATE")
                atual = self.conexao.execute(
                    "SELECT * FROM salas_multijogador WHERE id=?",
                    (int(sala.id),),
                ).fetchone()
                participa = self.conexao.execute(
                    """SELECT 1 FROM participantes_multijogador
                    WHERE sala_id=? AND aluno_id=?""",
                    (int(sala.id), int(aluno_id)),
                ).fetchone()
                if (
                    atual is None
                    or atual["status"] != "ABERTA"
                    or atual["rodada"] != sala.rodada
                    or atual["questao_id"] != questao.id
                    or participa is None
                ):
                    raise ErroDominio("A rodada foi atualizada. Recarregue a sala.")
                total = self.conexao.execute(
                    """SELECT COUNT(*) AS total FROM participantes_multijogador
                    WHERE sala_id=?""",
                    (int(sala.id),),
                ).fetchone()["total"]
                if total < 2:
                    raise ErroDominio("Aguarde outro aluno entrar na sala.")
                self.conexao.execute(
                    """INSERT INTO respostas_multijogador
                    (sala_id,rodada,aluno_id,questao_id,indice_escolhido,
                    correta,pontos,respondida_em) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        sala.id,
                        sala.rodada,
                        int(aluno_id),
                        questao.id,
                        int(indice_escolhido),
                        1 if correta else 0,
                        int(pontos),
                        self._agora(),
                    ),
                )
                self.conexao.execute(
                    """UPDATE participantes_multijogador SET pontos=pontos+?
                    WHERE sala_id=? AND aluno_id=?""",
                    (int(pontos), sala.id, int(aluno_id)),
                )
                self.conexao.execute(
                    """INSERT INTO tentativas (
                    aluno_id,questao_id,modo,dificuldade,indice_escolhido,
                    correta,pontos,respondida_em
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        int(aluno_id),
                        questao.id,
                        "MULTIJOGADOR",
                        questao.dificuldade,
                        int(indice_escolhido),
                        1 if correta else 0,
                        int(pontos),
                        self._agora(),
                    ),
                )
        except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
            raise ErroDominio("Você já respondeu nesta rodada.") from erro

    def avancar_rodada_multijogador(self, sala):
        """Avança com segurança quando todos responderam ou encerra a sequência."""

        with self._bloqueio, self.conexao:
            self.conexao.execute("BEGIN IMMEDIATE")
            atual = self.conexao.execute(
                "SELECT * FROM salas_multijogador WHERE id=?", (int(sala.id),)
            ).fetchone()
            if (
                atual is None
                or atual["status"] != "ABERTA"
                or int(atual["rodada"]) != int(sala.rodada)
            ):
                self.conexao.rollback()
                return self.buscar_sala_multijogador(sala.codigo)
            contagens = self.conexao.execute(
                """SELECT
                (SELECT COUNT(*) FROM participantes_multijogador WHERE sala_id=?) participantes,
                (SELECT COUNT(*) FROM respostas_multijogador
                 WHERE sala_id=? AND rodada=?) respostas""",
                (sala.id, sala.id, sala.rodada),
            ).fetchone()
            if (
                contagens["participantes"] < 2
                or contagens["respostas"] < contagens["participantes"]
            ):
                self.conexao.rollback()
                raise ErroDominio("Aguarde todos os participantes responderem.")
            proxima = self.conexao.execute(
                """SELECT questao_id FROM questoes_sala_multijogador
                WHERE sala_id=? AND ordem=?""",
                (sala.id, sala.rodada + 1),
            ).fetchone()
            if proxima is None:
                self.conexao.execute(
                    """UPDATE salas_multijogador SET status='ENCERRADA'
                    WHERE id=? AND rodada=? AND status='ABERTA'""",
                    (sala.id, sala.rodada),
                )
            else:
                self.conexao.execute(
                    """UPDATE salas_multijogador
                    SET questao_id=?, rodada=rodada+1
                    WHERE id=? AND rodada=? AND status='ABERTA'""",
                    (int(proxima["questao_id"]), sala.id, sala.rodada),
                )
            self.conexao.commit()
        return self.buscar_sala_multijogador(sala.codigo)
