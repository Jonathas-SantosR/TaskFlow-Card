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

from backend.taskflow.dominio import PERFIL_ALUNO, PERFIL_PROFESSOR, AcessoNegado, ErroDominio
from backend.taskflow.gemini import ErroGemini, ServicoGemini
from backend.taskflow.servico import ServicoTaskFlow
from banco_de_dados.repositorio import RepositorioTaskFlow


@dataclass(frozen=True, slots=True)
class DependenciasWeb:
    """Objetos compartilhados e injetados nos controladores web."""

    repositorio: RepositorioTaskFlow
    gemini: ServicoGemini
    tentativas_login: dict
    codigo_configuracao_professor: str

    def criar_servico(self, usuario=None):
        servico = ServicoTaskFlow(
            self.repositorio,
            self.gemini,
            self.tentativas_login,
            self.codigo_configuracao_professor,
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
        if usuario is None or not usuario.ativo:
            session.pop("usuario_id", None)
            return None
        return usuario

    @staticmethod
    def autenticar(usuario):
        session["usuario_id"] = usuario.id

    @staticmethod
    def encerrar():
        session.pop("usuario_id", None)


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
            destino = "painel_professor" if g.usuario.eh_professor else "area_aluno"
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
        if perfil_normalizado == PERFIL_PROFESSOR and not self.servico.primeiro_acesso:
            flash(
                "O professor responsável já foi cadastrado. Entre com a conta existente.",
                "aviso",
            )
            return redirect(url_for("login", perfil="professor"))
        return render_template("criar_conta.html", perfil=perfil_normalizado)

    def post(self, perfil):
        perfil_normalizado = self._perfil(perfil)
        try:
            usuario = self.servico.criar_conta(
                perfil_normalizado,
                request.form.get("nome", ""),
                request.form.get("identificador", ""),
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
                request.form.get("aceitou") == "1",
                request.form.get("codigo_configuracao", ""),
            )
            self.sessoes.autenticar(usuario)
            flash("Conta criada com sucesso.", "sucesso")
            destino = "painel_professor" if usuario.eh_professor else "area_aluno"
            return redirect(url_for(destino))
        except (ErroDominio, AcessoNegado) as erro:
            flash(str(erro), "erro")
            if perfil_normalizado == PERFIL_PROFESSOR and not self.servico.primeiro_acesso:
                return redirect(url_for("login", perfil="professor"))
            return render_template("criar_conta.html", perfil=perfil_normalizado)


class VisaoLogin(ControladorBase):
    @staticmethod
    def _perfil(perfil):
        perfil_normalizado = str(perfil).upper()
        if perfil_normalizado not in {PERFIL_PROFESSOR, PERFIL_ALUNO}:
            abort(404)
        return perfil_normalizado

    def get(self, perfil):
        perfil_normalizado = self._perfil(perfil)
        permite_cadastro = perfil_normalizado == PERFIL_ALUNO or self.servico.primeiro_acesso
        return render_template(
            "login.html",
            perfil=perfil_normalizado,
            permite_cadastro=permite_cadastro,
        )

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
            if usuario.primeiro_acesso:
                flash("Crie uma senha pessoal para concluir o primeiro login.", "aviso")
                return redirect(url_for("primeiro_login"))
            if usuario.eh_professor:
                if not servico.recuperacao_configurada():
                    flash("Configure seu código de recuperação em Segurança.", "aviso")
                return redirect(url_for("painel_professor"))
            return redirect(url_for("area_aluno"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            permite_cadastro = perfil_normalizado == PERFIL_ALUNO or self.servico.primeiro_acesso
            return render_template(
                "login.html",
                perfil=perfil_normalizado,
                permite_cadastro=permite_cadastro,
            )


class VisaoPrimeiroLogin(ControladorProtegido):
    @staticmethod
    def _destino(usuario):
        return "painel_professor" if usuario.eh_professor else "area_aluno"

    def get(self):
        if not g.usuario.primeiro_acesso:
            return redirect(url_for(self._destino(g.usuario)))
        return render_template("primeiro_login.html")

    def post(self):
        if not g.usuario.primeiro_acesso:
            return redirect(url_for(self._destino(g.usuario)))
        try:
            usuario = self.servico.alterar_senha_primeiro_acesso(
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
                request.form.get("aceitou") == "1",
            )
            flash("Primeiro login concluído.", "sucesso")
            return redirect(url_for(self._destino(usuario)))
        except (ErroDominio, AcessoNegado) as erro:
            flash(str(erro), "erro")
            return render_template("primeiro_login.html")


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
        return render_template("recuperar_aluno.html")


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


class VisaoSeguranca(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

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
        return render_template("alunos.html", alunos=self.servico.listar_alunos())

    def post(self):
        try:
            self.servico.criar_aluno(
                request.form.get("nome", ""),
                request.form.get("matricula", ""),
                request.form.get("senha", ""),
                request.form.get("confirmacao", ""),
            )
            flash("Aluno cadastrado. A senha informada é temporária.", "sucesso")
            return redirect(url_for("alunos"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return self.get()


class VisaoAlterarStatusAluno(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, aluno_id):
        try:
            aluno = self.servico.alternar_aluno(aluno_id)
            flash(f"{aluno.nome}: status atualizado.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("alunos"))


class VisaoExcluirAluno(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def post(self, aluno_id):
        try:
            self.servico.excluir_aluno(aluno_id)
            flash("Aluno excluído.", "sucesso")
        except ErroDominio as erro:
            flash(str(erro), "erro")
        return redirect(url_for("alunos"))


class VisaoSenhaAluno(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def _aluno(self, aluno_id):
        aluno = self.servico.buscar_aluno(aluno_id)
        if aluno is None or not aluno.eh_aluno:
            abort(404)
        return aluno

    def get(self, aluno_id):
        return render_template("reset_aluno.html", aluno=self._aluno(aluno_id))

    def post(self, aluno_id):
        aluno = self._aluno(aluno_id)
        try:
            self.servico.redefinir_senha_aluno(
                aluno.id, request.form.get("senha", ""), request.form.get("confirmacao", "")
            )
            flash("Senha temporária criada. O aluno deverá trocá-la.", "sucesso")
            return redirect(url_for("alunos"))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return render_template("reset_aluno.html", aluno=aluno)


class VisaoAuditoria(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        return render_template("auditoria.html", eventos=self.servico.listar_auditoria())


class VisaoIa(ControladorProtegido):
    perfil_exigido = PERFIL_PROFESSOR

    def get(self):
        return render_template("ia.html", questao=None, tema="", dificuldade="MÉDIO")

    def post(self):
        tema = request.form.get("tema", "")
        dificuldade = request.form.get("dificuldade", "MÉDIO")
        questao = None
        try:
            questao = self.servico.gerar_questao(tema, dificuldade)
            flash("Rascunho criado. Revise antes de utilizar.", "sucesso")
        except (ErroDominio, ErroGemini) as erro:
            flash(str(erro), "erro")
        return render_template("ia.html", questao=questao, tema=tema, dificuldade=dificuldade)


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
        return render_template("questoes.html", questoes=self.servico.listar_questoes())

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
        except (ErroDominio, ErroGemini) as erro:
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
        except (AcessoNegado, ErroDominio, ErroGemini) as erro:
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
            resultado=None,
            desempenho=self.servico.meu_desempenho(),
        )

    def post(self, modo):
        modo = self._modo(modo)
        try:
            questao_id = int(request.form.get("questao_id", "0"))
        except (TypeError, ValueError):
            questao_id = 0
        questao = self.servico.buscar_questao(questao_id)
        if questao is None:
            flash("A questão não está mais disponível.", "erro")
            return redirect(url_for("jogar", modo=modo.lower()))
        try:
            resultado = self.servico.responder_questao(
                questao.id, request.form.get("alternativa", ""), modo
            )
        except ErroDominio as erro:
            flash(str(erro), "erro")
            resultado = None
        return render_template(
            "jogar.html",
            modo=modo,
            questao=questao,
            resultado=resultado,
            desempenho=self.servico.meu_desempenho(),
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
                request.form.get("nome", ""), request.form.getlist("questoes")
            )
            flash(
                f"Sala {sala.nome} criada. Compartilhe o código {sala.codigo} com os alunos.",
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
        return render_template("multijogador.html")

    def post(self):
        try:
            sala = self.servico.entrar_sala_multijogador(request.form.get("codigo", ""))
            flash("Você entrou na sala.", "sucesso")
            return redirect(url_for("sala_multijogador", codigo=sala.codigo))
        except ErroDominio as erro:
            flash(str(erro), "erro")
            return render_template("multijogador.html")


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
        return render_template("desempenho.html", dashboard=self.servico.dashboard_pedagogica())


class VisaoAreaAluno(ControladorProtegido):
    perfil_exigido = PERFIL_ALUNO

    def get(self):
        return render_template("aluno.html", desempenho=self.servico.meu_desempenho())


class VisaoPrivacidadeConta(ControladorProtegido):
    """Permite ao titular anonimizar ou excluir a própria conta."""

    def get(self):
        return render_template("conta.html")

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


class AplicacaoTaskFlowWeb:
    """Compõe infraestrutura, ciclo de requisição e controladores do sistema."""

    def __init__(self, raiz, configuracao=None):
        self.raiz = Path(raiz)
        self.configuracao = dict(configuracao or {})
        banco_sqlite_teste = "BANCO" in self.configuracao
        banco = Path(
            self.configuracao.pop(
                "BANCO", self.raiz / "banco_de_dados" / "dados" / "taskflow.sqlite3"
            )
        )
        configuracao_mysql = self.configuracao.pop("MYSQL", None)
        usa_sqlite_exclusivamente_em_teste = bool(
            self.configuracao.get("TESTING") and banco_sqlite_teste and configuracao_mysql is None
        )
        if usa_sqlite_exclusivamente_em_teste:
            configuracao_mysql = None
        elif configuracao_mysql is None:
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
        codigo_configuracao_professor = self.configuracao.pop(
            "CODIGO_CONFIGURACAO_PROFESSOR",
            os.getenv("TASKFLOW_SETUP_CODE", ""),
        )

        self.app = Flask(
            __name__,
            template_folder=str(self.raiz / "frontend" / "templates"),
            static_folder=str(self.raiz / "frontend" / "static"),
        )
        self.app.config.update(
            SECRET_KEY=self._chave_sessao(banco),
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            MAX_CONTENT_LENGTH=64 * 1024,
        )
        self.app.config.update(self.configuracao)

        self.dependencias = DependenciasWeb(
            RepositorioTaskFlow(
                banco,
                chave_dados=chave_dados,
                configuracao_mysql=configuracao_mysql,
            ),
            gemini,
            {},
            str(codigo_configuracao_professor).strip(),
        )
        self.sessoes = GerenciadorSessao(self.dependencias.repositorio)
        self.app.extensions["taskflow_repositorio"] = self.dependencias.repositorio
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
            if g.usuario and request.endpoint != "static":
                agora = time.time()
                ultima = session.get("ultima_atividade", agora)
                em_partida = request.endpoint in {"jogar", "sala_multijogador", "proxima_rodada_multijogador"}
                mantendo_partida = (request.endpoint == "atividade_sessao" and session.get("em_partida") and request.headers.get("X-Partida") == "1")
                if agora - ultima >= 600 and not mantendo_partida:
                    session.clear()
                    g.usuario = None
                    flash("Sua sessão expirou após 10 minutos sem atividade. Entre novamente.", "erro")
                    return redirect(url_for("inicio"))
                session["ultima_atividade"] = agora
                if request.endpoint != "atividade_sessao":
                    session["em_partida"] = em_partida
            ProtecaoCsrf.validar_requisicao()
            permitidos = {"primeiro_login", "termos", "conta", "sair", "static"}
            if g.usuario and g.usuario.primeiro_acesso and request.endpoint not in permitidos:
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
            return {"csrf": ProtecaoCsrf.token(), "usuario_atual": g.usuario}

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
            ("/login/<perfil>", "login", VisaoLogin),
            ("/primeiro-login", "primeiro_login", VisaoPrimeiroLogin),
            ("/recuperar-professor", "recuperar_professor", VisaoRecuperarProfessor),
            ("/recuperar-aluno", "recuperar_aluno", VisaoRecuperarAluno),
            ("/sair", "sair", VisaoSair),
            ("/professor", "painel_professor", VisaoPainelProfessor),
            ("/seguranca", "seguranca", VisaoSeguranca),
            ("/alunos", "alunos", VisaoAlunos),
            ("/alunos/<int:aluno_id>/status", "alterar_status_aluno", VisaoAlterarStatusAluno),
            ("/alunos/<int:aluno_id>/excluir", "excluir_aluno", VisaoExcluirAluno),
            ("/alunos/<int:aluno_id>/senha", "reset_aluno", VisaoSenhaAluno),
            ("/auditoria", "auditoria", VisaoAuditoria),
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
            ("/aluno", "area_aluno", VisaoAreaAluno),
            ("/conta", "conta", VisaoPrivacidadeConta),
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
