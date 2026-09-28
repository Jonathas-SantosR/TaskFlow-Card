# TaskFlowCards Web — Segunda versão

Este repositório contém a segunda versão do TaskFlowCards, agora funcionando como uma aplicação web. O projeto foi desenvolvido com Python, Flask, HTML, CSS e JavaScript, usando MySQL 8 como banco de dados.

A proposta continua sendo utilizar perguntas em atividades pedagógicas de uma forma mais dinâmica. Nesta versão, o professor administra os alunos, prepara as questões e cria as salas. Os alunos podem treinar contra o bot ou participar das partidas on-line criadas pelo professor.

## O que já está funcionando

### Acesso e segurança

- login separado para professor e aluno;
- autorização de acordo com o perfil do usuário;
- criação do primeiro professor protegida por um código de configuração;
- troca obrigatória da senha temporária no primeiro acesso do aluno;
- recuperação da conta do professor por um código definido por ele;
- bloqueio temporário depois de várias tentativas erradas de login;
- proteção CSRF nos formulários e cookies de sessão com `HttpOnly`;
- registro das ações importantes na auditoria.

### Funções do professor

- cadastrar, bloquear, ativar e excluir alunos;
- criar uma nova senha temporária para um aluno;
- cadastrar, editar, liberar, pausar e excluir questões;
- gerar ou adaptar um rascunho de questão com o Google Gemini;
- solicitar a narração de uma questão com o Gemini Text-to-Speech;
- acompanhar as respostas, os acertos e os pontos dos alunos;
- consultar os registros de auditoria;
- criar, consultar, editar e excluir salas on-line.

Ao criar uma sala, o professor informa um nome, escolhe as questões e compartilha o código gerado com os alunos. As perguntas são apresentadas na ordem escolhida e as rodadas avançam automaticamente quando todos respondem.

### Funções do aluno

- criar a própria conta ou utilizar uma conta preparada pelo professor;
- aceitar os Termos de Uso e a Política de Privacidade no primeiro acesso;
- jogar no modo Contra Bot;
- entrar em uma sala on-line utilizando o código enviado pelo professor;
- receber feedback depois de responder;
- acompanhar o próprio desempenho;
- solicitar anonimização ou exclusão definitiva da conta.

No modo Contra Bot, o sistema evita repetir uma pergunta enquanto ainda houver outra questão ativa que o aluno não tenha respondido naquele ciclo.

## LGPD e privacidade

Os Termos de Uso e a Política de Privacidade podem ser acessados pelo rodapé do sistema a qualquer momento. A página explica quais dados são utilizados, por que são necessários e como o usuário pode exercer seus direitos.

Nome, e-mail e matrícula são criptografados antes de serem armazenados. Senhas e códigos de recuperação não são guardados em texto puro. Professor e aluno também possuem uma área própria para anonimizar ou excluir definitivamente a conta.

A auditoria utiliza IDs internos e não registra senhas, e-mails ou matrículas. Os eventos possuem assinatura digital para ajudar a identificar alterações indevidas.

## Requisitos

- Python 3.13;
- MySQL 8 em execução;
- usuário e senha com acesso ao banco escolhido;
- conexão com a internet somente para utilizar o Gemini.

O Gemini é opcional. Sem uma chave da API, o cadastro manual de questões, os jogos, os feedbacks e o restante do sistema continuam funcionando normalmente.

## Como iniciar

1. Verifique se o serviço do MySQL está funcionando.
2. Abra o arquivo `INICIAR.bat`.
3. Informe o servidor, a porta, o nome do banco, o usuário e a senha do MySQL. Os valores mostrados entre colchetes podem ser confirmados apenas pressionando Enter.
4. Se ainda não existir um professor, informe um código no campo **Código do primeiro professor**. Esse mesmo código será solicitado na criação da primeira conta administrativa. Se o professor já existir, deixe esse campo vazio.
5. Responda se deseja utilizar o Google Gemini. Se escolher `S`, informe a chave criada no Google AI Studio.
6. Aguarde até o terminal mostrar o endereço:

```text
http://127.0.0.1:5000
```

