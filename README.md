# TaskFlowCards Web — Segunda versão

Este repositório contém a segunda versão do TaskFlowCards, agora funcionando como uma aplicação web. O projeto foi desenvolvido com Python, Flask, HTML, CSS e JavaScript, usando MySQL 8 como banco de dados.

A proposta continua sendo utilizar perguntas em atividades pedagógicas de uma forma mais dinâmica. Nesta versão, o professor administra os alunos, prepara as questões e cria as salas. Os alunos podem treinar contra o bot ou participar das partidas on-line criadas pelo professor.

## Como organizei o código

Separei o que aparece no navegador das regras executadas no servidor. O projeto
continua sendo uma aplicação Flask, sem precisar de dois servidores ou de dois
repositórios para isso.

| Local | Responsabilidade |
| --- | --- |
| `frontend/templates/` | Páginas HTML com Jinja, renderizadas pelo Flask. |
| `frontend/static/` | CSS e JavaScript enviados ao navegador. |
| `backend/taskflow/web.py` | Rotas, controladores, sessão e proteção dos formulários. |
| `backend/taskflow/dominio.py` | Entidades e validações do domínio. |
| `backend/taskflow/servicos/` | Regras de contas, questões, jogos, salas e desempenho. |
| `banco_de_dados/persistencia/` | Consultas e gravações, separadas por responsabilidade. |
| `backend/taskflow/gemini.py` | Comunicação com a API externa. |
| `backend/taskflow/criptografia.py` e `seguranca.py` | Criptografia, assinaturas e proteção de senhas. |

As classes `ServicoTaskFlow` e `RepositorioTaskFlow` funcionam como fachadas:
elas encaminham as chamadas para classes menores. Assim, as telas continuam
usando a mesma interface, mas as regras não ficam todas concentradas em uma classe.
Os serviços recebem suas dependências e compartilham o contexto do usuário apenas
dentro da mesma instância. Cada requisição cria seu serviço com a identidade da
sessão. Os repositórios compartilham a conexão e o bloqueio existentes para manter
o comportamento das transações. A preparação do esquema e das chaves fica em
`banco_de_dados/persistencia/infraestrutura.py`.

O MySQL continua armazenando os registros no próprio servidor. A pasta
`banco_de_dados/` reúne o código de conexão, o esquema e os repositórios. A subpasta
`dados/` preserva os arquivos locais de segurança e não é publicada no Git.
Para iniciar manualmente, execute `python -m backend.app` na raiz do projeto,
com as variáveis do MySQL configuradas. Pelo Windows, continue usando `INICIAR.bat`.

Essa organização facilita encontrar problemas, testar regras isoladamente e
alterar uma funcionalidade sem misturar código de outras áreas. Separar arquivos,
por si só, não garante segurança: o navegador pode ser modificado pelo usuário.
Por isso, as permissões e validações precisam continuar no back-end, mesmo quando
o formulário também faz uma validação visual. As páginas usam serviços para as
consultas de negócio; o gerenciador de sessão consulta a persistência para validar
se a conta continua ativa.

A chave do Gemini fica em `config/gemini-key.txt`, fora de `frontend/static/`, e não deve
ser enviada ao navegador nem incluída no Git ou no ZIP distribuído. Ela continua
sendo um arquivo de texto local, não um arquivo criptografado. A refatoração não
altera as regras de cadastro, exclusão de contas ou o esquema do banco.

