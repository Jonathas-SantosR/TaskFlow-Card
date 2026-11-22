"""Camada web orientada a objetos do TaskFlowCards."""

import os
import secrets
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    abort,
    current_app,
    jsonify,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask.views import MethodView

from backend.taskflow.criptografia import CriptografiaDados
from backend.taskflow.dominio import (
    PERFIL_ALUNO,
    PERFIL_PROFESSOR,
    AcessoNegado,
    ErroDominio,
    normalizar_gmail,
)
from backend.taskflow.email import ErroEnvioEmail
from backend.taskflow.gemini import ErroGemini, ServicoGemini
from backend.taskflow.gmail import RemetenteGmail
from backend.taskflow.servico import ServicoTaskFlow
from backend.taskflow.servicos.recuperacao import ServicoRecuperacao
from banco_de_dados.repositorio import RepositorioTaskFlow
from banco_de_dados.banco import ErroConfiguracaoBanco


@dataclass(frozen=True, slots=True)
class DependenciasWeb:
    """Objetos compartilhados e injetados nos controladores web."""

    repositorio: RepositorioTaskFlow
    gemini: ServicoGemini
    tentativas_login: dict
    recuperacao: object = None

    def criar_servico(self, usuario=None):
        servico = ServicoTaskFlow(
            self.repositorio,
            self.gemini,
            self.tentativas_login,
        )
        servico.usuario_atual = usuario
        return servico


class GerenciadorSessao:
    """Encapsula a identidade mantida na sessão do navegador."""

    def __init__(self, repositorio):
        self.repositorio = repositorio

    def usuario_atual(self):
        usuario_id = session.get("usuario_id")
        if not usuario_id:
            return None
        usuario = self.repositorio.buscar_usuario(usuario_id)
        if (
            usuario is None
            or not usuario.ativo
            or usuario.perfil not in {PERFIL_PROFESSOR, PERFIL_ALUNO}
            or session.get("versao_sessao", 0) != usuario.versao_sessao
        ):
            session.clear()
            return None
        return usuario

    @staticmethod
    def autenticar(usuario):
        session.clear()
        session.permanent = False
        session["usuario_id"] = usuario.id
        session["versao_sessao"] = usuario.versao_sessao
        session["ultima_atividade"] = time.time()
        session["csrf"] = secrets.token_urlsafe(32)

    @staticmethod
    def encerrar():
        session.clear()
        session["csrf"] = secrets.token_urlsafe(32)


class ProtecaoCsrf:
    """Gera e valida o token dos formulários mutáveis."""

    CHAVE_SESSAO = "csrf"

    @classmethod
    def token(cls):
        if cls.CHAVE_SESSAO not in session:
            session[cls.CHAVE_SESSAO] = secrets.token_urlsafe(32)
        return session[cls.CHAVE_SESSAO]

    @classmethod
    def validar_requisicao(cls):
        if request.method != "POST":
            return
        esperado = session.get(cls.CHAVE_SESSAO)
        recebido = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
        if not esperado or not recebido or not secrets.compare_digest(esperado, recebido):
            abort(400, "Formulário expirado. Atualize a página e tente novamente.")


class ControladorBase(MethodView):
    """Oferece dependências e operações comuns às páginas."""

    init_every_request = False

    def __init__(self, dependencias, sessoes):
        self.dependencias = dependencias
        self.sessoes = sessoes

    @property
    def servico(self):
        return self.dependencias.criar_servico(g.usuario)


class ControladorProtegido(ControladorBase):
    """Superclasse de páginas que exigem autenticação e, opcionalmente, perfil."""

    perfil_exigido = None

    def dispatch_request(self, *args, **kwargs):
        if g.usuario is None:
            flash("Entre para continuar.", "erro")
            return redirect(url_for("perfis"))
        if self.perfil_exigido and g.usuario.perfil != self.perfil_exigido:
            abort(403)
        return super().dispatch_request(*args, **kwargs)


class VisaoInicio(ControladorBase):
    def get(self):
        if g.usuario:
            destino = "painel_professor" if g.usuario.pode_administrar else "area_aluno"
            return redirect(url_for(destino))
        return render_template("perfis.html")


class VisaoTermos(ControladorBase):
    def get(self):
        return render_template("legal.html")


class VisaoPerfis(ControladorBase):
    def get(self):
        return redirect(url_for("inicio"))


class VisaoPrimeiroProfessor(ControladorBase):
    def get(self):
        return redirect(url_for("criar_conta", perfil="professor"))

    def post(self):
        return redirect(url_for("criar_conta", perfil="professor"), code=307)


