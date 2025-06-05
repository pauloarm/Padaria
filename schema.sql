
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    senha TEXT NOT NULL,
    tipo TEXT DEFAULT 'usuario' -- adm ou usuario
);


CREATE TABLE IF NOT EXISTS itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    categoria TEXT NOT NULL,
    custo REAL NOT NULL,
    venda REAL NOT NULL
);


CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    valor_total REAL NOT NULL,
    forma_pagamento TEXT NOT NULL,
    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
);


CREATE TABLE IF NOT EXISTS itens_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantidade INTEGER NOT NULL,
    valor_unitario REAL NOT NULL,
    FOREIGN KEY(venda_id) REFERENCES vendas(id),
    FOREIGN KEY(item_id) REFERENCES itens(id)
);

CREATE TABLE IF NOT EXISTS sangrias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT NOT NULL,
    valor REAL NOT NULL,
    descricao TEXT,
    usuario_id INTEGER NOT NULL,
    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
);


CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    telefone TEXT,
    endereco TEXT,
    data_cadastro TEXT DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS contas_fiadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    venda_id INTEGER NOT NULL,
    valor REAL NOT NULL,
    pago BOOLEAN DEFAULT 0,
    data_venda TEXT NOT NULL,
    data_pagamento TEXT,
    FOREIGN KEY(cliente_id) REFERENCES clientes(id),
    FOREIGN KEY(venda_id) REFERENCES vendas(id)
);


CREATE TABLE IF NOT EXISTS historico_pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    valor_pago REAL NOT NULL,
    data_pagamento TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    FOREIGN KEY(cliente_id) REFERENCES clientes(id),
    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
);