-- Esquema PostgreSQL da versão unificada para banco vazio de demonstração.
CREATE TABLE IF NOT EXISTS aceites (
                    usuario_id INTEGER PRIMARY KEY,
                    termos_versao TEXT NOT NULL,
                    privacidade_versao TEXT NOT NULL,
                    aceito_em TEXT NOT NULL
                );

CREATE TABLE IF NOT EXISTS auditoria (
                    id BIGSERIAL PRIMARY KEY,
                    ocorrido_em TEXT NOT NULL,
                    ator_id INTEGER,
                    perfil TEXT NOT NULL,
                    evento TEXT NOT NULL,
                    recurso TEXT NOT NULL,
                    alvo_id INTEGER,
                    assinatura TEXT
                );

CREATE TABLE IF NOT EXISTS codigos_cadastro (
            perfil VARCHAR(20) NOT NULL,
            chave_email VARCHAR(80) NOT NULL,
            codigo_hash VARCHAR(80) NOT NULL,
            expira_em VARCHAR(40) NOT NULL,
            enviado_em VARCHAR(40) NOT NULL,
            janela_inicio VARCHAR(40) NOT NULL,
            envios_janela INTEGER NOT NULL DEFAULT 1,
            tentativas INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (perfil, chave_email)
            );

CREATE TABLE IF NOT EXISTS conflitos_identidade (chave_email VARCHAR(128) PRIMARY KEY);

CREATE TABLE IF NOT EXISTS emails_recuperacao (
            usuario_id BIGINT PRIMARY KEY,
            email TEXT NOT NULL
            );

CREATE TABLE IF NOT EXISTS limites_recuperacao (
        chave VARCHAR(160) PRIMARY KEY,
        janela_em VARCHAR(40) NOT NULL,
        ultimo_em VARCHAR(40) NOT NULL,
        quantidade INTEGER NOT NULL
    );

CREATE TABLE IF NOT EXISTS participantes_multijogador (
                    sala_id INTEGER NOT NULL,
                    aluno_id INTEGER NOT NULL,
                    pontos INTEGER NOT NULL DEFAULT 0,
                    entrou_em TEXT NOT NULL,
                    PRIMARY KEY (sala_id, aluno_id)
                );

CREATE TABLE IF NOT EXISTS perfil_aluno (
        aluno_id BIGINT PRIMARY KEY,
        idade INTEGER NOT NULL,
        ano_escolar VARCHAR(40) NOT NULL,
        turma VARCHAR(40) NOT NULL,
        sala_escolar VARCHAR(40) NOT NULL,
        chave_academica VARCHAR(64) NOT NULL,
        atualizado_em VARCHAR(40) NOT NULL
    );

CREATE TABLE IF NOT EXISTS questoes (
                    id BIGSERIAL PRIMARY KEY,
                    professor_id INTEGER,
                    tema TEXT NOT NULL,
                    dificuldade TEXT NOT NULL,
                    enunciado TEXT NOT NULL,
                    alternativas_json TEXT NOT NULL,
                    indice_correto INTEGER NOT NULL,
                    explicacao TEXT NOT NULL,
                    feedback_acerto TEXT NOT NULL,
                    feedback_erro TEXT NOT NULL,
                    criada_em TEXT NOT NULL,
                    ativa INTEGER NOT NULL DEFAULT 1
                );

CREATE TABLE IF NOT EXISTS questoes_sala_multijogador (
                    sala_id INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    questao_id INTEGER NOT NULL,
                    PRIMARY KEY (sala_id, ordem),
                    UNIQUE (sala_id, questao_id)
                );

CREATE TABLE IF NOT EXISTS respostas_multijogador (
                    sala_id INTEGER NOT NULL,
                    rodada INTEGER NOT NULL,
                    aluno_id INTEGER NOT NULL,
                    questao_id INTEGER NOT NULL,
                    indice_escolhido INTEGER NOT NULL,
                    correta INTEGER NOT NULL,
                    pontos INTEGER NOT NULL,
                    respondida_em TEXT NOT NULL,
                    PRIMARY KEY (sala_id, rodada, aluno_id)
                );

