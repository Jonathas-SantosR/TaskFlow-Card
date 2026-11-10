"""Regressões de identidade e autorização na composição dos serviços."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.taskflow.dominio import AcessoNegado
from backend.taskflow.servico import ServicoTaskFlow


class TestesServicosModulares(unittest.TestCase):
    def setUp(self):
        self.repositorio = Mock()
        self.servico = ServicoTaskFlow(self.repositorio, Mock())
        self.professor = SimpleNamespace(
            id=1, perfil="PROFESSOR", eh_professor=True, eh_aluno=False, primeiro_acesso=False
        )
        self.aluno = SimpleNamespace(
            id=2, perfil="ALUNO", eh_professor=False, eh_aluno=True, primeiro_acesso=False
        )

    def test_login_e_logout_atualizam_autorizacao_em_todos_os_servicos(self):
        self.repositorio.autenticar.return_value = self.professor
        self.repositorio.listar_questoes.return_value = ["questao"]
        self.servico.login("PROFESSOR", "professor", "senha")
        self.assertEqual(self.servico.questoes.listar_questoes(), ["questao"])
        self.servico.logout()
        with self.assertRaises(AcessoNegado):
            self.servico.questoes.listar_questoes()
        with self.assertRaises(AcessoNegado):
            self.servico.salas.listar_salas_professor()

    def test_identidade_nao_vaza_entre_servicos_de_requisicoes_diferentes(self):
        outro = ServicoTaskFlow(self.repositorio, Mock())
        self.servico.usuario_atual = self.professor
        with self.assertRaises(AcessoNegado):
            outro.listar_questoes()
        self.assertIsNone(outro.usuario_atual)

    def test_consulta_de_alunos_exige_professor_antes_de_acessar_banco(self):
        self.servico.usuario_atual = self.aluno
        with self.assertRaises(AcessoNegado):
            self.servico.buscar_aluno(2)
        self.repositorio.buscar_usuario.assert_not_called()

    def test_questao_inativa_nao_e_retornada_ao_aluno(self):
        questao = SimpleNamespace(ativa=False)
        self.repositorio.buscar_questao.return_value = questao
        self.servico.usuario_atual = self.aluno
        self.assertIsNone(self.servico.buscar_questao(1))
        self.servico.usuario_atual = self.professor
        self.assertIs(self.servico.buscar_questao(1), questao)

    def test_consulta_anonima_nao_acessa_questoes(self):
        with self.assertRaises(AcessoNegado):
            self.servico.buscar_questao(1)
        self.repositorio.buscar_questao.assert_not_called()
