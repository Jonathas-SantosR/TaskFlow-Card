"""Migração da identidade Gmail, compatível com a versão 6 anterior."""

from collections import Counter
from datetime import datetime, timezone

from backend.taskflow.dominio import ErroDominio, normalizar_gmail


class MigradorIdentidade:
    """Executado depois do carregamento da chave e da proteção dos dados legados."""

    def __init__(self, infraestrutura):
        self.banco = infraestrutura

    def aplicar(self):
        banco = self.banco
        if banco.conexao.execute("SELECT 1 FROM versoes_esquema WHERE versao=10").fetchone():
            return
        anterior = banco.conexao.execute(
            "SELECT descricao FROM versoes_esquema WHERE versao=6"
        ).fetchone()
        if anterior and anterior["descricao"] == "Identidade Gmail única e descontinuação de TI":
            if banco.tipo_banco == "mysql":
                colunas = {
                    linha["Field"]
                    for linha in banco.conexao.execute("SHOW COLUMNS FROM usuarios").fetchall()
                }
            else:
                colunas = {
                    linha["name"]
                    for linha in banco.conexao.execute("PRAGMA table_info(usuarios)").fetchall()
                }
            if {"chave_login_global", "identificador_legado"} <= colunas:
                return
        # A versão anterior usava o número 6 para outra migração. Preservamos
        # seu histórico e registramos a identidade Gmail como versão 10.
        versao_identidade = 10 if anterior else 6
        self._preparar_esquema()
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with banco._bloqueio:
            try:
                banco.conexao.execute("BEGIN IMMEDIATE")
                consulta = """SELECT u.*, e.email AS email_recuperacao FROM usuarios u
                    LEFT JOIN emails_recuperacao e ON e.usuario_id=u.id
                    WHERE u.anonimizado_em IS NULL"""
                if banco.tipo_banco == "mysql":
                    consulta += " FOR UPDATE"
                linhas = banco.conexao.execute(consulta).fetchall()
                candidatos = {}
                for linha in linhas:
                    if linha["perfil"] not in {"PROFESSOR", "ALUNO"}:
                        continue
                    identificador = banco.criptografia.descriptografar(linha["identificador"])
                    enderecos = [identificador]
                    if linha["email_recuperacao"]:
                        enderecos.append(
                            banco.criptografia.descriptografar(linha["email_recuperacao"])
                        )
                    for endereco in enderecos:
                        try:
                            candidatos[linha["id"]] = normalizar_gmail(endereco)
                            break
                        except ErroDominio:
                            continue
                quantidades = Counter(candidatos.values())
                for email, total in quantidades.items():
                    if total > 1:
                        banco.conexao.execute(
                            "INSERT OR IGNORE INTO conflitos_identidade(chave_email) VALUES (?)",
                            (banco.criptografia.indice(email),),
                        )
                for linha in linhas:
                    usuario_id = linha["id"]
                    gmail = candidatos.get(usuario_id)
                    if linha["perfil"] == "TI":
                        # Preserva nome, perfil e vínculos do histórico; revoga só o acesso.
                        banco.conexao.execute(
                            "UPDATE usuarios SET ativo=0,versao_sessao=versao_sessao+1 WHERE id=?",
                            (usuario_id,),
                        )
                    elif gmail and quantidades[gmail] == 1:
                        chave = banco.criptografia.indice(gmail)
                        banco.conexao.execute(
                            """UPDATE usuarios SET
                            identificador_legado=COALESCE(identificador_legado,identificador),
                            identificador=?,chave_identificador=?,chave_login_global=?,
                            versao_sessao=versao_sessao+1 WHERE id=?""",
                            (banco.criptografia.criptografar(gmail), chave, chave, usuario_id),
                        )
                    else:
                        # Contas sem endereço válido ou em conflito aguardam o próprio titular.
                        banco.conexao.execute(
                            "UPDATE usuarios SET versao_sessao=versao_sessao+1 WHERE id=?",
                            (usuario_id,),
                        )
                    banco.conexao.execute(
                        """UPDATE tokens_recuperacao SET usado_em=?
                        WHERE usuario_id=? AND usado_em IS NULL""",
                        (agora, usuario_id),
                    )
                banco.conexao.execute(
                    "INSERT INTO versoes_esquema VALUES (?,?,?)",
                    (versao_identidade, "Identidade Gmail única e descontinuação de TI", agora),
                )
                banco.conexao.commit()
            except Exception:
                if banco.conexao.in_transaction:
                    banco.conexao.rollback()
                raise

    def _preparar_esquema(self):
        banco = self.banco
        if banco.tipo_banco == "mysql":
            colunas = {
                linha["Field"]
                for linha in banco.conexao.execute("SHOW COLUMNS FROM usuarios").fetchall()
            }
            indices = {
                linha["Key_name"]
                for linha in banco.conexao.execute("SHOW INDEX FROM usuarios").fetchall()
            }
        else:
            colunas = {
                linha["name"]
                for linha in banco.conexao.execute("PRAGMA table_info(usuarios)").fetchall()
            }
            indices = {
                linha["name"]
                for linha in banco.conexao.execute("PRAGMA index_list(usuarios)").fetchall()
            }
        if "chave_login_global" not in colunas:
            banco.conexao.execute("ALTER TABLE usuarios ADD COLUMN chave_login_global VARCHAR(128)")
        if "identificador_legado" not in colunas:
            banco.conexao.execute("ALTER TABLE usuarios ADD COLUMN identificador_legado TEXT")
        if "uq_login_global" not in indices:
            banco.conexao.execute(
                "CREATE UNIQUE INDEX uq_login_global ON usuarios(chave_login_global)"
            )
        sufixo = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if banco.tipo_banco == "mysql" else ""
        banco.conexao.execute(
            "CREATE TABLE IF NOT EXISTS conflitos_identidade (chave_email VARCHAR(128) PRIMARY KEY)"
            + sufixo
        )
