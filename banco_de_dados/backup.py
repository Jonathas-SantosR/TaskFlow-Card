"""Backup local do MySQL e das chaves; restauração somente em destino vazio.

Use apenas arquivos de backup confiáveis. O ZIP contém dados e chaves privadas:
guarde-o fora do Git, com acesso restrito, e pare a aplicação durante a operação.
"""

import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from banco_de_dados.banco import conectar_mysql

CHAVES = (".data_key", ".audit_private.pem", ".audit_private.pub", ".session_secret")


def _executavel(nome):
    encontrado = shutil.which(nome)
    if encontrado:
        return encontrado
    raiz = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "MySQL"
    candidatos = sorted(raiz.glob(f"MySQL Server */bin/{nome}.exe"))
    if candidatos:
        return str(candidatos[-1])
    raise RuntimeError(f"Instale as ferramentas MySQL e coloque {nome} no PATH.")


def _rodar(nome, config, argumentos, entrada=None, saida=None):
    ambiente = os.environ.copy()
    ambiente["MYSQL_PWD"] = config.get("password", "")
    comando = [
        _executavel(nome),
        "--no-defaults",
        "--protocol=TCP",
        "--host=" + config["host"],
        "--port=" + str(config["port"]),
        "--user=" + config["user"],
    ]
    if config.get("ssl_ca"):
        comando.extend(["--ssl-mode=VERIFY_IDENTITY", "--ssl-ca=" + config["ssl_ca"]])
    resultado = subprocess.run(
        comando + argumentos,
        env=ambiente,
        stdin=entrada,
        stdout=saida,
        stderr=subprocess.PIPE,
        check=False,
    )
    if resultado.returncode:
        # Não imprimir credenciais nem conteúdo do dump em mensagens de erro.
        raise RuntimeError(
            f"{nome} falhou (código {resultado.returncode}). Confira conexão e permissões."
        )


def criar_backup(config, diretorio_chaves, destino):
    destino = Path(destino)
    if destino.exists():
        raise ValueError("O arquivo de destino já existe.")
    arquivos = {nome: (Path(diretorio_chaves) / nome).read_bytes() for nome in CHAVES}
    conexao = conectar_mysql(config, criar_banco=False)
    conexao.close()
    with tempfile.TemporaryDirectory() as temporario:
        dump = Path(temporario) / "banco.sql"
        with dump.open("wb") as saida:
            _rodar(
                "mysqldump",
                config,
                [
                    "--single-transaction",
                    "--skip-lock-tables",
                    "--no-tablespaces",
                    "--set-gtid-purged=OFF",
                    "--column-statistics=0",
                    "--skip-add-drop-table",
                    config["database"],
                ],
                saida=saida,
            )
        arquivos["banco.sql"] = dump.read_bytes()
        manifesto = {
            "versao": 1,
            "sha256": {
                nome: hashlib.sha256(conteudo).hexdigest() for nome, conteudo in arquivos.items()
            },
        }
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("xb") as arquivo_zip:
            with zipfile.ZipFile(arquivo_zip, "w", zipfile.ZIP_DEFLATED) as pacote:
                for nome, conteudo in arquivos.items():
                    pacote.writestr(nome, conteudo)
                pacote.writestr("manifesto.json", json.dumps(manifesto))


def restaurar_backup(config, origem, diretorio_chaves):
    pasta = Path(diretorio_chaves)
    if pasta.exists() and any(pasta.iterdir()):
        raise ValueError("A pasta de chaves de destino precisa estar vazia.")
    esperados = set(CHAVES) | {"banco.sql", "manifesto.json"}
    with zipfile.ZipFile(origem) as pacote:
        if set(pacote.namelist()) != esperados or len(pacote.namelist()) != len(esperados):
            raise ValueError("Estrutura de backup inválida.")
        manifesto = json.loads(pacote.read("manifesto.json"))
        if manifesto.get("versao") != 1:
            raise ValueError("Versão de backup não suportada.")
        arquivos = {nome: pacote.read(nome) for nome in esperados - {"manifesto.json"}}
    for nome, conteudo in arquivos.items():
        if hashlib.sha256(conteudo).hexdigest() != manifesto.get("sha256", {}).get(nome):
            raise ValueError("Backup corrompido; restauração cancelada.")
    conexao = conectar_mysql(config)
    try:
        if conexao.execute("SHOW TABLES").fetchall():
            raise ValueError("O banco de destino precisa estar vazio. Nada foi substituído.")
    finally:
        conexao.close()
    with tempfile.TemporaryFile() as entrada:
        entrada.write(arquivos["banco.sql"])
        entrada.seek(0)
        _rodar("mysql", config, [config["database"]], entrada=entrada, saida=subprocess.DEVNULL)
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in CHAVES:
        (pasta / nome).write_bytes(arquivos[nome])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=("criar", "restaurar"))
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--banco", required=True)
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=3306)
    parser.add_argument("--chaves", type=Path, required=True)
    args = parser.parse_args()
    config = dict(
        host=args.host,
        port=args.porta,
        database=args.banco,
        user=args.usuario,
        password=getpass.getpass("Senha MySQL: "),
    )
    if args.acao == "criar":
        criar_backup(config, args.chaves, args.arquivo)
    else:
        restaurar_backup(config, args.arquivo, args.chaves)
    print("Operação concluída. Guarde o backup e as chaves em local de acesso restrito.")


if __name__ == "__main__":
    main()
