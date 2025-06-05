import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import get_db, init_db, close_connection
import pdfkit
import io
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super_secret_key_123456'
app.teardown_appcontext(close_connection)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.template_filter('formatar_data')
def formatar_data(data_hora):
    try:
        # Converte string para objeto datetime
        dt = datetime.strptime(data_hora, '%Y-%m-%d %H:%M:%S')  # Se for com hora
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception as e:
        return data_hora  # Retorna original caso falhe

@app.before_request
def make_session_permanent():
    session.permanent = True  # Ativa expiração da sessão
app.permanent_session_lifetime = timedelta(hours=2)

# Usuário para o Flask-Login
class User(UserMixin):
    def __init__(self, id, nome, tipo):
        self.id = id
        self.nome = nome
        self.tipo = tipo

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cur = db.execute('SELECT * FROM usuarios WHERE id = ?', (user_id,))
    user = cur.fetchone()
    if user:
        return User(user[0], user[1], user[3])
    return None

# Rota inicial
@app.route('/')
def index():
    return render_template('index.html')

# Rota de login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form['nome']
        senha = request.form['senha']
        db = get_db()
        cur = db.execute('SELECT * FROM usuarios WHERE nome = ? AND senha = ?', (nome, senha))
        user = cur.fetchone()
        if user:
            user_obj = User(user[0], user[1], user[3])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Nome ou senha inválidos')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Rota de registro (somente ADM)
@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if current_user.tipo != 'adm':
        flash("Acesso negado.")
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nome = request.form['nome']
        senha = request.form['senha']
        tipo = request.form['tipo']
        db = get_db()
        db.execute('INSERT INTO usuarios (nome, senha, tipo) VALUES (?, ?, ?)', (nome, senha, tipo))
        db.commit()
        flash("Usuário cadastrado com sucesso!")
        return redirect(url_for('dashboard'))
    return render_template('register.html')

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()

    itens_count = db.execute('SELECT COUNT(*) FROM itens').fetchone()[0]

    # Conta vendas realizadas
    vendas_count = db.execute('SELECT COUNT(*) FROM vendas').fetchone()[0]

    # Soma total do estoque (quantidade disponível)
    estoque_total = db.execute('SELECT SUM(quantidade) FROM itens').fetchone()[0] or 0

    # Vendas por dia da semana (últimos 7 dias)
    vendas_por_dia_semana = [0] * 7  # Inicializa com zeros
    for i in range(7):
        data = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        count = db.execute('''
            SELECT COUNT(*) FROM vendas 
            WHERE DATE(data_hora) = ?
        ''', (data,)).fetchone()[0]
        vendas_por_dia_semana[6 - i] = count  # Ajuste para ordem crescente (domingo a sábado)

    # Itens mais vendidos
    top_itens_vendidos = db.execute('''
        SELECT i.nome, SUM(iv.quantidade) AS total_vendido
        FROM itens_venda iv JOIN itens i ON iv.item_id = i.id
        GROUP BY i.id ORDER BY total_vendido DESC LIMIT 4
    ''').fetchall()

    return render_template(
        'dashboard.html',
        itens_count=itens_count,
        vendas_count=vendas_count,
        estoque_total=estoque_total,
        vendas_por_dia_semana=vendas_por_dia_semana,
        top_itens_vendidos=top_itens_vendidos
    )

# Cadastro de Item
@app.route('/cadastro_item', methods=['GET', 'POST'])
@login_required
def cadastro_item():
    if request.method == 'POST':
        nome = request.form['nome']
        qtd = int(request.form['quantidade'])
        cat = request.form['categoria']
        custo = float(request.form['custo'])
        venda = float(request.form['venda'])

        db = get_db()
        db.execute('INSERT INTO itens (nome, quantidade, categoria, custo, venda) VALUES (?, ?, ?, ?, ?)',
                   (nome, qtd, cat, custo, venda))
        db.commit()
        flash("Item cadastrado com sucesso!")
        return redirect(url_for('cadastro_item'))
    return render_template('cadastro_item.html')

