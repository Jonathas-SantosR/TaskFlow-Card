# Orientação a objetos aplicada ao TaskFlowCards

## Referências pesquisadas

- [Classes no tutorial oficial do Python](https://docs.python.org/3/tutorial/classes.html)
- [Data classes na biblioteca padrão](https://docs.python.org/3/library/dataclasses.html)
- [Class-based views no Flask](https://flask.palletsprojects.com/en/stable/views/)
- [Application factories no Flask](https://flask.palletsprojects.com/en/stable/patterns/appfactories/)

## Conceitos usados

### Classe e objeto

Uma classe define dados e comportamentos relacionados. Um objeto é uma instância concreta dessa classe. No projeto, `Usuario` representa a entidade e objetos como `professor` e `aluno` são instâncias dela.

### Encapsulamento

Cada responsabilidade possui uma classe própria:

- `RepositorioTaskFlow`: fachada para repositórios de usuários, questões, salas, desempenho e auditoria;
- `ServicoTaskFlow`: fachada para serviços de contas, questões, jogos, salas e desempenho;
- `ServicoGemini`: integração externa;
- `GerenciadorSessao`: identidade do usuário autenticado;
- `ProtecaoCsrf`: proteção dos formulários;
- `CriptografiaDados`: criptografia autenticada e índice HMAC;
- `VisaoPrivacidadeConta`: anonimização e exclusão solicitadas pelo titular;
- `AplicacaoTaskFlowWeb`: composição e configuração do Flask.

### Composição

`AplicacaoTaskFlowWeb` recebe e conecta repositório, serviços, sessão e controladores. A composição foi preferida porque essas classes colaboram entre si, mas não representam variações do mesmo tipo.

`ContextoServico` mantém a identidade de cada instância e recebe as dependências.
Os serviços especializados compartilham esse contexto dentro da mesma requisição.
`InfraestruturaBanco` gerencia a conexão e as chaves; `MigradorBanco` registra as
versões do esquema. Os repositórios compartilham o bloqueio da conexão, inclusive
durante commit ou rollback das respostas concorrentes.

### Herança

As páginas herdam de `MethodView`, classe oficial do Flask. `ControladorProtegido` herda de `ControladorBase` apenas porque adiciona uma regra comum real: exigir autenticação e perfil. Páginas como `VisaoAlunos` e `VisaoAuditoria` especializam esse comportamento.

### Polimorfismo

Cada visão implementa `get()` ou `post()`. O Flask chama o método correspondente à requisição HTTP sem precisar conhecer a implementação interna de cada página.

### Entidade com comportamento

`Usuario` é uma `dataclass` imutável com propriedades como `eh_professor` e `eh_aluno`. Assim, a decisão de perfil pertence à própria entidade e não fica repetida pelas telas.

## Estrutura resultante

```text
backend/app.py                    ponto de entrada e fábrica
backend/taskflow/dominio.py       entidades e validações
backend/taskflow/criptografia.py  proteção reversível dos dados pessoais
banco_de_dados/repositorio.py   objetos de persistência
backend/taskflow/servico.py       objetos de regras de negócio
backend/taskflow/gemini.py        objeto da integração com IA
backend/taskflow/web.py           aplicação, sessão, CSRF e visões em classes
```

O projeto não cria classes apenas para aumentar a quantidade de código. Herança, composição e encapsulamento foram usados somente quando reduzem repetição e deixam responsabilidades verificáveis por testes.
