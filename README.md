# TaskFlowCards

**Jogo educacional web para acompanhamento da aprendizagem.** Professores organizam questões e salas; alunos treinam contra o bot ou participam de partidas on-line. As respostas ficam registradas e alimentam uma dashboard pedagógica.

> Esta documentação descreve o funcionamento técnico da versão de servidor. Os perfis ativos na interface são **professor** e **aluno**. O envio pelo Gmail depende da configuração do ambiente. O Gemini está desativado nesta versão.

## Sumário

- [Arquitetura](#arquitetura)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Fluxos de negócio](#fluxos-de-negócio)
- [Dados e segurança](#dados-e-segurança)
- [Integrações](#integrações)
- [Configuração e execução](#configuração-e-execução)
- [Verificações e limites](#verificações-e-limites)

## Arquitetura

O servidor usa **Python e Flask**, o navegador recebe **HTML gerado com Jinja, CSS e JavaScript**, e a implantação web usa **PostgreSQL**. A fábrica `criar_aplicacao()` em `backend/app.py` monta a aplicação; `backend/render_app.py` expõe o objeto `app` ao Gunicorn.

```text
Navegador
    │  HTTP, formulários e atualizações periódicas
    ▼
backend/taskflow/web.py          Rotas, sessão e respostas HTTP
    ▼
backend/taskflow/servicos/       Casos de uso e regras de negócio
    ├──► Gmail, quando configurado
    ▼
banco_de_dados/persistencia/     Leitura, gravação e migrações
    ▼
PostgreSQL
```

Uma requisição chega a uma classe de visão em `web.py`. A visão verifica a sessão e o perfil, lê os dados do formulário e chama `ServicoTaskFlow`. Essa fachada compõe serviços especializados de contas, questões, jogos, salas e desempenho. Os serviços validam as regras e usam `RepositorioTaskFlow` para persistir os dados. A resposta volta como página, redirecionamento, JSON ou áudio. A lógica de negócio fica fora dos templates e das consultas SQL.

## Estrutura do projeto

| Caminho | Responsabilidade |
| --- | --- |
| `backend/app.py` | Fábrica Flask e entrada geral da aplicação. |
| `backend/render_app.py` | Entrada de servidor que exige `DATABASE_URL`. |
| `backend/taskflow/web.py` | Visões, rotas, autorização, sessão, CSRF e tratamento HTTP. |
| `backend/taskflow/dominio.py` | Entidades, constantes e validações independentes da interface. |
| `backend/taskflow/classificacao.py` | Normalização de ano escolar, turma, período e idade. |
| `backend/taskflow/servico.py` | Fachada que reúne os serviços de casos de uso. |
| `backend/taskflow/servicos/` | Regras de contas, questões, jogos, salas, desempenho e recuperação. |
| `backend/taskflow/gemini.py` | Geração e narração de conteúdo com Gemini. |
| `backend/taskflow/gmail.py` | OAuth e envio pela API do Gmail. |
| `backend/taskflow/seguranca.py` e `criptografia.py` | Hash de senha, criptografia e assinatura da auditoria. |
| `banco_de_dados/esquema_postgres.sql` | Estrutura inicial das tabelas PostgreSQL. |
| `banco_de_dados/persistencia/` | Repositórios especializados e infraestrutura de banco. |
| `frontend/templates/` | Páginas Jinja dos dois perfis, jogos e conta. |
| `frontend/static/` | Estilos e comportamento no navegador. |
| `render.yaml` e `requirements.txt` | Processo web e dependências Python. |

As classes de serviço recebem suas dependências na criação da aplicação. Essa divisão permite alterar regras, persistência ou apresentação sem concentrar tudo em um único arquivo.

## Fluxos de negócio

### Cadastro, login e conta

- Professor e aluno têm páginas próprias de cadastro e login. O cadastro envia um **código numérico de seis dígitos** ao Gmail informado; o código expira em dez minutos e pode ser usado uma vez.
- O primeiro acesso do aluno completa nome, idade e classificação escolar. A idade aceita é de **10 a 15 anos**. A classificação usa ano do **6º ao 9º**, turma e período (**manhã, tarde ou integral**).
- O login limita tentativas inválidas e registra eventos de acesso. A recuperação de senha envia um link temporário ao Gmail da conta quando o remetente está configurado.
- Em **Minha conta**, o titular pode alterar a senha e usar as opções de privacidade mediante confirmação. A exclusão da conta encerra a sessão.
- Após dez minutos sem atividade fora da partida, a sessão exige novo login. Durante uma partida, a atividade segue regra própria para não interromper o jogo.

Arquivos centrais: `servicos/contas.py`, `servicos/recuperacao.py`, `web.py`, `seguranca.py` e `frontend/templates/conta.html`.

### Questões e salas

O professor cria, edita, pausa e organiza questões por tema e dificuldade. Cada sala reúne uma sequência de questões e tem disciplina, ano escolar, turma e período. O aluno encontra todas as salas compatíveis com seu perfil escolar e escolhe qual usar. A página verifica mudanças na lista **a cada minuto**.

O aluno **não digita código de sala**. Um identificador de seis caracteres continua sendo usado internamente nas rotas e no banco. A autorização confere se a sala pertence à classificação do aluno. Se uma sala ou questão ficar sem professor responsável, outro professor pode consultá-la e assumir sua responsabilidade.

Arquivos centrais: `servicos/salas.py`, `servicos/questoes.py`, `persistencia/salas.py` e `frontend/static/sala_aluno.js`.

### Treino contra bot e multijogador

No treino individual, o aluno recebe questões autorizadas para a sala escolhida. A dificuldade começa em **médio** e é ajustada conforme os acertos recentes naquela sala: abaixo de 50% vai para fácil; a partir de 80% vai para difícil. As novas tentativas registram sala, alternativa, acerto, pontos e horário. O aluno pode reiniciar todo o seu histórico contra o bot.

No multijogador, o aluno escolhe entre as salas vinculadas à sua turma que tiverem uma partida aberta. Rodadas, participantes e respostas são persistidos. O placar usa os pontos dos participantes, e a página consulta o estado da partida para manter a apresentação sincronizada.

Arquivos centrais: `servicos/jogos.py`, `servicos/salas.py`, `persistencia/desempenho.py`, `frontend/templates/jogar.html` e `sala_multijogador.html`.

### Dashboard pedagógica e auditoria

A dashboard reúne total de alunos, participação, aproveitamento, respostas, acertos, erros, faixas de desempenho e resultados por aluno. Os filtros incluem aluno, turma, sala, faixa, modo de jogo, dificuldade, situação da conta, datas e **bimestre do calendário a partir de 2026**. Os seis bimestres são pares fixos de meses: janeiro-fevereiro até novembro-dezembro. O intervalo usa o fuso de São Paulo; indicadores, gráficos e tabela consultam o mesmo recorte.

O dashboard do professor usa apenas tentativas atribuídas às salas sob sua responsabilidade. As tentativas antigas sem sala ficam no histórico geral do aluno. O dashboard e os logs atualizam a cada **dez segundos**. Os eventos são exibidos no horário de Brasília e os registros com mais de 14 dias são removidos ao iniciar o sistema, consultar ou registrar auditoria.

Arquivos centrais: `servicos/desempenho.py`, `persistencia/desempenho.py`, `persistencia/auditoria.py`, `frontend/templates/desempenho.html` e `_dados_desempenho.html`.

## Dados e segurança

O esquema PostgreSQL guarda usuários, perfis escolares, aceites, questões, salas, questões vinculadas às salas, participantes, respostas, tentativas de treino, recuperação e auditoria. A camada `banco_de_dados/persistencia/` separa as consultas por assunto. `InfraestruturaBanco` abre a conexão, prepara o esquema e aplica migrações.

No servidor, `DATABASE_URL` determina o PostgreSQL. O código ainda contém suporte a MySQL e SQLite para contextos locais e testes, mas `backend.render_app:app` exige PostgreSQL. Um banco novo começa vazio: dados de outra instalação não são copiados automaticamente. As tentativas guardam o instante da resposta; o filtro bimestral converte os limites dos dias de São Paulo para UTC antes da consulta.

- **Autorização:** visões protegidas exigem professor ou aluno; serviços e repositórios verificam também a propriedade de salas, questões e resultados.
- **Senhas:** são armazenadas como hash PBKDF2-HMAC-SHA256 com sal aleatório e 600.000 iterações, nunca em texto puro. O comprimento aceito é de 12 a 128 caracteres.
- **Formulários e sessão:** há token CSRF, cookies `HttpOnly` e `SameSite=Lax`. Com URL HTTPS, o cookie de sessão recebe `Secure`. Páginas dinâmicas usam `Cache-Control: no-store`.
- **Dados e auditoria:** `TASKFLOW_DATA_KEY` protege campos sensíveis com Fernet; `TASKFLOW_AUDIT_SEED` assina eventos com Ed25519. Essas chaves devem permanecer estáveis para os dados gravados continuarem legíveis e verificáveis.
- **Entrada e integrações:** formulários têm validação no servidor, limite de tamanho de requisição e mensagens de erro sem revelar chaves.
- **Privacidade:** o aceite dos documentos legais é registrado, e a área da conta permite operações de privacidade do titular.

## Integrações

### Narração

A leitura das perguntas no treino usa uma voz local em português, quando disponível no dispositivo. Esta versão não chama o Gemini.

### Gmail

`RemetenteGmail` usa OAuth e a API do Gmail para enviar códigos de cadastro e links de recuperação. A conta remetente e as credenciais são lidas do ambiente; não há senha do Gmail no código. Se a integração não estiver configurada ou o envio falhar, o sistema informa a indisponibilidade.

## Configuração e execução

| Variável | Finalidade |
| --- | --- |
| `DATABASE_URL` | Conexão PostgreSQL usada pela entrada de servidor. |
| `FLASK_SECRET_KEY` | Assinatura da sessão Flask. |
| `TASKFLOW_DATA_KEY` | Chave Fernet dos dados protegidos. |
| `TASKFLOW_AUDIT_SEED` | Semente privada de 32 bytes para auditoria. |
| `TASKFLOW_GMAIL_CLIENT_ID` | Identificador do cliente OAuth. |
| `TASKFLOW_GMAIL_CLIENT_SECRET` | Segredo do cliente OAuth. |
| `TASKFLOW_GMAIL_REFRESH_TOKEN` | Renovação da autorização do Gmail. |
| `TASKFLOW_GMAIL_SENDER` | Conta remetente autorizada. |

O `render.yaml` descreve um serviço Python e um PostgreSQL. O processo instala `requirements.txt` e inicia o Gunicorn com `backend.render_app:app`. Nenhum valor de chave deve ser escrito neste README ou nos arquivos de código.

## Verificações e limites

As últimas verificações locais cobriram compilação dos módulos Python, análise sintática de 32 templates Jinja, leitura de uma resposta de áudio REST simulada e os limites do filtro bimestral com consulta de acertos e erros. Essas verificações **não equivalem a uma execução completa no servidor**. Cadastro, Gmail, narração local, partidas e dashboard precisam ser conferidos novamente na instalação publicada.

O código contém componentes de compatibilidade com versões anteriores, inclusive partes do esquema e métodos legados. A documentação acima descreve os fluxos ativos da versão web.
