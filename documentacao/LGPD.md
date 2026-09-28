# Privacidade e LGPD no protótipo

Este documento registra as decisões técnicas da entrega acadêmica. Ele não declara conformidade jurídica integral e não substitui a análise da instituição responsável.

A segunda versão usa MySQL 8/PyMySQL como banco da aplicação. SQLite aparece somente nos testes automatizados isolados e nunca como banco do sistema em execução. Isso não altera as regras de criptografia, retenção ou direitos do titular. O conteúdo específico abaixo também está representado na página pública **Termos de Uso e Política de Privacidade**, acessível pelo rodapé do sistema a qualquer momento.

## Dados tratados

| Dado | Finalidade | Acesso | Retenção |
| --- | --- | --- | --- |
| Nome e e-mail do professor | Identificação e login administrativo | Criptografados; aplicação local | Até anonimização ou exclusão pelo titular |
| Nome e matrícula do aluno | Identificação e login do estudante | Criptografados; professor e o próprio aluno | Até anonimização ou exclusão pelo titular ou professor |
| Hash e salt de senha | Autenticação | Somente código de autenticação | Enquanto a conta existir |
| Hash e salt do código de recuperação | Recuperação da conta do professor | Somente código de autenticação | Enquanto estiver configurado |
| Indicador de primeiro acesso | Exigir troca da senha temporária do aluno | Aplicação local | Enquanto a troca estiver pendente |
| IDs, perfil, ação, recurso e horário | Auditoria | Professor | Eventos com mais de 90 dias são removidos quando um novo evento é registrado |
| Questões, alternativas, gabaritos e feedback | Disponibilizar conteúdo pedagógico no jogo | Professor e alunos durante a partida | Até exclusão pelo professor |
| Alternativa escolhida, acerto, modo, dificuldade, pontos e horário | Feedback e acompanhamento de desempenho | Próprio aluno e professor | Enquanto vinculados à conta; o vínculo é removido na anonimização ou exclusão |
| Tema, dificuldade e texto da questão | Geração, adaptação e narração opcionais | Professor, aluno na narração e API Gemini | O áudio não é salvo; o conteúdo revisado só é persistido quando o professor o salva |

Senhas e códigos de recuperação em texto puro não são armazenados. A auditoria não copia nomes, e-mails, matrículas, senhas, códigos ou conteúdo enviado à IA.

Nome, e-mail e matrícula são protegidos com criptografia autenticada Fernet. A busca de login usa um índice HMAC não reversível. A chave não é gravada no banco: fica no arquivo local ignorado `data/.data_key` ou na variável `TASKFLOW_DATA_KEY`.

Senhas e códigos não são criptografados de forma reversível: usam PBKDF2-HMAC-SHA256 com salt. Novos eventos de auditoria recebem assinatura assimétrica Ed25519; a chave pública permite detectar alteração do conteúdo registrado. A chave privada local fica em `data/.audit_private.pem`, arquivo ignorado pelo Git, e deve acompanhar o backup seguro do banco. Em publicação real, HTTPS/TLS e um cofre de chaves deverão proteger transporte e segredos.

## Direitos do titular e saída

Professor e aluno acessam **Minha conta / Privacidade e saída** depois de autenticados. Após confirmar a senha atual e digitar a ação escolhida, podem:

- anonimizar irreversivelmente nome e identificador, bloquear a credencial, retirar o aceite e desvincular IDs da auditoria;
- excluir definitivamente cadastro, credencial e aceite, também desvinculando referências da auditoria.

As duas opções encerram imediatamente a sessão. O registro técnico do tipo de ação permanece por até 90 dias sem ID do titular.

Quando o professor exclui administrativamente um aluno, o sistema também remove o aceite e as participações/respostas multijogador, desvincula tentativas e elimina referências pessoais da auditoria antes de apagar a conta.

## Perfis

- Sem login: pode ler os documentos, acessar os logins e criar conta de aluno. A criação do professor inicial exige o código privado `TASKFLOW_SETUP_CODE` definido no servidor; depois disso, o cadastro de professor é fechado.
- Professor: administra alunos e questões, consulta auditoria e desempenho e utiliza recursos de IA.
- Aluno: consulta o próprio perfil, joga e acompanha o próprio desempenho.

As permissões são verificadas na camada de serviço. Ocultar um botão não é considerado autorização.

## Google Gemini

A integração é opcional. Na criação, recebe tema e dificuldade; na adaptação e narração, recebe o texto pedagógico da questão. Há um filtro adicional para e-mail, números longos e menções a RA ou matrícula, mas ele não substitui a revisão humana. O áudio de narração é entregue ao navegador sem persistência local. O operador deve consultar os termos do plano da API antes de ativá-la.

## Pendências para uso real

1. Definir controlador, operadores, hipóteses legais e contato dos titulares.
2. Proteger o equipamento, o banco, a chave de criptografia e eventuais cópias de segurança.
3. Criar procedimentos de recuperação de acesso e resposta a incidentes.
4. Avaliar regras específicas para crianças e adolescentes.
5. Revisar retenção e transferência internacional aplicáveis ao provedor de IA.
