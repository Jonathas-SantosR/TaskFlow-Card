from pathlib import Path
import tempfile
import unittest

from app import criar_aplicacao


SENHA_PROFESSOR = "Professor!2026"
SENHA_ALUNO = "Estudante!2026"
NOVA_SENHA = "NovaSenha!2026"
CODIGO = "Recuperar!2026"
CODIGO_CONFIGURACAO = "InstalarProfessor!2026"


class GeminiFalso:
    def gerar_questao(self, tema, dificuldade):
        return {
            "enunciado": f"Questão sobre {tema}",
            "alternativas": ["A", "B", "C", "D"],
            "indice_correto": 1,
            "explicacao": f"Nível {dificuldade}",
            "feedback_acerto": "Muito bem.",
            "feedback_erro": "Revise a explicação.",
        }

    def adaptar_questao(self, questao, dificuldade):
        return {
            "enunciado": f"{questao.enunciado} ({dificuldade})",
            "alternativas": list(questao.alternativas),
            "indice_correto": questao.indice_correto,
            "explicacao": questao.explicacao,
            "feedback_acerto": "Muito bem.",
            "feedback_erro": "Tente novamente.",
        }

    def gerar_narracao(self, questao):
        return b"RIFFaudio-falso", "audio/wav"


class TestesWeb(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        banco = Path(self.temporario.name) / "web.sqlite3"
        self.app = criar_aplicacao({
            "TESTING": True,
            "SECRET_KEY": "segredo-exclusivo-dos-testes",
            "BANCO": banco,
            "GEMINI": GeminiFalso(),
            "CODIGO_CONFIGURACAO_PROFESSOR": CODIGO_CONFIGURACAO,
        })
        self.cliente = self.app.test_client()

    def tearDown(self):
        self.app.extensions["taskflow_repositorio"].fechar()
        self.temporario.cleanup()

    def csrf(self):
        with self.cliente.session_transaction() as sessao:
            return sessao["csrf"]

    def criar_professor(self):
        self.cliente.get("/")
        return self.cliente.post("/criar-conta/professor", data={
            "csrf": self.csrf(),
            "nome": "Professora Web",
            "identificador": "professora@web.test",
            "senha": SENHA_PROFESSOR,
            "confirmacao": SENHA_PROFESSOR,
            "codigo_configuracao": CODIGO_CONFIGURACAO,
            "aceitou": "1",
        })

    def sair(self):
        return self.cliente.post("/sair", data={"csrf": self.csrf()})

    def test_inicio_mostra_perfis_e_termos_sao_pagina_informativa(self):
        resposta = self.cliente.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b"Escolha seu perfil", resposta.data)
        termos = self.cliente.get("/termos")
        self.assertEqual(termos.status_code, 200)
        self.assertIn(b"Termos de Uso e Pol", termos.data)
        self.assertIn(b"PBKDF2-HMAC-SHA256", termos.data)
        self.assertIn(b"Google Gemini", termos.data)
        self.assertIn(b"Direitos do titular", termos.data)
        resposta = self.cliente.post("/criar-conta/professor", data={})
        self.assertEqual(resposta.status_code, 400)

    def test_cadastro_exige_checkbox_legal_e_paginas_tem_voltar(self):
        self.cliente.get("/")
        pagina = self.cliente.get("/criar-conta/professor")
        self.assertIn(b'name="aceitou"', pagina.data)
        self.assertIn(b'name="codigo_configuracao"', pagina.data)
        self.assertIn(b"required", pagina.data)
        self.assertIn(b"data-voltar", pagina.data)
        resposta = self.cliente.post("/criar-conta/professor", data={
            "csrf": self.csrf(), "nome": "Professora Sem Aceite",
            "identificador": "sem-aceite@web.test", "senha": SENHA_PROFESSOR,
            "confirmacao": SENHA_PROFESSOR,
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Leia e aceite".encode(), resposta.data)
        self.assertFalse(
            self.app.extensions["taskflow_repositorio"].possui_professor()
        )

    def test_primeiro_professor_exige_codigo_privado_de_configuracao(self):
        self.cliente.get("/")
        resposta = self.cliente.post("/criar-conta/professor", data={
            "csrf": self.csrf(), "nome": "Professor Não Autorizado",
            "identificador": "intruso@web.test", "senha": SENHA_PROFESSOR,
            "confirmacao": SENHA_PROFESSOR, "codigo_configuracao": "incorreto",
            "aceitou": "1",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Código de configuração".encode(), resposta.data)
        self.assertFalse(
            self.app.extensions["taskflow_repositorio"].possui_professor()
        )

    def test_cadastro_e_login_do_professor(self):
        resposta = self.criar_professor()
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta.location.endswith("/professor"))
        pagina = self.cliente.get("/professor")
        self.assertIn(b"Painel administrativo", pagina.data)
        self.sair()
        pagina = self.cliente.get("/login/professor")
        self.assertNotIn(b'name="aceitou"', pagina.data)
        self.assertNotIn(b"Criar conta", pagina.data)
        self.assertIn(b"conta respons", pagina.data)
        self.assertIn(b"data-voltar", pagina.data)
        cadastro_bloqueado = self.cliente.get("/criar-conta/professor")
        self.assertEqual(cadastro_bloqueado.status_code, 302)
        self.assertTrue(cadastro_bloqueado.location.endswith("/login/professor"))
        resposta = self.cliente.post("/login/professor", data={
            "csrf": self.csrf(), "identificador": "professora@web.test",
            "senha": SENHA_PROFESSOR,
        })
        self.assertTrue(resposta.location.endswith("/professor"))

    def test_seguranca_descreve_requisitos_do_codigo_de_recuperacao(self):
        self.criar_professor()
        pagina = self.cliente.get("/seguranca")
        self.assertEqual(pagina.status_code, 200)
        self.assertIn(b"12 e 128 caracteres", pagina.data)
        self.assertIn("letra maiúscula".encode(), pagina.data)
        self.assertIn(b"pelo menos um n", pagina.data)
        self.assertIn(b'minlength="12"', pagina.data)

    def test_aluno_pode_criar_a_propria_conta(self):
        self.cliente.get("/")
        pagina = self.cliente.get("/login/aluno")
        self.assertIn(b"Criar conta", pagina.data)
        self.assertNotIn(b'name="aceitou"', pagina.data)
        resposta = self.cliente.post("/criar-conta/aluno", data={
            "csrf": self.csrf(), "nome": "Aluno Autocadastro",
            "identificador": "RA-AUTO", "senha": SENHA_ALUNO,
            "confirmacao": SENHA_ALUNO, "aceitou": "1",
        })
        self.assertTrue(resposta.location.endswith("/aluno"))
        self.assertIn(b"Aluno Autocadastro", self.cliente.get("/aluno").data)

    def test_aluno_troca_senha_no_primeiro_login(self):
        self.criar_professor()
        resposta = self.cliente.post("/alunos", data={
            "csrf": self.csrf(), "nome": "Aluno Web", "matricula": "RA-WEB",
            "senha": SENHA_ALUNO, "confirmacao": SENHA_ALUNO,
        })
        self.assertTrue(resposta.location.endswith("/alunos"))
        self.sair()
        resposta = self.cliente.post("/login/aluno", data={
            "csrf": self.csrf(), "identificador": "RA-WEB", "senha": SENHA_ALUNO,
        })
        self.assertTrue(resposta.location.endswith("/primeiro-login"))
        self.assertTrue(self.cliente.get("/aluno").location.endswith("/primeiro-login"))
        resposta = self.cliente.post("/primeiro-login", data={
            "csrf": self.csrf(), "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA,
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Leia e aceite".encode(), resposta.data)
        self.assertTrue(self.cliente.get("/aluno").location.endswith("/primeiro-login"))
        resposta = self.cliente.post("/primeiro-login", data={
            "csrf": self.csrf(), "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA,
            "aceitou": "1",
        })
        self.assertTrue(resposta.location.endswith("/aluno"))
        self.assertIn(b"Aluno Web", self.cliente.get("/aluno").data)
        self.assertEqual(self.cliente.get("/auditoria").status_code, 403)

    def test_professor_redefine_senha_do_aluno(self):
        self.criar_professor()
        self.cliente.post("/alunos", data={
            "csrf": self.csrf(), "nome": "Aluno Recuperar", "matricula": "RA-REC",
            "senha": SENHA_ALUNO, "confirmacao": SENHA_ALUNO,
        })
        aluno = self.app.extensions["taskflow_repositorio"].listar_alunos()[0]
        resposta = self.cliente.post(f"/alunos/{aluno.id}/senha", data={
            "csrf": self.csrf(), "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA,
        })
        self.assertTrue(resposta.location.endswith("/alunos"))
        self.sair()
        resposta = self.cliente.post("/login/aluno", data={
            "csrf": self.csrf(), "identificador": "RA-REC", "senha": NOVA_SENHA,
        })
        self.assertTrue(resposta.location.endswith("/primeiro-login"))

    def test_recuperacao_do_professor(self):
        self.criar_professor()
        self.cliente.post("/seguranca", data={
            "csrf": self.csrf(), "codigo": CODIGO, "confirmacao": CODIGO,
        })
        self.sair()
        resposta = self.cliente.post("/recuperar-professor", data={
            "csrf": self.csrf(), "email": "professora@web.test", "codigo": CODIGO,
            "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA,
        })
        self.assertTrue(resposta.location.endswith("/login/professor"))
        resposta = self.cliente.post("/login/professor", data={
            "csrf": self.csrf(), "identificador": "professora@web.test", "senha": NOVA_SENHA,
        })
        self.assertTrue(resposta.location.endswith("/professor"))

    def test_professor_gera_questao_com_gemini(self):
        self.criar_professor()
        resposta = self.cliente.post("/ia", data={
            "csrf": self.csrf(), "tema": "matemática", "dificuldade": "FÁCIL",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Questão sobre matemática".encode(), resposta.data)
        self.assertIn(b"N\xc3\xadvel F\xc3\x81CIL", resposta.data)

    def test_professor_cadastra_e_edita_banco_de_questoes(self):
        self.criar_professor()
        resposta = self.cliente.post("/questoes", data={
            "csrf": self.csrf(),
            "tema": "Matemática",
            "dificuldade": "MÉDIO",
            "enunciado": "Quanto é dois mais dois?",
            "alternativa_0": "Três",
            "alternativa_1": "Quatro",
            "alternativa_2": "Cinco",
            "alternativa_3": "Seis",
            "indice_correto": "1",
            "explicacao": "Dois mais dois resulta em quatro.",
            "feedback_acerto": "Muito bem.",
            "feedback_erro": "Observe a operação.",
        })
        self.assertTrue(resposta.location.endswith("/questoes"))
        pagina = self.cliente.get("/questoes")
        self.assertIn("Quanto é dois mais dois?".encode(), pagina.data)
        repositorio = self.app.extensions["taskflow_repositorio"]
        questao = repositorio.listar_questoes()[0]
        resposta = self.cliente.post(f"/questoes/{questao.id}/editar", data={
            "csrf": self.csrf(),
            "tema": "Matemática",
            "dificuldade": "DIFÍCIL",
            "enunciado": "Quanto é dois elevado à terceira potência?",
            "alternativa_0": "Quatro",
            "alternativa_1": "Seis",
            "alternativa_2": "Oito",
            "alternativa_3": "Dez",
            "indice_correto": "2",
            "explicacao": "Dois ao cubo é oito.",
            "feedback_acerto": "Correto.",
            "feedback_erro": "Revise potenciação.",
        })
        self.assertTrue(resposta.location.endswith("/questoes"))
        self.assertEqual(
            repositorio.buscar_questao(questao.id).dificuldade, "DIFÍCIL"
        )

    def test_aluno_joga_recebe_feedback_e_professor_ve_desempenho(self):
        self.criar_professor()
        self.cliente.post("/questoes", data={
            "csrf": self.csrf(), "tema": "Ciências", "dificuldade": "FÁCIL",
            "enunciado": "Qual planeta habitamos?", "alternativa_0": "Marte",
            "alternativa_1": "Terra", "alternativa_2": "Vênus",
            "alternativa_3": "Júpiter", "indice_correto": "1",
            "explicacao": "Habitamos o planeta Terra.",
            "feedback_acerto": "Resposta correta.",
            "feedback_erro": "Nosso planeta é a Terra.",
        })
        self.cliente.post("/alunos", data={
            "csrf": self.csrf(), "nome": "Aluno Jogador", "matricula": "RA-JOGO",
            "senha": SENHA_ALUNO, "confirmacao": SENHA_ALUNO,
        })
        self.sair()
        self.cliente.post("/login/aluno", data={
            "csrf": self.csrf(), "identificador": "RA-JOGO", "senha": SENHA_ALUNO,
        })
        self.cliente.post("/primeiro-login", data={
            "csrf": self.csrf(), "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA,
            "aceitou": "1",
        })
        repositorio = self.app.extensions["taskflow_repositorio"]
        questao = repositorio.listar_questoes()[0]
        resposta = self.cliente.post("/jogar/bot", data={
            "csrf": self.csrf(),
            "questao_id": str(questao.id),
            "alternativa": "1",
        })
        self.assertIn("Acertou!".encode(), resposta.data)
        self.assertIn(b"+1 ponto", resposta.data)
        self.assertIn(b"Resultado do bot", resposta.data)
        self.sair()
        self.cliente.post("/login/professor", data={
            "csrf": self.csrf(),
            "identificador": "professora@web.test",
            "senha": SENHA_PROFESSOR,
        })
        pagina = self.cliente.get("/desempenho")
        self.assertIn("Aluno Jogador".encode(), pagina.data)
        self.assertIn(b"100%", pagina.data)

    def test_professor_cria_sala_e_aluno_entra_pelo_codigo(self):
        self.criar_professor()
        self.cliente.post("/questoes", data={
            "csrf": self.csrf(), "tema": "História", "dificuldade": "FÁCIL",
            "enunciado": "Em qual continente fica o Brasil?",
            "alternativa_0": "América", "alternativa_1": "Europa",
            "alternativa_2": "Ásia", "alternativa_3": "África",
            "indice_correto": "0", "explicacao": "O Brasil fica na América.",
        })
        repositorio = self.app.extensions["taskflow_repositorio"]
        professor = repositorio.autenticar(
            "PROFESSOR", "professora@web.test", SENHA_PROFESSOR
        )
        questao = repositorio.listar_questoes()[0]
        pagina_salas = self.cliente.get("/professor/salas")
        self.assertIn(b"Criar nova sala", pagina_salas.data)
        resposta = self.cliente.post("/professor/salas", data={
            "csrf": self.csrf(), "nome": "Revisão de História",
            "questoes": str(questao.id),
        })
        self.assertTrue(resposta.location.endswith("/professor/salas"))
        sala_criada = repositorio.listar_salas_professor(professor.id)[0]["sala"]
        self.assertEqual(sala_criada.nome, "Revisão de História")
        pagina_edicao = self.cliente.get(
            f"/professor/salas/{sala_criada.codigo}/editar"
        )
        self.assertIn(b"Salvar altera", pagina_edicao.data)
        resposta = self.cliente.post(
            f"/professor/salas/{sala_criada.codigo}/editar",
            data={
                "csrf": self.csrf(), "nome": "Revisão atualizada",
                "questoes": str(questao.id),
            },
        )
        self.assertTrue(resposta.location.endswith("/professor/salas"))
        self.cliente.post("/professor/salas", data={
            "csrf": self.csrf(), "nome": "Sala descartável",
            "questoes": str(questao.id),
        })
        sala_descartada = repositorio.listar_salas_professor(professor.id)[0]["sala"]
        resposta = self.cliente.post(
            f"/professor/salas/{sala_descartada.codigo}/excluir",
            data={"csrf": self.csrf()},
        )
        self.assertTrue(resposta.location.endswith("/professor/salas"))
        self.assertIsNone(repositorio.buscar_sala_multijogador(sala_descartada.codigo))
        self.cliente.post("/alunos", data={
            "csrf": self.csrf(), "nome": "Aluno Sala", "matricula": "RA-SALA",
            "senha": SENHA_ALUNO, "confirmacao": SENHA_ALUNO,
        })
        self.sair()
        self.cliente.post("/login/aluno", data={
            "csrf": self.csrf(), "identificador": "RA-SALA", "senha": SENHA_ALUNO,
        })
        self.cliente.post("/primeiro-login", data={
            "csrf": self.csrf(), "senha": NOVA_SENHA, "confirmacao": NOVA_SENHA,
            "aceitou": "1",
        })
        pagina = self.cliente.get("/aluno")
        self.assertIn(b"Contra Bot", pagina.data)
        self.assertIn(b"Multijogador On-line", pagina.data)
        self.assertNotIn(b"Desafio de pontos", pagina.data)
        pagina_multijogador = self.cliente.get("/multijogador")
        self.assertNotIn(b"Criar nova sala", pagina_multijogador.data)
        resposta = self.cliente.post("/multijogador", data={
            "csrf": self.csrf(), "codigo": sala_criada.codigo,
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta.location.endswith(
            f"/multijogador/{sala_criada.codigo}"
        ))
        sala = self.cliente.get(resposta.location)
        self.assertIn("Revisão atualizada".encode(), sala.data)
        self.assertIn(b"Aguardando outro aluno", sala.data)

    def test_aluno_solicita_anonimizacao_pela_web(self):
        self.criar_professor()
        self.cliente.post("/alunos", data={
            "csrf": self.csrf(), "nome": "Aluno Titular", "matricula": "RA-TITULAR",
            "senha": SENHA_ALUNO, "confirmacao": SENHA_ALUNO,
        })
        self.sair()
        self.cliente.post("/login/aluno", data={
            "csrf": self.csrf(), "identificador": "RA-TITULAR", "senha": SENHA_ALUNO,
        })
        pagina = self.cliente.get("/conta")
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("Solicitar anonimização".encode(), pagina.data)
        self.assertIn(b"Solicitar exclus\xc3\xa3o definitiva", pagina.data)
        resposta = self.cliente.post("/conta", data={
            "csrf": self.csrf(), "modo": "ANONIMIZAR", "senha": SENHA_ALUNO,
            "confirmacao": "ANONIMIZAR",
        })
        self.assertTrue(resposta.location.endswith("/perfis"))
        self.assertTrue(self.cliente.get("/aluno").location.endswith("/perfis"))
        repositorio = self.app.extensions["taskflow_repositorio"]
        self.assertIsNone(
            repositorio.autenticar("ALUNO", "RA-TITULAR", SENHA_ALUNO)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
