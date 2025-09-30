from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    
    
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        note_text = request.form["note"]
        new_note = Note(content=note_text)
        db.session.add(new_note)
        db.session.commit()
        return redirect(url_for("index"))

    notes = Note.query.all()
    return render_template("index.html", notes=notes)

@app.route("/summarize/<int:note_id>")
def summarize(note_id):
    note = Note.query.get(note_id)
    if note:
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel("models/gemini-1.5-flash")
            response = model.generate_content([f"Tóm tắt ghi chú này: {note.content}"])
            note.summary = response.text.strip()
        except Exception as e:
            note.summary = f"Lỗi AI: {str(e)}"
        db.session.commit()
    return redirect(url_for("index"))

@app.route("/delete/<int:note_id>", methods=["POST"])
def delete_note(note_id):
    note = Note.query.get(note_id)
    if note:
        db.session.delete(note)
        db.session.commit()
    return redirect(url_for("index"))

@app.route("/edit/<int:note_id>", methods=["GET", "POST"])
def edit_note(note_id):
    note = Note.query.get(note_id)
    if request.method == "POST":
        note.content = request.form["note"]
        db.session.commit()
        return redirect(url_for("index"))
    return render_template("edit.html", note=note)

if __name__ == "__main__":
    with app.app_context():
        db.create_all() 
    app.run(debug=True)


