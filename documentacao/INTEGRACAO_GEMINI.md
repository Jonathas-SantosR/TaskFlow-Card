# Integração com Google Gemini

## Objetivo

O TaskFlowCards utiliza a API do Google Gemini como apoio ao professor. A IA
não publica conteúdo automaticamente e não substitui a revisão pedagógica.

## Configuração

- `GEMINI_API_KEY`: chave criada no Google AI Studio;
- `GEMINI_MODEL`: modelo de texto usado para questões e adaptações;
- `GEMINI_TTS_MODEL`: modelo de áudio usado para narração.

As chaves são lidas de variáveis de ambiente e não são gravadas no código ou
no banco de dados.

## Operações

### Geração de questão

O professor informa tema e dificuldade. O backend chama `generateContent`
e exige uma resposta JSON estruturada com enunciado, quatro alternativas,
índice correto, explicação e feedback para acerto e erro. O resultado aparece
como rascunho e só entra no banco quando o professor seleciona **Salvar no
banco**.

### Adaptação

Uma questão revisada pode originar outra versão em nível fácil, médio ou
difícil. A original é preservada, e a variação passa novamente pela revisão
do professor.

### Narração

O backend envia o texto da questão ao endpoint `v1beta/interactions` com um
modelo Gemini Text-to-Speech e solicita retorno `audio/wav`. O áudio é devolvido
diretamente ao navegador e não é armazenado no banco. O padrão atual é
`gemini-3.8-flash-lite-tts`, configurável por `GEMINI_TTS_MODEL`.

Para demonstrar a integração, execute `INICIAR.bat`, responda `S` quando a
opção do Google Gemini for apresentada e informe a chave do Google AI Studio.
Depois, gere uma questão e teste a narração. Uma chave real e habilitada é
indispensável; os testes automatizados validam o formato da requisição sem
consumir créditos.

## Privacidade e segurança

- nome, e-mail, matrícula, telefone e documentos não fazem parte do prompt;
- padrões comuns desses dados são bloqueados antes da chamada externa;
- a chave fica somente no servidor;
- erros são traduzidos sem expor chave, prompt ou resposta do provedor;
- geração, adaptação e narração são registradas na auditoria;
- o professor deve revisar o conteúdo antes de liberá-lo.

## Funcionamento sem IA

Sem chave ou durante indisponibilidade do serviço, o professor pode cadastrar
e editar questões manualmente. Partidas, correção, feedback salvo e desempenho
continuam disponíveis.
