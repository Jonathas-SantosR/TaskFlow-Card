"""TaskFlowCards Web: API Flask e página única para salas e alunos."""

import argparse
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from backend import ErroValidacaoSala, RepositorioSalas, SalaNaoEncontrada
from student_backend import (
    AlunoNaoEncontrado,
    ErroValidacaoAluno,
    RepositorioAlunos,
)

DIRETORIO_BASE = Path(__file__).resolve().parent
BANCO_PADRAO = DIRETORIO_BASE / "data" / "salas.sqlite3"


def criar_aplicacao(banco=None):
    """Monta a aplicação e permite trocar o banco durante os testes."""
    aplicacao = Flask(__name__)
    aplicacao.config.update(
        BANCO_DE_DADOS=str(banco or BANCO_PADRAO),
        JSON_SORT_KEYS=False,
    )

    # Cada requisição recebe sua própria conexão. Isso evita compartilhar uma
    # conexão SQLite entre requisições executadas em threads diferentes.
    def repositorio_salas():
        return RepositorioSalas(aplicacao.config["BANCO_DE_DADOS"])

    def repositorio_alunos():
        return RepositorioAlunos(aplicacao.config["BANCO_DE_DADOS"])

    # Páginas e diagnóstico -------------------------------------------------

    @aplicacao.get("/")
    def pagina_inicial():
        return render_template("index.html")

    @aplicacao.get("/api/saude")
    def saude():
        return jsonify(status="ok", aplicacao="TaskFlowCards Web")

    # API de salas ----------------------------------------------------------

    @aplicacao.route("/api/salas", methods=["GET", "POST"])
    def colecao_salas():
        repositorio = repositorio_salas()
        try:
            if request.method == "GET":
                status = request.args.get("status") or None
                salas = repositorio.listar(request.args.get("busca", ""), status)
                return jsonify(dados=[sala.para_dict() for sala in salas])
            dados = request.get_json(silent=True) or {}
            sala = repositorio.criar(
                dados.get("nome", ""),
                dados.get("descricao", ""),
                dados.get("modo", "CLASSICO"),
                dados.get("status", "ABERTA"),
            )
            return jsonify(dados=sala.para_dict()), 201
        finally:
            repositorio.fechar()

    @aplicacao.route("/api/salas/<int:sala_id>", methods=["GET", "PUT", "DELETE"])
    def item_sala(sala_id):
        repositorio = repositorio_salas()
        try:
            if request.method == "GET":
                return jsonify(dados=repositorio.buscar(sala_id).para_dict())
            if request.method == "DELETE":
                repositorio.excluir(sala_id)
                return "", 204
            dados = request.get_json(silent=True) or {}
            sala = repositorio.atualizar(
                sala_id,
                dados.get("nome", ""),
                dados.get("descricao", ""),
                dados.get("modo", "CLASSICO"),
                dados.get("status", "ABERTA"),
            )
            return jsonify(dados=sala.para_dict())
        finally:
            repositorio.fechar()

    # API de alunos ---------------------------------------------------------

    @aplicacao.route("/api/alunos", methods=["GET", "POST"])
    def colecao_alunos():
        repositorio = repositorio_alunos()
        try:
            if request.method == "GET":
                status = request.args.get("status") or None
                alunos = repositorio.listar(request.args.get("busca", ""), status)
                return jsonify(dados=[aluno.para_dict() for aluno in alunos])
            dados = request.get_json(silent=True) or {}
            aluno = repositorio.criar(
                dados.get("nome", ""),
                dados.get("matricula", ""),
                dados.get("email", ""),
                dados.get("status", "ATIVO"),
            )
            return jsonify(dados=aluno.para_dict()), 201
        finally:
            repositorio.fechar()

    @aplicacao.route("/api/alunos/<int:aluno_id>", methods=["GET", "PUT", "DELETE"])
    def item_aluno(aluno_id):
        repositorio = repositorio_alunos()
        try:
            if request.method == "GET":
                return jsonify(dados=repositorio.buscar(aluno_id).para_dict())
            if request.method == "DELETE":
                repositorio.excluir(aluno_id)
                return "", 204
            dados = request.get_json(silent=True) or {}
            aluno = repositorio.atualizar(
                aluno_id,
                dados.get("nome", ""),
                dados.get("matricula", ""),
                dados.get("email", ""),
                dados.get("status", "ATIVO"),
            )
            return jsonify(dados=aluno.para_dict())
        finally:
            repositorio.fechar()

    # Tradução das exceções do domínio para respostas HTTP previsíveis.
    @aplicacao.errorhandler(ErroValidacaoSala)
    @aplicacao.errorhandler(ErroValidacaoAluno)
    def erro_validacao(erro):
        return jsonify(erro=str(erro)), 400

    @aplicacao.errorhandler(SalaNaoEncontrada)
    @aplicacao.errorhandler(AlunoNaoEncontrado)
    def nao_encontrado(erro):
        return jsonify(erro=str(erro)), 404

    @aplicacao.errorhandler(sqlite3.Error)
    def erro_banco(_erro):
        return jsonify(erro="Não foi possível acessar o banco de dados."), 500

    return aplicacao


def principal():
    """Lê os argumentos do terminal e inicia o servidor de desenvolvimento."""
    analisador = argparse.ArgumentParser(description="TaskFlowCards Web")
    analisador.add_argument("--banco", type=Path, default=BANCO_PADRAO)
    analisador.add_argument("--host", default="127.0.0.1")
    analisador.add_argument("--porta", type=int, default=5000)
    argumentos = analisador.parse_args()
    criar_aplicacao(argumentos.banco).run(
        host=argumentos.host,
        port=argumentos.porta,
        debug=False,
    )


if __name__ == "__main__":
    principal()