# Estoque
@app.route('/estoque', methods=['GET'])
@login_required
def estoque():
    pesquisa = request.args.get('pesquisa', '')
    categoria = request.args.get('categoria', '')
    query = 'SELECT * FROM itens WHERE 1=1'
    params = []

    if pesquisa:
        query += ' AND nome LIKE ?'
        params.append(f'%{pesquisa}%')
    if categoria:
        query += ' AND categoria = ?'
        params.append(categoria)

    db = get_db()
    cur = db.execute(query, params)
    itens = cur.fetchall()

    categorias = db.execute('SELECT DISTINCT categoria FROM itens').fetchall()
    return render_template('estoque.html', itens=itens, categorias=categorias)

# Venda
@app.route('/venda', methods=['GET', 'POST'])
@login_required
def venda():
    carrinho = session.get('carrinho', [])
    total = sum(i['valor'] for i in carrinho)
    db = get_db()

    clientes = db.execute('SELECT * FROM clientes ORDER BY nome ASC').fetchall()
    
    print("Clientes encontrados:", clientes)
    for cliente in clientes:
        print("Cliente:", cliente['id'], cliente['nome'])

    if request.method == 'POST':
        if 'limpar' in request.form:
            session['carrinho'] = []
            return redirect(url_for('venda'))

        item_id = int(request.form['item_id'])
        qtd = int(request.form['qtd'])

        db = get_db()
        item = db.execute('SELECT * FROM itens WHERE id = ?', (item_id,)).fetchone()

        if not item:
            flash("Item não encontrado.")
            return redirect(url_for('venda'))

        # Verifica se há estoque suficiente
        if qtd > item[2]:  # item[2] é a quantidade disponível
            flash(f"Quantidade insuficiente em estoque para {item[1]}.")
            return redirect(url_for('venda'))

        valor_total = item[5] * qtd  # item[5] é o preço de venda
        carrinho.append({
            'id': item_id,
            'nome': item[1],
            'quantidade': qtd,
            'valor': valor_total
        })
        session['carrinho'] = carrinho
        return redirect(url_for('venda'))

    elif request.method == 'GET':
        db = get_db()
        itens = db.execute('SELECT * FROM itens').fetchall()
        return render_template('venda.html', itens=itens, carrinho=carrinho, total=total, clientes=clientes)
    
@app.route('/historico_vendas')
@login_required
def historico_vendas():
    db = get_db()
    usuario_id = current_user.id
    vendas_usuario = db.execute('''
        SELECT v.id, u.nome, v.valor_total, v.data_hora 
        FROM vendas v 
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE v.usuario_id = ?
        ORDER BY v.data_hora DESC
    ''', (usuario_id,)).fetchall()

    return render_template('historico_vendas.html', vendas=vendas_usuario)

