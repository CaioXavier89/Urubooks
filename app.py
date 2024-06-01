import os

from cs50 import SQL
from datetime import date
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash


from helpers import apology, login_required

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///urubooks.db")

# Estilos possíveis para as flash messages
FLASH_STYLES = [
    "primary",
    "secondary",
    "success",
    "danger",
    "warning",
    "info",
]

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    acervo = db.execute('SELECT COUNT(*) FROM acervo')[0]['COUNT(*)']
    usuarios = db.execute('SELECT COUNT(*) FROM users')[0]['COUNT(*)']
    return render_template("index.html", acervo=acervo, usuarios=usuarios)

@app.route("/usuarios")
@login_required
def usuarios():
    return render_template("usuarios/index.html")


@app.route("/history")
@login_required
def history():
    return render_template("history.html")

@app.route("/emprestar", methods=["GET", "POST"])
@login_required
def emprestar():
    if request.method == "POST":
        livro = request.method.get("livro_id")
        contato = request.method.get("contato_id")

        db.execute()
        db.execute()
        flash('Empréstimo cadastrado', 'success')
        return redirect('/')
    else:
        return render_template("emprestar.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # clears session data
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        if 'user_id' in session:
            return redirect('/')
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/usuarios/cadastro", methods=["GET", "POST"])
@login_required
def usuarios_cadastro():
    if request.method == "POST":
        # handles nome input
        nome = request.form.get("nome")
        if not nome:
            return apology("Nome necessário")
        
        # handles cpf input
        cpf = request.form.get('cpf').replace("-", "").replace(".", "")
        if len(cpf) != 11:
            return apology("Formato de CPF inválido")
        try:
            cpf = int(cpf)
        except:
            return apology("Formato de CPF inválido")
        consulta_cpf = db.execute(
        "SELECT * FROM contatos WHERE cpf = ?", cpf
        )
        if len(consulta_cpf) != 0:
            return apology("Esse CPF já está cadastrado")
        
        # handles telefone input
        telefone = request.form.get('telefone').replace("-", "").replace("(", "").replace(")", "")
        telefone = int(telefone)
        if not telefone:
            return apology('Telefone necessário')
        
        # handles e-mail
        email = request.form.get('e-mail')
        
        # handles endereço
        endereço = request.form.get('endereço')

        # com tudo validado, insere linha no banco de dados
        db.execute("INSERT INTO contatos (nome, cpf, telefone, email, endereço) VALUES (?, ?, ?, ?, ?)", nome, cpf, telefone, email, endereço)
        
        flash("Usuário cadastrado com sucesso!", "success")
        return redirect('/')
    else:
        return render_template("usuarios/cadastro.html")

@app.route("/acervo", methods=["GET", "POST"])
@login_required
def acervo():
    if request.method == "POST":
        ''' o método post é usado nessa rota para editar e excluir livros do acervo '''
        # handles exclusão do banco de dados
        delete_request = request.form.get('delete-id')
        if delete_request:
            db.execute("UPDATE acervo SET status = 'ARQUIVADO' WHERE id = ?", delete_request)
            flash("Status da obra atualizado com sucesso", "warning")
            return redirect("/acervo")
        
        # handles edição de livro
        # identifica o livro sendo editado
        edited_book = db.execute("SELECT * FROM acervo WHERE id = ?", request.form.get('edited-book-id'))
        # checa se há houve algum input nos campos, em caso negativo, atribui o valor anterior
        if edited_book:
            new_titulo = request.form.get('edit-titulo') if request.form.get('edit-titulo') else request.form.get('titulo-anterior')
            new_autor = request.form.get('edit-autor') if request.form.get('edit-autor') else request.form.get('autor-anterior')
            new_editora = request.form.get('edit-editora') if request.form.get('edit-editora') else request.form.get('editora-anterior')
            new_ano = request.form.get('edit-ano') if request.form.get('edit-ano') else request.form.get('ano-anterior')
            new_status = request.form.get('edit-status') if request.form.get('edit-status') else request.form.get('status-anterior')
            # atualiza banco de dados
            db.execute("UPDATE acervo SET titulo = ?, autor = ?, editora = ?, ano = ?, status = ? WHERE id = ?", new_titulo, new_autor, new_editora, new_ano, new_status, edited_book[0]["id"])
            
            flash("A obra foi editada com sucesso!", "success")
            return redirect("/acervo")

        # caso nada tenha sido editado ou deletado
        flash("Nada foi alterado", "success")
        return redirect("/acervo")
    
    
    # MÉTODO = "GET"
    else: 
        # checa se há request de edição para abrir pop-up
        edited_book = {}
        if edit_id := request.args.get("edit-book"):
            edited_book = db.execute("SELECT * FROM acervo WHERE id = ?", edit_id)[0] 
        

        # handles filtros
        # cria dicionário de filtros
        filtros = {}
        # filtros não modificados para serem usados no HTML
        filtros_placeholder = {}

        # adiciona filtro ao dicionário se houver request
        filtro_titulo = request.args.get('filtro-titulo')
        if filtro_titulo:
            filtros_placeholder["titulo"] = filtro_titulo
            filtros["titulo"] = "%" + filtro_titulo + "%"

        filtro_autor = request.args.get('filtro-autor')
        if filtro_autor:
            filtros_placeholder["autor"] = filtro_autor
            filtros["autor"] = "%" + filtro_autor + "%"

        filtro_ano = request.args.get("filtro-ano")
        if filtro_ano:
            filtros_placeholder["ano"] = filtro_ano
            filtros["ano"] = "%" + filtro_ano + "%"

        filtro_editora = request.args.get("filtro-editora")
        if filtro_editora:
            filtros_placeholder["editora"] = filtro_editora
            filtros["editora"] = "%" + filtro_editora + "%"

        filtro_arquivado = " id IN (SELECT id FROM acervo WHERE status != 'ARQUIVADO')"
        if request.args.get('mostrar-arquivados') == 'true':
            filtro_arquivado = " id IN (SELECT id FROM acervo WHERE status = 'DISPONIVEL' OR status = 'EMPRESTADO' OR status = 'ARQUIVADO')"

        
        # prepara dados para paginação
        LIVROS_POR_PAGINA = 50
        pagina_atual = int(request.args.get("pagina", 0))
        offset = LIVROS_POR_PAGINA * pagina_atual        

        
        # prepara query base
        query = "SELECT * FROM acervo"
        # adiciona filtros existentes
        if filtros:
            query += " WHERE " + " AND ".join([f"{key} LIKE ?" for key in filtros])
            acervo = db.execute(query + " AND " + filtro_arquivado + " ORDER BY titulo" + " LIMIT ?, ?", *tuple(filtros.values()), offset, LIVROS_POR_PAGINA)
            search_size = len(db.execute(query + " AND " + filtro_arquivado + " ORDER BY titulo", *tuple(filtros.values())))
        # caso não haja filtros, roda query base
        else:
            acervo = db.execute(query + " WHERE " + filtro_arquivado + " ORDER BY titulo" + " LIMIT ?, ?", offset, LIVROS_POR_PAGINA)
            search_size = len(db.execute(query + " WHERE " + filtro_arquivado))

        # prepara dicionário para ser usado no HTML
        page_data = {
            "search_size":search_size,
            "atual":pagina_atual,
            "max":int(search_size/LIVROS_POR_PAGINA)
        }
        return render_template("acervo/index.html", acervo=acervo, edited_book=edited_book, filtros=filtros_placeholder, page_data=page_data)

@app.route("/acervo/incluir", methods=["GET", "POST"])
@login_required
def acervo_incluir():
    if request.method == "POST":
        titulo = request.form.get('titulo')
        autor = request.form.get('autor')
        editora = request.form.get('editora')
        ano = request.form.get('ano')

        db.execute('INSERT INTO acervo (titulo, autor, editora, ano, status) VALUES (?, ?, ?, ?, "DISPONIVEL")', titulo, autor, editora, ano)
        flash("Livro cadastrado", "success")
        return redirect(url_for("/acervo"))       
    else:
        return render_template("acervo/incluir.html")

if __name__ == '__main__':
    app.run(debug=True)