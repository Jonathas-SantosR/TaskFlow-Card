"""Ponto de entrada da versão web orientada a objetos."""

import logging
import os
from pathlib import Path

from backend.taskflow.criptografia import ErroCriptografia
from backend.taskflow.web import AplicacaoTaskFlowWeb
from banco_de_dados.banco import ErroAutenticacaoMySQL, ErroConfiguracaoBanco

RAIZ = Path(__file__).resolve().parent.parent


def _pasta_dados():
    return Path(os.environ.get("TASKFLOW_DATA_DIR") or RAIZ / "banco_de_dados" / "dados")


def criar_aplicacao(configuracao=None):
    """Fábrica compatível com Flask e testes automatizados."""
    if os.environ.get("TASKFLOW_DATA_DIR"):
        configuracao = dict(configuracao or {})
        configuracao.setdefault("BANCO", _pasta_dados() / "taskflow.sqlite3")
    return AplicacaoTaskFlowWeb(RAIZ, configuracao).criar()


def executar_servidor():
    """Executa o servidor e deixa o endereço disponível para acesso manual."""

    from werkzeug.serving import make_server

    endereco = "http://127.0.0.1:5000"
    aplicacao = criar_aplicacao()
    servidor = make_server("127.0.0.1", 5000, aplicacao, threaded=True)
    print("", flush=True)
    print("TASKFLOWCARDS INICIADO", flush=True)
    print(f"Acesse no navegador: {endereco}", flush=True)
    print("Para encerrar o servidor, pressione Ctrl + C.", flush=True)
    print("", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.", flush=True)
    finally:
        # serve_forever ja terminou; shutdown e destinado a outra thread
        # enquanto o loop esta ativo. Aqui basta liberar o socket.
        servidor.server_close()
        aplicacao.extensions["taskflow_recuperacao"].fechar()
        aplicacao.extensions["taskflow_repositorio"].fechar()


if __name__ == "__main__":
    arquivo_log = _pasta_dados() / "inicializacao.log"
    arquivo_log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=arquivo_log,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        executar_servidor()
    except ErroAutenticacaoMySQL as erro:
        logging.exception("Não foi possível autenticar no MySQL.")
        print(erro, flush=True)
        raise SystemExit(2) from None
    except ErroCriptografia as erro:
        logging.exception("Não foi possível abrir os dados do TaskFlowCards.")
        print(erro, flush=True)
        print("Confira o nome do banco MySQL e a chave de dados (.data_key) dessa instalação.", flush=True)
        raise SystemExit(3) from None
    except ErroConfiguracaoBanco as erro:
        logging.exception("Não foi possível iniciar o TaskFlowCards.")
        print(erro, flush=True)
        raise SystemExit(1) from None
    except Exception:
        logging.exception("Não foi possível iniciar o TaskFlowCards.")
        print(
            f"Não foi possível iniciar. Consulte o log: {arquivo_log}",
            flush=True,
        )
        raise