@app.route('/historico_caixa')
@login_required
def historico_caixa():
    db = get_db()
    
    # Buscar todos os dias com vendas ou sangrias
    vendas_por_dia = db.execute('''
        SELECT DATE(data_hora), SUM(valor_total) AS total_venda, 
               SUM(CASE WHEN forma_pagamento = 'dinheiro' THEN valor_total ELSE 0 END) AS total_dinheiro,
               SUM(CASE WHEN forma_pagamento = 'cartao' THEN valor_total ELSE 0 END) AS total_cartao
        FROM vendas
        GROUP BY DATE(data_hora)
    ''').fetchall()

    sangrias_por_dia = db.execute('''
        SELECT DATE(data_hora), SUM(valor) AS total_sangria
        FROM sangrias
        GROUP BY DATE(data_hora)
    ''').fetchall()

    # Agrupar por data
    dados_por_data = {}

    for venda in vendas_por_dia:
        data = venda[0]
        if data not in dados_por_data:
            dados_por_data[data] = {
                'data': data,
                'total_venda': venda[1],
                'total_dinheiro': venda[2],
                'total_cartao': venda[3],
                'total_sangria': 0
            }

    for sangria in sangrias_por_dia:
        data = sangria[0]
        if data in dados_por_data:
            dados_por_data[data]['total_sangria'] = sangria[1]
        else:
            dados_por_data[data] = {
                'data': data,
                'total_venda': 0,
                'total_dinheiro': 0,
                'total_cartao': 0,
                'total_sangria': sangria[1]
            }

    # Calcular saldo final
    historico = []
    for data, dados in dados_por_data.items():
        saldo_final = round(dados['total_dinheiro'] - dados['total_sangria'], 2)
        historico.append({
            'data': dados['data'],
            'total_venda': dados['total_venda'],
            'total_dinheiro': dados['total_dinheiro'],
            'total_cartao': dados['total_cartao'],
            'total_sangria': dados['total_sangria'],
            'saldo_final': saldo_final
        })

    # Ordenar por data (mais recente primeiro)
    historico.sort(key=lambda x: x['data'], reverse=True)

    return render_template('historico_caixa.html', historico=historico)

