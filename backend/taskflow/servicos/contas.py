import secrets
from datetime import datetime, timedelta, timezone

from backend.taskflow.dominio import (
    PERFIL_ALUNO,
    PERFIL_PROFESSOR,
    AcessoNegado,
    ErroDominio,
    normalizar_identificador,
    normalizar_nome,
)
from backend.taskflow.seguranca import validar_codigo_recuperacao, validar_senha
from backend.taskflow.classificacao import validar_idade
from backend.taskflow.servicos.base import ServicoBase


class ServicoContas(ServicoBase):
    def buscar_aluno(self, aluno_id):
        professor = self._professor()
        return next(
            (aluno for aluno in self.repositorio.listar_alunos(professor.id)
             if aluno.id == int(aluno_id)), None
        )

    @property
    def primeiro_acesso(self):
        return not self.repositorio.possui_professor()

    @staticmethod
    def _exigir_aceite(aceitou):
        if aceitou is not True:
            raise ErroDominio("Leia e aceite os Termos de Uso e a Política de Privacidade.")

    def criar_primeiro_professor(
        self, nome, email, senha, confirmacao, aceitou, codigo_configuracao=""
    ):
        self._exigir_aceite(aceitou)
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

        self.validar_cadastro(perfil, nome, identificador, senha, confirmacao, aceitou, codigo_configuracao)
        if perfil == PERFIL_ALUNO:
            nome = "Aluno"
        usuario = self.repositorio.criar_usuario(perfil, nome, identificador, senha)
        self.repositorio.registrar_aceite(usuario.id)
        self.repositorio.registrar_evento(
            usuario.perfil, "CONTA_CRIADA", "USUARIOS", usuario.id, usuario.id
        )
        self.usuario_atual = usuario
        return usuario

    def validar_cadastro(
        self, perfil, nome, identificador, senha, confirmacao, aceitou, codigo_configuracao=""
    ):
        self._exigir_aceite(aceitou)
        if perfil not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            raise ErroDominio("Perfil inválido.")
        if senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        validar_senha(senha)
        normalizar_identificador(perfil, identificador)
        if perfil == PERFIL_PROFESSOR:
            normalizar_nome(nome)

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

    def concluir_perfil_aluno(self, nome, idade, codigo_sala, senha, confirmacao, aceitou):
        """Aceita chamadas legadas por código e usa a mesma validação por classificação."""
        sala = self.repositorio.salas.buscar_sala_multijogador(codigo_sala)
        if sala is None or not sala.chave_academica:
            raise ErroDominio("Sala não encontrada para esse código.")
        return self.concluir_perfil_aluno_classificacao(
            nome, idade, sala.ano_escolar, sala.turma, sala.sala_escolar,
            senha, confirmacao, aceitou,
        )

    def concluir_perfil_aluno_classificacao(
        self, nome, idade, ano_escolar, turma, periodo, senha, confirmacao, aceitou
    ):
        aluno = self._aluno()
        self._exigir_aceite(aceitou)
        if self.repositorio.salas.buscar_perfil_aluno(aluno.id):
            raise AcessoNegado("Seu perfil escolar já foi preenchido.")
        if aluno.primeiro_acesso and senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        usuario = self.repositorio.concluir_perfil_aluno_classificacao(
            aluno.id,
            aluno.versao_sessao,
            normalizar_nome(nome),
            idade,
            ano_escolar,
            turma,
            periodo,
            senha if aluno.primeiro_acesso else None,
        )
        self.usuario_atual = usuario
        self.repositorio.registrar_evento(
            usuario.perfil, "PERFIL_ESCOLAR_CONCLUIDO", "ALUNOS", usuario.id, usuario.id
        )
        return usuario

    def configurar_recuperacao(self, codigo, confirmacao):
        professor = self._professor()
        if not professor.eh_professor:
            raise AcessoNegado("O código de emergência é exclusivo do professor responsável.")
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
        if not professor.eh_professor:
            raise AcessoNegado("O código de emergência é exclusivo do professor responsável.")
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
        professor = self._professor()
        return self.repositorio.listar_alunos(professor.id)

    def encerrar_conta(self, modo, senha, confirmacao):
        """Executa a solicitação do titular após confirmar senha e intenção."""

        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre novamente para alterar sua conta.")
        modo = str(modo).strip().upper()
        confirmacao = str(confirmacao).strip().upper()
        if usuario.eh_aluno and modo != "EXCLUIR":
            raise ErroDominio("Para encerrar a conta de aluno, escolha excluir definitivamente.")
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

    def alterar_senha(self, senha_atual, nova_senha, confirmacao):
        usuario = self.usuario_atual
        if usuario is None:
            raise AcessoNegado("Entre novamente para alterar sua senha.")
        if nova_senha != confirmacao:
            raise ErroDominio("As senhas não coincidem.")
        atualizado = self.repositorio.alterar_senha_titular(
            usuario.id, senha_atual, nova_senha
        )
        self.usuario_atual = atualizado
        self.repositorio.registrar_evento(
            usuario.perfil, "SENHA_ALTERADA", "USUARIOS", usuario.id, usuario.id
        )
        return atualizado

    def atualizar_idade_professor(self, idade):
        professor = self._professor()
        atualizado = self.repositorio.definir_idade_professor(
            professor.id, validar_idade(idade)
        )
        self.usuario_atual = atualizado
        self.repositorio.registrar_evento(
            professor.perfil, "IDADE_PROFESSOR_ATUALIZADA", "USUARIOS", professor.id,
            professor.id,
        )
        return atualizado

    def _chave_tentativa(self, perfil, identificador):
        try:
            identificador = normalizar_identificador(perfil, identificador)
        except ErroDominio:
            pass
        return f"{perfil}|{str(identificador).strip().casefold()}"
