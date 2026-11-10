"""Fluxo real de três sessões de navegador contra MySQL de teste."""

import os
import threading
import unittest

from werkzeug.serving import make_server

from backend.taskflow.servico import ServicoTaskFlow
from tests import test_integracao_mysql, test_web


@unittest.skipUnless(
    os.getenv("TASKFLOW_TEST_BROWSER") == "1" and os.getenv("TASKFLOW_TEST_MYSQL") == "1",
    "Navegador e MySQL não solicitados",
)
class TestesNavegador(unittest.TestCase):
    def test_professor_e_dois_alunos_concluem_partida_e_dashboard(self):
        from playwright.sync_api import expect, sync_playwright

        expect.set_options(timeout=20000)

        ambiente = test_integracao_mysql.TestesMySQLReal()
        ambiente.setUp()
        self.addCleanup(ambiente.tearDown)
        ambiente.criar_professor()
        repo = ambiente.app.extensions["taskflow_repositorio"]
        professor = repo.autenticar("PROFESSOR", "professora@web.test", test_web.SENHA_PROFESSOR)
        servico = ServicoTaskFlow(repo, test_web.GeminiFalso())
        servico.usuario_atual = professor
        for numero in (1, 2):
            servico.criar_questao(
                "Soma",
                "FÁCIL",
                f"Quanto é {numero} + {numero}?",
                [str(numero * 2), "8", "9", "10"],
                0,
                "Somamos as parcelas.",
            )
            aluno = ServicoTaskFlow(repo, test_web.GeminiFalso())
            aluno.criar_conta(
                "ALUNO",
                f"Aluno Navegador {numero}",
                f"RA-NAV-{numero}",
                test_web.SENHA_ALUNO,
                test_web.SENHA_ALUNO,
                True,
            )
        servidor = make_server("127.0.0.1", 0, ambiente.app, threaded=True)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()

        def encerrar():
            servidor.shutdown()
            servidor.server_close()
            thread.join(timeout=5)

        self.addCleanup(encerrar)
        url = f"http://127.0.0.1:{servidor.server_port}"
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(
                channel=os.getenv("TASKFLOW_BROWSER_CHANNEL", "msedge")
            )
            try:
                contextos = [navegador.new_context() for _ in range(3)]
                paginas = [contexto.new_page() for contexto in contextos]
                for pagina in paginas:
                    pagina.set_default_timeout(20000)
                for numero, pagina in enumerate(paginas):
                    perfil = "professor" if numero == 0 else "aluno"
                    pagina.goto(f"{url}/login/{perfil}")
                    pagina.locator('[name="identificador"]').fill(
                        "professora@web.test" if numero == 0 else f"RA-NAV-{numero}"
                    )
                    pagina.locator('[name="senha"]').fill(
                        test_web.SENHA_PROFESSOR if numero == 0 else test_web.SENHA_ALUNO
                    )
                    pagina.get_by_role("button", name="Entrar", exact=True).click()
                    pagina.wait_for_url("**/professor" if numero == 0 else "**/aluno")
                painel = paginas[0]
                painel.goto(f"{url}/professor/salas")
                painel.locator('[name="nome"]').fill("Revisão no navegador")
                for opcao in painel.locator('[name="questoes"]').all():
                    opcao.check()
                painel.get_by_role(
                    "button", name="Criar sala com as perguntas selecionadas"
                ).click()
                codigo = repo.listar_salas_professor(professor.id)[0]["sala"].codigo
                for pagina in paginas[1:]:
                    pagina.goto(f"{url}/multijogador")
                    pagina.locator('[name="codigo"]').fill(codigo)
                    pagina.get_by_role("button", name="Entrar pelo código").click()
                for rodada in (1, 2):
                    for pagina in paginas[1:]:
                        expect(pagina.locator(".cabecalho-pagina")).to_contain_text(
                            f"Rodada {rodada}"
                        )
                        pagina.locator('[name="alternativa"][value="0"]').check()
                        pagina.get_by_role("button", name="Responder nesta rodada").click()
                for pagina in paginas[1:]:
                    expect(pagina.locator(".cabecalho-pagina")).to_contain_text(
                        "Partida finalizada"
                    )
                painel.goto(f"{url}/desempenho")
                expect(
                    painel.locator(".dashboard-indicadores article").nth(3).locator("strong")
                ).to_have_text("4")
                expect(
                    painel.locator(".dashboard-indicadores article").nth(2).locator("strong")
                ).to_have_text("100.0%")
                expect(painel.locator("tbody tr")).to_have_count(2)
                # O perfil aluno permanece impedido de abrir o dashboard administrativo.
                resposta = paginas[1].goto(f"{url}/desempenho")
                self.assertEqual(resposta.status, 403)
            finally:
                navegador.close()