O navegador não é aberto automaticamente. Copie o endereço ou digite-o no navegador que preferir. O terminal precisa continuar aberto durante o uso. Para encerrar o servidor, pressione `Ctrl + C`.

Na primeira execução, o `INICIAR.bat` cria o ambiente virtual `.venv` e instala as bibliotecas listadas em `requirements.txt`.

## Como os arquivos de inicialização e teste foram feitos

Os arquivos `INICIAR.bat`, `INICIAR_MYSQL.ps1` e `TESTAR.bat` são arquivos de texto com comandos do Windows. Eles não são programas compilados e podem ser abertos no VS Code ou no Bloco de Notas.

No Explorador de Arquivos, o Windows pode ocultar as extensões. Nesse caso, `INICIAR` é o arquivo `INICIAR.bat`, `INICIAR_MYSQL` é `INICIAR_MYSQL.ps1` e `TESTAR` é `TESTAR.bat`.

Para criar arquivos desse tipo manualmente:

1. Abra a pasta do projeto no VS Code.
2. Crie um arquivo novo.
3. Salve usando exatamente a extensão `.bat` ou `.ps1`.
4. Deixe os arquivos na pasta principal, no mesmo local do `app.py`.
5. Confira se o Windows não acrescentou `.txt` ao nome. O arquivo precisa se chamar `INICIAR.bat`, e não `INICIAR.bat.txt`.

Os três arquivos trabalham desta forma:

```text
INICIAR.bat
    └── chama INICIAR_MYSQL.ps1
            └── configura MySQL e Gemini
                    └── executa app.py

TESTAR.bat
    └── usa o Python da .venv
            └── executa os testes da pasta tests
```

### Código do `INICIAR.bat`

```bat
@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=py"

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  "%PYTHON_EXE%" -3 -m venv .venv 2>nul || "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 goto erro
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_MYSQL.ps1"
if errorlevel 1 goto erro
goto fim

:erro
echo.
echo Nao foi possivel iniciar. Confira o Python e a configuracao do MySQL.
pause

:fim
endlocal
```

O `@echo off` evita que todos os comandos sejam repetidos na tela. O `cd /d "%~dp0"` faz o terminal entrar na pasta onde o arquivo está salvo. Depois, o script procura o Python 3.13 e usa o comando `py` como alternativa.

Se a pasta `.venv` ainda não existir, o próprio arquivo cria o ambiente virtual. Em seguida, instala as dependências do `requirements.txt` e chama o script `INICIAR_MYSQL.ps1`. Se alguma etapa falhar, o fluxo vai para `:erro` e mantém a mensagem visível com `pause`.

### Código do `INICIAR_MYSQL.ps1`

```powershell
$ErrorActionPreference = "Stop"
$executavel = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$aplicacao = Join-Path $PSScriptRoot "app.py"

$hostInformado = Read-Host "Servidor MySQL [127.0.0.1]"
$portaInformada = Read-Host "Porta MySQL [3306]"
$bancoInformado = Read-Host "Nome do banco [taskflowcards]"
$usuarioInformado = Read-Host "Usuário MySQL"
$senhaSegura = Read-Host "Senha MySQL" -AsSecureString
$credencial = [System.Net.NetworkCredential]::new("", $senhaSegura)
$codigoInicial = Read-Host "Código do primeiro professor (deixe vazio se já existe)" -AsSecureString
$credencialInicial = [System.Net.NetworkCredential]::new("", $codigoInicial)

$env:TASKFLOW_MYSQL_HOST = if ($hostInformado) { $hostInformado } else { "127.0.0.1" }
$env:TASKFLOW_MYSQL_PORT = if ($portaInformada) { $portaInformada } else { "3306" }
$env:TASKFLOW_MYSQL_DATABASE = if ($bancoInformado) { $bancoInformado } else { "taskflowcards" }
$env:TASKFLOW_MYSQL_USER = $usuarioInformado
$env:TASKFLOW_MYSQL_PASSWORD = $credencial.Password
if ($credencialInicial.Password) {
    $env:TASKFLOW_SETUP_CODE = $credencialInicial.Password
}

$usarGemini = Read-Host "Deseja usar o Google Gemini? [S/N]"
if ($usarGemini -match '^[Ss]$') {
    $geminiSegura = Read-Host "Chave do Google AI Studio" -AsSecureString
    $credencialGemini = [System.Net.NetworkCredential]::new("", $geminiSegura)
    $env:GEMINI_API_KEY = $credencialGemini.Password
    $env:GEMINI_MODEL = "gemini-3.5-flash-lite"
}

try {
    Write-Host ""
    Write-Host "Servidor pronto para iniciar." -ForegroundColor Green
    Write-Host "O navegador não será aberto automaticamente." -ForegroundColor Cyan
    & $executavel $aplicacao
}
finally {
    Remove-Item Env:TASKFLOW_MYSQL_HOST -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_DATABASE -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_USER -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_SETUP_CODE -ErrorAction SilentlyContinue
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:GEMINI_MODEL -ErrorAction SilentlyContinue
}
```

