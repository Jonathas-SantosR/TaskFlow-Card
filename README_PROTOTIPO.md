# TaskFlowCards Web

Versão web do protótipo TaskFlowCards. O sistema reúne o gerenciamento de salas e
alunos em uma única página, com frontend em HTML, CSS e JavaScript e backend em
Python, Flask e SQLite.

O projeto Pygame original permanece separado e não é modificado por esta versão.

## Funcionalidades

### Salas

- Criar sala com nome, descrição, modo e status.
- Consultar e buscar por nome, código ou descrição.
- Filtrar salas abertas e fechadas.
- Atualizar e excluir uma sala.
- Paginar a listagem.

### Alunos

- Cadastrar aluno com nome, matrícula/RA, e-mail e status.
- Consultar e buscar por nome, matrícula ou e-mail.
- Filtrar alunos ativos e bloqueados.
- Atualizar e excluir um aluno.
- Validar formato de e-mail e impedir matrícula ou e-mail duplicado.

As duas funcionalidades ficam na mesma página e podem ser acessadas pelas abas
`Salas` e `Alunos`. O navegador avisa antes de descartar alterações não salvas.

## Como executar no Windows

Requer Python 3.10 ou superior. Execute:

```text
iniciar.bat
```

Na primeira vez, o arquivo cria o ambiente `.venv` e instala o Flask. Em seguida,
o navegador abre automaticamente em:

```text
http://127.0.0.1:5000
```

Mantenha o terminal aberto enquanto estiver utilizando o sistema. Para encerrar,
pressione `Ctrl+C` no terminal.

Também é possível iniciar manualmente pelo PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## Banco de dados

Os registros ficam em `data/salas.sqlite3`. A cópia web começa com uma cópia
independente dos dados do protótipo Pygame no momento da criação. Alterações feitas
na versão web não modificam o banco do projeto original.

## Testes automatizados

Execute no terminal:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_web.py
```

Ou execute `testar.bat`. Os testes utilizam um banco temporário e verificam página
inicial, saúde da API, CRUD de salas, CRUD de alunos, buscas, filtros, validações,
duplicidades e respostas para registros inexistentes.

## Estrutura

- `app.py`: servidor Flask e rotas da API.
- `backend.py`: entidade `Sala`, regras e repositório SQLite das salas.
- `student_backend.py`: entidade `Aluno`, regras e repositório SQLite dos alunos.
- `templates/index.html`: estrutura da interface web.
- `static/styles.css`: aparência responsiva inspirada no protótipo Pygame.
- `static/app.js`: interação da página e comunicação com a API.
- `test_web.py`: testes automatizados da aplicação web.
- `requirements.txt`: dependências Python.
- `iniciar.bat`: prepara e inicia o sistema.
- `testar.bat`: executa os testes pelo terminal.

## API

| Método | Rota | Operação |
| --- | --- | --- |
| `GET` / `POST` | `/api/salas` | Listar ou criar salas |
| `GET` / `PUT` / `DELETE` | `/api/salas/<id>` | Consultar, atualizar ou excluir uma sala |
| `GET` / `POST` | `/api/alunos` | Listar ou cadastrar alunos |
| `GET` / `PUT` / `DELETE` | `/api/alunos/<id>` | Consultar, atualizar ou excluir um aluno |
| `GET` | `/api/saude` | Verificar o funcionamento do backend |

## Classes e entidades

Os nomes usados no código estão em português:

- `Sala`: entidade com código, nome, descrição, modo, status e datas.
- `Aluno`: entidade com matrícula, nome, e-mail, status e datas.
- `RepositorioSalas`: realiza o CRUD da entidade `Sala`.
- `RepositorioAlunos`: realiza o CRUD da entidade `Aluno`.
- `ErroValidacaoSala` e `ErroValidacaoAluno`: representam dados inválidos.
- `SalaNaoEncontrada` e `AlunoNaoEncontrado`: representam cadastros inexistentes.

Os métodos dos repositórios também estão em português: `criar`, `buscar`, `listar`,
`atualizar`, `excluir` e `fechar`.

## Tecnologias

- Python 3
- Flask
- SQLite
- HTML5
- CSS3
- JavaScript

Esta é uma aplicação local de desenvolvimento. Para disponibilizá-la publicamente,
será necessário configurar hospedagem e um servidor adequado para produção.
