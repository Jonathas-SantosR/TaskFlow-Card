import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.taskflow.dominio import AcessoNegado
from backend.taskflow.servico import ServicoTaskFlow


class TestesDashboard(unittest.TestCase):
    def preparar(self, totais):
        repositorio = Mock()
        repositorio.listar_alunos.return_value = [
            SimpleNamespace(id=i, nome=f"Aluno {i}", ativo=True) for i in range(len(totais))
        ]
        repositorio.listar_desempenho_turma.return_value = [
            dict(aluno_id=i, total=t, acertos=a, pontos=a) for i, (t, a) in enumerate(totais) if t
        ]
        servico = ServicoTaskFlow(repositorio, Mock())
        servico.usuario_atual = SimpleNamespace(eh_professor=True)
        return servico

    def test_media_ponderada_e_alunos_sem_respostas(self):
        d = self.preparar([(1, 1), (9, 0), (0, 0)]).dashboard_pedagogica()
        self.assertEqual(d["aproveitamento"], 10)
        self.assertEqual(d["participacao"], 66.7)
        self.assertEqual(d["erros"], 9)
        self.assertEqual([f["total"] for f in d["faixas"]], [1, 0, 1, 1])

    def test_limites_das_faixas(self):
        d = self.preparar([(10, 8), (10, 5), (10, 4)]).dashboard_pedagogica()
        self.assertEqual([f["total"] for f in d["faixas"]], [1, 1, 1, 0])

    def test_sem_alunos(self):
        d = self.preparar([]).dashboard_pedagogica()
        self.assertEqual((d["participacao"], d["aproveitamento"], d["respostas"]), (0, 0, 0))

    def test_aluno_nao_acessa_dashboard(self):
        servico = self.preparar([])
        servico.usuario_atual = SimpleNamespace(eh_professor=False)
        with self.assertRaises(AcessoNegado):
            servico.dashboard_pedagogica()
