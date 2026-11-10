"""Testes opcionais em bancos novos; nunca usam o banco normal da aplicação."""

import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.app import criar_aplicacao
from backend.taskflow.dominio import ErroDominio
from backend.taskflow.servico import ServicoTaskFlow
from banco_de_dados.backup import criar_backup, restaurar_backup
from banco_de_dados.repositorio import RepositorioTaskFlow
from tests import test_web


@unittest.skipUnless(os.getenv("TASKFLOW_TEST_MYSQL") == "1", "MySQL isolado não solicitado")
class TestesMySQLReal(test_web.TestesWeb):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.config_mysql = {
            "host": os.environ["TASKFLOW_TEST_MYSQL_HOST"],
            "port": int(os.environ["TASKFLOW_TEST_MYSQL_PORT"]),
            "user": os.environ["TASKFLOW_TEST_MYSQL_USER"],
            "password": os.environ.get("TASKFLOW_TEST_MYSQL_PASSWORD", ""),
            "database": "taskflow_teste_" + uuid.uuid4().hex,
        }
        self.app = criar_aplicacao(
            {
                "TESTING": True,
                "SECRET_KEY": "teste-sem-dados-reais",
                "BANCO": Path(self.temporario.name) / "local",
                "MYSQL": self.config_mysql,
                "GEMINI": test_web.GeminiFalso(),
                "CODIGO_CONFIGURACAO_PROFESSOR": test_web.CODIGO_CONFIGURACAO,
            }
        )
        self.cliente = self.app.test_client()

    def tearDown(self):
        repositorio = self.app.extensions["taskflow_repositorio"]
        try:
            # Nome criado por este teste, não recebido do usuário.
            repositorio.conexao.execute(f"DROP DATABASE `{self.config_mysql['database']}`")
        finally:
            repositorio.fechar()
            self.temporario.cleanup()

    def test_mysql_real_rollback_e_migracoes_idempotentes(self):
        repo = self.app.extensions["taskflow_repositorio"]
        self.assertEqual(repo.tipo_banco, "mysql")
        with self.assertRaises(RuntimeError):
            with repo.conexao:
                repo.conexao.execute("INSERT INTO versoes_esquema VALUES (999,'teste','agora')")
                raise RuntimeError("simulação de falha")
        self.assertIsNone(
            repo.conexao.execute("SELECT * FROM versoes_esquema WHERE versao=999").fetchone()
        )
        outro = RepositorioTaskFlow(repo.caminho, configuracao_mysql=self.config_mysql)
        try:
            self.assertEqual(
                len(outro.conexao.execute("SELECT * FROM versoes_esquema").fetchall()), 3
            )
        finally:
            outro.fechar()

    def test_backup_restaurado_preserva_login_criptografia_e_auditoria(self):
        self.criar_professor()
        repo = self.app.extensions["taskflow_repositorio"]
        raiz = Path(self.temporario.name)
        pacote = raiz / "backup.zip"
        criar_backup(self.config_mysql, raiz, pacote)
        destino = dict(self.config_mysql, database="taskflow_teste_" + uuid.uuid4().hex)
        chaves = raiz / "restaurado"
        restaurar_backup(destino, pacote, chaves)
        restaurado = RepositorioTaskFlow(chaves / "local", configuracao_mysql=destino)
        try:
            professor = restaurado.autenticar(
                "PROFESSOR", "professora@web.test", test_web.SENHA_PROFESSOR
            )
            self.assertEqual(professor.nome, "Professora Web")
            self.assertEqual(len(restaurado.listar_eventos()), len(repo.listar_eventos()))
            self.assertTrue(all(evento["integridade"] for evento in restaurado.listar_eventos()))
            with self.assertRaises(ValueError):
                restaurar_backup(destino, pacote, raiz / "outras_chaves")
        finally:
            restaurado.conexao.execute(f"DROP DATABASE `{destino['database']}`")
            restaurado.fechar()

    def test_respostas_simultaneas_nao_duplicam_pontos(self):
        self.criar_professor()
        repo = self.app.extensions["taskflow_repositorio"]
        professor = repo.autenticar("PROFESSOR", "professora@web.test", test_web.SENHA_PROFESSOR)
        servico = ServicoTaskFlow(repo, test_web.GeminiFalso())
        servico.usuario_atual = professor
        questao = servico.criar_questao(
            "Soma", "FÁCIL", "Quanto é 2 + 2?", ["4", "5", "6", "7"], 0, "Somamos duas parcelas."
        )
        sala = servico.criar_sala_multijogador("Teste concorrente", [questao.id])
        jogadores = []
        for numero in range(2):
            jogador = ServicoTaskFlow(repo, test_web.GeminiFalso())
            jogador.criar_conta(
                "ALUNO",
                f"Aluno {numero}",
                f"RA-{numero}",
                test_web.SENHA_ALUNO,
                test_web.SENHA_ALUNO,
                True,
            )
            jogador.entrar_sala_multijogador(sala.codigo)
            jogadores.append(jogador)

        def responder():
            try:
                jogadores[0].responder_sala_multijogador(sala.codigo, 0)
                return True
            except ErroDominio:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda _: responder(), range(2)))
        self.assertEqual(sum(resultados), 1)
        registro = repo.conexao.execute(
            "SELECT COUNT(*) AS total FROM respostas_multijogador"
        ).fetchone()
        self.assertEqual(registro["total"], 1)