Referências usadas para essa organização:
[modularização no Flask](https://flask.palletsprojects.com/en/stable/blueprints/) e
[autorização no servidor — OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## Funcionalidades

### Salvar a conexão com o MySQL

Ao abrir `INICIAR.bat`, informe servidor, porta, banco, usuário e senha. No final,
escolha **S** para salvar em `config/mysql-config.json`. Nas próximas aberturas:

- **Enter:** reutiliza a conexão salva;
- **A:** altera os campos e permite salvar as mudanças; Enter mantém cada valor anterior;
- **R:** remove somente a configuração salva e solicita uma conexão para aquela sessão;
- **N:** usa outra conexão apenas naquela sessão, preservando o arquivo anterior.

A alteração pergunta separadamente se você quer trocar a senha. Remover a
configuração não exclui o banco, as tabelas nem os resultados. O MySQL ainda
precisa estar iniciado. O código de configuração do primeiro professor não é salvo.

O arquivo é portátil e contém a senha em texto legível. Ele está no `.gitignore`,
mas também deve ser retirado ao compartilhar a pasta por ZIP, junto de
`config/gemini-key.txt`. O projeto deve ser entregue sem credenciais pessoais.
O auxiliar `MYSQL_CONFIGURACAO.ps1` cuida da leitura, validação, menu e gravação.
Para testar esse fluxo sem acessar um banco real:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests\TESTAR_CONFIGURACAO_MYSQL.ps1
```

As versões das dependências estão fixadas em `requirements.txt`. O inicializador
procura Python 3.11 ou superior por `py` ou `python`; uma `.venv` copiada de outro
computador precisa ser recriada se apontar para uma instalação inexistente.

Também há verificações locais de qualidade, testes com MySQL real, teste de
navegador e backup com restauração em destino vazio. Consulte
[Validação local](documentacao/VALIDACAO_LOCAL.md) e
[Backup e migrações](documentacao/BACKUP_E_MIGRACOES.md).
Esses recursos não dependem de automação no GitHub ou hospedagem pública.

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
4. Deixe os inicializadores na pasta principal, ao lado do `README.md`.
5. Confira se o Windows não acrescentou `.txt` ao nome. O arquivo precisa se chamar `INICIAR.bat`, e não `INICIAR.bat.txt`.

Os três arquivos trabalham desta forma:

```text
INICIAR.bat
    └── chama INICIAR_MYSQL.ps1
            └── configura MySQL e Gemini
                    └── executa backend/app.py

TESTAR.bat
    └── usa o Python da .venv
            └── executa os testes da pasta tests
```

### Código do `INICIAR.bat`

```bat
@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto validar_ambiente
py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if not errorlevel 1 goto criar_com_py
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if errorlevel 1 goto python_ausente
python -m venv .venv
if errorlevel 1 goto erro
goto validar_ambiente

:criar_com_py
py -3 -m venv .venv
if errorlevel 1 goto erro

:validar_ambiente
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3,11))"
if errorlevel 1 (
  echo O ambiente .venv nao e valido nesta maquina. Renomeie essa pasta e inicie novamente.
  goto erro
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro

rem O servidor usa um console proprio. Este lote termina antes de Ctrl+C,
rem evitando a confirmacao de encerramento do CMD durante o jogo.
start "TaskFlowCards - servidor" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_MYSQL.ps1"
goto fim

:erro
echo.
echo Nao foi possivel iniciar. Confira o Python e a configuracao do MySQL.
pause
goto fim

:python_ausente
echo Instale Python 3.11 ou superior e habilite o comando python ou py.
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
Set-Location -LiteralPath $PSScriptRoot

. (Join-Path $PSScriptRoot 'MYSQL_CONFIGURACAO.ps1')
$configuracaoMySql = Select-MySqlConfiguration -Path (Join-Path $PSScriptRoot 'config\mysql-config.json')
$codigoInicial = Read-Host "Código do primeiro professor (deixe vazio se já existe)" -AsSecureString
$credencialInicial = [System.Net.NetworkCredential]::new("", $codigoInicial)

$env:TASKFLOW_MYSQL_HOST = $configuracaoMySql.servidor
$env:TASKFLOW_MYSQL_PORT = [string]$configuracaoMySql.porta
$env:TASKFLOW_MYSQL_DATABASE = $configuracaoMySql.banco
$env:TASKFLOW_MYSQL_USER = $configuracaoMySql.usuario
$env:TASKFLOW_MYSQL_PASSWORD = $configuracaoMySql.senha
if ($credencialInicial.Password) {
    $env:TASKFLOW_SETUP_CODE = $credencialInicial.Password
}

. (Join-Path $PSScriptRoot 'GEMINI_CREDENCIAL.ps1')
$arquivoGemini = Join-Path $PSScriptRoot 'config\gemini-key.txt'
$geminiSegura = $null
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
try {
    $geminiSegura = Read-GeminiCredential -Path $arquivoGemini
}
catch {
    Write-Host 'Nao foi possivel ler config/gemini-key.txt. Confira o arquivo ou cadastre a chave novamente.' -ForegroundColor Yellow
}
if ($geminiSegura) {
    Write-Host 'Chave Gemini encontrada em config/gemini-key.txt.' -ForegroundColor Green
    do {
        $opcaoGemini = (Read-Host 'Gemini: Enter para usar a chave salva, A para alterar, R para remover, N para nao usar nesta sessao').Trim().ToUpperInvariant()
    } while ($opcaoGemini -notin @('', 'A', 'R', 'N'))
    if ($opcaoGemini -eq 'R') {
        if ((Read-Host 'Remover a chave salva? [S/N]') -match '^[Ss]$') {
            Remove-Item -LiteralPath $arquivoGemini -ErrorAction Stop
            $geminiSegura = $null
            Write-Host 'Arquivo da chave removido. Isso nao revoga a chave no Google.'
        }
    }
    elseif ($opcaoGemini -eq 'N') { $geminiSegura = $null }
}
else {
    Write-Host 'Nenhuma chave Gemini salva no arquivo do projeto.'
    $opcaoGemini = if ((Read-Host 'Deseja informar e salvar a chave em config/gemini-key.txt? [S/N]') -match '^[Ss]$') { 'A' } else { 'N' }
}
if ($opcaoGemini -eq 'A') {
    $novaChaveGemini = Read-Host 'Nova chave do Google AI Studio (Enter cancela)' -AsSecureString
    if ($novaChaveGemini.Length -gt 0) {
        try {
            Save-GeminiCredential -Path $arquivoGemini -Secret $novaChaveGemini
            $geminiSegura = Read-GeminiCredential -Path $arquivoGemini
            Write-Host 'Chave salva em config/gemini-key.txt. Voce pode editar esse arquivo no Bloco de Notas.' -ForegroundColor Green
        }
        catch { Write-Host 'Nao foi possivel salvar a nova chave. A configuracao anterior foi mantida.' -ForegroundColor Yellow }
    }
}
if ($geminiSegura) {
    $credencialGemini = [System.Net.NetworkCredential]::new("", $geminiSegura)
    $env:GEMINI_API_KEY = $credencialGemini.Password
    $env:GEMINI_MODEL = "gemini-3.5-flash-lite"
}

try {
    Write-Host ""
    Write-Host "Servidor pronto para iniciar." -ForegroundColor Green
    Write-Host "O navegador não será aberto automaticamente." -ForegroundColor Cyan
    & $executavel -m backend.app
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

O Gemini usa a chave salva em `config/gemini-key.txt`, conforme a opção escolhida na inicialização. O bloco `try` executa `python -m backend.app` a partir da raiz do projeto. O bloco `finally` remove as variáveis do processo quando o programa termina; o arquivo da chave permanece até o usuário alterá-lo ou removê-lo.

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

A chave usada para criptografar os dados fica em `banco_de_dados/dados/.data_key`. As chaves da assinatura da auditoria ficam em `banco_de_dados/dados/.audit_private.pem` e `banco_de_dados/dados/.audit_private.pub`. Esses arquivos não devem ser enviados ao GitHub. Para não perder o acesso aos dados criptografados, o backup do MySQL deve ser acompanhado das chaves.

Mais informações estão em `documentacao/MYSQL.md`.

## Criptografia utilizada

- Fernet para criptografar nome, e-mail e matrícula;
- HMAC para criar índices de busca de login que não revelam o identificador;
- PBKDF2-HMAC-SHA256 com salt para senhas e códigos de recuperação;
- Ed25519 para assinar os eventos da auditoria e detectar adulterações.

Essas proteções cuidam dos dados armazenados. Em uma publicação real, ainda seria necessário utilizar HTTPS/TLS e manter as chaves em um local seguro.

## Integração com o Gemini

A integração com o Google Gemini é utilizada para gerar e adaptar questões e, quando disponível, produzir a narração. O professor sempre deve revisar o conteúdo antes de liberá-lo para os alunos.

A chave local fica em `config/gemini-key.txt`, ignorado pelo Git, e é carregada no ambiente do servidor. Ela não é enviada ao navegador. A documentação técnica está em `documentacao/INTEGRACAO_GEMINI.md`.

## Estrutura principal

```text
backend/
  app.py                      ponto de entrada da aplicação
  taskflow/                   domínio, serviços, segurança, rotas e Gemini
frontend/
  templates/                  páginas HTML com Jinja
  static/                     estilos e JavaScript
banco_de_dados/
  banco.py                    conexão e esquema MySQL
  repositorio.py              fachada de persistência
  persistencia/               consultas e preparação do esquema
  dados/                      chaves e arquivos locais (fora do Git)
config/                       configuração local do Gemini
tests/                        testes automatizados
documentacao/                 documentação técnica e de privacidade
INICIAR.bat                   inicializador principal
INICIAR_MYSQL.ps1             configuração usada pelo inicializador
requirements.txt              dependências do projeto
```