@app.route('/editar_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def editar_item(item_id):
    db = get_db()
    item = db.execute('SELECT * FROM itens WHERE id = ?', (item_id,)).fetchone()

    if not item:
        flash("Item não encontrado.")
        return redirect(url_for('estoque'))

    if request.method == 'POST':
        nome = request.form['nome']
        quantidade = int(request.form['quantidade'])
        categoria = request.form['categoria']
        custo = float(request.form['custo'])
        venda = float(request.form['venda'])

        db.execute('''
            UPDATE itens 
            SET nome = ?, quantidade = ?, categoria = ?, custo = ?, venda = ? 
            WHERE id = ?
        ''', (nome, quantidade, categoria, custo, venda, item_id))
        db.commit()
        flash("Item atualizado com sucesso!")
        return redirect(url_for('estoque'))

    return render_template('editar_item.html', item=item)

@app.route('/excluir_item/<int:item_id>')
@login_required
def excluir_item(item_id):
    db = get_db()
    db.execute('DELETE FROM itens WHERE id = ?', (item_id,))
    db.commit()
    flash("Item excluído com sucesso!")
    return redirect(url_for('estoque'))

@app.route('/remover_item_carrinho', methods=['POST'])
@login_required
def remover_item_carrinho():
    item_id = int(request.form['item_id'])
    carrinho = session.get('carrinho', [])

    # Remove apenas o primeiro item com esse ID (ou pode remover todos, se quiser)
    for i, item in enumerate(carrinho):
        if item['id'] == item_id:
            carrinho.pop(i)
            break

    session['carrinho'] = carrinho
    return redirect(url_for('venda'))

@app.route('/cancelar_venda', methods=['POST'])
@login_required
def cancelar_venda():
    session.pop('carrinho', None)
    flash("Venda cancelada com sucesso.")
    return redirect(url_for('venda'))

@app.route('/caixa')
@login_required
def caixa():
    db = get_db()
    hoje = datetime.now().strftime('%Y-%m-%d')
    # Vendas normais do dia (dinheiro e cartão)
    vendas_do_dia = db.execute('''
        SELECT v.id, v.data_hora, v.forma_pagamento, u.nome, v.valor_total
        FROM vendas v
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE DATE(v.data_hora) = ?
        AND v.forma_pagamento IN ('dinheiro', 'cartao')
    ''', (hoje,)).fetchall()

    # Pagamentos de fiado feitos HOJE
    pagamentos_fiados = db.execute('''
        SELECT hp.valor_pago, c.nome, hp.data_pagamento
        FROM historico_pagamentos hp
        JOIN clientes c ON hp.cliente_id = c.id
        WHERE DATE(hp.data_pagamento) = ?
    ''', (hoje,)).fetchall()

    total_vendas = sum(v[4] for v in vendas_do_dia)
    total_dinheiro = sum(v[4] for v in vendas_do_dia if v[2]=='dinheiro')
    total_cartao = sum(v[4] for v in vendas_do_dia if v[2] == 'cartao') 
    total_pagamentos_fiados = sum(p[0] for p in pagamentos_fiados)
    total_caixa = total_vendas + total_pagamentos_fiados

    # Sangrias do dia
    sangrias_do_dia = db.execute('''
        SELECT s.id, s.data_hora, s.valor, s.descricao, u.nome
        FROM sangrias s
        JOIN usuarios u ON s.usuario_id = u.id
        WHERE DATE(s.data_hora) = ?
    ''', (hoje,)).fetchall()
    
    #conta a receber
    contas_fiadas = db.execute('''
        SELECT f.valor, c.nome AS nome_cliente, f.data_venda
        FROM contas_fiadas f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE DATE(f.data_venda) = ? AND f.pago = 0
    ''', (hoje,)).fetchall()

    total_sangrias = sum(float(s[2]) for s in sangrias_do_dia)

    saldo_final = round(total_dinheiro - total_sangrias, 2)

    return render_template(
        'caixa.html',
        vendas=vendas_do_dia,
        pagamentos_fiados = pagamentos_fiados,
        sangrias=sangrias_do_dia,
        total_vendas=total_vendas,
        total_dinheiro=total_dinheiro,
        total_pagamentos_fiados = total_pagamentos_fiados,
        total_cartao=total_cartao,
        total_sangrias=total_sangrias,
        total_caixa = total_caixa,
        saldo_final=saldo_final,
        contas_fiadas=contas_fiadas,
        data_hoje=datetime.now().strftime('%d/%m/%Y')
    )

@app.route('/registrar_sangria', methods=['GET', 'POST'])
@login_required
def registrar_sangria():
    if request.method == 'POST':
        try:
            valor = float(request.form['valor'])
            descricao = request.form.get('descricao', '')
            db = get_db()
            data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            db.execute('''
                INSERT INTO sangrias (data_hora, valor, descricao, usuario_id)
                VALUES (?, ?, ?, ?)
            ''', (data_hora, valor, descricao, current_user.id))
            db.commit()
            flash("Sangria registrada com sucesso!")
            return redirect(url_for('caixa'))
        except ValueError:
            flash("Valor inválido.")
            return redirect(url_for('registrar_sangria'))

    return render_template('registrar_sangria.html')

@app.route('/cadastrar_cliente', methods=['GET', 'POST'])
@login_required
def cadastrar_cliente():
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        telefone = request.form.get('telefone')
        endereco = request.form.get('endereco')

        db = get_db()
        try:
            db.execute('''
                INSERT INTO clientes (nome, telefone, endereco)
                VALUES (?, ?, ?)
            ''', (nome, telefone, endereco))
            db.commit()
            flash("Cliente cadastrado com sucesso!")
            return redirect(url_for('listar_clientes'))
        except sqlite3.IntegrityError:
            flash("Nome já existe. Use outro.")
            return redirect(url_for('cadastrar_cliente'))

    return render_template('cadastrar_cliente.html')

@app.route('/listar_clientes')
@login_required
def listar_clientes():
    db = get_db()
    
    # Busca clientes com dívidas abertas
    clientes_com_divida = db.execute('''
        SELECT c.id, c.nome, SUM(f.valor) AS total_devido
        FROM clientes c
        JOIN contas_fiadas f ON c.id = f.cliente_id
        WHERE f.pago = 0
        GROUP BY c.id
    ''').fetchall()

    # Clientes com dívidas quitadas
    clientes_quitados = db.execute('''
        SELECT c.id, c.nome, SUM(f.valor) AS valor_pago, MAX(f.data_pagamento) AS ultima_pagamento
        FROM clientes c
        JOIN contas_fiadas f ON c.id = f.cliente_id
        WHERE f.pago = 1
        GROUP BY c.id
    ''').fetchall()

    return render_template(
        'listar_clientes.html',
        clientes_abertos=clientes_com_divida,
        clientes_quitados=clientes_quitados
    )

@app.route('/ver_conta_cliente/<int:cliente_id>')
@login_required
def ver_conta_cliente(cliente_id):
    db = get_db()
    
    cliente = db.execute('SELECT * FROM clientes WHERE id = ?', (cliente_id,)).fetchone()
    if not cliente:
        flash("Cliente não encontrado.")
        return redirect(url_for('listar_clientes'))

    # Busca TODAS as dívidas (pago = 0 ou 1)
    dividas = db.execute('''
        SELECT f.id, v.data_hora, f.valor, c.nome, f.pago, f.data_pagamento
        FROM contas_fiadas f
        JOIN clientes c ON f.cliente_id = c.id
        JOIN vendas v ON f.venda_id = v.id
        WHERE f.cliente_id = ?
        ORDER BY f.data_venda DESC
    ''', (cliente_id,)).fetchall()

    total_devido = db.execute('''
        SELECT SUM(valor) FROM contas_fiadas
        WHERE cliente_id = ? AND pago = 0
    ''', (cliente_id,)).fetchone()[0] or 0.0

    dividas_pagas = db.execute('''
        SELECT f.valor, v.data_hora
        FROM contas_fiadas f
        JOIN vendas v ON f.venda_id = v.id
        WHERE f.cliente_id = ? AND f.pago = 1
    ''', (cliente_id,)).fetchall()

    total_pago = sum(d[0] for d in dividas_pagas)

    return render_template('ver_conta_cliente.html', cliente=cliente, dividas=dividas, total_devido=total_devido, total_pago=total_pago)

@app.route('/pagar_divida/<int:id>', methods=['POST'])
@login_required
def pagar_divida(id):
    db = get_db()
    divida = db.execute('SELECT * FROM contas_fiadas WHERE id = ?', (id,)).fetchone()
    
    if not divida:
        flash("Dívida não encontrada.")
        return redirect(url_for('listar_clientes'))

    data_pagamento = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('''
        UPDATE contas_fiadas SET 
        pago = 1,
        data_pagamento = ?
        WHERE id = ?
    ''', (data_pagamento, id))

    db.execute('''
        INSERT INTO historico_pagamentos (cliente_id, valor_pago, data_pagamento, usuario_id)
        VALUES (?, ?, ?, ?)
    ''', (divida[1], divida[3], data_pagamento, current_user.id))

    db.commit()
    flash("Dívida paga com sucesso!")

    return redirect(url_for('listar_clientes'))

@app.route('/gerar_recibo_pagamento/<int:id>')
@login_required
def gerar_recibo_pagamento(id):
    db = get_db()
    
    # Busca dados da dívida e cliente
    divida = db.execute('''
        SELECT f.*, c.nome 
        FROM contas_fiadas f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.id = ?
    ''', (id,)).fetchone()

    if not divida:
        flash("Dívida não encontrada.")
        return redirect(url_for('listar_clientes'))

    cliente_nome = divida['nome']
    valor_pago = divida[3]  # valor
    data_pagamento = divida[5]  # data_pagamento
    vendedor = current_user.nome

    html = render_template('recibo_pagamento.html',
                           cliente_nome=cliente_nome,
                           valor_pago=valor_pago,
                           data_pagamento=data_pagamento,
                           vendedor=vendedor)

    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    options = {'enable-local-file-access': None}
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)

    return send_file(
        io.BytesIO(pdf),
        download_name=f'recibo_pagamento_{cliente_nome}_{data_pagamento}.pdf',
        as_attachment=True,
        mimetype='application/pdf'
    )

