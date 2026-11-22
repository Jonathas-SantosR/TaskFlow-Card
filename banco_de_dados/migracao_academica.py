"""Acrescenta classificação de salas e perfil do aluno sem alterar dados legados."""


def migrar_academico(infraestrutura):
    banco = infraestrutura
    mysql = banco.tipo_banco == "mysql"
    if mysql:
        colunas = {
            linha["Field"]
            for linha in banco.conexao.execute("SHOW COLUMNS FROM salas_multijogador").fetchall()
        }
    else:
        colunas = {
            linha["name"]
            for linha in banco.conexao.execute("PRAGMA table_info(salas_multijogador)").fetchall()
        }
    for coluna, tamanho in (
        ("ano_escolar", 40),
        ("turma", 40),
        ("sala_escolar", 40),
        ("chave_academica", 64),
    ):
        if coluna not in colunas:
            banco.conexao.execute(
                f"ALTER TABLE salas_multijogador ADD COLUMN {coluna} VARCHAR({tamanho}) NULL"
            )
    if mysql:
        indices = {
            linha["Key_name"]
            for linha in banco.conexao.execute("SHOW INDEX FROM salas_multijogador").fetchall()
        }
        if "uq_sala_chave_academica" not in indices:
            banco.conexao.execute(
                "CREATE UNIQUE INDEX uq_sala_chave_academica ON salas_multijogador(chave_academica)"
            )
    else:
        banco.conexao.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_sala_chave_academica ON salas_multijogador(chave_academica)"
        )
    banco.conexao.execute(
        """CREATE TABLE IF NOT EXISTS perfil_aluno (
        aluno_id BIGINT PRIMARY KEY,
        idade INTEGER NOT NULL,
        ano_escolar VARCHAR(40) NOT NULL,
        turma VARCHAR(40) NOT NULL,
        sala_escolar VARCHAR(40) NOT NULL,
        chave_academica VARCHAR(64) NOT NULL,
        atualizado_em VARCHAR(40) NOT NULL
    )"""
        + (" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci" if mysql else "")
    )
    if mysql:
        indices = {
            linha["Key_name"]
            for linha in banco.conexao.execute("SHOW INDEX FROM perfil_aluno").fetchall()
        }
        if "idx_perfil_aluno_classificacao" not in indices:
            banco.conexao.execute(
                "CREATE INDEX idx_perfil_aluno_classificacao ON perfil_aluno(chave_academica)"
            )
    else:
        banco.conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_perfil_aluno_classificacao ON perfil_aluno(chave_academica)"
        )
