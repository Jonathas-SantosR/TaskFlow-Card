# Termos de uso e aviso de privacidade

Versão acadêmica do TaskFlowCards — entrega de 28/09.

## 1. Finalidade

O TaskFlowCards é um protótipo acadêmico destinado a apoiar atividades pedagógicas gamificadas. O sistema não substitui a avaliação, a orientação nem o acompanhamento realizado pelo professor.

## 2. Usuários e responsabilidades

- O professor administra alunos e utiliza os recursos pedagógicos.
- O aluno acessa somente a própria área e seus próprios dados.
- Cada usuário deve utilizar uma credencial individual e manter sua senha em sigilo.
- Durante a fase de protótipo, devem ser utilizados dados fictícios.

## 3. Dados tratados

O sistema armazena nome, e-mail do professor ou matrícula do aluno, perfil, status da conta, indicador de primeiro acesso, senha protegida por hash e, quando configurado, o hash do código de recuperação. Para as atividades pedagógicas, também armazena questões, alternativa escolhida, acerto ou erro, modo, dificuldade, pontos e horário da resposta. Os registros de auditoria utilizam identificadores internos e não registram senhas, códigos, e-mails ou matrículas.

## 4. Segurança e retenção

As senhas são protegidas por PBKDF2-SHA256 com salt aleatório. Nome, e-mail e matrícula são criptografados de forma autenticada, e o índice usado no login é um HMAC não reversível. Registros de auditoria com mais de 90 dias são removidos quando um novo evento é registrado.

O titular autenticado pode anonimizar ou excluir definitivamente a própria conta. Ambas as opções exigem a senha atual, removem o aceite, desvinculam referências pessoais da auditoria e das respostas e encerram a sessão. A anonimização mantém somente um registro desidentificado e bloqueado; a exclusão apaga o cadastro.

Como se trata de um protótipo local, ainda não há servidor central, cofre institucional de chaves ou rotina automática de cópia de segurança.

## 5. Google Gemini

A integração com o Google Gemini é opcional e serve para criar rascunhos, adaptar questões e gerar narração. A chave deve ser informada na variável de ambiente `GEMINI_API_KEY` e nunca deve ser gravada no código ou no banco. O áudio produzido é enviado ao navegador e não fica armazenado.

Não devem ser enviados à IA nomes, e-mails, telefones, documentos, matrículas ou outras informações capazes de identificar estudantes. Todo conteúdo gerado precisa ser revisado pelo professor antes do uso.

## 6. Aceite

O acesso ao sistema depende da confirmação destes termos na tela inicial. O aceite é registrado no banco de dados com a versão do documento e a data correspondente.