@app.route('/pagar_dividas_cliente/<int:cliente_id>/<tipo>', methods=['POST'])
@login_required
def pagar_dividas_cliente(cliente_id, tipo):
    db = get_db()
    
    # Busca todas as dívidas não pagas do cliente
    dividas_abertas = db.execute('''
        SELECT * FROM contas_fiadas 
        WHERE cliente_id = ? AND pago = 0
    ''', (cliente_id,)).fetchall()

    if not dividas_abertas:
        flash("Nenhuma dívida em aberto.")
        return redirect(url_for('ver_conta_cliente', cliente_id=cliente_id))

    data_pagamento = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if tipo == 'todas':
        # Paga todas as dívidas do cliente
        db.execute('''
            UPDATE contas_fiadas SET 
            pago = 1,
            data_pagamento = ?
            WHERE cliente_id = ? AND pago = 0
        ''', (data_pagamento, cliente_id))
        
        total_pago = sum(d[3] for d in dividas_abertas)

        db.execute('''
            INSERT INTO historico_pagamentos (cliente_id, valor_pago, data_pagamento, usuario_id)
            VALUES (?, ?, ?, ?)
        ''', (cliente_id, total_pago, data_pagamento, current_user.id))

    elif tipo == 'selecionadas':
        # Paga apenas as dívidas selecionadas
        ids_str = request.form.get('divida_ids')
        if not ids_str:
            flash("Nenhuma dívida selecionada.")
            return redirect(url_for('ver_conta_cliente', cliente_id=cliente_id))

        ids_list = ids_str.split(',')
        placeholders = ','.join(['?'] * len(ids_list))
        
        # Pega os registros para somar o valor pago
        dividas_selecionadas = db.execute(f'''
            SELECT * FROM contas_fiadas 
            WHERE id IN ({placeholders}) AND cliente_id = ?
        ''', (*ids_list, cliente_id)).fetchall()

        total_pago = sum(d[3] for d in dividas_selecionadas)

        # Marca como paga
        db.execute(f'''
            UPDATE contas_fiadas SET 
            pago = 1,
            data_pagamento = ?
            WHERE id IN ({placeholders}) AND cliente_id = ?
        ''', (data_pagamento, *ids_list, cliente_id))

        # Registra no histórico
        db.execute('''
            INSERT INTO historico_pagamentos (cliente_id, valor_pago, data_pagamento, usuario_id)
            VALUES (?, ?, ?, ?)
        ''', (cliente_id, total_pago, data_pagamento, current_user.id))

    db.commit()
    flash(f"Você pagou R$ {total_pago:.2f}.")
    return redirect(url_for('ver_conta_cliente', cliente_id=cliente_id))

