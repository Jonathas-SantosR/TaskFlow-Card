import secrets
from datetime import datetime, timedelta, timezone

from backend.taskflow.dominio import PERFIL_ALUNO, PERFIL_PROFESSOR, AcessoNegado, ErroDominio
from backend.taskflow.seguranca import validar_codigo_recuperacao
from backend.taskflow.servicos.base import ServicoBase


class ServicoContas(ServicoBase):
    def buscar_aluno(self, aluno_id):
        self._professor()
        aluno = self.repositorio.buscar_usuario(aluno_id)
        return aluno if aluno is not None and aluno.eh_aluno else None

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
        self,
        perfil,
        nome,
        identificador,
        senha,
        confirmacao,
        aceitou,
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
            usuario = self.repositorio.criar_primeiro_professor(nome, identificador, senha)
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
            quantidade, inicio = self._tentativas.get(chave, (0, datetime.now(timezone.utc)))
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
            professor.perfil,
            "RECUPERACAO_CONFIGURADA",
            "USUARIOS",
            professor.id,
            professor.id,
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
            professor.perfil,
            "SENHA_ALUNO_REDEFINIDA",
            "ALUNOS",
            professor.id,
            aluno.id,
        )
        return atualizado

    def listar_auditoria(self):
        self._professor()
        return self.repositorio.listar_eventos()

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
        self.repositorio.registrar_evento(usuario.perfil, evento, "PRIVACIDADE")
        self.usuario_atual = None
        return modo

    def _chave_tentativa(self, perfil, identificador):
        return f"{perfil}|{str(identificador).strip().casefold()}"
