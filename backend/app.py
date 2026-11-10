"""Ponto de entrada da versão web orientada a objetos."""

import logging
from pathlib import Path

from backend.taskflow.web import AplicacaoTaskFlowWeb

RAIZ = Path(__file__).resolve().parent.parent


def criar_aplicacao(configuracao=None):
    """Fábrica compatível com Flask e testes automatizados."""
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


if __name__ == "__main__":
    arquivo_log = RAIZ / "banco_de_dados" / "dados" / "inicializacao.log"
    arquivo_log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=arquivo_log,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        executar_servidor()
    except Exception:
        logging.exception("Não foi possível iniciar o TaskFlowCards.")
        print(
            f"Não foi possível iniciar. Consulte o log: {arquivo_log}",
            flush=True,
        )
        raise
