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


def migrar_salas_por_disciplina(banco):
    """Abre a turma a várias salas e mantém o histórico anterior sem atribuição."""
    conexao = banco.conexao
    if banco.tipo_banco == "mysql":
        colunas_sala = {linha["Field"] for linha in conexao.execute(
            "SHOW COLUMNS FROM salas_multijogador"
        ).fetchall()}
        colunas_tentativas = {linha["Field"] for linha in conexao.execute(
            "SHOW COLUMNS FROM tentativas"
        ).fetchall()}
    elif banco.tipo_banco == "postgres":
        colunas = conexao.execute(
            """SELECT table_name, column_name FROM information_schema.columns
               WHERE table_schema=current_schema()
               AND table_name IN ('salas_multijogador','tentativas')"""
        ).fetchall()
        colunas_sala = {l["column_name"] for l in colunas if l["table_name"] == "salas_multijogador"}
        colunas_tentativas = {l["column_name"] for l in colunas if l["table_name"] == "tentativas"}
    else:
        colunas_sala = {l["name"] for l in conexao.execute(
            "PRAGMA table_info(salas_multijogador)"
        ).fetchall()}
        colunas_tentativas = {l["name"] for l in conexao.execute(
            "PRAGMA table_info(tentativas)"
        ).fetchall()}

    if "disciplina" not in colunas_sala:
        conexao.execute("ALTER TABLE salas_multijogador ADD COLUMN disciplina VARCHAR(60)")
    if "sala_id" not in colunas_tentativas:  # As tentativas antigas ficam sem sala atribuída.
        conexao.execute("ALTER TABLE tentativas ADD COLUMN sala_id BIGINT")

    indices = (
        ("salas_multijogador", "idx_salas_chave_academica", "chave_academica"),
        ("tentativas", "idx_tentativas_sala_modo", "sala_id,modo,aluno_id"),
        ("auditoria", "idx_auditoria_ocorrido_em", "ocorrido_em"),
    )
    for tabela, nome, campos in indices:
        if banco.tipo_banco == "mysql":
            existentes = {linha["Key_name"] for linha in conexao.execute(
                f"SHOW INDEX FROM {tabela}"
            ).fetchall()}
            if nome not in existentes:
                campos_mysql = "ocorrido_em(40)" if tabela == "auditoria" else campos
                conexao.execute(f"CREATE INDEX {nome} ON {tabela}({campos_mysql})")
            if tabela == "salas_multijogador" and "uq_sala_chave_academica" in existentes:
                conexao.execute("DROP INDEX uq_sala_chave_academica ON salas_multijogador")
        else:
            conexao.execute(f"CREATE INDEX IF NOT EXISTS {nome} ON {tabela}({campos})")
    if banco.tipo_banco != "mysql":
        conexao.execute("DROP INDEX IF EXISTS uq_sala_chave_academica")