@app.route('/gerar_recibo_dividas_quitadas/<int:cliente_id>')
@login_required
def gerar_recibo_dividas_quitadas(cliente_id):
    db = get_db()
    
    cliente = db.execute('SELECT nome FROM clientes WHERE id = ?', (cliente_id,)).fetchone()
    if not cliente:
        flash("Cliente não encontrado.")
        return redirect(url_for('listar_clientes'))

    # Busca apenas dívidas que já foram pagas
    dividas_pagas = db.execute('''
        SELECT f.valor, v.data_hora
        FROM contas_fiadas f
        JOIN vendas v ON f.venda_id = v.id
        WHERE f.cliente_id = ? AND f.pago = 1
    ''', (cliente_id,)).fetchall()

    if not dividas_pagas:
        flash("Não há dívidas quitadas para este cliente.")
        return redirect(url_for('ver_conta_cliente', cliente_id=cliente_id))

    total_pago = sum(d[0] for d in dividas_pagas)
    data_pagamento = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    vendedor = current_user.nome

    html = render_template(
        'recibo_pagamento_todas_dividas.html',
        cliente_nome=cliente['nome'],
        dividas=dividas_pagas,
        total_pago=total_pago,
        data_pagamento=data_pagamento,
        vendedor=vendedor
    )

    options = {
    'enable-local-file-access': None,
    'encoding': 'UTF-8',
    'no-stop-slow-scripts': None,  # Para evitar timeout em scripts pesados
}

    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    return send_file(
        io.BytesIO(pdf),
        download_name=f'recibo_dividas_quitadas_{cliente_id}_{datetime.now().strftime("%Y%m%d")}.pdf',
        as_attachment=True,
        mimetype='application/pdf'
    )

