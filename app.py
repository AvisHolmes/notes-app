from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, TextAreaField, SubmitField, PasswordField
from wtforms.validators import DataRequired
from datetime import datetime
import secrets
import os
import sqlite3
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# Модель для заметок
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, nullable=True)

# Формы
class NoteForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired()])
    content = TextAreaField('Содержимое', validators=[DataRequired()])
    submit = SubmitField('Сохранить')

class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')

class RegisterForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Зарегистрироваться')

def init_users_table():
    """Создание таблицы users через сырой SQL"""
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    # Добавляем тестовых пользователей
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES ('admin', 'admin123')")
        cursor.execute("INSERT INTO users (username, password) VALUES ('user1', 'password1')")
    except:
        pass
    conn.commit()
    conn.close()

# ============= УЯЗВИМЫЕ ЭНДПОИНТЫ =============

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # УЯЗВИМЫЙ КОД: конкатенация строк в SQL-запросе!
        conn = sqlite3.connect('notes.db')
        cursor = conn.cursor()
        
        sql = f"SELECT id, username, password FROM users WHERE username = '{username}' AND password = '{password}'"
        
        try:
            cursor.execute(sql)
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user[0]
                session['username'] = user[1]
                flash(f'Добро пожаловать в систему, {user[1]}!', 'success')
                conn.close()
                return redirect(url_for('index'))
            else:
                flash('Неверное имя пользователя или пароль!', 'error')
                conn.close()
        except Exception as e:
            flash(f'Ошибка: {str(e)}', 'error')
            conn.close()
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # УЯЗВИМЫЙ КОД: конкатенация строк
        conn = sqlite3.connect('notes.db')
        cursor = conn.cursor()
        
        sql = f"INSERT INTO users (username, password) VALUES ('{username}', '{password}')"
        
        try:
            cursor.execute(sql)
            conn.commit()
            conn.close()
            flash('Регистрация успешна! Теперь войдите.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Ошибка: {str(e)}', 'error')
            conn.close()
    
    return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

# ============= ОСТАЛЬНЫЕ ЭНДПОИНТЫ =============

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    form = NoteForm()
    if form.validate_on_submit():
        new_note = Note(
            title=form.title.data,
            content=form.content.data,
            user_id=session.get('user_id')
        )
        db.session.add(new_note)
        db.session.commit()
        flash('Заметка добавлена!', 'success')
        return redirect(url_for('index'))
    
    notes = Note.query.filter_by(user_id=session.get('user_id')).order_by(Note.created_at.desc()).all()
    return render_template('index.html', form=form, notes=notes, username=session.get('username'))

@app.route('/edit/<int:note_id>', methods=['GET', 'POST'])
def edit_note(note_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    note = Note.query.get_or_404(note_id)
    if note.user_id != session.get('user_id'):
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    
    form = NoteForm()
    if form.validate_on_submit():
        note.title = form.title.data
        note.content = form.content.data
        db.session.commit()
        flash('Заметка обновлена!', 'success')
        return redirect(url_for('index'))
    
    form.title.data = note.title
    form.content.data = note.content
    return render_template('edit.html', form=form, note=note)

@app.route('/delete/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    note = Note.query.get_or_404(note_id)
    if note.user_id != session.get('user_id'):
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    
    db.session.delete(note)
    db.session.commit()
    flash('Заметка удалена!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_users_table()
    app.run(debug=True, port=8080, host='0.0.0.0')
