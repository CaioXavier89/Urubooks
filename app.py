import os

from cs50 import SQL
from datetime import date, timedelta
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import ast

from helpers import login_required
port = os.environ.get('PORT')

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

# planos disponíveis
PLANOS = [
    "BÁSICO",
]
PRAZO_EMPRESTIMO_DEFAULT = 15 # DIAS
PRAZO_ASSINATURA_DEFAULT = 365 # DIAS
PLANO_ASSINATURA_DEFAULT = "BÁSICO"
HOJE = date.today()

OPERAÇÕES_HISTORICO = [
    "INCLUSÃO NO ACERVO",
    "ASSINATURA",
    "VENCIMENTO DE ASSINATURA",
    "EMPRÉSTIMO",
    "DEVOLUÇÃO",
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
    # checa se banco de dados já foi atualizado hoje
    last_update = db.execute("SELECT data FROM updated")
    if not last_update or date.fromisoformat(last_update[0]["data"]) < HOJE:
        # caso não tenha sido atualizada hoje, registra data de atualização do db e atualiza status se encontrar alguma assinatura vencida
        db.execute("DELETE FROM updated")
        db.execute("INSERT INTO updated (data) VALUES(?)", HOJE.isoformat())
        assinaturas_ativas = db.execute("SELECT * FROM assinaturas WHERE status = 'ATIVA'")
        for a in assinaturas_ativas:
            if date.fromisoformat(a["prazo"]) < HOJE:
                db.execute("UPDATE assinaturas SET status = 'VENCIDA' WHERE id = ?", a["id"])
                db.execute('INSERT INTO historico (data, contato_cpf, operacao) VALUES(?, ?, "VENCIMENTO DE ASSINATURA")', HOJE.isoformat(), a["contato_cpf"])
        
    assinaturas = db.execute("SELECT * FROM assinaturas JOIN contatos ON assinaturas.contato_cpf = contatos.cpf\
                             WHERE assinaturas.status = 'ATIVA' ORDER BY assinaturas.prazo DESC LIMIT 20")
    emprestimos = db.execute("SELECT * FROM emprestimos JOIN contatos ON emprestimos.contato_cpf = contatos.cpf\
                             JOIN acervo ON emprestimos.obra_id = acervo.id\
                             ORDER BY emprestimos.prazo DESC LIMIT 20")
    for e in emprestimos:
        if date.fromisoformat(e["prazo"]) < HOJE:
            e["atrasado"] = "true"
        else:
            e["atrasado"] = "false"

    acervo = db.execute('SELECT COUNT(*) FROM acervo')[0]['COUNT(*)']
    usuarios = db.execute('SELECT COUNT(*) FROM assinaturas WHERE status = "ATIVA"')[0]['COUNT(*)']

    return render_template("index.html", acervo=acervo, usuarios=usuarios, assinaturas=assinaturas, emprestimos=emprestimos, hoje=HOJE.isoformat())


@app.route("/acervo", methods=["GET", "POST"])
@login_required
def acervo(): 
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
        filtros_placeholder["arquivado"] = 'true'
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


@app.route("/acervo/editar", methods=["GET", "POST"])
@login_required
def acervo_editar():
    if request.method == "POST":
        # handles arquivamento do banco de dados
        if delete_request := request.form.get('delete-id'):
            db.execute("DELETE FROM emprestimos WHERE obra_id = ?", delete_request)
            db.execute("DELETE FROM acervo WHERE id = ?", delete_request)
            flash("Obra removida do banco de dados.", "warning")
            return redirect("/acervo")
        
        previous_data = ast.literal_eval(request.form.get("previous_data"))
        
        id = request.form.get('book-id')
        titulo = request.form.get('titulo')
        autor = request.form.get('autor')
        editora = request.form.get('editora')
        ano = request.form.get('ano')
        status = request.form.get('status')
        # atualiza banco de dados

        if titulo == previous_data["titulo"] and autor == previous_data["autor"]\
            and editora == previous_data["editora"] and ano == str(previous_data["ano"]) and status == previous_data["status"]:
            flash("Não houve alterações na obra", "info")
            return redirect("/acervo")
        else:
            db.execute("UPDATE acervo SET titulo = ?, autor = ?, editora = ?, ano = ?, status = ? WHERE id = ?", titulo, autor, editora, ano, status, id)
            flash("A obra foi editada com sucesso!", "success")
            return redirect("/acervo")

    # MÉTODO "GET"
    else:
        obra_id = request.args.get("edit-book")
        edited_book = db.execute("SELECT * FROM acervo WHERE id = ?", obra_id)

        emprestimos = db.execute(
            "SELECT * FROM emprestimos JOIN contatos ON emprestimos.contato_cpf = contatos.cpf WHERE emprestimos.obra_id = ?", obra_id
            )
            
        for row in emprestimos:
            if HOJE > date.fromisoformat(row["prazo"]):
                row["atrasado"] = "true"
            else:
                row["atrasado"] = "false"

        if edited_book:
            edited_book = edited_book[0]
            
            return render_template("/acervo/editar.html", edited_book=edited_book, emprestimos=emprestimos)
        else:
            flash('Erro', 'danger')
            return redirect("/acervo")


@app.route("/acervo/incluir", methods=["GET", "POST"])
@login_required
def acervo_incluir():
    if request.method == "POST":
        titulo = request.form.get('titulo')
        autor = request.form.get('autor')
        editora = request.form.get('editora')
        ano = request.form.get('ano')

        if len(db.execute('SELECT * FROM acervo WHERE titulo = ? AND autor = ? AND editora = ? AND ano = ?', titulo, autor, editora, ano)) != 0:
            flash("Esse livro já existe no acervo", "warning")
            return render_template("acervo/incluir.html")

        db.execute('INSERT INTO acervo (titulo, autor, editora, ano, status) VALUES (?, ?, ?, ?, "DISPONIVEL")', titulo, autor, editora, ano)
        obra_id = db.execute("SELECT last_insert_rowid()")[0]["last_insert_rowid()"]
        db.execute("INSERT INTO historico (data, operacao, obra_id) VALUES(?, 'INCLUSÃO NO ACERVO', ?)", HOJE.isoformat(), obra_id)
        flash("Livro cadastrado", "success")
    
        if cpf := request.form.get("user-id"):
            prazo = request.form.get("prazo")
            fazer_emprestimo(obra_id, cpf, prazo)
            flash("Empréstimo cadastrado", "success")
        
        return redirect("/acervo")
        
    else:
        prazo_default = HOJE + timedelta(days=PRAZO_ASSINATURA_DEFAULT)
        return render_template("acervo/incluir.html", hoje=HOJE, prazo_default=prazo_default)


@app.route("/assinatura", methods=["POST"])
@login_required
def assinatura():
    if deletar := request.form.get("deletar-assinatura"):
        db.execute("DELETE FROM assinaturas WHERE id = ?", deletar)
        flash("Assinatura cancelada", "success")
        return redirect("/usuarios")
    contato_cpf = request.form.get("user-id")
    plano = request.form.get("plano")
    prazo = request.form.get("prazo")
    
    if fazer_assinatura(contato_cpf, plano, prazo) == True:
        db.execute('INSERT INTO historico (data, contato_cpf, operacao) VALUES(?, ?, "NOVA ASSINATURA")', HOJE.isoformat(), contato_cpf)
        flash("Assinatura feita com sucesso.", "success")
        return redirect("/")


@app.route("/cpf-search")
def cpf_search():
    cpf = request.args.get("cpf")
    usuario = {
        "nome":"",
        "cpf":"",
    }

    if query := db.execute("SELECT * FROM contatos WHERE cpf = ?", cpf):
        usuario = query[0]
        if len(db.execute("SELECT * FROM assinaturas WHERE contato_cpf = ? AND status = 'ATIVA'", cpf)) != 0:
            usuario["assinante"] = "true"
        else:
            usuario["assinante"] = "false"
        
    return jsonify(usuario)


@app.route("/devolver", methods=["POST"])
def devolver():
    obra_id = request.form.get("book-id")
    emprestimo_id = request.form.get("emprestimo-id")

    if obra_id and emprestimo_id:
        contato_cpf = db.execute("SELECT contato_cpf FROM emprestimos WHERE id = ?", emprestimo_id)[0]["contato_cpf"]
        db.execute("DELETE FROM emprestimos WHERE id = ?", emprestimo_id)
        db.execute('INSERT INTO historico (data, contato_cpf, obra_id, operacao) VALUES(?, ?, ?, "DEVOLUÇÃO")', HOJE.isoformat(), contato_cpf, obra_id)
        
        # checar se a obra está emprestada a alguém, caso negativo mudar status da obra para disponível
        if len(db.execute("SELECT * FROM emprestimos WHERE obra_id = ?", obra_id)) == 0:
            db.execute("UPDATE acervo SET status = 'DISPONIVEL' WHERE id = ?", obra_id)

        flash("Obra devolvida com sucesso", "success")
        return redirect("/")
    else:
        flash("Não foi possível realizar a devolução", "danger")
        return redirect("/")


@app.route("/emprestar", methods=["GET", "POST"])
@login_required
def emprestar():
    # O método POST faz as operações de inclusão do empréstimo no banco de dados e no histórico
    if request.method == "POST":
        obra_id = request.form.get("book-id")
        contato_cpf = request.form.get("user-id")
        prazo = request.form.get("prazo")

        fazer_emprestimo(obra_id, contato_cpf, prazo)
        db.execute('INSERT INTO historico (data, contato_cpf, obra_id, operacao) VALUES(?, ?, ?, "EMPRÉSTIMO")', HOJE.isoformat(), contato_cpf, obra_id)
        flash('Empréstimo cadastrado', 'success')
        return redirect('/')
    
    # MÉTODO GET
    # O método get é utilizado para disponibilizar e popular os formulários antes de ser enviado para o banco de dado
    else:
        data = {
            "hoje": HOJE,
            "prazodefault": HOJE + timedelta(days=PRAZO_EMPRESTIMO_DEFAULT),
        }

        if livro := db.execute("SELECT * FROM acervo WHERE id = ?", request.args.get("book-id")):
            livro = livro[0]

        contato_cpf = request.args.get("user-id")
        if usuario := db.execute("SELECT * FROM contatos WHERE cpf = ?", contato_cpf):
            usuario = usuario[0]
            if len(db.execute("SELECT * FROM assinaturas WHERE contato_cpf = ? AND status = 'ATIVA'", contato_cpf)) != 0:
                    usuario["assinante"] = "true"
            else:
                usuario["assinante"] = "false"
        
        else:
            usuario = {
                "nome":"",
                "cpf":"",
            }
        return render_template("emprestar.html", livro=livro, usuario=usuario, data=data)


@app.route("/historico")
@login_required
def historico():
    REGISTRO_POR_PAGINA = 30
    pagina = int(request.args.get("pagina", 0))
    offset = REGISTRO_POR_PAGINA * pagina
    historico = db.execute("SELECT * FROM historico LEFT JOIN acervo on historico.obra_id = acervo.id \
                           LEFT JOIN contatos on historico.contato_cpf = contatos.cpf ORDER BY historico.data DESC LIMIT ?, ?",
                           offset, REGISTRO_POR_PAGINA)
    page_data = {
        "atual":pagina,
        "max":int(len(historico)/REGISTRO_POR_PAGINA),
    }
    return render_template("historico.html", historico=historico, page_data=page_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # clears session data
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Preencha o campo de login", "danger")
            return redirect("/")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Preencha o campo de senha", "danger")
            return redirect("/")

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            flash("Senha ou usuário inválidos", "danger")
            return redirect("/login")

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


@app.route("/usuarios")
@login_required
def usuarios():
    CONTATOS_POR_PAGINA = 20
    pagina = request.args.get("pagina", 0)
    offset = CONTATOS_POR_PAGINA * pagina  
    usuarios = db.execute("SELECT * FROM contatos ORDER BY nome LIMIT ?, ?", offset, CONTATOS_POR_PAGINA)
    filtro = "off"
    if request.args.get("filtrar-assinantes"):
        usuarios = db.execute("SELECT * FROM contatos JOIN assinaturas ON contatos.cpf = assinaturas.contato_cpf WHERE assinaturas.status = 'ATIVA' ORDER BY nome LIMIT ?, ?", offset, CONTATOS_POR_PAGINA)
        filtro="on"  

    page_data = {
    "atual":int(pagina),
    "max":int(len(usuarios)/CONTATOS_POR_PAGINA),
    }

    return render_template("usuarios/index.html", usuarios=usuarios, page_data=page_data, filtro=filtro)


@app.route("/usuarios/cadastro", methods=["GET", "POST"])
@login_required
def usuarios_cadastro():
    if request.method == "POST":
        # handles nome input
        nome = request.form.get("nome")
        if not nome:
            flash("Nome necessário", "danger")
            return redirect("/usuarios")
        
        # handles cpf input
        cpf = request.form.get('cpf').replace("-", "").replace(".", "")
        if len(cpf) != 11:
            flash("Formato de CPF inválido", "danger")
            return redirect("/usuarios")
        try:
            int(cpf)
        except ValueError:
            flash("Formato de CPF inválido", 'danger')
            return redirect("/usuarios")

        consulta_cpf = db.execute(
        "SELECT * FROM contatos WHERE cpf = ?", cpf
        )
        if len(consulta_cpf) != 0:
            flash("Esse CPF já está cadastrado", 'danger')
            return redirect("/usuarios")
        
        telefone = request.form.get('telefone').replace("-", "").replace("(", "").replace(")", "")
        email = request.form.get('e-mail')
        endereço = request.form.get('endereço')

        # com tudo validado, insere linha no banco de dados
        db.execute("INSERT INTO contatos (nome, cpf, telefone, email, endereço) VALUES (?, ?, ?, ?, ?)", nome, cpf, telefone, email, endereço)

        if request.form.get("cadastrar-assinante") == "on":
            fazer_assinatura(cpf, request.form.get("plano"), request.form.get("prazo"))
            db.execute('INSERT INTO historico (data, contato_cpf, operacao) VALUES(?, ?, "NOVA ASSINATURA")', HOJE.isoformat(), cpf)
        
        flash("Usuário cadastrado com sucesso!", "success")
        return redirect('/')
    else:
        prazo_default = HOJE + timedelta(days=PRAZO_ASSINATURA_DEFAULT)
        return render_template("usuarios/cadastro.html", hoje=HOJE.isoformat(), prazo_default=prazo_default, plano_default=PLANO_ASSINATURA_DEFAULT)


@app.route("/usuarios/detalhes", methods=["POST", "GET"])
@login_required
def usuarios_detalhes():
    if request.method == "POST":
        # FAZER EXCLUSÃO DO CONTATO DO DB
        if deletar_cpf := request.form.get("delete-id"):
            db.execute("DELETE FROM emprestimos WHERE contato_cpf = ?", deletar_cpf)
            db.execute("DELETE FROM assinaturas WHERE contato_cpf = ?", deletar_cpf)
            db.execute("DELETE FROM contatos WHERE cpf = ?", deletar_cpf)
            
            flash("Usuário deletado do banco de dados", "success")
            return redirect("/usuarios")

        # FAZER EDIÇÃO DO CONTATO
        nome = request.form.get("nome")
        cpf = request.form.get("cpf")
        telefone = request.form.get("telefone")
        endereço = request.form.get("endereço")
        email = request.form.get("email")

        if nome and cpf:
            db.execute("UPDATE contatos SET nome = ?, cpf = ?, telefone = ?, endereço= ?, email = ? WHERE cpf = ?", nome, cpf, telefone, endereço, email, cpf)
            flash("Contato editado com sucesso", "success")
            return redirect("/usuarios")
        else:
            flash("Erro", "danger")
            return redirect("/usuarios")


    # MÉTODO GET
    else:
        if user_cpf := request.args.get("detalhar"):
            contato = db.execute("SELECT * FROM contatos WHERE cpf = ?", user_cpf)[0]
            emprestimos = db.execute(
                        "SELECT emprestimos.id, emprestimos.obra_id, emprestimos.contato_cpf,\
                        emprestimos.prazo, emprestimos.data,\
                        acervo.titulo, acervo.autor, acervo.editora, acervo.ano, acervo.status\
                        FROM emprestimos JOIN acervo ON emprestimos.obra_id = acervo.id\
                    WHERE emprestimos.contato_cpf = ?", user_cpf)
            
            for row in emprestimos:
                if HOJE > date.fromisoformat(row["prazo"]):
                    row["atrasado"] = "true"
                else:
                    row["atrasado"] = "false"
            
            assinaturas = db.execute("SELECT * FROM assinaturas WHERE contato_cpf = ? ORDER BY prazo DESC LIMIT 10", user_cpf)

            prazo_default = HOJE + timedelta(days=PRAZO_ASSINATURA_DEFAULT)
        else:
            flash("Usuário não encontrado", "danger")
            return redirect("/")
        
        return render_template("usuarios/detalhes.html", contato=contato, emprestimos=emprestimos, hoje=HOJE.isoformat(), prazo_default=prazo_default, plano_default=PLANO_ASSINATURA_DEFAULT, assinaturas=assinaturas)

# FUNÇÕES
def fazer_emprestimo(id, cpf, prazo):
    if validate_iso(prazo) == True:
        db.execute("INSERT INTO emprestimos (obra_id, contato_cpf, data, prazo) VALUES (?, ?, ?, ?)", id, cpf, HOJE.isoformat(), prazo)
        db.execute("UPDATE acervo SET status = 'EMPRESTADO' WHERE id = ?", id)
        return True


def fazer_assinatura(cpf, plano, prazo):
    if validate_iso(prazo) == True:
        if len(db.execute("SELECT * FROM assinaturas WHERE contato_cpf = ? AND status = 'ATIVA'", cpf)) == 0:
            db.execute("INSERT INTO assinaturas (contato_cpf, data, plano, prazo, status) VALUES (?, ?, ?, ?, 'ATIVA')", cpf, HOJE.isoformat(), plano, prazo)
            return True
        else:
            flash("O usuário já possui uma assinatura ativa.", "danger")
            return redirect("/")


def validate_iso(prazo):
    try:
        date.fromisoformat(prazo)
    except ValueError:
        flash("Formato inválido. Utilize: AAAA-MM-DD.", "danger")
        return redirect("/")
    else:
        return True


if __name__ == '__main__':
    app.run(debug=False, port=port)

