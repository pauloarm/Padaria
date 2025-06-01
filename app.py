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
        return render_template('venda.html', itens=itens, carrinho=carrinho, total=total)
    
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

@app.route('/finalizar_venda', methods=['POST'])
@login_required
def finalizar_venda():
    carrinho = session.get('carrinho', [])
    if not carrinho:
        flash("Carrinho vazio.")
        return redirect(url_for('venda'))

    pagamento = request.form['pagamento']
    troco = 0.0
    pago = float(request.form.get('pago', 0))

    total = sum(i['valor'] for i in carrinho)
    
    if pagamento == 'dinheiro' and pago < total:
        flash("Valor pago insuficiente.")
        return redirect(url_for('venda'))

    if pagamento == 'dinheiro':
        troco = round(pago - total, 2)

    db = get_db()
    data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Salva a venda
    db.execute('''
        INSERT INTO vendas (data_hora, usuario_id, valor_total, forma_pagamento) 
        VALUES (?, ?, ?, ?)
    ''', (data_hora, current_user.id, total, pagamento))
    venda_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # Salva os itens da venda
    for item in carrinho:
        db.execute('''
            INSERT INTO itens_venda (venda_id, item_id, quantidade, valor_unitario) 
            VALUES (?, ?, ?, ?)
        ''', (venda_id, item['id'], item['quantidade'], item['valor'] / item['quantidade']))

        # Agora sim: reduzir o estoque
        db.execute('''
            UPDATE itens SET quantidade = quantidade - ? WHERE id = ?
        ''', (item['quantidade'], item['id']))

    db.commit()
    session.pop('carrinho', None)
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

    pagina = int(request.args.get('pagina', 1))
    limite = 10  # Mostrar 10 vendas por página
    offset = (pagina - 1) * limite

    #buscar todas as vendas com os dados do vendedor
    vendas = db.execute('''
        SELECT v.id, u.nome, v.data_hora, v.valor_total, v.forma_pagamento
        FROM vendas v JOIN usuarios u ON v.usuario_id = u.id 
        ORDER BY v.data_hora DESC
        LIMIT ? OFFSET ?            
    ''', (limite, offset)).fetchall()


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

    has_next = (offset + limite) < total_venda

    return render_template('listar_vendas.html', vendas=vendas_com_itens, pagina=pagina, has_next=has_next)
    

if __name__ == '__main__':
    init_db(app)
    app.run(debug=True)

