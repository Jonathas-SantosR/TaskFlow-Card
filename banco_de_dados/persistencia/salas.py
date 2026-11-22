import sqlite3
from contextlib import nullcontext

from backend.taskflow.classificacao import (
    ANOS_ESCOLARES,
    PERIODOS,
    normalizar_classificacao,
    validar_idade_aluno,
)
from backend.taskflow.dominio import ErroDominio, SalaMultijogador
from banco_de_dados.banco import ErroIntegridadeBanco
from banco_de_dados.persistencia.base import RepositorioBase

PARTICIPANTES_VALIDOS = """SELECT p.* FROM participantes_multijogador p
    JOIN salas_multijogador s ON s.id=p.sala_id
    JOIN usuarios u ON u.id=p.aluno_id AND u.ativo=1 AND u.perfil='ALUNO'
    JOIN perfil_aluno a ON a.aluno_id=p.aluno_id
        AND a.chave_academica=s.chave_academica
    WHERE s.chave_academica IS NOT NULL"""


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
            ano_escolar=linha["ano_escolar"] or "",
            turma=linha["turma"] or "",
            sala_escolar=linha["sala_escolar"] or "",
            chave_academica=linha["chave_academica"],
        )

    @staticmethod
    def _classificacao_opcional(ano_escolar, turma, sala_escolar):
        if any((ano_escolar, turma, sala_escolar)):
            return normalizar_classificacao(ano_escolar, turma, sala_escolar)
        return dict(ano_escolar=None, turma=None, sala_escolar=None, chave_academica=None)

    def criar_sala_multijogador(
        self, codigo, nome, criador_id, questoes_ids, ano_escolar="", turma="", sala_escolar=""
    ):
        """Cria uma sala do professor com a sequência escolhida de questões."""

        questoes_ids = [int(questao_id) for questao_id in questoes_ids]
        if not questoes_ids:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        dados = self._classificacao_opcional(ano_escolar, turma, sala_escolar)
        try:
            with self._bloqueio, self.conexao:
                cursor = self.conexao.execute(
                    """INSERT INTO salas_multijogador
                    (codigo,nome,criador_id,questao_id,rodada,status,criada_em,
                    ano_escolar,turma,sala_escolar,chave_academica)
                    VALUES(?,?,?,?,1,'ABERTA',?,?,?,?,?)""",
                    (
                        codigo,
                        nome,
                        int(criador_id),
                        questoes_ids[0],
                        self._agora(),
                        dados["ano_escolar"],
                        dados["turma"],
                        dados["sala_escolar"],
                        dados["chave_academica"],
                    ),
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
            raise ErroDominio(
                "Já existe uma sala com esse ano escolar, turma e período. "
                "Edite a sala existente ou confira os dados."
            ) from erro
        return self.buscar_sala_multijogador(codigo)

    def listar_salas_professor(self, professor_id):
        condicao = "WHERE s.criador_id=?" if professor_id is not None else ""
        parametros = (int(professor_id),) if professor_id is not None else ()
        with self._bloqueio:
            linhas = self.conexao.execute(
                f"""SELECT s.*,
                COUNT(DISTINCT q.ordem) AS total_questoes,
                COUNT(DISTINCT p.aluno_id) AS total_alunos,
                (SELECT COUNT(*) FROM perfil_aluno a
                 JOIN usuarios u ON u.id=a.aluno_id AND u.ativo=1
                 WHERE a.chave_academica=s.chave_academica) AS total_matriculados
                FROM salas_multijogador s
                LEFT JOIN questoes_sala_multijogador q ON q.sala_id=s.id
                LEFT JOIN ({PARTICIPANTES_VALIDOS}) p ON p.sala_id=s.id
                {condicao}
                GROUP BY s.id ORDER BY s.id DESC""",
                parametros,
            ).fetchall()
        return [
            {
                "sala": self._sala_multijogador(linha),
                "total_questoes": int(linha["total_questoes"]),
                "total_alunos": int(linha["total_alunos"]),
                "total_matriculados": int(linha["total_matriculados"]),
            }
            for linha in linhas
        ]

    def aderir_sala_multijogador(self, codigo, professor_id):
        with self._bloqueio, self.conexao:
            cursor = self.conexao.execute(
                """UPDATE salas_multijogador SET criador_id=?
                WHERE codigo=? AND criador_id IS NULL""",
                (int(professor_id), str(codigo).upper()),
            )
        if cursor.rowcount != 1:
            raise ErroDominio("Esta sala não está disponível para adesão.")
        return self.buscar_sala_multijogador(codigo)

    def questoes_ids_sala_multijogador(self, sala_id):
        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT questao_id FROM questoes_sala_multijogador
                WHERE sala_id=? ORDER BY ordem""",
                (int(sala_id),),
            ).fetchall()
        return [int(linha["questao_id"]) for linha in linhas]

    def atualizar_sala_multijogador(
        self, sala_id, nome, questoes_ids, ano_escolar="", turma="", sala_escolar=""
    ):
        """Troca a sequência e reinicia rodada, respostas e placar da sala."""

        sala_id = int(sala_id)
        questoes_ids = [int(questao_id) for questao_id in questoes_ids]
        if not questoes_ids:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        dados = self._classificacao_opcional(ano_escolar, turma, sala_escolar)
        with self._bloqueio:
            self.conexao.execute("BEGIN IMMEDIATE")
            try:
                anterior = self.conexao.execute(
                    "SELECT ano_escolar,turma,sala_escolar,chave_academica "
                    "FROM salas_multijogador WHERE id=?",
                    (sala_id,),
                ).fetchone()
                if anterior is None:
                    raise ErroDominio("Sala não encontrada.")
                cursor = self.conexao.execute(
                    """UPDATE salas_multijogador
                    SET nome=?,questao_id=?,rodada=1,status='ABERTA',
                    ano_escolar=?,turma=?,sala_escolar=?,chave_academica=? WHERE id=?""",
                    (
                        nome,
                        questoes_ids[0],
                        dados["ano_escolar"],
                        dados["turma"],
                        dados["sala_escolar"],
                        dados["chave_academica"],
                        sala_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ErroDominio("Sala não encontrada.")
                # Ao converter apenas a antiga sala física em período, mantém
                # os alunos da mesma turma associados à sala e ao histórico.
                if (
                    anterior["chave_academica"]
                    and anterior["sala_escolar"] not in PERIODOS
                    and anterior["ano_escolar"] == dados["ano_escolar"]
                    and anterior["turma"] == dados["turma"]
                ):
                    self.conexao.execute(
                        """UPDATE perfil_aluno SET sala_escolar=?,chave_academica=?,
                        atualizado_em=? WHERE chave_academica=?""",
                        (
                            dados["sala_escolar"], dados["chave_academica"],
                            self._agora(), anterior["chave_academica"],
                        ),
                    )
                self.conexao.execute(
                    "DELETE FROM respostas_multijogador WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.execute(
                    "UPDATE participantes_multijogador SET pontos=0 WHERE sala_id=?",
                    (sala_id,),
                )
                self.conexao.execute(
                    """DELETE FROM participantes_multijogador WHERE sala_id=?
                    AND aluno_id NOT IN (
                        SELECT aluno_id FROM perfil_aluno WHERE chave_academica=?
                    )""",
                    (sala_id, dados["chave_academica"]),
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
            except (sqlite3.IntegrityError, ErroIntegridadeBanco) as erro:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise ErroDominio(
                    "Já existe uma sala com esse ano escolar, turma e período."
                ) from erro
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

    def listar_classificacoes(self):
        """Oferece somente salas que podem receber a matrícula automática."""

        with self._bloqueio:
            linhas = self.conexao.execute(
                """SELECT codigo,nome,ano_escolar,turma,sala_escolar,status
                FROM salas_multijogador WHERE chave_academica IS NOT NULL
                ORDER BY ano_escolar,turma,sala_escolar,nome"""
            ).fetchall()
        return [
            dict(linha) for linha in linhas
            if linha["ano_escolar"] in ANOS_ESCOLARES
            and linha["sala_escolar"] in PERIODOS
        ]

    def buscar_perfil_aluno(self, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                "SELECT * FROM perfil_aluno WHERE aluno_id=?", (int(aluno_id),)
            ).fetchone()
        return dict(linha) if linha else None

    def salvar_perfil_aluno(
        self, aluno_id, idade, ano_escolar, turma, sala_escolar, *, na_transacao=False
    ):
        """Na transação do primeiro acesso, o chamador confirma ou desfaz tudo."""

        idade = validar_idade_aluno(idade)
        dados = normalizar_classificacao(ano_escolar, turma, sala_escolar)
        with self._bloqueio, nullcontext() if na_transacao else self.conexao:
            aluno = self.conexao.execute(
                """SELECT 1 FROM usuarios WHERE id=? AND perfil='ALUNO'
                AND ativo=1 AND anonimizado_em IS NULL""",
                (int(aluno_id),),
            ).fetchone()
            if aluno is None:
                raise ErroDominio("Aluno não encontrado ou inativo.")
            # DELETE + INSERT fica na mesma transação em ambos os bancos.
            self.conexao.execute("DELETE FROM perfil_aluno WHERE aluno_id=?", (int(aluno_id),))
            self.conexao.execute(
                """INSERT INTO perfil_aluno
                (aluno_id,idade,ano_escolar,turma,sala_escolar,chave_academica,atualizado_em)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    int(aluno_id),
                    idade,
                    dados["ano_escolar"],
                    dados["turma"],
                    dados["sala_escolar"],
                    dados["chave_academica"],
                    self._agora(),
                ),
            )
            # Evita continuar participando de uma partida de uma classificação anterior.
            self.conexao.execute(
                """DELETE FROM participantes_multijogador WHERE aluno_id=?
                AND sala_id NOT IN (
                    SELECT id FROM salas_multijogador WHERE chave_academica=?
                )""",
                (int(aluno_id), dados["chave_academica"]),
            )
        return self.buscar_perfil_aluno(aluno_id)

    def sala_academica_aluno(self, aluno_id):
        """A associação acompanha criação/exclusão/alteração de salas pela classificação."""

        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT s.* FROM salas_multijogador s
                JOIN perfil_aluno a ON a.chave_academica=s.chave_academica
                JOIN usuarios u ON u.id=a.aluno_id AND u.ativo=1 AND u.perfil='ALUNO'
                WHERE a.aluno_id=?""",
                (int(aluno_id),),
            ).fetchone()
        return self._sala_multijogador(linha)

    def aluno_pertence_sala(self, aluno_id, sala_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT 1 FROM salas_multijogador s
                JOIN perfil_aluno a ON a.chave_academica=s.chave_academica
                JOIN usuarios u ON u.id=a.aluno_id AND u.ativo=1 AND u.perfil='ALUNO'
                WHERE a.aluno_id=? AND s.id=?""",
                (int(aluno_id), int(sala_id)),
            ).fetchone()
        return linha is not None

    def questao_autorizada_aluno(self, aluno_id, questao_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                """SELECT 1 FROM perfil_aluno a
                JOIN usuarios u ON u.id=a.aluno_id AND u.ativo=1 AND u.perfil='ALUNO'
                JOIN salas_multijogador s ON s.chave_academica=a.chave_academica
                JOIN questoes_sala_multijogador sq ON sq.sala_id=s.id
                JOIN questoes q ON q.id=sq.questao_id AND q.ativa=1
                WHERE a.aluno_id=? AND q.id=?""",
                (int(aluno_id), int(questao_id)),
            ).fetchone()
        return linha is not None

    def entrar_sala_multijogador(self, sala_id, aluno_id):
        with self._bloqueio, self.conexao:
            sala = self.conexao.execute(
                "SELECT status FROM salas_multijogador WHERE id=?",
                (int(sala_id),),
            ).fetchone()
            if sala is None or sala["status"] != "ABERTA":
                raise ErroDominio("Esta sala não está disponível.")
            if not self.aluno_pertence_sala(aluno_id, sala_id):
                raise ErroDominio("Você só pode entrar na sala do seu ano escolar, turma e período.")
            self.conexao.execute(
                """INSERT OR IGNORE INTO participantes_multijogador
                (sala_id,aluno_id,pontos,entrou_em) VALUES(?,?,0,?)""",
                (int(sala_id), int(aluno_id), self._agora()),
            )

    def participante_na_sala(self, sala_id, aluno_id):
        with self._bloqueio:
            linha = self.conexao.execute(
                f"""SELECT 1 FROM ({PARTICIPANTES_VALIDOS}) p
                WHERE p.sala_id=? AND p.aluno_id=?""",
                (int(sala_id), int(aluno_id)),
            ).fetchone()
        return linha is not None

    def participantes_multijogador(self, sala):
        with self._bloqueio:
            linhas = self.conexao.execute(
                f"""SELECT p.aluno_id, p.pontos,
                CASE WHEN r.aluno_id IS NULL THEN 0 ELSE 1 END AS respondeu
                FROM ({PARTICIPANTES_VALIDOS}) p
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
                    or not self.aluno_pertence_sala(aluno_id, sala.id)
                    or not self.questao_autorizada_aluno(aluno_id, questao.id)
                ):
                    raise ErroDominio("A rodada foi atualizada. Recarregue a sala.")
                total = self.conexao.execute(
                    f"""SELECT COUNT(*) AS total FROM ({PARTICIPANTES_VALIDOS}) p
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
                f"""SELECT
                (SELECT COUNT(*) FROM ({PARTICIPANTES_VALIDOS}) p WHERE sala_id=?) participantes,
                (SELECT COUNT(*) FROM respostas_multijogador r
                 JOIN ({PARTICIPANTES_VALIDOS}) p
                    ON p.sala_id=r.sala_id AND p.aluno_id=r.aluno_id
                 WHERE r.sala_id=? AND r.rodada=?) respostas""",
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
