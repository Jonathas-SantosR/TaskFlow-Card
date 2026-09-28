from dataclasses import fields, is_dataclass
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask.views import MethodView

from app import criar_aplicacao
from taskflow.dominio import (
    Desempenho,
    PERFIL_ALUNO,
    PERFIL_PROFESSOR,
    Questao,
    ResultadoResposta,
    Usuario,
)
from taskflow.web import (
    AplicacaoTaskFlowWeb,
    ControladorBase,
    ControladorProtegido,
    DependenciasWeb,
    GerenciadorSessao,
    ProtecaoCsrf,
    VisaoAlunos,
    VisaoLogin,
)


class TestesOrientacaoObjetos(unittest.TestCase):
    def test_usuario_e_entidade_com_comportamento(self):
        usuario = Usuario(1, PERFIL_PROFESSOR, "prof@teste.local", "Professor", True, "agora")
        self.assertTrue(is_dataclass(usuario))
        self.assertTrue(usuario.eh_professor)
        self.assertFalse(usuario.eh_aluno)
        self.assertIn("primeiro_acesso", {campo.name for campo in fields(usuario)})

        aluno = Usuario(2, PERFIL_ALUNO, "RA-1", "Aluno", True, "agora")
        self.assertTrue(aluno.eh_aluno)
        self.assertFalse(aluno.eh_professor)

    def test_controladores_web_usam_heranca_do_flask(self):
        self.assertTrue(issubclass(ControladorBase, MethodView))
        self.assertTrue(issubclass(ControladorProtegido, ControladorBase))
        self.assertTrue(issubclass(VisaoLogin, ControladorBase))
        self.assertTrue(issubclass(VisaoAlunos, ControladorProtegido))

    def test_modulo_pedagogico_usa_entidades_de_dominio(self):
        questao = Questao(
            1,
            1,
            "Matemática",
            "FÁCIL",
            "Quanto é 1 + 1?",
            ("1", "2", "3", "4"),
            1,
            "O resultado é dois.",
            "Correto.",
            "Tente novamente.",
            "agora",
        )
        self.assertTrue(is_dataclass(questao))
        self.assertEqual(questao.alternativa_correta, "2")
        self.assertEqual(questao.pontos, 1)
        self.assertTrue(is_dataclass(ResultadoResposta))
        self.assertTrue(is_dataclass(Desempenho))

    def test_responsabilidades_estao_em_classes_separadas(self):
        self.assertTrue(is_dataclass(DependenciasWeb))
        self.assertTrue(hasattr(GerenciadorSessao, "usuario_atual"))
        self.assertTrue(hasattr(ProtecaoCsrf, "validar_requisicao"))
        self.assertTrue(hasattr(AplicacaoTaskFlowWeb, "_registrar_rotas"))

    def test_fabrica_cria_instancias_independentes(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            primeira = criar_aplicacao({
                "TESTING": True, "SECRET_KEY": "primeira",
                "BANCO": raiz / "primeira.sqlite3",
            })
            segunda = criar_aplicacao({
                "TESTING": True, "SECRET_KEY": "segunda",
                "BANCO": raiz / "segunda.sqlite3",
            })
            try:
                self.assertIsNot(primeira, segunda)
                self.assertIsNot(
                    primeira.extensions["taskflow_repositorio"],
                    segunda.extensions["taskflow_repositorio"],
                )
            finally:
                primeira.extensions["taskflow_repositorio"].fechar()
                segunda.extensions["taskflow_repositorio"].fechar()

    def test_execucao_normal_configura_mysql_obrigatoriamente(self):
        configuracao_mysql = {
            "host": "mysql.local", "port": 3306, "user": "taskflow",
            "password": "segredo-de-teste", "database": "taskflowcards",
        }
        with patch("taskflow.web.RepositorioTaskFlow") as classe_repositorio:
            criar_aplicacao({
                "SECRET_KEY": "segredo-da-sessao",
                "MYSQL": configuracao_mysql,
            })
        argumentos = classe_repositorio.call_args.kwargs
        self.assertEqual(argumentos["configuracao_mysql"], configuracao_mysql)
        self.assertIsNotNone(argumentos["configuracao_mysql"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