Esse arquivo foi separado porque o PowerShell permite solicitar senhas sem mostrá-las na tela usando `-AsSecureString`. Ele recebe as informações do MySQL e guarda esses valores apenas em variáveis de ambiente do processo.

Se o Gemini for ativado, a chave também fica somente no ambiente enquanto o servidor estiver funcionando. O bloco `try` executa o `app.py`. O bloco `finally` remove as variáveis quando o programa termina, mesmo que ocorra algum erro.

O `INICIAR.bat` chama esse script usando `-ExecutionPolicy Bypass` apenas para aquela execução. Isso evita alterar permanentemente a política do PowerShell do computador.

### Código do `TESTAR.bat`

```bat
@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INICIAR.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -m unittest -v
pause
endlocal
```

O `TESTAR.bat` verifica primeiro se o ambiente virtual já foi criado. Depois utiliza o Python da própria `.venv` para executar o `unittest`. A opção `-B` impede a criação de arquivos de cache durante os testes e `-v` mostra o nome e o resultado de cada teste. O `pause` deixa a janela aberta para que o resultado possa ser lido.

Esses arquivos não guardam a senha do MySQL nem a chave do Gemini. As informações são solicitadas a cada inicialização e permanecem somente enquanto o processo estiver aberto.

## Banco de dados

A aplicação utiliza somente MySQL 8 durante a execução. As tabelas são criadas e atualizadas automaticamente quando o projeto inicia. Elas utilizam InnoDB e `utf8mb4`.

O SQLite aparece apenas nos bancos temporários dos testes automatizados; ele não é uma opção de banco para executar o sistema.

A chave usada para criptografar os dados fica em `data/.data_key`. As chaves da assinatura da auditoria ficam em `data/.audit_private.pem` e `data/.audit_private.pub`. Esses arquivos não devem ser enviados ao GitHub. Para não perder o acesso aos dados criptografados, o backup do MySQL deve ser acompanhado das chaves.

Mais informações estão em `documentacao/MYSQL.md`.

## Criptografia utilizada

- Fernet para criptografar nome, e-mail e matrícula;
- HMAC para criar índices de busca de login que não revelam o identificador;
- PBKDF2-HMAC-SHA256 com salt para senhas e códigos de recuperação;
- Ed25519 para assinar os eventos da auditoria e detectar adulterações.

Essas proteções cuidam dos dados armazenados. Em uma publicação real, ainda seria necessário utilizar HTTPS/TLS e manter as chaves em um local seguro.

## Integração com o Gemini

A integração com o Google Gemini é utilizada para gerar e adaptar questões e, quando disponível, produzir a narração. O professor sempre deve revisar o conteúdo antes de liberá-lo para os alunos.

A chave fica somente no ambiente do servidor e não é colocada no código ou no navegador. A documentação técnica está em `documentacao/INTEGRACAO_GEMINI.md`.

## Estrutura principal

```text
app.py                 ponto de entrada da aplicação
INICIAR.bat            inicializador principal
INICIAR_MYSQL.ps1      configuração interna usada pelo inicializador
requirements.txt       dependências do projeto
taskflow/              domínio, serviços, segurança, banco e Gemini
templates/             páginas HTML com Jinja
static/                estilos e JavaScript
tests/                 testes automatizados
documentacao/          documentação técnica e de privacidade
```
