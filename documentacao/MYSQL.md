# MySQL na segunda versão

O TaskFlowCards usa MySQL 8 com o driver PyMySQL como único banco durante a
execução. SQLite aparece apenas em bancos temporários isolados dos testes
automatizados; não existe modo SQLite no sistema.

## Requisitos

- servidor MySQL 8 em execução;
- usuário MySQL com permissão para criar e utilizar o banco escolhido;
- dependências instaladas por `pip install -r requirements.txt`.

O projeto cria as tabelas automaticamente com InnoDB e `utf8mb4`. Nenhuma
senha do MySQL deve ser gravada no código ou enviada ao GitHub.
Uma restrição única baseada em coluna gerada garante no próprio banco que
somente um professor administrativo não anonimizado possa existir, inclusive
sob acessos simultâneos.

## Iniciar diretamente no MySQL

Execute `INICIAR.bat` e informe servidor, porta, banco, usuário e senha.
A senha é digitada de forma oculta e fica somente no ambiente do processo.

As variáveis aceitas são:

| Variável | Exemplo | Finalidade |
| --- | --- | --- |
| `TASKFLOW_MYSQL_HOST` | `127.0.0.1` | Servidor |
| `TASKFLOW_MYSQL_PORT` | `3306` | Porta |
| `TASKFLOW_MYSQL_DATABASE` | `taskflowcards` | Banco |
| `TASKFLOW_MYSQL_USER` | `taskflow_app` | Usuário da aplicação |
| `TASKFLOW_MYSQL_PASSWORD` | valor secreto | Senha da aplicação |
| `TASKFLOW_MYSQL_SSL_CA` | caminho do certificado | TLS para servidor remoto |

Em produção, use um usuário exclusivo com privilégios apenas sobre o banco
`taskflowcards`. Para conexão remota, configure TLS por
`TASKFLOW_MYSQL_SSL_CA`; não exponha a porta 3306 diretamente à internet.

Os arquivos `banco_de_dados/dados/.data_key` e `banco_de_dados/dados/.audit_private.pem` devem ser mantidos com
a aplicação e protegidos no backup, pois permitem descriptografar os dados e
validar ou assinar a auditoria.
