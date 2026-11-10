import unittest

from banco_de_dados.banco import ESQUEMA_MYSQL, ConexaoMySQL, adaptar_sql_mysql


class CursorFalso:
    def __init__(self):
        self.chamadas = []
        self.lastrowid = 0
        self.rowcount = 0

    def execute(self, *argumentos):
        self.chamadas.append(argumentos)


class ConexaoFalsa:
    def __init__(self):
        self.cursor_criado = CursorFalso()

    def cursor(self):
        return self.cursor_criado


class TestesCompatibilidadeMySQL(unittest.TestCase):
    def test_consulta_sem_parametros_preserva_percentual_literal(self):
        conexao_falsa = ConexaoFalsa()
        conexao = ConexaoMySQL(conexao_falsa, RuntimeError)
        conexao.execute("SELECT 1 WHERE 'enc:v1:dado' LIKE 'enc:v1:%'")
        chamada = conexao_falsa.cursor_criado.chamadas[0]
        self.assertEqual(len(chamada), 1)
        self.assertIn("LIKE 'enc:v1:%'", chamada[0])

    def test_adapta_marcadores_funcoes_e_insercao_ignorada(self):
        consulta = """INSERT OR IGNORE INTO participantes_multijogador
        (sala_id,aluno_id) SELECT ?,? ORDER BY RANDOM()"""
        adaptada = adaptar_sql_mysql(consulta)
        self.assertIn("INSERT IGNORE", adaptada)
        self.assertIn("SELECT %s,%s", adaptada)
        self.assertIn("ORDER BY RAND()", adaptada)
        self.assertNotIn("?", adaptada)

    def test_esquema_mysql_usa_innodb_utf8mb4_e_chaves_unicas(self):
        self.assertIn("ENGINE=InnoDB", ESQUEMA_MYSQL)
        self.assertIn("DEFAULT CHARSET=utf8mb4", ESQUEMA_MYSQL)
        self.assertIn("AUTO_INCREMENT", ESQUEMA_MYSQL)
        self.assertIn("UNIQUE (perfil, chave_identificador)", ESQUEMA_MYSQL)
        self.assertIn("UNIQUE (professor_unico)", ESQUEMA_MYSQL)
        self.assertIn("GENERATED ALWAYS AS", ESQUEMA_MYSQL)
        self.assertIn("PRIMARY KEY (sala_id, rodada, aluno_id)", ESQUEMA_MYSQL)
        self.assertIn("nome VARCHAR(80) NOT NULL", ESQUEMA_MYSQL)


if __name__ == "__main__":
    unittest.main()
