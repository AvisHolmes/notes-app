from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired
from datetime import datetime
import secrets
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Создаем приложение
app = Flask(__name__)

# СРАЗУ настраиваем всю конфигурацию
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', 'sqlite:///notes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Теперь добавляем middleware для заголовков
@app.after_request
def add_security_headers(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response

# Подключаем базу данных и защиту
db = SQLAlchemy(app)
csrf = CSRFProtect(app)


# Модель для заметок с информацией о владельце
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.String(50), nullable=False)
    
    def is_owner(self, current_user_id):
        """Проверяет, является ли пользователь владельцем заметки"""
        return self.user_id == current_user_id

# Форма для заметок
class NoteForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired()])
    content = TextAreaField('Содержимое', validators=[DataRequired()])
    submit = SubmitField('Сохранить')

# Генерируем уникальный ID для каждой сессии
@app.before_request
def before_request():
    if 'user_id' not in session:
        session['user_id'] = secrets.token_hex(16)

# Главная страница - показываем ВСЕ заметки, но с учетом владельцев
@app.route('/', methods=['GET', 'POST'])
def index():
    form = NoteForm()
    
    if form.validate_on_submit():
        new_note = Note(
            title=form.title.data.strip(),
            content=form.content.data.strip(),
            user_id=session['user_id']
        )
        db.session.add(new_note)
        db.session.commit()
        flash('Заметка добавлена!', 'success')
        return redirect(url_for('index'))
    
    # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: показываем ВСЕ заметки
    all_notes = Note.query.order_by(Note.created_at.desc()).all()
    
    # Считаем статистику для демонстрации
    total_notes = len(all_notes)
    my_notes_count = len([n for n in all_notes if n.user_id == session['user_id']])
    other_notes_count = total_notes - my_notes_count
    
    return render_template('index.html', 
                           form=form, 
                           notes=all_notes,
                           total_notes=total_notes,
                           my_notes_count=my_notes_count,
                           other_notes_count=other_notes_count,
                           current_user_id=session['user_id'])

# Редактирование - строгая проверка владельца
@app.route('/edit/<int:note_id>', methods=['GET', 'POST'])
def edit_note(note_id):
    # Находим заметку
    note = Note.query.get_or_404(note_id)
    
    # КРИТИЧЕСКАЯ ПРОВЕРКА: только владелец может редактировать
    if not note.is_owner(session['user_id']):
        flash(f'ДОСТУП ЗАПРЕЩЁН! Вы не можете редактировать чужую заметку.', 'error')
        return redirect(url_for('index'))
    
    form = NoteForm()
    
    if form.validate_on_submit():
        note.title = form.title.data.strip()
        note.content = form.content.data.strip()
        db.session.commit()
        flash('Заметка успешно обновлена!', 'success')
        return redirect(url_for('index'))
    
    if request.method == 'GET':
        form.title.data = note.title
        form.content.data = note.content
    
    return render_template('edit.html', form=form, note=note)

# Удаление - также только для владельцев
@app.route('/delete/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    
    # КРИТИЧЕСКАЯ ПРОВЕРКА: только владелец может удалить
    if not note.is_owner(session['user_id']):
        flash(f'ДОСТУП ЗАПРЕЩЁН! Вы не можете удалить чужую заметку.', 'error')
        return redirect(url_for('index'))
    
    db.session.delete(note)
    db.session.commit()
    flash('Заметка удалена!', 'success')
    return redirect(url_for('index'))

# Сброс сессии для тестирования разных пользователей
@app.route('/switch_user')
def switch_user():
    old_id = session['user_id']
    session['user_id'] = secrets.token_hex(16)
    flash(f'Сменили пользователя: {old_id} → {session["user_id"]}', 'info')
    return redirect(url_for('index'))

# Запуск приложения
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # ИСПРАВЛЕНИЕ 2: Используем переменную окружения для режима отладки
    debug_mode = os.environ.get('DEBUG_MODE', 'False').lower() == 'true'
    app.run(debug=debug_mode)