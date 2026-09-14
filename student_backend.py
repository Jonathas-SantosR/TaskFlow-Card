"""Entidade, validações e persistência dos alunos."""

import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

STATUS_ALUNOS = ("ATIVO", "BLOQUEADO")
PADRAO_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class Aluno:
    """representa um aluno cadastrado no TaskFlow Cards."""

    id: int
    matricula: str
    nome: str
    email: str
    status: str
    criado_em: str
    atualizado_em: str

    @classmethod
    def de_linha(cls, linha):
        return cls(
            id=linha["id"],
            matricula=linha["matricula"],
            nome=linha["nome"],
            email=linha["email"],
            status=linha["status"],
            criado_em=linha["criado_em"],
            atualizado_em=linha["atualizado_em"],
        )

    def para_dict(self):
        return asdict(self)


class ErroValidacaoAluno(ValueError):
    pass


class AlunoNaoEncontrado(LookupError):
    pass


class RepositorioAlunos:
    """Isola o domínio de alunos dos detalhes de persistência do SQLite."""

    def __init__(self, banco):
        """Abre o banco e prepara a estrutura necessária para o CRUD."""
        if str(banco) != ":memory:":
            Path(banco).parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(banco, timeout=5)
        self.conexao.row_factory = sqlite3.Row
        with self.conexao:
            # A checagem anterior à criação identifica bancos que ainda possuem
            # apenas a entidade legada em inglês.
            tabela_nova_existe = self.conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alunos'"
            ).fetchone()
            self.conexao.execute("""
                CREATE TABLE IF NOT EXISTS alunos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT NOT NULL,
                    chave_matricula TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    chave_nome TEXT NOT NULL,
                    email TEXT NOT NULL,
                    chave_email TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('ATIVO','BLOQUEADO')),
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )
            """)
            tabela_antiga = self.conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='students'"
            ).fetchone()
            # A migração acontece uma única vez para que registros excluídos da
            # nova tabela não sejam recuperados acidentalmente da tabela antiga.
            if not tabela_nova_existe and tabela_antiga:
                self.conexao.execute("""
                    INSERT OR IGNORE INTO alunos
                    (id, matricula, chave_matricula, nome, chave_nome, email,
                     chave_email, status, criado_em, atualizado_em)
                    SELECT id, registration, registration_key, name, name_key,
                           email, email_key, status, created_at, updated_at
                    FROM students
                """)

    @staticmethod
    def validar(nome, matricula, email, status):
        """Normaliza os campos e aplica as regras do cadastro de alunos."""
        if not all(isinstance(valor, str) for valor in (nome, matricula, email)):
            raise ErroValidacaoAluno("Nome, matrícula e e-mail devem ser textos.")
        nome = " ".join(nome.split())
        matricula = "".join(matricula.split())
        email = email.strip()
        if not 2 <= len(nome) <= 60:
            raise ErroValidacaoAluno("Informe um nome com 2 a 60 caracteres.")
        if not 2 <= len(matricula) <= 20:
            raise ErroValidacaoAluno("Informe uma matrícula com 2 a 20 caracteres.")
        if len(email) > 100 or PADRAO_EMAIL.fullmatch(email) is None:
            raise ErroValidacaoAluno("Informe um e-mail válido com até 100 caracteres.")
        if status not in STATUS_ALUNOS:
            raise ErroValidacaoAluno("Status inválido.")
        return nome, matricula, email

    @staticmethod
    def _mensagem_duplicidade(erro):
        """Converte detalhes internos do SQLite em mensagens compreensíveis."""
        mensagem = str(erro)
        if "chave_matricula" in mensagem:
            return "Já existe um aluno com essa matrícula."
        if "chave_email" in mensagem:
            return "Já existe um aluno com esse e-mail."
        return "Matrícula ou e-mail já cadastrado."

    def criar(self, nome, matricula, email, status="ATIVO"):
        """Valida, persiste e devolve o aluno criado."""
        nome, matricula, email = self.validar(nome, matricula, email, status)
        agora = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self.conexao:
                # As chaves normalizadas impedem duplicidades que diferem apenas
                # por letras maiúsculas e minúsculas.
                cursor = self.conexao.execute("""
                    INSERT INTO alunos
                    (matricula, chave_matricula, nome, chave_nome, email,
                     chave_email, status, criado_em, atualizado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (matricula, matricula.casefold(), nome, nome.casefold(),
                      email, email.casefold(), status, agora, agora))
        except sqlite3.IntegrityError as erro:
            raise ErroValidacaoAluno(self._mensagem_duplicidade(erro)) from erro
        return self.buscar(cursor.lastrowid)

    def buscar(self, aluno_id):
        """Busca um aluno pelo identificador ou informa que ele não existe."""
        linha = self.conexao.execute(
            "SELECT * FROM alunos WHERE id = ?", (aluno_id,)
        ).fetchone()
        if linha is None:
            raise AlunoNaoEncontrado("Aluno não encontrado. Atualize a lista.")
        return Aluno.de_linha(linha)

    def listar(self, busca="", status=None):
        """Lista alunos em ordem recente, com busca textual e filtro opcional."""
        if status is not None and status not in STATUS_ALUNOS:
            raise ErroValidacaoAluno("Status de consulta inválido.")
        linhas = self.conexao.execute(
            "SELECT * FROM alunos WHERE (? IS NULL OR status = ?) ORDER BY id DESC",
            (status, status),
        ).fetchall()
        consulta = busca.strip().casefold()
        alunos = [Aluno.de_linha(linha) for linha in linhas]
        return [aluno for aluno in alunos if consulta in
                f"{aluno.matricula} {aluno.nome} {aluno.email}".casefold()]

    def atualizar(self, aluno_id, nome, matricula, email, status="ATIVO"):
        """Atualiza os dados editáveis sem alterar a data de criação."""
        nome, matricula, email = self.validar(nome, matricula, email, status)
        self.buscar(aluno_id)
        try:
            with self.conexao:
                self.conexao.execute("""
                    UPDATE alunos SET matricula=?, chave_matricula=?, nome=?,
                    chave_nome=?, email=?, chave_email=?, status=?, atualizado_em=? WHERE id=?
                """, (matricula, matricula.casefold(), nome, nome.casefold(),
                      email, email.casefold(), status,
                      datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                      aluno_id))
        except sqlite3.IntegrityError as erro:
            raise ErroValidacaoAluno(self._mensagem_duplicidade(erro)) from erro
        return self.buscar(aluno_id)

    def excluir(self, aluno_id):
        """Remove exatamente um aluno e sinaliza concorrência ou ID inválido."""
        with self.conexao:
            cursor = self.conexao.execute(
                "DELETE FROM alunos WHERE id = ?", (aluno_id,)
            )
            if cursor.rowcount != 1:
                raise AlunoNaoEncontrado("Aluno não encontrado. Atualize a lista.")

    def fechar(self):
        """Libera a conexão com o banco."""
        self.conexao.close()