CREATE TABLE IF NOT EXISTS salas_multijogador (
                    id BIGSERIAL PRIMARY KEY,
                    codigo TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    criador_id INTEGER,
                    questao_id INTEGER NOT NULL,
                    rodada INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'ABERTA',
                    criada_em TEXT NOT NULL
                , ano_escolar VARCHAR(40) NULL, turma VARCHAR(40) NULL, sala_escolar VARCHAR(40) NULL, chave_academica VARCHAR(64) NULL);

CREATE TABLE IF NOT EXISTS solicitacoes_recuperacao (
        id VARCHAR(64) PRIMARY KEY,
        chave_conta VARCHAR(128) NOT NULL,
        chave_origem VARCHAR(128) NOT NULL,
        criada_em VARCHAR(40) NOT NULL,
        atualizada_em VARCHAR(40) NOT NULL,
        status VARCHAR(24) NOT NULL,
        codigo_erro VARCHAR(40),
        token_hash VARCHAR(64)
    );

CREATE TABLE IF NOT EXISTS tentativas (
                    id BIGSERIAL PRIMARY KEY,
                    aluno_id INTEGER,
                    questao_id INTEGER,
                    modo TEXT NOT NULL,
                    dificuldade TEXT NOT NULL,
                    indice_escolhido INTEGER NOT NULL,
                    correta INTEGER NOT NULL,
                    pontos INTEGER NOT NULL,
                    respondida_em TEXT NOT NULL
                );

CREATE TABLE IF NOT EXISTS tokens_recuperacao (
            token_hash VARCHAR(64) PRIMARY KEY,
            usuario_id BIGINT NOT NULL,
            expira_em VARCHAR(40) NOT NULL,
            usado_em VARCHAR(40) NULL);

CREATE TABLE IF NOT EXISTS usuarios (
                    id BIGSERIAL PRIMARY KEY,
                    perfil TEXT NOT NULL CHECK(perfil IN ('PROFESSOR','ALUNO','TI')),
                    identificador TEXT NOT NULL,
                    chave_identificador TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    senha_hash TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    primeiro_acesso INTEGER NOT NULL DEFAULT 0,
                    idade INTEGER,
                    recuperacao_hash TEXT, anonimizado_em TEXT, versao_sessao INTEGER NOT NULL DEFAULT 0, chave_login_global VARCHAR(128), identificador_legado TEXT,
                    UNIQUE(perfil, chave_identificador)
                );

CREATE TABLE IF NOT EXISTS versoes_esquema (
            versao INTEGER PRIMARY KEY,
            descricao VARCHAR(120) NOT NULL,
            aplicada_em VARCHAR(40) NOT NULL
        );

CREATE INDEX IF NOT EXISTS idx_participantes_multijogador_aluno
                ON participantes_multijogador(aluno_id, sala_id);

CREATE INDEX IF NOT EXISTS idx_perfil_aluno_classificacao ON perfil_aluno(chave_academica);

CREATE INDEX IF NOT EXISTS idx_questoes_ativas
                ON questoes(ativa, dificuldade);

CREATE INDEX IF NOT EXISTS idx_salas_multijogador_codigo
                ON salas_multijogador(codigo, status);

CREATE INDEX IF NOT EXISTS idx_solicitacoes_recuperacao_data ON solicitacoes_recuperacao(criada_em);

CREATE INDEX IF NOT EXISTS idx_tentativas_aluno
                ON tentativas(aluno_id, respondida_em);

CREATE INDEX IF NOT EXISTS idx_tokens_recuperacao_usuario
                ON tokens_recuperacao(usuario_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_login_global ON usuarios(chave_login_global);

CREATE INDEX IF NOT EXISTS idx_salas_chave_academica ON salas_multijogador(chave_academica);