class VisaoCriarConta(ControladorBase):
    @staticmethod
    def _perfil(perfil):
        perfil_normalizado = str(perfil).upper()
        if perfil_normalizado not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            abort(404)
        return perfil_normalizado

    def get(self, perfil):
        perfil_normalizado = self._perfil(perfil)
        if request.args.get("alterar") == "1":
            for chave in ("cadastro_email", "cadastro_perfil", "cadastro_autorizado"):
                session.pop(chave, None)
        return self._pagina(perfil_normalizado)

    @staticmethod
    def _exige_codigo():
        # Somente testes legados podem dispensar a confirmação; produção sempre exige.
        return not current_app.testing or current_app.config.get("TESTAR_CADASTRO_COM_CODIGO", False)

    def _pagina(self, perfil):
        email = session.get("cadastro_email") if session.get("cadastro_perfil") == perfil else None
        return render_template(
            "criar_conta.html", perfil=perfil,
            etapa_codigo=self._exige_codigo(), email_cadastro=email,
        )

    def post(self, perfil):
        perfil_normalizado = self._perfil(perfil)
        try:
            email = request.form.get("identificador", "")
            if self._exige_codigo():
                email = session.get("cadastro_email", "")
                if session.get("cadastro_perfil") != perfil_normalizado or not email:
                    raise ErroDominio("Solicite primeiro o código enviado ao Gmail.")
                self.servico.contas.validar_cadastro(
                    perfil_normalizado, request.form.get("nome", ""), email,
                    request.form.get("senha", ""), request.form.get("confirmacao", ""),
                    request.form.get("aceitou") == "1",
                )
                self.dependencias.repositorio.verificacao_cadastro.conferir(
                    perfil_normalizado, email, request.form.get("codigo_email", "")
                )
            usuario = self.servico.criar_conta(
                perfil_normalizado,
                request.form.get("nome", ""),
                email,
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
                request.form.get("aceitou") == "1",
            )
            self.sessoes.autenticar(usuario)
            flash("Conta criada com sucesso.", "sucesso")
            destino = "painel_professor" if usuario.eh_professor else "primeiro_login"
            return redirect(url_for(destino))
        except (ErroDominio, AcessoNegado) as erro:
            flash(str(erro), "erro")
            return self._pagina(perfil_normalizado)


class VisaoEnviarCodigoCadastro(ControladorBase):
    def post(self, perfil):
        perfil_normalizado = VisaoCriarConta._perfil(perfil)
        if not VisaoCriarConta._exige_codigo():
            abort(404)
        try:
            email = normalizar_gmail(request.form.get("identificador", ""))
            remetente = self.dependencias.recuperacao.remetente
            if not remetente.configurada:
                raise ErroDominio("O envio pelo Gmail ainda não está configurado nesta instalação.")
            destinatario, codigo = self.dependencias.repositorio.verificacao_cadastro.emitir(
                perfil_normalizado, email
            )
            remetente.enviar_codigo_cadastro(destinatario, codigo, perfil_normalizado)
            session["cadastro_email"] = destinatario
            session["cadastro_perfil"] = perfil_normalizado
            session["cadastro_autorizado"] = True
            flash("Enviamos um código de seis dígitos ao Gmail informado. Ele expira em 10 minutos.", "sucesso")
        except (ErroDominio, AcessoNegado, ErroEnvioEmail) as erro:
            flash(str(erro), "erro")
        return redirect(url_for("criar_conta", perfil=perfil_normalizado.lower()))