@app.route('/finalizar_venda', methods=['POST'])
@login_required
def finalizar_venda():
    carrinho = session.get('carrinho', [])
    if not carrinho:
        flash("Carrinho vazio.")
        return redirect(url_for('venda'))

    pagamento = request.form['pagamento']
    
    pago = 0.0
    if pagamento == 'dinheiro':
        try:
            pago = float(request.form.get('pago', 0))
        except ValueError:
            flash("Por favor, insira um valor válido.")
            return redirect(url_for('venda'))

    total = sum(i['valor'] for i in carrinho)

    if pagamento == 'dinheiro' and pago < total:
        flash("Valor pago é menor que o total da venda.")
        return redirect(url_for('venda'))

    db = get_db()
    data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Primeiro salva a venda para obter o ID
    db.execute('''
        INSERT INTO vendas (data_hora, usuario_id, valor_total, forma_pagamento) 
        VALUES (?, ?, ?, ?)
    ''', (data_hora, current_user.id, total, pagamento))
    venda_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # Agora sim, registra a dívida se for fiado
    if pagamento == 'fiado':
        cliente_id = int(request.form['cliente_id'])
        db.execute('''
            INSERT INTO contas_fiadas (cliente_id, venda_id, valor, pago, data_venda)
            VALUES (?, ?, ?, 0, ?)
        ''', (cliente_id, venda_id, total, data_hora))

    # Salva os itens da venda
    for item in carrinho:
        db.execute('''
            INSERT INTO itens_venda (venda_id, item_id, quantidade, valor_unitario) 
            VALUES (?, ?, ?, ?)
        ''', (venda_id, item['id'], item['quantidade'], item['valor'] / item['quantidade']))

        # Atualiza estoque somente após salvar a venda
        db.execute('''
            UPDATE itens SET quantidade = quantidade - ? WHERE id = ?
        ''', (item['quantidade'], item['id']))

    db.commit()
    session.pop('carrinho', None)

    if pagamento == 'dinheiro':
        troco = round(pago - total, 2)
        flash(f"Venda finalizada com sucesso! Troco: R$ {troco:.2f}")
    else:
        flash("Venda finalizada com sucesso!")

    return redirect(url_for('venda'))

# Relatórios
@app.route('/relatorios')
@login_required
def relatorios():
    return render_template('relatorios.html')

