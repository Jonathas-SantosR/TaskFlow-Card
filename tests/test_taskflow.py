import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from backend.taskflow.dominio import PERFIL_ALUNO, PERFIL_PROFESSOR, AcessoNegado, ErroDominio
from backend.taskflow.gemini import ErroGemini, ServicoGemini
from backend.taskflow.servico import ServicoTaskFlow
from banco_de_dados.repositorio import ProfessorJaExiste, RepositorioTaskFlow

SENHA_PROFESSOR = "Professor!2026"
SENHA_ALUNO = "Estudante!2026"
NOVA_SENHA = "NovaSenha!2026"
CODIGO_RECUPERACAO = "Recuperar!2026"
CODIGO_CONFIGURACAO = "InstalarProfessor!2026"


class TestesTaskFlow(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        banco = Path(self.temporario.name) / "teste.sqlite3"
        self.repositorio = RepositorioTaskFlow(banco)
        self.gemini = ServicoGemini(chave="chave-teste")
        self.servico = ServicoTaskFlow(
            self.repositorio,
            self.gemini,
            codigo_configuracao_professor=CODIGO_CONFIGURACAO,
        )

    def tearDown(self):
        self.repositorio.fechar()
        self.temporario.cleanup()

    def criar_professor(self):
        return self.servico.criar_primeiro_professor(
            "Professora Ana",
            "ana@escola.test",
            SENHA_PROFESSOR,
            SENHA_PROFESSOR,
            True,
            CODIGO_CONFIGURACAO,
        )

    def criar_questao(self, dificuldade="MÉDIO"):
        return self.servico.criar_questao(
            "Matemática",
            dificuldade,
            "Quanto é dois mais dois?",
            ["Três", "Quatro", "Cinco", "Seis"],
            1,
            "Dois mais dois resulta em quatro.",
            "Muito bem! Você aplicou a soma corretamente.",
            "Observe a soma das duas parcelas.",
        )

    def test_primeiro_professor_e_unico_e_senha_nao_vaza(self):
        professor = self.criar_professor()
        self.assertEqual(professor.perfil, PERFIL_PROFESSOR)
        self.assertNotIn("senha", str(professor.para_dict()).casefold())
        self.servico.logout()
        with self.assertRaises(ProfessorJaExiste):
            self.servico.criar_primeiro_professor(
                "Outro Professor",
                "outro@escola.test",
                SENHA_PROFESSOR,
                SENHA_PROFESSOR,
                True,
                CODIGO_CONFIGURACAO,
            )

    def test_autocadastro_de_segundo_professor_e_bloqueado(self):
        self.criar_professor()
        self.servico.logout()
        with self.assertRaises(AcessoNegado):
            self.servico.criar_conta(
                PERFIL_PROFESSOR,
                "Professor sem autorização",
                "outro@escola.test",
                SENHA_PROFESSOR,
                SENHA_PROFESSOR,
                True,
            )

    def test_aceite_e_credenciais_sao_obrigatorios(self):
        with self.assertRaises(ErroDominio):
            self.servico.criar_primeiro_professor(
                "Professora Ana",
                "ana@escola.test",
                SENHA_PROFESSOR,
                SENHA_PROFESSOR,
                False,
                CODIGO_CONFIGURACAO,
            )
        self.criar_professor()
        self.servico.logout()
        with self.assertRaises(ErroDominio):
            self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", "errada")
        usuario = self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", SENHA_PROFESSOR)
        self.assertEqual(usuario.nome, "Professora Ana")

    def test_login_bloqueia_apos_cinco_tentativas(self):
        self.criar_professor()
        self.servico.logout()
        for _ in range(5):
            with self.assertRaisesRegex(ErroDominio, "Credenciais inválidas"):
                self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", "senha-incorreta")
        with self.assertRaisesRegex(ErroDominio, "Aguarde 15 minutos"):
            self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", SENHA_PROFESSOR)

    def test_professor_cadastra_e_administra_aluno(self):
        self.criar_professor()
        aluno = self.servico.criar_aluno("Aluno Teste", "RA-2026", SENHA_ALUNO, SENHA_ALUNO)
        self.assertTrue(aluno.ativo)
        self.assertEqual(len(self.servico.listar_alunos()), 1)
        bloqueado = self.servico.alternar_aluno(aluno.id)
        self.assertFalse(bloqueado.ativo)
        self.assertIsNone(self.repositorio.autenticar(PERFIL_ALUNO, "RA-2026", SENHA_ALUNO))
        self.servico.excluir_aluno(aluno.id)
        self.assertEqual(self.servico.listar_alunos(), [])

    def test_exclusao_administrativa_remove_vinculos_do_aluno(self):
        professor = self.criar_professor()
        questao = self.criar_questao()
        aluno = self.servico.criar_aluno(
            "Aluno com vínculos", "RA-VINCULOS", SENHA_ALUNO, SENHA_ALUNO
        )
        colega = self.servico.criar_aluno("Aluno colega", "RA-COLEGA", SENHA_ALUNO, SENHA_ALUNO)
        self.repositorio.registrar_aceite(aluno.id)
        sala = self.repositorio.criar_sala_multijogador(
            "ABC123", "Sala de vínculos", professor.id, [questao.id]
        )
        self.repositorio.entrar_sala_multijogador(sala.id, aluno.id)
        self.repositorio.entrar_sala_multijogador(sala.id, colega.id)
        self.repositorio.registrar_resposta_multijogador(
            sala, aluno.id, questao, questao.indice_correto, True, questao.pontos
        )
        self.repositorio.registrar_evento(PERFIL_ALUNO, "LOGIN_OK", "SESSAO", aluno.id, aluno.id)

        self.servico.excluir_aluno(aluno.id)

        self.assertIsNone(self.repositorio.buscar_usuario(aluno.id))
        for tabela, coluna in (
            ("aceites", "usuario_id"),
            ("participantes_multijogador", "aluno_id"),
            ("respostas_multijogador", "aluno_id"),
        ):
            quantidade = self.repositorio.conexao.execute(
                f"SELECT COUNT(*) FROM {tabela} WHERE {coluna}=?", (aluno.id,)
            ).fetchone()[0]
            self.assertEqual(quantidade, 0)
        referencias = self.repositorio.conexao.execute(
            "SELECT COUNT(*) FROM auditoria WHERE ator_id=? OR alvo_id=?",
            (aluno.id, aluno.id),
        ).fetchone()[0]
        self.assertEqual(referencias, 0)

    def test_professor_gerencia_banco_de_questoes(self):
        self.criar_professor()
        questao = self.criar_questao()
        self.assertEqual(len(self.servico.listar_questoes()), 1)
        self.assertEqual(questao.alternativa_correta, "Quatro")
        atualizada = self.servico.atualizar_questao(
            questao.id,
            "Matemática",
            "DIFÍCIL",
            "Qual é o resultado de dois elevado à terceira potência?",
            ["Quatro", "Seis", "Oito", "Dez"],
            2,
            "Dois ao cubo é igual a oito.",
        )
        self.assertEqual(atualizada.dificuldade, "DIFÍCIL")
        pausada = self.servico.alternar_questao(questao.id)
        self.assertFalse(pausada.ativa)
        self.servico.excluir_questao(questao.id)
        self.assertEqual(self.servico.listar_questoes(), [])

    def test_aluno_recebe_feedback_e_desempenho(self):
        self.criar_professor()
        questao = self.criar_questao()
        aluno = self.servico.criar_aluno("Aluno Jogador", "RA-JOGO", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        self.servico.login(PERFIL_ALUNO, "RA-JOGO", SENHA_ALUNO)
        selecionada = self.servico.proxima_questao("BOT")
        self.assertEqual(selecionada.id, questao.id)
        resultado = self.servico.responder_questao(questao.id, 1, "BOT")
        self.assertTrue(resultado.correta)
        self.assertEqual(resultado.pontos_recebidos, 2)
        desempenho = self.servico.meu_desempenho()
        self.assertEqual(
            (desempenho.total, desempenho.acertos, desempenho.pontos),
            (1, 1, 2),
        )
        self.assertEqual(desempenho.percentual, 100)
        self.assertEqual(aluno.id, self.servico.usuario_atual.id)

    def test_modo_bot_adapta_dificuldade_ao_desempenho(self):
        self.criar_professor()
        media = self.criar_questao("MÉDIO")
        facil = self.servico.criar_questao(
            "Geografia",
            "FÁCIL",
            "Qual é a capital do Brasil?",
            ["Brasília", "Salvador", "Recife", "Manaus"],
            0,
            "Brasília é a capital federal.",
        )
        self.servico.criar_aluno("Aluno Treino", "RA-TREINO", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        self.servico.login(PERFIL_ALUNO, "RA-TREINO", SENHA_ALUNO)
        for _ in range(3):
            self.servico.responder_questao(media.id, 0, "BOT")
        proxima = self.servico.proxima_questao("BOT")
        self.assertEqual(proxima.id, facil.id)

    def test_modo_bot_nao_repete_antes_de_usar_todas_as_questoes(self):
        self.criar_professor()
        questoes = [
            self.criar_questao("MÉDIO"),
            self.servico.criar_questao(
                "Geografia",
                "FÁCIL",
                "Qual é a capital do Brasil?",
                ["Brasília", "Salvador", "Recife", "Manaus"],
                0,
                "Brasília é a capital federal.",
            ),
            self.servico.criar_questao(
                "Ciências",
                "DIFÍCIL",
                "Qual planeta é conhecido como vermelho?",
                ["Marte", "Vênus", "Júpiter", "Saturno"],
                0,
                "Marte possui aparência avermelhada.",
            ),
        ]
        self.servico.criar_aluno("Aluno Ciclo", "RA-CICLO", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        self.servico.login(PERFIL_ALUNO, "RA-CICLO", SENHA_ALUNO)
        vistos = []
        for _ in questoes:
            questao = self.servico.proxima_questao("BOT")
            self.assertNotIn(questao.id, vistos)
            vistos.append(questao.id)
            self.servico.responder_questao(questao.id, questao.indice_correto, "BOT")
        self.assertEqual(set(vistos), {questao.id for questao in questoes})

    def test_multijogador_cria_sala_compartilha_questao_e_avanca_rodada(self):
        self.criar_professor()
        primeira = self.criar_questao("MÉDIO")
        segunda = self.servico.criar_questao(
            "Geografia",
            "FÁCIL",
            "Qual é a capital do Brasil?",
            ["Brasília", "Salvador", "Recife", "Manaus"],
            0,
            "Brasília é a capital federal.",
        )
        sala = self.servico.criar_sala_multijogador("Revisão geral", [primeira.id, segunda.id])
        self.assertEqual(sala.nome, "Revisão geral")
        self.assertEqual(
            self.repositorio.questoes_ids_sala_multijogador(sala.id),
            [primeira.id, segunda.id],
        )
        self.assertEqual(len(self.servico.listar_salas_professor()), 1)
        sala = self.servico.atualizar_sala_multijogador(
            sala.codigo, "Revisão invertida", [segunda.id, primeira.id]
        )
        self.assertEqual(sala.nome, "Revisão invertida")
        self.assertEqual(sala.questao_id, segunda.id)
        self.servico.criar_aluno("Aluno Um", "RA-UM", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.criar_aluno("Aluno Dois", "RA-DOIS", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()

        jogador_um = ServicoTaskFlow(self.repositorio, self.gemini)
        jogador_dois = ServicoTaskFlow(self.repositorio, self.gemini)
        jogador_um.login(PERFIL_ALUNO, "RA-UM", SENHA_ALUNO)
        jogador_dois.login(PERFIL_ALUNO, "RA-DOIS", SENHA_ALUNO)

        jogador_um.entrar_sala_multijogador(sala.codigo)
        jogador_dois.entrar_sala_multijogador(sala.codigo)
        estado_um = jogador_um.estado_sala_multijogador(sala.codigo)
        self.assertEqual(len(estado_um["participantes"]), 2)
        questao = estado_um["questao"]
        jogador_um.responder_sala_multijogador(sala.codigo, questao.indice_correto)
        jogador_dois.responder_sala_multijogador(sala.codigo, questao.indice_correto)
        estado_final = jogador_um.estado_sala_multijogador(sala.codigo)
        self.assertTrue(estado_final["todos_responderam"])
        rodada_dois = jogador_um.avancar_rodada_multijogador(sala.codigo)
        self.assertEqual(rodada_dois.rodada, 2)
        self.assertEqual(rodada_dois.questao_id, primeira.id)
        questao = jogador_um.estado_sala_multijogador(sala.codigo)["questao"]
        jogador_um.responder_sala_multijogador(sala.codigo, questao.indice_correto)
        jogador_dois.responder_sala_multijogador(sala.codigo, questao.indice_correto)
        encerrada = jogador_dois.avancar_rodada_multijogador(sala.codigo)
        self.assertEqual(encerrada.status, "ENCERRADA")
        self.assertTrue(jogador_um.estado_sala_multijogador(sala.codigo)["partida_encerrada"])
        self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", SENHA_PROFESSOR)
        self.servico.excluir_sala_multijogador(sala.codigo)
        self.assertIsNone(self.repositorio.buscar_sala_multijogador(sala.codigo))

    def test_aluno_troca_senha_temporaria_no_primeiro_login(self):
        self.criar_professor()
        self.servico.criar_aluno("Aluno Primeiro Acesso", "RA-INICIAL", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        aluno = self.servico.login(PERFIL_ALUNO, "RA-INICIAL", SENHA_ALUNO)
        self.assertTrue(aluno.primeiro_acesso)
        atualizado = self.servico.alterar_senha_primeiro_acesso(NOVA_SENHA, NOVA_SENHA, True)
        self.assertFalse(atualizado.primeiro_acesso)
        self.servico.logout()
        with self.assertRaisesRegex(ErroDominio, "Credenciais inválidas"):
            self.servico.login(PERFIL_ALUNO, "RA-INICIAL", SENHA_ALUNO)
        autenticado = self.servico.login(PERFIL_ALUNO, "RA-INICIAL", NOVA_SENHA)
        self.assertFalse(autenticado.primeiro_acesso)

    def test_professor_recupera_senha_com_codigo_configurado(self):
        self.criar_professor()
        self.servico.configurar_recuperacao(CODIGO_RECUPERACAO, CODIGO_RECUPERACAO)
        self.assertTrue(self.servico.recuperacao_configurada())
        self.servico.logout()
        self.servico.recuperar_senha_professor(
            "ana@escola.test",
            CODIGO_RECUPERACAO,
            NOVA_SENHA,
            NOVA_SENHA,
        )
        usuario = self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", NOVA_SENHA)
        self.assertEqual(usuario.perfil, PERFIL_PROFESSOR)

    def test_codigo_de_recuperacao_exige_tamanho_maiuscula_e_numero(self):
        self.criar_professor()
        casos_invalidos = (
            ("Curto1", "12 a 128"),
            ("somenteletras1", "maiúscula"),
            ("SomenteLetras", "número"),
        )
        for codigo, mensagem in casos_invalidos:
            with self.subTest(codigo=codigo):
                with self.assertRaisesRegex(ErroDominio, mensagem):
                    self.servico.configurar_recuperacao(codigo, codigo)

    def test_professor_redefine_senha_temporaria_do_aluno(self):
        self.criar_professor()
        aluno = self.servico.criar_aluno("Aluno Recuperado", "RA-REC", SENHA_ALUNO, SENHA_ALUNO)
        redefinido = self.servico.redefinir_senha_aluno(aluno.id, NOVA_SENHA, NOVA_SENHA)
        self.assertTrue(redefinido.primeiro_acesso)
        self.servico.logout()
        autenticado = self.servico.login(PERFIL_ALUNO, "RA-REC", NOVA_SENHA)
        self.assertTrue(autenticado.primeiro_acesso)

    def test_aluno_nao_acessa_funcoes_administrativas(self):
        self.criar_professor()
        self.servico.criar_aluno("Aluno Teste", "RA-1", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        self.servico.login(PERFIL_ALUNO, "RA-1", SENHA_ALUNO)
        with self.assertRaises(AcessoNegado):
            self.servico.listar_alunos()
        with self.assertRaises(AcessoNegado):
            self.servico.listar_auditoria()

    def test_auditoria_usa_ids_e_nao_dados_pessoais(self):
        professor = self.criar_professor()
        aluno = self.servico.criar_aluno("Maria Privada", "RA-PRIVADO", SENHA_ALUNO, SENHA_ALUNO)
        eventos = self.servico.listar_auditoria()
        self.assertTrue(any(item["evento"] == "ALUNO_CRIADO" for item in eventos))
        texto = str(eventos)
        self.assertNotIn("Maria Privada", texto)
        self.assertNotIn("RA-PRIVADO", texto)
        self.assertIn(str(professor.id), texto)
        self.assertIn(str(aluno.id), texto)
        self.assertTrue(all(item["integridade"] is True for item in eventos))

    def test_assinatura_assimetrica_detecta_adulteracao_da_auditoria(self):
        self.criar_professor()
        evento_original = self.repositorio.listar_eventos()[0]
        self.assertTrue(evento_original["integridade"])
        with self.repositorio.conexao:
            self.repositorio.conexao.execute(
                "UPDATE auditoria SET recurso='ALTERADO' WHERE id=(SELECT MAX(id) FROM auditoria)"
            )
        evento_adulterado = self.repositorio.listar_eventos()[0]
        self.assertFalse(evento_adulterado["integridade"])

    def test_dados_pessoais_ficam_criptografados_no_banco(self):
        professor = self.criar_professor()
        linha = self.repositorio.conexao.execute(
            """SELECT identificador, chave_identificador, nome, senha_hash
            FROM usuarios WHERE id=?""",
            (professor.id,),
        ).fetchone()
        conteudo_bruto = " ".join(str(valor) for valor in linha)
        self.assertNotIn("Professora Ana", conteudo_bruto)
        self.assertNotIn("ana@escola.test", conteudo_bruto)
        self.assertTrue(linha["identificador"].startswith("enc:v1:"))
        self.assertTrue(linha["nome"].startswith("enc:v1:"))
        self.assertTrue(linha["chave_identificador"].startswith("idx:v1:"))
        self.assertTrue(linha["senha_hash"].startswith("pbkdf2_sha256$"))
        self.servico.logout()
        autenticado = self.servico.login(PERFIL_PROFESSOR, "ana@escola.test", SENHA_PROFESSOR)
        self.assertEqual(autenticado.nome, "Professora Ana")

    def test_aluno_pode_anonimizar_a_propria_conta(self):
        self.criar_professor()
        aluno = self.servico.criar_aluno("Aluno Privado", "RA-ANONIMO", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        self.servico.login(PERFIL_ALUNO, "RA-ANONIMO", SENHA_ALUNO)
        modo = self.servico.encerrar_conta("ANONIMIZAR", SENHA_ALUNO, "ANONIMIZAR")
        self.assertEqual(modo, "ANONIMIZAR")
        anonimizado = self.repositorio.buscar_usuario(aluno.id)
        self.assertTrue(anonimizado.anonimizado)
        self.assertFalse(anonimizado.ativo)
        self.assertEqual(anonimizado.nome, "Usuário anonimizado")
        self.assertNotEqual(anonimizado.identificador, "RA-ANONIMO")
        self.assertIsNone(self.repositorio.autenticar(PERFIL_ALUNO, "RA-ANONIMO", SENHA_ALUNO))
        evento = self.repositorio.listar_eventos()[0]
        self.assertEqual(evento["evento"], "CONTA_ANONIMIZADA")
        self.assertIsNone(evento["ator_id"])
        self.assertIsNone(evento["alvo_id"])

    def test_aluno_pode_excluir_definitivamente_a_propria_conta(self):
        self.criar_professor()
        aluno = self.servico.criar_aluno("Aluno Saída", "RA-SAIDA", SENHA_ALUNO, SENHA_ALUNO)
        self.servico.logout()
        self.servico.login(PERFIL_ALUNO, "RA-SAIDA", SENHA_ALUNO)
        modo = self.servico.encerrar_conta("EXCLUIR", SENHA_ALUNO, "EXCLUIR")
        self.assertEqual(modo, "EXCLUIR")
        self.assertIsNone(self.repositorio.buscar_usuario(aluno.id))
        self.assertIsNone(self.repositorio.autenticar(PERFIL_ALUNO, "RA-SAIDA", SENHA_ALUNO))
        evento = self.repositorio.listar_eventos()[0]
        self.assertEqual(evento["evento"], "CONTA_EXCLUIDA")
        self.assertIsNone(evento["ator_id"])
        self.assertIsNone(evento["alvo_id"])

    def test_saida_exige_senha_e_confirmacao_exata(self):
        professor = self.criar_professor()
        with self.assertRaisesRegex(ErroDominio, "Digite"):
            self.servico.encerrar_conta("EXCLUIR", SENHA_PROFESSOR, "não")
        with self.assertRaisesRegex(ErroDominio, "Senha atual incorreta"):
            self.servico.encerrar_conta("EXCLUIR", "senha errada", "EXCLUIR")
        self.assertIsNotNone(self.repositorio.buscar_usuario(professor.id))

    def test_gemini_rejeita_dado_pessoal_antes_da_rede(self):
        with patch("backend.taskflow.gemini.request.urlopen") as abrir:
            with self.assertRaises(ErroDominio):
                self.gemini.gerar_questao("Aluno aluno@escola.test", "MÉDIO")
        abrir.assert_not_called()

    def test_gemini_retorna_questao_estruturada(self):
        conteudo = {
            "enunciado": "Quanto é 2 + 2?",
            "alternativas": ["3", "4", "5", "6"],
            "indice_correto": 1,
            "explicacao": "A soma de dois com dois é quatro.",
        }
        resposta_api = {"candidates": [{"content": {"parts": [{"text": json.dumps(conteudo)}]}}]}
        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.read.return_value = json.dumps(resposta_api).encode("utf-8")
        with patch("backend.taskflow.gemini.request.urlopen", return_value=resposta) as abrir:
            questao = self.gemini.gerar_questao("adição", "FÁCIL")
        self.assertEqual(questao["indice_correto"], 1)
        requisicao = abrir.call_args.args[0]
        self.assertEqual(requisicao.get_header("X-goog-api-key"), "chave-teste")
        self.assertIn(b"responseSchema", requisicao.data)

    def test_gemini_gera_narracao_wav(self):
        self.criar_professor()
        questao = self.criar_questao()
        resposta_api = {
            "output_audio": {
                "data": base64.b64encode(b"RIFFaudio-de-teste").decode("ascii"),
                "mime_type": "audio/wav",
            }
        }
        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.read.return_value = json.dumps(resposta_api).encode("utf-8")
        with patch("backend.taskflow.gemini.request.urlopen", return_value=resposta) as abrir:
            audio, tipo = self.servico.gerar_narracao(questao.id)
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(tipo, "audio/wav")
        requisicao = abrir.call_args.args[0]
        self.assertTrue(requisicao.full_url.endswith("/v1beta/interactions"))
        self.assertIn(b"gemini-3.8-flash-lite-tts", requisicao.data)
        self.assertIn(b"response_format", requisicao.data)
        self.assertIn(b"speech_config", requisicao.data)

    def test_gemini_sem_chave_exibe_configuracao_pendente(self):
        with self.assertRaises(ErroGemini):
            ServicoGemini(chave="").gerar_questao("geografia", "MÉDIO")

    def test_gemini_usa_modelo_atual_para_novos_projetos(self):
        self.assertEqual(
            ServicoGemini(chave="chave-teste").modelo,
            "gemini-3.5-flash-lite",
        )

    def test_gemini_explica_chave_invalida_sem_expor_resposta(self):
        corpo = json.dumps(
            {
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": "API key not valid: segredo-que-nao-pode-vazar",
                    "details": [{"reason": "API_KEY_INVALID"}],
                }
            }
        ).encode("utf-8")
        resposta = HTTPError("https://teste", 400, "Bad Request", {}, BytesIO(corpo))
        with patch("backend.taskflow.gemini.request.urlopen", side_effect=resposta):
            with self.assertRaisesRegex(ErroGemini, "chave.*inválida.*HTTP 400") as erro:
                self.gemini.gerar_questao("matemática", "MÉDIO")
        self.assertNotIn("segredo-que-nao-pode-vazar", str(erro.exception))

    def test_gemini_explica_modelo_indisponivel(self):
        corpo = json.dumps(
            {"error": {"code": 404, "status": "NOT_FOUND", "message": "Not found"}}
        ).encode("utf-8")
        resposta = HTTPError("https://teste", 404, "Not Found", {}, BytesIO(corpo))
        with patch("backend.taskflow.gemini.request.urlopen", side_effect=resposta):
            with self.assertRaisesRegex(ErroGemini, "modelo.*HTTP 404"):
                self.gemini.gerar_questao("matemática", "MÉDIO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