class VisaoLogin(ControladorBase):
    @staticmethod
    def _perfil(perfil):
        perfil_normalizado = str(perfil).upper()
        if perfil_normalizado not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            abort(404)
        return perfil_normalizado

    def get(self, perfil):
        return render_template("login.html", perfil=self._perfil(perfil))

    def post(self, perfil):
        perfil_normalizado = self._perfil(perfil)
        try:
            servico = self.servico
            usuario = servico.login(
                perfil_normalizado,
                request.form.get("identificador", ""),
                request.form.get("senha", ""),
            )
            self.sessoes.autenticar(usuario)
            if usuario.primeiro_acesso or (
                usuario.eh_aluno
                and self.dependencias.repositorio.salas.buscar_perfil_aluno(usuario.id) is None
            ):
                flash("Complete o primeiro acesso para continuar.", "aviso")
                return redirect(url_for("primeiro_login"))
            if usuario.pode_administrar:
                return redirect(url_for("painel_professor"))
            return redirect(url_for("area_aluno"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return render_template("login.html", perfil=perfil_normalizado)


class VisaoPrimeiroLogin(ControladorProtegido):
    @staticmethod
    def _destino(usuario):
        return "painel_professor" if usuario.pode_administrar else "area_aluno"

    def get(self):
        if not g.perfil_pendente:
            return redirect(url_for(self._destino(g.usuario)))
        return render_template("primeiro_login.html")

    def post(self):
        if not g.perfil_pendente:
            return redirect(url_for(self._destino(g.usuario)))
        try:
            senha = request.form.get("senha", "")
            confirmacao = request.form.get("confirmacao", "")
            aceitou = request.form.get("aceitou") == "1"
            if g.usuario.eh_aluno:
                usuario = self.servico.contas.concluir_perfil_aluno_classificacao(
                    request.form.get("nome", ""),
                    request.form.get("idade", ""),
                    request.form.get("ano_escolar", ""),
                    request.form.get("turma", ""),
                    request.form.get("sala_escolar", ""),
                    senha,
                    confirmacao,
                    aceitou,
                )
            else:
                usuario = self.servico.alterar_senha_primeiro_acesso(senha, confirmacao, aceitou)
            self.sessoes.autenticar(usuario)
            flash("Primeiro login concluído.", "sucesso")
            return redirect(url_for(self._destino(usuario)))
        except (ErroDominio, AcessoNegado) as erro:
            flash(str(erro), "erro")
            return self.get(), 400


class VisaoRecuperarProfessor(ControladorBase):
    def get(self):
        return render_template("recuperar_professor.html")

    def post(self):
        try:
            self.servico.recuperar_senha_professor(
                request.form.get("email", ""),
                request.form.get("codigo", ""),
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
            )
            flash("Senha redefinida. Entre com a nova senha.", "sucesso")
            return redirect(url_for("login", perfil="professor"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return render_template("recuperar_professor.html")


class VisaoRecuperarAluno(ControladorBase):
    def get(self):
        return redirect(url_for("recuperar_email", perfil="ALUNO"))


class VisaoSair(ControladorBase):
    def post(self):
        if g.usuario:
            self.servico.logout()
        self.sessoes.encerrar()
        flash("Sessão encerrada.", "sucesso")
        return redirect(url_for("inicio"))


class VisaoPainelProfessor(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        return render_template("professor.html")


class VisaoAcervoSemProfessor(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        return render_template(
            "acervo_sem_professor.html",
            salas=self.servico.salas_sem_professor(),
            questoes=self.servico.questoes_sem_professor(),
        )


class VisaoAderirSala(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, codigo):
        try:
            self.servico.aderir_sala(codigo)
            flash("Você assumiu a responsabilidade por esta sala.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("acervo_sem_professor"))


class VisaoAderirQuestao(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, questao_id):
        try:
            self.servico.aderir_questao(questao_id)
            flash("Você assumiu a responsabilidade por esta questão.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("acervo_sem_professor"))


class VisaoSeguranca(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def dispatch_request(self, *args, **kwargs):
        if g.usuario and not g.usuario.eh_professor:
            abort(403)
        return super().dispatch_request(*args, **kwargs)

    def get(self):
        return render_template("seguranca.html", configurada=self.servico.recuperacao_configurada())

    def post(self):
        try:
            self.servico.configurar_recuperacao(
                request.form.get("codigo", ""), request.form.get("confirmacao", "")
            )
            flash("Código de recuperação salvo.", "sucesso")
            return redirect(url_for("seguranca"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self.get()


class VisaoAlunos(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        salas = self.dependencias.repositorio.salas
        return render_template(
            "alunos.html",
            alunos=[
                (aluno, salas.buscar_perfil_aluno(aluno.id))
                for aluno in self.servico.listar_alunos()
            ],
        )


class VisaoIa(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def _renderizar(self, questao, tema, dificuldade):
        uso_gemini = self.dependencias.repositorio.auditoria.resumo_uso_gemini()
        return render_template(
            "ia.html", questao=questao, tema=tema,
            dificuldade=dificuldade, uso_gemini=uso_gemini,
        )

    def get(self):
        return self._renderizar(None, "", "MÉDIO")

    def post(self):
        tema = request.form.get("tema", "")
        dificuldade = request.form.get("dificuldade", "MÉDIO")
        questao = None
        try:
            questao = self.servico.gerar_questao(tema, dificuldade)
            flash("Rascunho criado. Revise antes de utilizar.", "sucesso")
        except ErroGemini as erro:
            flash(str(erro), "aviso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return self._renderizar(questao, tema, dificuldade)


class VisaoSalvarQuestaoIa(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self):
        try:
            self.servico.criar_questao(
                request.form.get("tema", ""),
                request.form.get("dificuldade", ""),
                request.form.get("enunciado", ""),
                [request.form.get(f"alternativa_{indice}", "") for indice in range(4)],
                request.form.get("indice_correto", ""),
                request.form.get("explicacao", ""),
                request.form.get("feedback_acerto", ""),
                request.form.get("feedback_erro", ""),
            )
            flash("Questão revisada e salva no banco.", "sucesso")
            return redirect(url_for("questoes"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return redirect(url_for("ia"))


class VisaoQuestoes(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        try:
            dados = self.servico.questoes.painel_questoes(request.args)
        except ErroDominio as erro:
            flash(str(erro), "erro")
            dados = self.servico.questoes.painel_questoes()
            return render_template("questoes.html", **dados), 400
        return render_template("questoes.html", **dados)

    def post(self):
        try:
            self.servico.criar_questao(
                request.form.get("tema", ""),
                request.form.get("dificuldade", ""),
                request.form.get("enunciado", ""),
                [request.form.get(f"alternativa_{indice}", "") for indice in range(4)],
                request.form.get("indice_correto", ""),
                request.form.get("explicacao", ""),
                request.form.get("feedback_acerto", ""),
                request.form.get("feedback_erro", ""),
            )
            flash("Questão cadastrada e liberada para o jogo.", "sucesso")
            return redirect(url_for("questoes"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self.get()


class VisaoEditarQuestao(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def _questao(self, questao_id):
        questao = self.servico.buscar_questao(questao_id)
        if questao is None:
            abort(404)
        return questao

    def get(self, questao_id):
        return render_template("editar_questao.html", questao=self._questao(questao_id))

    def post(self, questao_id):
        questao = self._questao(questao_id)
        try:
            self.servico.atualizar_questao(
                questao.id,
                request.form.get("tema", ""),
                request.form.get("dificuldade", ""),
                request.form.get("enunciado", ""),
                [request.form.get(f"alternativa_{indice}", "") for indice in range(4)],
                request.form.get("indice_correto", ""),
                request.form.get("explicacao", ""),
                request.form.get("feedback_acerto", ""),
                request.form.get("feedback_erro", ""),
            )
            flash("Questão atualizada.", "sucesso")
            return redirect(url_for("questoes"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self.get(questao.id)


class VisaoAlternarQuestao(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, questao_id):
        try:
            questao = self.servico.alternar_questao(questao_id)
            estado = "liberada" if questao.ativa else "pausada"
            flash(f"Questão {estado}.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("questoes"))


class VisaoExcluirQuestao(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, questao_id):
        try:
            self.servico.excluir_questao(questao_id)
            flash("Questão excluída.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("questoes"))


class VisaoAdaptarQuestao(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, questao_id):
        try:
            adaptada = self.servico.adaptar_questao(questao_id, request.form.get("dificuldade", ""))
            flash(f"Variação adaptada criada como questão #{adaptada.id}.", "sucesso")
        except ErroGemini as erro:
            flash(str(erro), "aviso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("questoes"))


class VisaoNarracaoQuestao(ControladorProtegido):
    def post(self, questao_id):
        try:
            audio, tipo = self.servico.gerar_narracao(questao_id)
            return send_file(
                BytesIO(audio),
                mimetype=tipo,
                download_name=f"questao-{questao_id}.wav",
            )
        except ErroGemini as erro:
            return {"erro": str(erro)}, 503
        except (AcessoNegado, ErroDominio) as erro:
            return {"erro": str(erro)}, 400


class VisaoJogar(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    @staticmethod
    def _modo(modo):
        modo = str(modo or "").strip().upper()
        if modo != "BOT":
            abort(404)
        return modo

    def get(self, modo):
        modo = self._modo(modo)
        return render_template(
            "jogar.html",
            modo=modo,
            questao=self.servico.proxima_questao(modo),
            sala_academica=self.dependencias.repositorio.salas.sala_academica_aluno(g.usuario.id),
            resultado=None,
            desempenho=self.servico.meu_desempenho(modo),
        )

    def post(self, modo):
        modo = self._modo(modo)
        try:
            questao_id = int(request.form.get("questao_id", "0"))
        except (TypeError, ValueError):
            questao_id = 0
        try:
            resultado = self.servico.responder_questao(
                questao_id, request.form.get("alternativa", ""), modo
            )
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return redirect(url_for("jogar", modo=modo.lower()))
        questao = self.servico.buscar_questao(questao_id)
        return render_template(
            "jogar.html",
            modo=modo,
            questao=questao,
            sala_academica=self.dependencias.repositorio.salas.sala_academica_aluno(g.usuario.id),
            resultado=resultado,
            desempenho=self.servico.meu_desempenho(modo),
        )


class VisaoSalasProfessor(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        questoes = [questao for questao in self.servico.listar_questoes() if questao.ativa]
        return render_template(
            "salas_professor.html",
            questoes=questoes,
            salas=self.servico.listar_salas_professor(),
        )

    def post(self):
        try:
            sala = self.servico.criar_sala_multijogador(
                request.form.get("nome", ""),
                request.form.getlist("questoes"),
                request.form.get("ano_escolar", ""),
                request.form.get("turma", ""),
                request.form.get("sala_escolar", ""),
            )
            flash(
                f"Sala {sala.nome} criada. Alunos da turma serão vinculados automaticamente.",
                "sucesso",
            )
            return redirect(url_for("salas_professor"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self.get()


class VisaoEditarSalaProfessor(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def _pagina(self, codigo):
        dados = self.servico.dados_sala_professor(codigo)
        questoes = [questao for questao in self.servico.listar_questoes() if questao.ativa]
        return render_template("editar_sala_professor.html", questoes=questoes, **dados)

    def get(self, codigo):
        try:
            return self._pagina(codigo)
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return redirect(url_for("salas_professor"))

    def post(self, codigo):
        try:
            self.servico.atualizar_sala_multijogador(
                codigo,
                request.form.get("nome", ""),
                request.form.getlist("questoes"),
                request.form.get("ano_escolar", ""),
                request.form.get("turma", ""),
                request.form.get("sala_escolar", ""),
            )
            flash("Sala atualizada e partida reiniciada.", "sucesso")
            return redirect(url_for("salas_professor"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self._pagina(codigo)


class VisaoExcluirSalaProfessor(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, codigo):
        try:
            self.servico.excluir_sala_multijogador(codigo)
            flash("Sala excluída definitivamente.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("salas_professor"))


class VisaoMultijogador(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def get(self):
        sala = self.dependencias.repositorio.salas.sala_academica_aluno(g.usuario.id)
        return render_template("multijogador.html", sala=sala)

    def post(self):
        try:
            sala_vinculada = self.dependencias.repositorio.salas.sala_academica_aluno(g.usuario.id)
            if sala_vinculada is None:
                raise ErroDominio("Ainda não há sala vinculada ao seu ano, turma e período.")
            sala = self.servico.entrar_sala_multijogador(sala_vinculada.codigo)
            flash("Você entrou na sala.", "sucesso")
            return redirect(url_for("sala_multijogador", codigo=sala.codigo))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self.get()


class VisaoSalaMultijogador(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def _estado(self, codigo):
        try:
            return self.servico.estado_sala_multijogador(codigo)
        except (AcessoNegado, ErroDominio) as erro:
            flash(str(erro), "erro")
            return None

    def get(self, codigo):
        estado = self._estado(codigo)
        if estado is None:
            return redirect(url_for("multijogador"))
        return render_template("sala_multijogador.html", **estado)

    def post(self, codigo):
        try:
            self.servico.responder_sala_multijogador(codigo, request.form.get("alternativa", ""))
            flash("Resposta registrada nesta rodada.", "sucesso")
        except (AcessoNegado, ErroDominio) as erro:
            flash(str(erro), "erro")
        return redirect(url_for("sala_multijogador", codigo=codigo.upper()))


class VisaoProximaRodadaMultijogador(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def post(self, codigo):
        try:
            sala = self.servico.avancar_rodada_multijogador(codigo)
            if sala.status == "ENCERRADA":
                flash("Partida concluída. Confira o placar final.", "sucesso")
        except (AcessoNegado, ErroDominio):
            # Mais de um navegador pode solicitar o avanço simultaneamente.
            # A operação no banco é atômica; a página apenas recarrega o estado atual.
            pass
        return redirect(url_for("sala_multijogador", codigo=codigo.upper()))


class VisaoDesempenho(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        try:
            dashboard = self.servico.dashboard_pedagogica(request.args)
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return render_template(
                "desempenho.html", dashboard=self.servico.dashboard_pedagogica()
            ), 400
        return render_template("desempenho.html", dashboard=dashboard)


class VisaoDadosDesempenho(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        try:
            dashboard = self.servico.dashboard_pedagogica(request.args)
        except ErroDominio:
            abort(400)
        return render_template("_dados_desempenho.html", dashboard=dashboard)


class VisaoAuditoria(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        return render_template("auditoria.html", eventos=self.servico.listar_auditoria())


class VisaoDadosAuditoria(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        return render_template("_dados_auditoria.html", eventos=self.servico.listar_auditoria())


class VisaoAreaAluno(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def get(self):
        salas = self.dependencias.repositorio.salas
        return render_template(
            "aluno.html",
            desempenho=self.servico.meu_desempenho("BOT"),
            escolar=salas.buscar_perfil_aluno(g.usuario.id),
            sala=salas.sala_academica_aluno(g.usuario.id),
        )


class VisaoDadosSalaAluno(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def get(self):
        sala = self.dependencias.repositorio.salas.sala_academica_aluno(g.usuario.id)
        return jsonify({"codigo": sala.codigo if sala else None})


class VisaoReiniciarTreinoBot(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def post(self):
        removidas = self.servico.reiniciar_treino_bot()
        flash(f"Treino contra bot reiniciado. {removidas} resposta(s) removida(s).", "sucesso")
        return redirect(url_for("area_aluno"))


class VisaoPrivacidadeConta(ControladorProtegido):
    """Permite ao titular anonimizar ou excluir a própria conta."""

    def get(self):
        escolar = (
            self.dependencias.repositorio.salas.buscar_perfil_aluno(g.usuario.id)
            if g.usuario.eh_aluno else None
        )
        return render_template("conta.html", escolar=escolar)

    def post(self):
        try:
            modo = self.servico.encerrar_conta(
                request.form.get("modo", ""),
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
            )
            self.sessoes.encerrar()
            mensagem = (
                "Conta anonimizada e sessão encerrada."
                if modo == "ANONIMIZAR"
                else "Conta e dados pessoais excluídos definitivamente."
            )
            flash(mensagem, "sucesso")
            return redirect(url_for("perfis"))
        except (ErroDominio, AcessoNegado) as erro:
            flash(str(erro), "erro")
            return self.get()


class VisaoAlterarSenha(ControladorProtegido):
    def post(self):
        try:
            usuario = self.servico.alterar_senha(
                request.form.get("senha_atual", ""),
                request.form.get("nova_senha", ""),
                request.form.get("confirmacao_nova", ""),
            )
            self.sessoes.autenticar(usuario)
            flash("Senha alterada. As outras sessões foram encerradas.", "sucesso")
            return redirect(url_for("conta"))
        except (ErroDominio, AcessoNegado) as erro:
            flash(str(erro), "erro")
            return redirect(url_for("conta"))


class VisaoIdadeProfessor(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self):
        try:
            self.servico.atualizar_idade_professor(request.form.get("idade", ""))
            flash("Idade atualizada.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("conta"))


class VisaoRecuperarEmail(ControladorBase):
    def get(self):
        perfil = request.args.get("perfil", "ALUNO").upper()
        if perfil not in {PERFIL_ALUNO, PERFIL_PROFESSOR}:
            perfil = PERFIL_ALUNO
        return render_template(
            "recuperar_email.html", perfil=perfil, requisicao_id=secrets.token_urlsafe(24)
        )

    def post(self):
        mensagem = self.dependencias.recuperacao.solicitar(
            request.form.get("perfil", ""),
            request.form.get("identificador", ""),
            origem=request.remote_addr or "local",
            chave_requisicao=request.form.get("requisicao_id", ""),
        )
        flash(mensagem, "sucesso")
        return redirect(url_for("recuperar_email", perfil=request.form.get("perfil", "ALUNO")))


class VisaoRedefinirSenha(ControladorBase):
    def get(self):
        return render_template("redefinir_senha.html", token="")

    def post(self):
        try:
            self.dependencias.recuperacao.redefinir(
                request.form.get("token", ""),
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
            )
            self.sessoes.encerrar()
            flash("Senha redefinida. Entre com a nova senha.", "sucesso")
            return redirect(url_for("inicio"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return render_template("redefinir_senha.html", token=request.form.get("token", "")), 400


class AplicacaoTaskFlowWeb:
    """Compõe infraestrutura, ciclo de requisição e controladores do sistema."""

    def __init__(self, raiz, configuracao=None):
        self.raiz = Path(raiz)
        self.configuracao = dict(configuracao or {})
        postgres_url = str(
            self.configuracao.pop("POSTGRES_URL", None)
            or os.getenv("DATABASE_URL", "")
        ).strip()
        if postgres_url and not self.configuracao.get("TESTING"):
            obrigatorias = (
                "TASKFLOW_DATA_KEY", "FLASK_SECRET_KEY",
                "TASKFLOW_AUDIT_SEED",
            )
            ausentes = [nome for nome in obrigatorias if not os.getenv(nome, "").strip()]
            if not (
                self.configuracao.get("PUBLIC_URL")
                or os.getenv("TASKFLOW_PUBLIC_URL")
                or os.getenv("RENDER_EXTERNAL_URL")
            ):
                ausentes.append("TASKFLOW_PUBLIC_URL/RENDER_EXTERNAL_URL")
            if ausentes:
                raise ErroConfiguracaoBanco(
                    "Configuração do Render incompleta: " + ", ".join(ausentes)
                )
        banco_sqlite_teste = "BANCO" in self.configuracao
        banco = Path(
            self.configuracao.pop(
                "BANCO", self.raiz / "banco_de_dados" / "dados" / "taskflow.sqlite3"
            )
        )
        configuracao_mysql = self.configuracao.pop("MYSQL", None)
        usa_sqlite_exclusivamente_em_teste = bool(
            self.configuracao.get("TESTING") and banco_sqlite_teste
            and configuracao_mysql is None and not postgres_url
        )
        if usa_sqlite_exclusivamente_em_teste:
            configuracao_mysql = None
        elif configuracao_mysql is None and not postgres_url:
            configuracao_mysql = {
                "host": os.getenv("TASKFLOW_MYSQL_HOST", "127.0.0.1"),
                "port": os.getenv("TASKFLOW_MYSQL_PORT", "3306"),
                "user": os.getenv("TASKFLOW_MYSQL_USER", ""),
                "password": os.getenv("TASKFLOW_MYSQL_PASSWORD", ""),
                "database": os.getenv("TASKFLOW_MYSQL_DATABASE", "taskflowcards"),
                "ssl_ca": os.getenv("TASKFLOW_MYSQL_SSL_CA", ""),
            }
        gemini = self.configuracao.pop("GEMINI", None) or ServicoGemini()
        chave_dados = self.configuracao.pop("CHAVE_DADOS", None)

        self.app = Flask(
            __name__,
            template_folder=str(self.raiz / "frontend" / "templates"),
            static_folder=str(self.raiz / "frontend" / "static"),
        )
        self.app.config.update(
            SECRET_KEY=self._chave_sessao(banco),
            PUBLIC_URL=(
                self.configuracao.get("PUBLIC_URL")
                or os.getenv("TASKFLOW_PUBLIC_URL")
                or os.getenv("RENDER_EXTERNAL_URL", "")
            ),
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_SECURE=str(
                self.configuracao.get("PUBLIC_URL")
                or os.getenv("TASKFLOW_PUBLIC_URL")
                or os.getenv("RENDER_EXTERNAL_URL", "")
            ).startswith("https://"),
            MAX_CONTENT_LENGTH=64 * 1024,
        )
        self.app.config.update(self.configuracao)

        repositorio = RepositorioTaskFlow(
            banco, chave_dados=chave_dados, configuracao_mysql=configuracao_mysql,
            postgres_url=postgres_url,
        )
        remetente = self.app.config.get("REMETENTE_EMAIL")
        if remetente is None:
            pasta_gmail = Path(os.getenv("TASKFLOW_DATA_DIR") or banco.parent)
            caminho_gmail = pasta_gmail / ".gmail_oauth"
            variaveis_gmail = (
                "TASKFLOW_GMAIL_CLIENT_ID",
                "TASKFLOW_GMAIL_CLIENT_SECRET",
                "TASKFLOW_GMAIL_REFRESH_TOKEN",
                "TASKFLOW_GMAIL_SENDER",
            )
            credenciais_ambiente = all(os.getenv(nome) for nome in variaveis_gmail)
            criptografia_gmail = None
            if not credenciais_ambiente:
                criptografia_gmail = CriptografiaDados.carregar(
                    pasta_gmail / ".gmail_key",
                    permitir_criar=not caminho_gmail.exists(),
                    variavel_ambiente="TASKFLOW_GMAIL_KEY",
                )
            remetente = RemetenteGmail(
                caminho_gmail,
                criptografia_gmail,
                base_url=self.app.config.get("PUBLIC_URL"),
            )
        tentativas_login = {}
        recuperacao = ServicoRecuperacao(
            repositorio, remetente, tentativas_login, envio_assincrono=not self.app.testing
        )
        self.dependencias = DependenciasWeb(
            repositorio,
            gemini,
            tentativas_login,
            recuperacao,
        )
        self.sessoes = GerenciadorSessao(self.dependencias.repositorio)
        self.app.extensions["taskflow_repositorio"] = self.dependencias.repositorio
        self.app.extensions["taskflow_recuperacao"] = recuperacao
        self._registrar_ciclo_requisicao()
        self._registrar_rotas()
        self._registrar_erros()

    @staticmethod
    def _chave_sessao(banco):
        definida = os.getenv("FLASK_SECRET_KEY", "").strip()
        if definida:
            return definida
        arquivo = Path(banco).parent / ".session_secret"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        if not arquivo.exists():
            arquivo.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        return arquivo.read_text(encoding="utf-8").strip()

    def _registrar_ciclo_requisicao(self):
        @self.app.before_request
        def preparar_requisicao():
            g.usuario = self.sessoes.usuario_atual()
            g.perfil_pendente = False
            acesso_direto = (
                request.method == "GET"
                and request.headers.get("Sec-Fetch-Site") == "none"
                and request.headers.get("Sec-Fetch-Mode") == "navigate"
            )
            if g.usuario and acesso_direto:
                self.sessoes.encerrar()
                g.usuario = None
                flash("Por segurança, entre novamente ao abrir o site.", "aviso")
                return redirect(url_for("inicio"))
            if g.usuario and request.endpoint != "static":
                agora = time.time()
                ultima = session.get("ultima_atividade", agora)
                em_partida = request.endpoint in {
                    "jogar",
                    "sala_multijogador",
                    "proxima_rodada_multijogador",
                }
                mantendo_partida = (
                    request.endpoint == "atividade_sessao"
                    and session.get("em_partida")
                    and request.headers.get("X-Partida") == "1"
                )
                if agora - ultima >= 600 and not mantendo_partida:
                    session.clear()
                    g.usuario = None
                    flash(
                        "Sua sessão expirou após 10 minutos sem atividade. Entre novamente.", "erro"
                    )
                    return redirect(url_for("inicio"))
                if request.endpoint not in {"dados_desempenho", "dados_auditoria", "dados_sala_aluno"}:
                    session["ultima_atividade"] = agora
                if request.endpoint not in {"atividade_sessao", "dados_desempenho", "dados_auditoria", "dados_sala_aluno"}:
                    session["em_partida"] = em_partida
            ProtecaoCsrf.validar_requisicao()
            permitidos = {
                "primeiro_login", "termos", "conta", "sair", "static", "atividade_sessao"
            }
            if g.usuario and request.endpoint != "static":
                g.perfil_pendente = g.usuario.primeiro_acesso or (
                    g.usuario.eh_aluno
                    and self.dependencias.repositorio.salas.buscar_perfil_aluno(g.usuario.id)
                    is None
                )
            if g.perfil_pendente and request.endpoint not in permitidos:
                return redirect(url_for("primeiro_login"))
            return None

        @self.app.post("/sessao/atividade", endpoint="atividade_sessao")
        def atividade_sessao():
            if not g.usuario:
                return "", 401
            if request.form.get("expirar") == "1":
                session.clear()
                flash("Sua sessão expirou após 10 minutos sem atividade. Entre novamente.", "erro")
            return "", 204

        @self.app.context_processor
        def contexto_global():
            return {
                "csrf": ProtecaoCsrf.token(),
                "usuario_atual": g.usuario,
                "ia_configurada": getattr(self.dependencias.gemini, "configurado", True),
            }

        @self.app.after_request
        def proteger_paginas(resposta):
            if request.endpoint != "static":
                resposta.headers["Cache-Control"] = "no-store"
            resposta.headers["Referrer-Policy"] = "no-referrer"
            resposta.headers["X-Content-Type-Options"] = "nosniff"
            return resposta

    def _adicionar_rota(self, regra, endpoint, controlador):
        visualizacao = controlador.as_view(endpoint, self.dependencias, self.sessoes)
        self.app.add_url_rule(regra, view_func=visualizacao)

    def _registrar_rotas(self):
        rotas = [
            ("/", "inicio", VisaoInicio),
            ("/termos", "termos", VisaoTermos),
            ("/perfis", "perfis", VisaoPerfis),
            ("/primeiro-professor", "primeiro_professor", VisaoPrimeiroProfessor),
            ("/criar-conta/<perfil>", "criar_conta", VisaoCriarConta),
            ("/cadastro/enviar-codigo/<perfil>", "enviar_codigo_cadastro", VisaoEnviarCodigoCadastro),
            ("/login/<perfil>", "login", VisaoLogin),
            ("/primeiro-login", "primeiro_login", VisaoPrimeiroLogin),
            ("/recuperar-professor", "recuperar_professor", VisaoRecuperarProfessor),
            ("/recuperar-aluno", "recuperar_aluno", VisaoRecuperarAluno),
            ("/recuperar-senha", "recuperar_email", VisaoRecuperarEmail),
            ("/redefinir-senha", "redefinir_senha", VisaoRedefinirSenha),
            ("/sair", "sair", VisaoSair),
            ("/professor", "painel_professor", VisaoPainelProfessor),
            ("/professor/acervo", "acervo_sem_professor", VisaoAcervoSemProfessor),
            ("/professor/acervo/salas/<codigo>/aderir", "aderir_sala", VisaoAderirSala),
            ("/professor/acervo/questoes/<int:questao_id>/aderir", "aderir_questao", VisaoAderirQuestao),
            ("/seguranca", "seguranca", VisaoSeguranca),
            ("/alunos", "alunos", VisaoAlunos),
            ("/ia", "ia", VisaoIa),
            ("/ia/salvar", "salvar_questao_ia", VisaoSalvarQuestaoIa),
            ("/questoes", "questoes", VisaoQuestoes),
            ("/questoes/<int:questao_id>/editar", "editar_questao", VisaoEditarQuestao),
            ("/questoes/<int:questao_id>/status", "alternar_questao", VisaoAlternarQuestao),
            ("/questoes/<int:questao_id>/excluir", "excluir_questao", VisaoExcluirQuestao),
            ("/questoes/<int:questao_id>/adaptar", "adaptar_questao", VisaoAdaptarQuestao),
            ("/questoes/<int:questao_id>/narracao", "narracao_questao", VisaoNarracaoQuestao),
            ("/jogar/<modo>", "jogar", VisaoJogar),
            ("/professor/salas", "salas_professor", VisaoSalasProfessor),
            ("/professor/salas/<codigo>/editar", "editar_sala_professor", VisaoEditarSalaProfessor),
            (
                "/professor/salas/<codigo>/excluir",
                "excluir_sala_professor",
                VisaoExcluirSalaProfessor,
            ),
            ("/multijogador", "multijogador", VisaoMultijogador),
            ("/multijogador/<codigo>", "sala_multijogador", VisaoSalaMultijogador),
            (
                "/multijogador/<codigo>/proxima",
                "proxima_rodada_multijogador",
                VisaoProximaRodadaMultijogador,
            ),
            ("/desempenho", "desempenho", VisaoDesempenho),
            ("/desempenho/dados", "dados_desempenho", VisaoDadosDesempenho),
            ("/auditoria", "auditoria", VisaoAuditoria),
            ("/auditoria/dados", "dados_auditoria", VisaoDadosAuditoria),
            ("/aluno", "area_aluno", VisaoAreaAluno),
            ("/aluno/sala/dados", "dados_sala_aluno", VisaoDadosSalaAluno),
            ("/aluno/treino-bot/reiniciar", "reiniciar_treino_bot", VisaoReiniciarTreinoBot),
            ("/conta", "conta", VisaoPrivacidadeConta),
            ("/conta/senha", "alterar_senha", VisaoAlterarSenha),
            ("/conta/idade", "idade_professor", VisaoIdadeProfessor),
        ]
        for regra, endpoint, controlador in rotas:
            self._adicionar_rota(regra, endpoint, controlador)

    def _registrar_erros(self):
        def exibir_erro(erro):
            mensagens = {
                400: "Formulário inválido ou expirado.",
                403: "Acesso não autorizado.",
                404: "Página não encontrada.",
            }
            return render_template(
                "erro.html", codigo=erro.code, mensagem=mensagens[erro.code]
            ), erro.code

        for codigo in (400, 403, 404):
            self.app.register_error_handler(codigo, exibir_erro)

    def criar(self):
        return self.app
