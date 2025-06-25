from flask import Flask, render_template, request, redirect, url_for, session, send_file
import psycopg2
from datetime import datetime
from functools import wraps
import openpyxl
from io import BytesIO
import os

app = Flask(__name__)
app.secret_key = 'chave_secreta_segura'

# Conexão com PostgreSQL (Render)
def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "seu_host_aqui"),
        database=os.getenv("DB_NAME", "seu_db"),
        user=os.getenv("DB_USER", "seu_user"),
        password=os.getenv("DB_PASSWORD", "sua_senha"),
        port=os.getenv("DB_PORT", 5432)
    )

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == "admin" and password == "admin":
            session["user"] = username
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Credenciais inválidas")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/estoque", methods=["GET", "POST"])
@login_required
def estoque():
    conn = get_conn()
    c = conn.cursor()
    if request.method == "POST":
        nome = request.form["nome"]
        valor = float(request.form["valor"])
        quantidade = int(request.form["quantidade"])
        c.execute("INSERT INTO produtos (nome, valor, quantidade) VALUES (%s, %s, %s)", (nome, valor, quantidade))
        conn.commit()
    c.execute("SELECT * FROM produtos ORDER BY nome ASC")
    produtos = c.fetchall()
    conn.close()
    return render_template("estoque.html", produtos=produtos)

@app.route("/editar_produto/<int:id>", methods=["GET", "POST"])
@login_required
def editar_produto(id):
    conn = get_conn()
    c = conn.cursor()
    if request.method == "POST":
        nome = request.form["nome"]
        valor = float(request.form["valor"])
        quantidade = int(request.form["quantidade"])
        c.execute("UPDATE produtos SET nome=%s, valor=%s, quantidade=%s WHERE id=%s", (nome, valor, quantidade, id))
        conn.commit()
        conn.close()
        return redirect(url_for("estoque"))
    c.execute("SELECT * FROM produtos WHERE id=%s", (id,))
    produto = c.fetchone()
    conn.close()
    return render_template("editar_produto.html", produto=produto)

@app.route("/excluir_produto/<int:id>")
@login_required
def excluir_produto(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM produtos WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("estoque"))

@app.route("/saida", methods=["GET", "POST"])
@login_required
def saida():
    conn = get_conn()
    c = conn.cursor()
    if request.method == "POST":
        produto_id = int(request.form["produto"])
        quantidade = int(request.form["quantidade"])
        vendedor = request.form["vendedor"]
        desconto = float(request.form["desconto"]) / 100
        data = datetime.now().strftime("%Y-%m-%d %H:%M")

        c.execute("SELECT nome, valor, quantidade FROM produtos WHERE id=%s", (produto_id,))
        produto = c.fetchone()

        if produto and produto[2] >= quantidade:
            novo_estoque = produto[2] - quantidade
            total_bruto = quantidade * produto[1]
            total_final = total_bruto * (1 - desconto)
            c.execute("UPDATE produtos SET quantidade=%s WHERE id=%s", (novo_estoque, produto_id))
            c.execute("INSERT INTO vendas (produto, quantidade, vendedor, data, total, desconto) VALUES (%s, %s, %s, %s, %s, %s)",
                      (produto[0], quantidade, vendedor, data, total_final, desconto))
            conn.commit()

    c.execute("SELECT * FROM produtos ORDER BY nome ASC")
    produtos = c.fetchall()
    c.execute("SELECT * FROM vendas ORDER BY data DESC")
    vendas = c.fetchall()
    conn.close()
    return render_template("saida.html", produtos=produtos, vendas=vendas)

@app.route("/excluir_venda/<int:id>")
@login_required
def excluir_venda(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM vendas WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("saida"))

@app.route("/relatorios")
@login_required
def relatorios():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM vendas ORDER BY data DESC")
    vendas = c.fetchall()
    c.execute("SELECT * FROM produtos ORDER BY nome ASC")
    produtos = c.fetchall()
    conn.close()
    return render_template("relatorios.html", vendas=vendas, produtos=produtos)

@app.route("/exportar_vendas")
@login_required
def exportar_vendas():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM vendas")
    vendas = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vendas"
    ws.append(["ID", "Produto", "Quantidade", "Vendedor", "Data", "Total", "Desconto"])
    for v in vendas:
        ws.append(v)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name="vendas.xlsx", as_attachment=True)

@app.route("/exportar_estoque")
@login_required
def exportar_estoque():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM produtos ORDER BY nome ASC")
    produtos = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Estoque"
    ws.append(["ID", "Nome", "Valor", "Quantidade"])
    for p in produtos:
        ws.append(p)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name="estoque.xlsx", as_attachment=True)

@app.route("/comissao")
@login_required
def comissao():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT vendedor, SUM(total) as total_vendido FROM vendas GROUP BY vendedor")
    dados = c.fetchall()
    resultado = []

    def calcular_comissao(valor):
        if valor <= 500:
            return valor * 0.10
        elif valor <= 1000:
            return valor * 0.15
        else:
            return valor * 0.20

    for linha in dados:
        vendedor = linha[0]
        total = linha[1]
        comissao = calcular_comissao(total)
        resultado.append((vendedor, total, comissao))

    conn.close()
    return render_template("comissao.html", resultado=resultado)

if __name__ == "__main__":
    app.run(debug=True)