@app.route('/gerar_relatorio/<tipo>')
@login_required
def gerar_relatorio(tipo):
    db = get_db()
    hoje = datetime.now().strftime('%Y-%m-%d')
    if tipo == 'vendas':
        vendas = db.execute('''
            SELECT v.id, u.nome, v.data_hora, v.valor_total, v.forma_pagamento 
            FROM vendas v JOIN usuarios u ON v.usuario_id = u.id
            ORDER BY v.data_hora DESC
        ''').fetchall()

        vendas_com_itens = []
        for venda in vendas:
            itens = db.execute('''
                SELECT i.nome, iv.quantidade, iv.valor_unitario 
                FROM itens_venda iv JOIN itens i ON iv.item_id = i.id
                WHERE iv.venda_id = ?
            ''', (venda[0],)).fetchall()
            
            vendas_com_itens.append({
                "id": venda[0],
                "usuario": venda[1],
                "data_hora": venda[2],
                "valor_total": venda[3],
                "forma_pagamento": venda[4],
                "itens": [{"nome": i[0], "qtd": i[1], "valor": i[2]} for i in itens]
            })

        html = render_template('relatorio_todas_vendidas.html', vendas=vendas_com_itens)
                
    elif tipo == 'mais_vendidos':
        mais_vendidos = db.execute('''
            SELECT i.nome, SUM(iv.quantidade) AS total_vendido, 
                   AVG(i.venda - i.custo) AS lucro_medio
            FROM itens_venda iv JOIN itens i ON iv.item_id = i.id
            GROUP BY i.id ORDER BY total_vendido DESC LIMIT 10
        ''').fetchall()
        html = render_template('relatorio_mais_vendidos.html', itens=mais_vendidos)

    elif tipo == 'fechamento_caixa':
        vendas_do_dia = db.execute('''
        SELECT v.id, v.data_hora, v.forma_pagamento, u.nome, v.valor_total
        FROM vendas v
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE DATE(v.data_hora) = ?
        AND v.forma_pagamento IN ('dinheiro', 'cartao')
    ''', (hoje,)).fetchall()

        # Pagamentos de fiado feitos HOJE
        pagamentos_fiados = db.execute('''
            SELECT hp.valor_pago, c.nome, hp.data_pagamento
            FROM historico_pagamentos hp
            JOIN clientes c ON hp.cliente_id = c.id
            WHERE DATE(hp.data_pagamento) = ?
        ''', (hoje,)).fetchall()

        total_vendas = sum(v[4] for v in vendas_do_dia)
        total_dinheiro = sum(v[4] for v in vendas_do_dia if v[2]=='dinheiro')
        total_cartao = sum(v[4] for v in vendas_do_dia if v[2] == 'cartao') 
        total_pagamentos_fiados = sum(p[0] for p in pagamentos_fiados)
        total_caixa = total_vendas + total_pagamentos_fiados
        saldo_final_dinheiro = total_dinheiro  # Aqui você pode adicionar ou subtrair sangrias

        html = render_template(
            'relatorio_fechamento_caixa.html',
            vendas=vendas_do_dia,
            pagamentos_fiados = pagamentos_fiados,
            total_vendas=total_vendas,
            total_dinheiro=total_dinheiro,
            total_cartao=total_cartao,
            total_caixa=total_caixa,
            total_pagamentos_fiados=total_pagamentos_fiados,
            saldo_final_dinheiro=saldo_final_dinheiro,
            data_hoje=hoje
        )

    options = {
    'enable-local-file-access': None,
    'encoding': 'UTF-8',
    'no-stop-slow-scripts': None,  # Para evitar timeout em scripts pesados
}

    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    return send_file(
        io.BytesIO(pdf),
        download_name=f'relatorio_{tipo}.pdf',
        as_attachment=True,
        mimetype='application/pdf')

@app.route('/listar_vendas')
@login_required
def listar_vendas():
    db = get_db()

        #buscar todas as vendas com os dados do vendedor
    vendas = db.execute('''
        SELECT v.id, u.nome, v.data_hora, v.valor_total, v.forma_pagamento
        FROM vendas v JOIN usuarios u ON v.usuario_id = u.id 
        ORDER BY v.data_hora DESC          
    ''').fetchall()


    #para cada venda, busca os itens vendidos nela
    vendas_com_itens = []
    for venda in vendas:
        itens_venda = db.execute('''
            SELECT i.nome, iv.quantidade, iv.valor_unitario
            FROM itens_venda iv
            JOIN itens i ON iv.item_id = i.id
            WHERE iv.venda_id = ?
        ''', (venda[0],)).fetchall()

        #formatação da lista
        itens_lista = [{"nome": item[0], "qtd": item[1], "valor": item[2]} for item in itens_venda]
        total_venda = sum(item["qtd"]*item["valor"] for item in itens_lista)

        vendas_com_itens.append({
            "id": venda[0],
            "usuario": venda[1],
            "data_hora":venda[2],
            "valor_total": venda[3],
            "forma_pagamento": venda[4],
            "itens": itens_lista,
            "total_calculado": total_venda
        })


    return render_template('listar_vendas.html', vendas=vendas_com_itens)
    
if __name__ == '__main__':
    init_db(app)
    app.run(debug=True)

