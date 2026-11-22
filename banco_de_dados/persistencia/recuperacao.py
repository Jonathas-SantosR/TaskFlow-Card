"""Endereços protegidos e tokens descartáveis de recuperação de senha."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from backend.taskflow.dominio import ErroDominio, normalizar_gmail
from backend.taskflow.seguranca import criar_hash
from banco_de_dados.persistencia.base import RepositorioBase

TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
LINK_INVALIDO = "Link inválido, expirado ou já utilizado. Solicite uma nova recuperação."


def migrar_controle_recuperacao(infraestrutura):
    """Migração 8: cotas e solicitações persistentes, sem guardar Gmail ou IP."""

    conexao = infraestrutura.conexao
    sufixo = (
        " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if infraestrutura.tipo_banco == "mysql" else ""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS limites_recuperacao (
        chave VARCHAR(160) PRIMARY KEY,
        janela_em VARCHAR(40) NOT NULL,
        ultimo_em VARCHAR(40) NOT NULL,
        quantidade INTEGER NOT NULL
    )"""
        + sufixo
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS solicitacoes_recuperacao (
        id VARCHAR(64) PRIMARY KEY,
        chave_conta VARCHAR(128) NOT NULL,
        chave_origem VARCHAR(128) NOT NULL,
        criada_em VARCHAR(40) NOT NULL,
        atualizada_em VARCHAR(40) NOT NULL,
        status VARCHAR(24) NOT NULL,
        codigo_erro VARCHAR(40),
        token_hash VARCHAR(64)
    )"""
        + sufixo
    )
    if infraestrutura.tipo_banco == "mysql":
        indices = {
            r["Key_name"]
            for r in conexao.execute("SHOW INDEX FROM solicitacoes_recuperacao").fetchall()
        }
        if "idx_solicitacoes_recuperacao_data" not in indices:
            conexao.execute(
                "CREATE INDEX idx_solicitacoes_recuperacao_data ON solicitacoes_recuperacao(criada_em)"
            )
    else:
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_solicitacoes_recuperacao_data ON solicitacoes_recuperacao(criada_em)"
        )


class RepositorioRecuperacao(RepositorioBase):
    def __init__(self, infraestrutura, usuarios):
        super().__init__(infraestrutura)
        self.usuarios = usuarios

    def email_do_usuario(self, usuario):
        if usuario is None or not usuario.ativo or usuario.anonimizado:
            return ""
        if usuario.perfil not in {"PROFESSOR", "ALUNO"}:
            return ""
        try:
            return normalizar_gmail(usuario.identificador)
        except ErroDominio:
            return ""

    def salvar_email(self, usuario_id, email, versao_esperada=None):
        raise ErroDominio(
            "A recuperação utiliza somente o Gmail de login. Atualize o cadastro da conta."
        )

    def buscar_destinatario(self, perfil, identificador):
        try:
            identificador = normalizar_gmail(identificador)
        except ErroDominio:
            return None
        if perfil not in {"PROFESSOR", "ALUNO"}:
            return None
        usuario = self.usuarios.buscar_por_login(perfil, identificador)
        email = self.email_do_usuario(usuario)
        return (usuario, email) if email else None

    def reservar_solicitacao(self, gmail, origem="", chave_requisicao="", agora=None):
        """Reserva cotas uma única vez mesmo entre processos e após reiniciar."""

        gmail = normalizar_gmail(gmail)
        agora = agora or datetime.now(timezone.utc)
        instante = agora.isoformat()
        conta = self.criptografia.indice(f"recuperacao:conta:{gmail}")
        origem = self.criptografia.indice(f"recuperacao:origem:{str(origem or 'local')[:200]}")
        nonce = str(chave_requisicao or secrets.token_urlsafe(32))[:256]
        solicitacao_id = hashlib.sha256(
            self.criptografia.indice(f"{conta}|{origem}|{nonce}").encode("ascii")
        ).hexdigest()
        # Todos os processos obtêm os locks nesta ordem. Uma origem bloqueada
        # não cria linhas para cada novo endereço inventado por um cliente.
        cotas = [
            (f"origem:{origem}", 900, 10, 0),
            (f"dia:{conta}", 86400, 10, 0),
            (f"hora:{conta}", 3600, 3, 60),
        ]
        with self._bloqueio:
            try:
                self.conexao.execute("BEGIN IMMEDIATE")
                antigo = self.conexao.execute(
                    "SELECT status FROM solicitacoes_recuperacao WHERE id=?", (solicitacao_id,)
                ).fetchone()
                if antigo:
                    self.conexao.commit()
                    return {"id": solicitacao_id, "nova": False, "status": antigo["status"]}
                registros = []
                for chave, janela, maximo, intervalo in cotas:
                    self.conexao.execute(
                        """INSERT OR IGNORE INTO limites_recuperacao(chave,janela_em,ultimo_em,quantidade)
                        VALUES(?,?,?,0)""",
                        (chave, instante, instante),
                    )
                    sql = "SELECT * FROM limites_recuperacao WHERE chave=?"
                    if self.tipo_banco in {"mysql", "postgres"}:
                        sql += " FOR UPDATE"
                    linha = self.conexao.execute(sql, (chave,)).fetchone()
                    inicio = datetime.fromisoformat(linha["janela_em"])
                    ultimo = datetime.fromisoformat(linha["ultimo_em"])
                    quantidade = (
                        linha["quantidade"] if (agora - inicio).total_seconds() < janela else 0
                    )
                    if quantidade >= maximo or (
                        linha["quantidade"] and (agora - ultimo).total_seconds() < intervalo
                    ):
                        self.conexao.commit()
                        return {"id": None, "nova": False, "status": "LIMITE"}
                    registros.append(
                        (
                            quantidade + 1,
                            instante if not quantidade else linha["janela_em"],
                            instante,
                            chave,
                        )
                    )
                # Releitura após obter os locks: outra conexão pode ter reservado o mesmo clique.
                sql = "SELECT status FROM solicitacoes_recuperacao WHERE id=?"
                if self.tipo_banco in {"mysql", "postgres"}:
                    sql += " FOR UPDATE"
                antigo = self.conexao.execute(sql, (solicitacao_id,)).fetchone()
                if antigo:
                    self.conexao.commit()
                    return {"id": solicitacao_id, "nova": False, "status": antigo["status"]}
                for valores in registros:
                    self.conexao.execute(
                        "UPDATE limites_recuperacao SET quantidade=?,janela_em=?,ultimo_em=? WHERE chave=?",
                        valores,
                    )
                self.conexao.execute(
                    """INSERT INTO solicitacoes_recuperacao
                    (id,chave_conta,chave_origem,criada_em,atualizada_em,status)
                    VALUES(?,?,?,?,?,'SOLICITADO')""",
                    (solicitacao_id, conta, origem, instante, instante),
                )
                self.conexao.execute(
                    "DELETE FROM limites_recuperacao WHERE ultimo_em<?",
                    ((agora - timedelta(days=2)).isoformat(),),
                )
                self.conexao.execute(
                    "DELETE FROM solicitacoes_recuperacao WHERE criada_em<?",
                    ((agora - timedelta(days=7)).isoformat(),),
                )
                self.conexao.commit()
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise
        return {"id": solicitacao_id, "nova": True, "status": "SOLICITADO"}

    def concluir_solicitacao(self, solicitacao_id, status, codigo_erro=None):
        if status not in {"ENVIADO", "FALHOU", "IGNORADO"}:
            raise ValueError("Estado de envio inválido.")
        with self._bloqueio, self.conexao:
            self.conexao.execute(
                """UPDATE solicitacoes_recuperacao SET status=?,codigo_erro=?,atualizada_em=?
                WHERE id=? AND status IN ('SOLICITADO','ENVIANDO')""",
                (status, codigo_erro, self._agora(), solicitacao_id),
            )

    def iniciar_envio(self, solicitacao_id, token):
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self._bloqueio, self.conexao:
            self.conexao.execute("BEGIN IMMEDIATE")
            valido = self.conexao.execute(
                """SELECT t.usuario_id FROM tokens_recuperacao t
                JOIN usuarios u ON u.id=t.usuario_id WHERE t.token_hash=?
                AND t.usado_em IS NULL AND t.expira_em>? AND u.ativo=1
                AND u.anonimizado_em IS NULL AND u.perfil IN ('PROFESSOR','ALUNO')""",
                (token_hash, datetime.now(timezone.utc).isoformat()),
            ).fetchone()
            if not valido:
                return False
            cursor = self.conexao.execute(
                """UPDATE solicitacoes_recuperacao SET status='ENVIANDO',atualizada_em=?
                WHERE id=? AND token_hash=? AND status='SOLICITADO'""",
                (self._agora(), solicitacao_id, token_hash),
            )
            return cursor.rowcount == 1

    def listar_solicitacoes(self, limite=20):
        with self._bloqueio, self.conexao:
            # Processos interrompidos nunca provocam reenvio automático após reiniciar.
            corte = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            self.conexao.execute(
                """UPDATE solicitacoes_recuperacao SET status='INTERROMPIDO',codigo_erro='ENVIO_INTERROMPIDO'
                WHERE status IN ('SOLICITADO','ENVIANDO') AND criada_em<?""",
                (corte,),
            )
            linhas = self.conexao.execute(
                """SELECT criada_em,atualizada_em,status,codigo_erro
                FROM solicitacoes_recuperacao ORDER BY criada_em DESC LIMIT ?""",
                (min(max(int(limite), 1), 100),),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def emitir_token(
        self, usuario_id, email_esperado=None, versao_esperada=None, solicitacao_id=None
    ):
        token = secrets.token_urlsafe(32)
        agora = datetime.now(timezone.utc)
        with self._bloqueio, self.conexao:
            self.conexao.execute("BEGIN IMMEDIATE")
            consulta = "SELECT * FROM usuarios WHERE id=? AND ativo=1 AND anonimizado_em IS NULL"
            if self.tipo_banco in {"mysql", "postgres"}:
                consulta += " FOR UPDATE"
            linha = self.conexao.execute(consulta, (usuario_id,)).fetchone()
            if linha is None:
                raise ErroDominio("Conta indisponível.")
            usuario = self.usuarios._usuario(linha)
            if (versao_esperada is not None and usuario.versao_sessao != versao_esperada) or (
                email_esperado is not None and self.email_do_usuario(usuario) != email_esperado
            ):
                raise ErroDominio("Os dados da conta mudaram. Solicite novamente.")
            self.conexao.execute(
                "DELETE FROM tokens_recuperacao WHERE expira_em<=?", (agora.isoformat(),)
            )
            if solicitacao_id:
                cursor = self.conexao.execute(
                    """UPDATE solicitacoes_recuperacao SET token_hash=?,atualizada_em=?
                    WHERE id=? AND status='SOLICITADO' AND token_hash IS NULL""",
                    (
                        hashlib.sha256(token.encode("ascii")).hexdigest(),
                        agora.isoformat(),
                        solicitacao_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ErroDominio("Esta solicitação já foi processada.")
            self.conexao.execute(
                "UPDATE tokens_recuperacao SET usado_em=? WHERE usuario_id=? AND usado_em IS NULL",
                (agora.isoformat(), usuario_id),
            )
            self.conexao.execute(
                """INSERT INTO tokens_recuperacao(token_hash,usuario_id,expira_em,usado_em)
                VALUES(?,?,?,NULL)""",
                (
                    hashlib.sha256(token.encode("ascii")).hexdigest(),
                    usuario_id,
                    (agora + timedelta(minutes=30)).isoformat(),
                ),
            )
        return token

    def revogar_token(self, token):
        with self._bloqueio, self.conexao:
            self.conexao.execute(
                "UPDATE tokens_recuperacao SET usado_em=? WHERE token_hash=? AND usado_em IS NULL",
                (self._agora(), hashlib.sha256(token.encode("ascii")).hexdigest()),
            )

    def redefinir(self, token, senha):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise ErroDominio(LINK_INVALIDO)
        senha_hash = criar_hash(senha)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        agora = datetime.now(timezone.utc).isoformat()
        with self._bloqueio:
            try:
                self.conexao.execute("BEGIN IMMEDIATE")
                consulta = """SELECT t.usuario_id FROM tokens_recuperacao t
                    JOIN usuarios u ON u.id=t.usuario_id WHERE t.token_hash=?
                    AND t.usado_em IS NULL AND t.expira_em>?
                    AND u.ativo=1 AND u.anonimizado_em IS NULL
                    AND u.perfil IN ('PROFESSOR','ALUNO')"""
                if self.tipo_banco in {"mysql", "postgres"}:
                    consulta += " FOR UPDATE"
                linha = self.conexao.execute(consulta, (token_hash, agora)).fetchone()
                if linha is None:
                    raise ErroDominio(LINK_INVALIDO)
                usuario_id = linha["usuario_id"]
                cursor = self.conexao.execute(
                    """UPDATE tokens_recuperacao SET usado_em=?
                    WHERE token_hash=? AND usado_em IS NULL AND expira_em>?""",
                    (agora, token_hash, agora),
                )
                if cursor.rowcount != 1:
                    raise ErroDominio(LINK_INVALIDO)
                self.conexao.execute(
                    """UPDATE usuarios SET senha_hash=?,
                    versao_sessao=versao_sessao+1 WHERE id=?""",
                    (senha_hash, usuario_id),
                )
                self.conexao.execute(
                    """UPDATE tokens_recuperacao SET usado_em=?
                    WHERE usuario_id=? AND usado_em IS NULL""",
                    (agora, usuario_id),
                )
                self.conexao.commit()
            except Exception:
                if self.conexao.in_transaction:
                    self.conexao.rollback()
                raise
        return self.usuarios.buscar_usuario(usuario_id)
