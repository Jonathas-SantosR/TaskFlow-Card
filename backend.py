"""Entidade, validações e persistência das salas."""

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

MODOS = ("CLASSICO", "RITMO", "CAOS")
STATUS_SALAS = ("ABERTA", "FECHADA")


@dataclass(frozen=True)
class Sala:
    """Entidade que representa uma sala do TaskFlowCards."""

    id: int
    codigo: str
    nome: str
    descricao: str
    modo: str
    status: str
    criada_em: str
    atualizada_em: str

    @classmethod
    def de_linha(cls, linha):
        return cls(
            id=linha["id"],
            codigo=linha["codigo"],
            nome=linha["nome"],
            descricao=linha["descricao"],
            modo=linha["modo"],
            status=linha["status"],
            criada_em=linha["criada_em"],
            atualizada_em=linha["atualizada_em"],
        )

    def para_dict(self):
        return asdict(self)


class ErroValidacaoSala(ValueError):
    pass


class SalaNaoEncontrada(LookupError):
    pass


class RepositorioSalas:
    """Isola o domínio de salas dos detalhes de persistência do SQLite."""

    def __init__(self, banco):
        """Abre o banco e prepara a estrutura necessária para o CRUD."""
        if str(banco) != ":memory:":
            Path(banco).parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(banco, timeout=5)
        self.conexao.row_factory = sqlite3.Row
        with self.conexao:
            # A checagem anterior à criação identifica se este banco ainda usa
            # somente a entidade legada em inglês.
            tabela_nova_existe = self.conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='salas'"
            ).fetchone()
            self.conexao.execute("""
                CREATE TABLE IF NOT EXISTS salas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    chave_nome TEXT NOT NULL UNIQUE,
                    descricao TEXT NOT NULL,
                    modo TEXT NOT NULL CHECK(modo IN ('CLASSICO','RITMO','CAOS')),
                    status TEXT NOT NULL CHECK(status IN ('ABERTA','FECHADA')),
                    criada_em TEXT NOT NULL,
                    atualizada_em TEXT NOT NULL
                )
            """)
            tabela_antiga = self.conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rooms'"
            ).fetchone()
            # Migra apenas uma vez. Assim, uma sala excluída não reaparece a
            # partir da tabela antiga em uma conexão futura.
            if not tabela_nova_existe and tabela_antiga:
                self.conexao.execute("""
                    INSERT OR IGNORE INTO salas
                    (id, codigo, nome, chave_nome, descricao, modo, status,
                     criada_em, atualizada_em)
                    SELECT id, code, name, name_key, description, mode, status,
                           created_at, updated_at FROM rooms
                """)

    @staticmethod
    def validar(nome, descricao, modo, status):
        """Normaliza os campos e rejeita dados fora das regras do domínio."""
        if not isinstance(nome, str) or not isinstance(descricao, str):
            raise ErroValidacaoSala("Nome e descrição devem ser textos.")
        nome = " ".join(nome.split())
        descricao = " ".join(descricao.split())
        if not 1 <= len(nome) <= 40:
            raise ErroValidacaoSala("Informe um nome com 1 a 40 caracteres.")
        if len(descricao) > 120:
            raise ErroValidacaoSala("A descrição deve ter no máximo 120 caracteres.")
        if modo not in MODOS or status not in STATUS_SALAS:
            raise ErroValidacaoSala("Modo ou status inválido.")
        return nome, descricao

    def criar(self, nome, descricao="", modo="CLASSICO", status="ABERTA"):
        """Valida, persiste e devolve a sala criada."""
        nome, descricao = self.validar(nome, descricao, modo, status)
        agora = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self.conexao:
                # A chave normalizada garante unicidade sem diferenciar
                # maiúsculas, minúsculas ou espaços repetidos.
                cursor = self.conexao.execute("""
                    INSERT INTO salas
                    (codigo, nome, chave_nome, descricao, modo, status, criada_em, atualizada_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (uuid4().hex[:8].upper(), nome, nome.casefold(), descricao,
                      modo, status, agora, agora))
        except sqlite3.IntegrityError as erro:
            raise ErroValidacaoSala(
                "Já existe uma sala com esse nome. Escolha outro."
            ) from erro
        return self.buscar(cursor.lastrowid)

    def buscar(self, sala_id):
        """Busca uma sala pelo identificador ou informa que ela não existe."""
        linha = self.conexao.execute(
            "SELECT * FROM salas WHERE id = ?", (sala_id,)
        ).fetchone()
        if linha is None:
            raise SalaNaoEncontrada("Sala não encontrada. Atualize a lista.")
        return Sala.de_linha(linha)

    def listar(self, busca="", status=None):
        """Lista salas em ordem recente, com busca textual e filtro opcional."""
        if status is not None and status not in STATUS_SALAS:
            raise ErroValidacaoSala("Status de consulta inválido.")
        linhas = self.conexao.execute(
            "SELECT * FROM salas WHERE (? IS NULL OR status = ?) ORDER BY id DESC",
            (status, status),
        ).fetchall()
        consulta = busca.strip().casefold()
        salas = [Sala.de_linha(linha) for linha in linhas]
        return [sala for sala in salas if consulta in
                f"{sala.codigo} {sala.nome} {sala.descricao}".casefold()]

    def atualizar(self, sala_id, nome, descricao="", modo="CLASSICO", status="ABERTA"):
        """Substitui os dados editáveis sem alterar código ou data de criação."""
        nome, descricao = self.validar(nome, descricao, modo, status)
        self.buscar(sala_id)
        try:
            with self.conexao:
                self.conexao.execute("""
                    UPDATE salas SET nome=?, chave_nome=?, descricao=?, modo=?,
                    status=?, atualizada_em=? WHERE id=?
                """, (nome, nome.casefold(), descricao, modo, status,
                      datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                      sala_id))
        except sqlite3.IntegrityError as erro:
            raise ErroValidacaoSala(
                "Já existe uma sala com esse nome. Escolha outro."
            ) from erro
        return self.buscar(sala_id)

    def excluir(self, sala_id):
        """Remove exatamente uma sala e sinaliza concorrência ou ID inválido."""
        with self.conexao:
            cursor = self.conexao.execute("DELETE FROM salas WHERE id = ?", (sala_id,))
            if cursor.rowcount != 1:
                raise SalaNaoEncontrada("Sala não encontrada. Atualize a lista.")

    def fechar(self):
        """Libera explicitamente a conexão com o banco."""
        self.conexao.close()
