from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from textwrap import wrap
import os
import google.generativeai as genai

app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        note_text = request.form["note"]
        new_note = Note(content=note_text)
        db.session.add(new_note)
        db.session.commit()
        return redirect(url_for("index"))

    notes = Note.query.all()
    return render_template("index.html", notes=notes)


@app.route("/summarize/<int:note_id>", methods=["POST"])
@login_required
def summarize(note_id):
    note = Note.query.get(note_id)
    if note:
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model_name = os.getenv("GEMINI_MODEL", "models/gemini-pro-latest")
            models = genai.list_models()  # optional debug
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([f"Tóm tắt ghi chú này: {note.content}"])
            note.summary = getattr(response, "text", str(response)).strip()
        except Exception as e:
            note.summary = f"Lỗi AI: {str(e)}"
        db.session.commit()
    return redirect(url_for("index"))


@app.route("/delete/<int:note_id>", methods=["POST"])
@login_required
def delete_note(note_id):
    note = Note.query.get(note_id)
    if note:
        db.session.delete(note)
        db.session.commit()
    return redirect(url_for("index"))


@app.route("/edit/<int:note_id>", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    note = Note.query.get(note_id)
    if request.method == "POST":
        note.content = request.form["note"]
        db.session.commit()
        return redirect(url_for("index"))
    return render_template("edit.html", note=note)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))
        return render_template("login.html", error="Tên đăng nhập hoặc mật khẩu không đúng")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            return render_template("register.html", error="Vui lòng nhập username và password")
        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Tên tài khoản đã tồn tại")
        u = User(username=username)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        login_user(u)
        return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/export_pdf")
@login_required
def export_pdf():
    notes = Note.query.order_by(Note.id).all()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    x_margin = 40
    y = height - 40
    line_height = 14

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x_margin, y, "Notes Export")
    y -= 30
    c.setFont("Helvetica", 11)

    for note in notes:
        if y < 80:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 11)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_margin, y, f"Note #{note.id}")
        y -= line_height
        c.setFont("Helvetica", 10)
        for line in wrap(note.content, 90):
            c.drawString(x_margin, y, line)
            y -= line_height
            if y < 80:
                c.showPage()
                y = height - 40
                c.setFont("Helvetica", 10)
        if note.summary:
            y -= 6
            c.setFont("Helvetica-Oblique", 10)
            for line in wrap("Tóm tắt: " + note.summary, 90):
                c.drawString(x_margin + 10, y, line)
                y -= line_height
                if y < 80:
                    c.showPage()
                    y = height - 40
                    c.setFont("Helvetica-Oblique", 10)
        y -= 12

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="notes_export.pdf", mimetype="application/pdf")


@app.route("/models")
def list_models():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    models = genai.list_models()
    model_names = [m.name for m in models]
    return "<br>".join(model_names)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not User.query.first():
            u = User(username="admin")
            u.set_password("password")
            db.session.add(u)
            db.session.commit()
    app.run(debug=True)




