"""Casos de uso: coordena regras, persistência e integração externa."""

from datetime import datetime, timedelta, timezone
import secrets

from taskflow.dominio import (
    AcessoNegado,
    ErroDominio,
    MODOS_JOGO,
    ParticipanteSala,
    PERFIL_ALUNO,
    PERFIL_PROFESSOR,
    ResultadoResposta,
    normalizar_questao,
)
from taskflow.seguranca import validar_codigo_recuperacao


class ServicoTaskFlow:
    def __init__(
        self, repositorio, gemini, tentativas=None, codigo_configuracao_professor=""
    ):
        self.repositorio = repositorio
        self.gemini = gemini
        self.usuario_atual = None
        self._tentativas = tentativas if tentativas is not None else {}
        self._codigo_configuracao_professor = str(
            codigo_configuracao_professor or ""
        ).strip()

    @property
    def primeiro_acesso(self):
        return not self.repositorio.possui_professor()

    @staticmethod
    def _exigir_aceite(aceitou):
        if aceitou is not True:
            raise ErroDominio("Leia e aceite os Termos de Uso e a Política de Privacidade.")

    def _validar_codigo_configuracao_professor(self, codigo_recebido):
        if not self._codigo_configuracao_professor:
            raise AcessoNegado(
                "Cadastro administrativo desativado. Configure TASKFLOW_SETUP_CODE "
                "no servidor antes de criar o professor inicial."
            )
        if not secrets.compare_digest(
            self._codigo_configuracao_professor,
            str(codigo_recebido or "").strip(),
        ):
            raise AcessoNegado("Código de configuração do professor inválido.")

    def criar_primeiro_professor(
        self, nome, email, senha, confirmacao, aceitou, codigo_configuracao=""
    ):
        self._exigir_aceite(aceitou)
        self._validar_codigo_configuracao_professor(codigo_configuracao)
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        usuario = self.repositorio.criar_primeiro_professor(nome, email, senha)
        self.repositorio.registrar_aceite(usuario.id)
        self.repositorio.registrar_evento(
            usuario.perfil, "PRIMEIRO_PROFESSOR", "USUARIOS", usuario.id, usuario.id
        )
        self.usuario_atual = usuario
        return usuario

    def criar_conta(
        self, perfil, nome, identificador, senha, confirmacao, aceitou,
        codigo_configuracao="",
    ):
        """Cria uma conta ativa após o titular aceitar os documentos legais."""

        self._exigir_aceite(aceitou)
        if perfil not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            raise ErroDominio("Perfil inválido.")
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        if perfil == PERFIL_PROFESSOR:
            if self.repositorio.possui_professor():
                raise AcessoNegado(
                    "O professor responsável já foi cadastrado. Entre com a conta existente."
                )
            self._validar_codigo_configuracao_professor(codigo_configuracao)
            usuario = self.repositorio.criar_primeiro_professor(
                nome, identificador, senha
            )
        else:
            usuario = self.repositorio.criar_usuario(
                perfil, nome, identificador, senha, primeiro_acesso=False
            )
        self.repositorio.registrar_aceite(usuario.id)
        self.repositorio.registrar_evento(
            usuario.perfil, "CONTA_CRIADA", "USUARIOS", usuario.id, usuario.id
        )
        self.usuario_atual = usuario
        return usuario

    def _chave_tentativa(self, perfil, identificador):
        return f"{perfil}|{str(identificador).strip().casefold()}"

    def _bloqueado(self, chave):
        quantidade, inicio = self._tentativas.get(chave, (0, datetime.now(timezone.utc)))
        if datetime.now(timezone.utc) - inicio >= timedelta(minutes=15):
            self._tentativas.pop(chave, None)
            return False
        return quantidade >= 5

    def login(self, perfil, identificador, senha):
        chave = self._chave_tentativa(perfil, identificador)
        if self._bloqueado(chave):
            raise ErroDominio("Muitas tentativas. Aguarde 15 minutos.")
        usuario = self.repositorio.autenticar(perfil, identificador, senha)
        if usuario is None:
            quantidade, inicio = self._tentativas.get(
                chave, (0, datetime.now(timezone.utc))
            )
            self._tentativas[chave] = (quantidade + 1, inicio)
            self.repositorio.registrar_evento("ANONIMO", "LOGIN_FALHOU", "SESSAO")
            raise ErroDominio("Credenciais inválidas ou conta bloqueada.")
        self._tentativas.pop(chave, None)
        self.usuario_atual = usuario
        self.repositorio.registrar_evento(
            usuario.perfil, "LOGIN_OK", "SESSAO", usuario.id, usuario.id
        )
        return usuario

    def logout(self):
        if self.usuario_atual:
            usuario = self.usuario_atual
            self.repositorio.registrar_evento(
                usuario.perfil, "LOGOUT", "SESSAO", usuario.id, usuario.id
            )
        self.usuario_atual = None

    def alterar_senha_primeiro_acesso(self, senha, confirmacao, aceitou):
        if self.usuario_atual is None or not self.usuario_atual.primeiro_acesso:
            raise AcessoNegado("Não há primeiro acesso pendente.")
        self._exigir_aceite(aceitou)
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        usuario = self.repositorio.definir_senha(self.usuario_atual.id, senha)
        self.repositorio.registrar_aceite(usuario.id)
        self.usuario_atual = usuario
        self.repositorio.registrar_evento(
            usuario.perfil, "SENHA_PRIMEIRO_ACESSO", "USUARIOS", usuario.id, usuario.id
        )
        return usuario

    def configurar_recuperacao(self, codigo, confirmacao):
        professor = self._professor()
        if codigo != confirmacao:
            raise ErroDominio("Os códigos de recuperação não coincidem.")
        validar_codigo_recuperacao(codigo)
        self.repositorio.configurar_recuperacao_professor(professor.id, codigo)
        self.repositorio.registrar_evento(
            professor.perfil, "RECUPERACAO_CONFIGURADA", "USUARIOS",
            professor.id, professor.id,
        )

    def recuperacao_configurada(self):
        professor = self._professor()
        return self.repositorio.professor_possui_recuperacao(professor.id)

    def recuperar_senha_professor(self, email, codigo, senha, confirmacao):
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        professor = self.repositorio.recuperar_senha_professor(email, codigo, senha)
        self._tentativas.pop(self._chave_tentativa(PERFIL_PROFESSOR, email), None)
        self.repositorio.registrar_evento(
            "ANONIMO", "SENHA_PROFESSOR_RECUPERADA", "USUARIOS", None, professor.id
        )
        return professor

    def _professor(self):
        if not self.usuario_atual or not self.usuario_atual.eh_professor:
            raise AcessoNegado("Acesso permitido somente ao professor.")
        return self.usuario_atual

    def _aluno(self):
        if not self.usuario_atual or not self.usuario_atual.eh_aluno:
            raise AcessoNegado("Acesso permitido somente ao aluno.")
        return self.usuario_atual

    def listar_alunos(self):
        self._professor()
        return self.repositorio.listar_alunos()

    def criar_aluno(self, nome, matricula, senha, confirmacao):
        professor = self._professor()
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        aluno = self.repositorio.criar_aluno(nome, matricula, senha)
        self.repositorio.registrar_evento(
            professor.perfil, "ALUNO_CRIADO", "ALUNOS", professor.id, aluno.id
        )
        return aluno

    def alternar_aluno(self, aluno_id):
        professor = self._professor()
        aluno = self.repositorio.buscar_usuario(aluno_id)
        if aluno is None or not aluno.eh_aluno:
            raise ErroDominio("Aluno não encontrado.")
        atualizado = self.repositorio.definir_ativo(aluno.id, not aluno.ativo)
        evento = "ALUNO_ATIVADO" if atualizado.ativo else "ALUNO_BLOQUEADO"
        self.repositorio.registrar_evento(
            professor.perfil, evento, "ALUNOS", professor.id, aluno.id
        )
        return atualizado

    def excluir_aluno(self, aluno_id):
        professor = self._professor()
        self.repositorio.excluir_aluno(aluno_id)
        self.repositorio.registrar_evento(
            professor.perfil, "ALUNO_EXCLUIDO", "ALUNOS", professor.id, None
        )

    def redefinir_senha_aluno(self, aluno_id, senha, confirmacao):
        professor = self._professor()
        aluno = self.repositorio.buscar_usuario(aluno_id)
        if aluno is None or not aluno.eh_aluno:
            raise ErroDominio("Aluno não encontrado.")
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        atualizado = self.repositorio.definir_senha(aluno.id, senha, primeiro_acesso=True)
        self._tentativas.pop(self._chave_tentativa(PERFIL_ALUNO, aluno.identificador), None)
        self.repositorio.registrar_evento(
            professor.perfil, "SENHA_ALUNO_REDEFINIDA", "ALUNOS",
            professor.id, aluno.id,
        )
        return atualizado

    def listar_auditoria(self):
        self._professor()
        return self.repositorio.listar_eventos()

    def gerar_questao(self, tema, dificuldade):
        professor = self._professor()
        questao = self.gemini.gerar_questao(tema, dificuldade)
        self.repositorio.registrar_evento(
            professor.perfil, "IA_QUESTAO", "GEMINI", professor.id
        )
        return questao

    def listar_questoes(self):
        self._professor()
        return self.repositorio.listar_questoes()

    def criar_questao(
        self,
        tema,
        dificuldade,
        enunciado,
        alternativas,
        indice_correto,
        explicacao,
        feedback_acerto="",
        feedback_erro="",
    ):
        professor = self._professor()
        dados = normalizar_questao(
            tema,
            dificuldade,
            enunciado,
            alternativas,
            indice_correto,
            explicacao,
            feedback_acerto,
            feedback_erro,
        )
        questao = self.repositorio.criar_questao(professor.id, dados)
        self.repositorio.registrar_evento(
            professor.perfil, "QUESTAO_CRIADA", "QUESTOES", professor.id, questao.id
        )
        return questao

    def salvar_questao_gerada(self, tema, dificuldade, questao):
        if not isinstance(questao, dict):
            raise ErroDominio("O rascunho da IA não está disponível.")
        return self.criar_questao(
            tema,
            dificuldade,
            questao.get("enunciado", ""),
            questao.get("alternativas", []),
            questao.get("indice_correto", ""),
            questao.get("explicacao", ""),
            questao.get("feedback_acerto", ""),
            questao.get("feedback_erro", ""),
        )

    def atualizar_questao(
        self,
        questao_id,
        tema,
        dificuldade,
        enunciado,
        alternativas,
        indice_correto,
        explicacao,
        feedback_acerto="",
        feedback_erro="",
    ):
        professor = self._professor()
        dados = normalizar_questao(
            tema,
            dificuldade,
            enunciado,
            alternativas,
            indice_correto,
            explicacao,
            feedback_acerto,
            feedback_erro,
        )
        questao = self.repositorio.atualizar_questao(questao_id, dados)
        self.repositorio.registrar_evento(
            professor.perfil,
            "QUESTAO_ATUALIZADA",
            "QUESTOES",
            professor.id,
            questao.id,
        )
        return questao

    def alternar_questao(self, questao_id):
        professor = self._professor()
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is None:
            raise ErroDominio("Questão não encontrada.")
        questao = self.repositorio.definir_questao_ativa(
            questao.id, not questao.ativa
        )
        self.repositorio.registrar_evento(
            professor.perfil,
            "QUESTAO_ATUALIZADA",
            "QUESTOES",
            professor.id,
            questao.id,
        )
        return questao

    def excluir_questao(self, questao_id):
        professor = self._professor()
        self.repositorio.excluir_questao(questao_id)
        self.repositorio.registrar_evento(
            professor.perfil,
            "QUESTAO_EXCLUIDA",
            "QUESTOES",
            professor.id,
            int(questao_id),
        )

    def adaptar_questao(self, questao_id, dificuldade):
        professor = self._professor()
        original = self.repositorio.buscar_questao(questao_id)
        if original is None:
            raise ErroDominio("Questão não encontrada.")
        dados = self.gemini.adaptar_questao(original, dificuldade)
        adaptada = self.salvar_questao_gerada(
            original.tema, dificuldade, dados
        )
        self.repositorio.registrar_evento(
            professor.perfil,
            "IA_QUESTAO_ADAPTADA",
            "GEMINI",
            professor.id,
            adaptada.id,
        )
        return adaptada

    def gerar_narracao(self, questao_id):
        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre para utilizar a narração.")
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is None or (usuario.eh_aluno and not questao.ativa):
            raise ErroDominio("Questão não encontrada.")
        audio, tipo = self.gemini.gerar_narracao(questao)
        self.repositorio.registrar_evento(
            usuario.perfil, "IA_NARRACAO", "GEMINI", usuario.id, questao.id
        )
        return audio, tipo

    def _dificuldade_adaptativa(self, aluno_id):
        recentes = self.repositorio.acertos_recentes(aluno_id)
        if len(recentes) < 3:
            return "MÉDIO"
        aproveitamento = sum(recentes) / len(recentes)
        if aproveitamento < 0.5:
            return "FÁCIL"
        if aproveitamento >= 0.8:
            return "DIFÍCIL"
        return "MÉDIO"

    def proxima_questao(self, modo):
        aluno = self._aluno()
        modo = str(modo or "").strip().upper()
        if modo not in MODOS_JOGO:
            raise ErroDominio("Modo de jogo inválido.")
        if modo != "BOT":
            raise ErroDominio("Entre em uma sala para jogar o modo multijogador.")
        dificuldade = self._dificuldade_adaptativa(aluno.id)
        return self.repositorio.selecionar_questao(
            dificuldade, aluno_id=aluno.id
        )

    def responder_questao(self, questao_id, indice_escolhido, modo):
        aluno = self._aluno()
        modo = str(modo or "").strip().upper()
        if modo not in MODOS_JOGO:
            raise ErroDominio("Modo de jogo inválido.")
        if modo != "BOT":
            raise ErroDominio("Entre em uma sala para responder no multijogador.")
        questao = self.repositorio.buscar_questao(questao_id)
        if questao is None or not questao.ativa:
            raise ErroDominio("Esta questão não está mais disponível.")
        try:
            indice_escolhido = int(indice_escolhido)
        except (TypeError, ValueError):
            raise ErroDominio("Escolha uma alternativa.") from None
        if indice_escolhido not in range(4):
            raise ErroDominio("Escolha uma alternativa válida.")
        correta = indice_escolhido == questao.indice_correto
        pontos = questao.pontos if correta else 0
        feedback = questao.feedback_acerto if correta else questao.feedback_erro
        chance_bot = {"FÁCIL": 75, "MÉDIO": 60, "DIFÍCIL": 45}[questao.dificuldade]
        bot_acertou = secrets.randbelow(100) < chance_bot
        pontos_bot = questao.pontos if bot_acertou else 0
        self.repositorio.registrar_tentativa(
            aluno.id,
            questao,
            modo,
            indice_escolhido,
            correta,
            pontos,
        )
        self.repositorio.registrar_evento(
            aluno.perfil,
            "RESPOSTA_REGISTRADA",
            "PARTIDA",
            aluno.id,
            questao.id,
        )
        return ResultadoResposta(
            correta=correta,
            alternativa_correta=questao.alternativa_correta,
            feedback=feedback,
            pontos_recebidos=pontos,
            bot_acertou=bot_acertou,
            pontos_bot=pontos_bot,
        )

    @staticmethod
    def _normalizar_codigo_sala(codigo):
        codigo = "".join(
            caractere for caractere in str(codigo or "").upper()
            if caractere.isalnum()
        )
        if len(codigo) != 6:
            raise ErroDominio("Informe o código de seis caracteres da sala.")
        return codigo

    def _normalizar_questoes_sala(self, questoes_ids):
        ids_normalizados = []
        for valor in questoes_ids:
            try:
                questao_id = int(valor)
            except (TypeError, ValueError):
                continue
            if questao_id not in ids_normalizados:
                ids_normalizados.append(questao_id)
        if not ids_normalizados:
            raise ErroDominio("Selecione pelo menos uma questão para a sala.")
        for questao_id in ids_normalizados:
            questao = self.repositorio.buscar_questao(questao_id)
            if questao is None or not questao.ativa:
                raise ErroDominio("Uma das questões selecionadas não está disponível.")
        return ids_normalizados

    @staticmethod
    def _normalizar_nome_sala(nome):
        nome = " ".join(str(nome or "").split())
        if len(nome) < 3:
            raise ErroDominio("Informe um nome para a sala com pelo menos 3 caracteres.")
        if len(nome) > 80:
            raise ErroDominio("O nome da sala deve ter no máximo 80 caracteres.")
        return nome

    def criar_sala_multijogador(self, nome, questoes_ids):
        professor = self._professor()
        nome = self._normalizar_nome_sala(nome)
        ids_normalizados = self._normalizar_questoes_sala(questoes_ids)
        alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        codigo = "".join(secrets.choice(alfabeto) for _ in range(6))
        sala = self.repositorio.criar_sala_multijogador(
            codigo, nome, professor.id, ids_normalizados
        )
        self.repositorio.registrar_evento(
            professor.perfil,
            "SALA_MULTIJOGADOR_CRIADA",
            "PARTIDA",
            professor.id,
            sala.id,
        )
        return sala

    def listar_salas_professor(self):
        professor = self._professor()
        return self.repositorio.listar_salas_professor(professor.id)

    def _sala_do_professor(self, codigo):
        professor = self._professor()
        sala = self.repositorio.buscar_sala_multijogador(
            self._normalizar_codigo_sala(codigo)
        )
        if sala is None or sala.criador_id != professor.id:
            raise ErroDominio("Sala não encontrada.")
        return professor, sala

    def dados_sala_professor(self, codigo):
        _, sala = self._sala_do_professor(codigo)
        return {
            "sala": sala,
            "questoes_ids": self.repositorio.questoes_ids_sala_multijogador(
                sala.id
            ),
        }

    def atualizar_sala_multijogador(self, codigo, nome, questoes_ids):
        professor, sala = self._sala_do_professor(codigo)
        nome = self._normalizar_nome_sala(nome)
        ids_normalizados = self._normalizar_questoes_sala(questoes_ids)
        self.repositorio.atualizar_sala_multijogador(
            sala.id, nome, ids_normalizados
        )
        self.repositorio.registrar_evento(
            professor.perfil,
            "SALA_MULTIJOGADOR_EDITADA",
            "PARTIDA",
            professor.id,
            sala.id,
        )
        return self.repositorio.buscar_sala_multijogador(sala.codigo)

    def excluir_sala_multijogador(self, codigo):
        professor, sala = self._sala_do_professor(codigo)
        self.repositorio.excluir_sala_multijogador(sala.id)
        self.repositorio.registrar_evento(
            professor.perfil,
            "SALA_MULTIJOGADOR_EXCLUIDA",
            "PARTIDA",
            professor.id,
            sala.id,
        )

    def entrar_sala_multijogador(self, codigo):
        aluno = self._aluno()
        codigo = self._normalizar_codigo_sala(codigo)
        sala = self.repositorio.buscar_sala_multijogador(codigo)
        if sala is None or sala.status != "ABERTA":
            raise ErroDominio("Sala não encontrada ou encerrada.")
        self.repositorio.entrar_sala_multijogador(sala.id, aluno.id)
        self.repositorio.registrar_evento(
            aluno.perfil,
            "SALA_MULTIJOGADOR_ENTRADA",
            "PARTIDA",
            aluno.id,
            sala.id,
        )
        return sala

    def estado_sala_multijogador(self, codigo):
        aluno = self._aluno()
        sala = self.repositorio.buscar_sala_multijogador(
            self._normalizar_codigo_sala(codigo)
        )
        if sala is None:
            raise ErroDominio("Sala não encontrada.")
        if not self.repositorio.participante_na_sala(sala.id, aluno.id):
            raise AcessoNegado("Entre na sala antes de acessar a partida.")
        questao = self.repositorio.buscar_questao(sala.questao_id)
        if questao is None or not questao.ativa:
            raise ErroDominio("A questão desta rodada não está disponível.")

        participantes = []
        for linha in self.repositorio.participantes_multijogador(sala):
            usuario = self.repositorio.buscar_usuario(linha["aluno_id"])
            if usuario is None or not usuario.ativo:
                continue
            participantes.append(
                ParticipanteSala(
                    aluno_id=usuario.id,
                    nome=usuario.nome,
                    pontos=int(linha["pontos"]),
                    respondeu=bool(linha["respondeu"]),
                )
            )

        linha_resposta = self.repositorio.resposta_multijogador(sala, aluno.id)
        minha_resposta = None
        if linha_resposta:
            correta = bool(linha_resposta["correta"])
            minha_resposta = ResultadoResposta(
                correta=correta,
                alternativa_correta=questao.alternativa_correta,
                feedback=(
                    questao.feedback_acerto if correta else questao.feedback_erro
                ),
                pontos_recebidos=int(linha_resposta["pontos"]),
            )
        return {
            "sala": sala,
            "questao": questao,
            "participantes": participantes,
            "minha_resposta": minha_resposta,
            "pode_responder": (
                sala.status == "ABERTA"
                and len(participantes) >= 2
                and minha_resposta is None
            ),
            "todos_responderam": (
                len(participantes) >= 2
                and all(participante.respondeu for participante in participantes)
            ),
            "sou_criador": sala.criador_id == aluno.id,
            "partida_encerrada": sala.status == "ENCERRADA",
        }

    def responder_sala_multijogador(self, codigo, indice_escolhido):
        aluno = self._aluno()
        estado = self.estado_sala_multijogador(codigo)
        sala = estado["sala"]
        questao = estado["questao"]
        try:
            indice_escolhido = int(indice_escolhido)
        except (TypeError, ValueError):
            raise ErroDominio("Escolha uma alternativa.") from None
        if indice_escolhido not in range(4):
            raise ErroDominio("Escolha uma alternativa válida.")
        correta = indice_escolhido == questao.indice_correto
        pontos = questao.pontos if correta else 0
        self.repositorio.registrar_resposta_multijogador(
            sala, aluno.id, questao, indice_escolhido, correta, pontos
        )
        self.repositorio.registrar_evento(
            aluno.perfil,
            "RESPOSTA_MULTIJOGADOR",
            "PARTIDA",
            aluno.id,
            sala.id,
        )
        return ResultadoResposta(
            correta=correta,
            alternativa_correta=questao.alternativa_correta,
            feedback=questao.feedback_acerto if correta else questao.feedback_erro,
            pontos_recebidos=pontos,
        )

    def avancar_rodada_multijogador(self, codigo):
        aluno = self._aluno()
        estado = self.estado_sala_multijogador(codigo)
        sala = estado["sala"]
        if sala.status == "ENCERRADA":
            return sala
        if not estado["todos_responderam"]:
            raise ErroDominio("Aguarde todos os participantes responderem.")
        atualizada = self.repositorio.avancar_rodada_multijogador(sala)
        self.repositorio.registrar_evento(
            aluno.perfil,
            "RODADA_MULTIJOGADOR_AVANCADA",
            "PARTIDA",
            aluno.id,
            sala.id,
        )
        return atualizada

    def meu_desempenho(self):
        aluno = self._aluno()
        return self.repositorio.desempenho_aluno(aluno.id)

    def desempenho_turma(self):
        self._professor()
        alunos = {aluno.id: aluno for aluno in self.repositorio.listar_alunos()}
        resultados = []
        for linha in self.repositorio.listar_desempenho_turma():
            aluno = alunos.get(linha["aluno_id"])
            if aluno is None:
                continue
            desempenho = self.repositorio.desempenho_aluno(aluno.id)
            resultados.append((aluno, desempenho))
        return resultados

    def encerrar_conta(self, modo, senha, confirmacao):
        """Executa a solicitação do titular após confirmar senha e intenção."""

        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre novamente para alterar sua conta.")
        modo = str(modo).strip().upper()
        confirmacao = str(confirmacao).strip().upper()
        if modo not in {"ANONIMIZAR", "EXCLUIR"}:
            raise ErroDominio("Escolha anonimizar ou excluir definitivamente.")
        if confirmacao != modo:
            raise ErroDominio(f'Digite "{modo}" para confirmar a solicitação.')
        if not self.repositorio.conferir_senha_usuario(usuario.id, senha):
            raise ErroDominio("Senha atual incorreta.")

        if modo == "ANONIMIZAR":
            self.repositorio.anonimizar_usuario(usuario.id)
            evento = "CONTA_ANONIMIZADA"
        else:
            self.repositorio.excluir_usuario_definitivamente(usuario.id)
            evento = "CONTA_EXCLUIDA"
        self.repositorio.registrar_evento(
            usuario.perfil, evento, "PRIVACIDADE"
        )
        self.usuario_atual = None
        return modo
