import vk_api
import smtplib
import time, random, string, os
from datetime import datetime
from flask import Blueprint, request, jsonify, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_cors import CORS
from .models import db, User, Project, StudyGroup, Report, ProjectType, UserStatus, Application, ApplicationStatus, ProjectStatus
from . import db, login_manager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

main = Blueprint('main', __name__)
CORS(main)

vk_session = vk_api.VkApi(token='')  # Введите токен

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@main.route('/')
def index():
    projects = Project.query.all()
    projects_data = [{
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "status": p.status
    } for p in projects]
    return jsonify(projects=projects_data), 200

@main.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    full_name = data.get('full_name')
    group_id = int(data.get('group'))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return {"error": "Этот email уже используется"}, 400

    hashed_password = generate_password_hash(password, method='sha256')
    user = User(full_name=full_name, email=email, password=hashed_password, group_id=group_id)

    db.session.add(user)
    db.session.commit()

    return {"message": "Пользователь зарегистрирован"}, 201

@main.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = User.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        login_user(user)
        return {"message": "Успешный вход", "user_id": user.id}, 200
    return {"error": "Неправильная почта или пароль"}, 401

@main.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return {"message": "Успешный выход"}, 200

@main.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    user = current_user
    applications = Application.query.filter_by(user_id=user.id).all()
    projects = [Project.query.get(application.project_id) for application in applications]

    applications_data = [{"id": a.id, "project_id": a.project_id, "status": a.status} for a in applications]
    projects_data = [{
        "id": p.id, 
        "title": p.title, 
        "description": p.description, 
        "status": p.status
    } for p in projects]

    user_data = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role
    }

    return jsonify({
        "user": user_data,
        "projects": projects_data,
        "applications": applications_data
    }), 200

@main.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    project_type = data.get('project_type')
    problem = data.get('problem')
    max_participants = data.get('max_participants')
    solution = data.get('solution')
    target_groups = data.get('target_groups')
    mentors = data.get('mentors')
    status = project_status_user[current_user.status.name]

    project = Project(
        title=title,
        description=description,
        max_participants=max_participants,
        project_type=project_type,
        problem=problem,
        solution=solution,
        status=status
    )

    db.session.add(project)
    db.session.commit()

    for group_id in target_groups:
        group = StudyGroup.query.get(group_id)
        if group:
            project.target_groups.append(group)

    for mentor_id in mentors:
        mentor = User.query.get(mentor_id)
        if mentor:
            project.mentors.append(mentor)

    project.manager_id = current_user.id
    db.session.commit()

    return jsonify({'message': 'Проект создан', 'project_id': project.id}), 201

@main.route('/project/<int:project_id>', methods=['GET'])
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    application = Application.query.filter_by(user_id=current_user.id, project_id=project.id).first()
    reports = Report.query.filter_by(project_id=project_id).all()

    project_data = {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "status": project.status,
        "reports": [{"id": r.id, "file": r.file, "date": r.date} for r in reports]
    }
    application_data = {
        "id": application.id,
        "status": application.status
    } if application else None

    return jsonify({"project": project_data, "application": application_data}), 200

# Удаление заявки
@main.route('/delete_application/<int:application_id>', methods=['DELETE'])
@login_required
def delete_application(application_id):
    application = Application.query.get_or_404(application_id)

    if application.user_id != current_user.id:
        abort(403)

    db.session.delete(application)
    db.session.commit()
    return {"message": "Заявка удалена"}, 200

# Обработка заявки
@main.route('/application/<int:application_id>/process', methods=['POST'])
@login_required
def process_application(application_id):
    application = Application.query.get_or_404(application_id)
    project_id = application.project_id
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.manager_id and current_user not in project.mentors:
        abort(403)

    data = request.get_json()
    action = data.get('action')
    project_url = f'/api/project/{project.id}'

    if action == 'approve':
        application.status = ApplicationStatus.accepted
        db.session.commit()
        send_notification(application.user.email, application.user.vk_profile,
                          f"Ваша заявка на проект {project.title} была подтверждена. Ссылка на проект: {project_url}")
        accepted_applications_count = Application.query.filter_by(project_id=project.id, status=ApplicationStatus.accepted).count()
        if accepted_applications_count >= project.max_participants:
            project.status = ProjectStatus.closed_recruitment
            db.session.commit()
    elif action == 'reject':
        application.status = ApplicationStatus.rejected
        db.session.commit()
        send_notification(application.user.email, application.user.vk_profile,
                          f"Ваша заявка на проект {project.title} была отклонена. Ссылка на проект: {project_url}")

    return {"message": f"Заявка {action}"}, 200

def save_photo(photo):
    directory = os.path.join(os.path.dirname(__file__), 'static', 'photos')
    if not os.path.exists(directory):
        os.makedirs(directory)

    filename = generate_unique_filename()
    filepath = os.path.join(directory, filename)

    photo.save(filepath)

    photo_url = '/static/photos/' + filename
    return photo_url

def save_report(file):
    filename = secure_filename(file.filename)
    directory = os.path.join(os.path.dirname(__file__), 'static', 'reports')
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, filename)
    file.save(file_path)
    return filename

def generate_unique_filename():
    timestamp = str(int(time.time()))  
    random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=8))  
    filename = timestamp + '_' + random_string + '.jpg'  
    return filename

#Сделать Уведомления
def send_notification(email, vk_profile, message):
    send_email(email, "Уведомление с сайта ОПД", message)
    send_vk_message(vk_session, vk_profile, message)

def send_vk_message(vk_session, user_id, message):
    try:
        vk = vk_session.get_api()
        vk.messages.send(user_id=user_id, message=message, random_id=0)
    except Exception as e:
        print(f"Error sending VK message to {user_id}: {e}")

def notify_project_changes(project):

    project_url = url_for('main.project_detail', project_id=project.id, _external=True)
    message = f"Проект '{project.title}' был обновлен. Подробности: {project_url}"

    participants = User.query.join(Application).filter(Application.project_id == project.id).all()

    for user in participants:
        send_notification(user.email, user.vk_profile, message)

    for mentor in project.mentors:
        send_notification(mentor.email, mentor.vk_profile, message)

def notify_project_change(project, status):
    project_url = url_for('main.project_detail', project_id=project.id, _external=True)
    message = f"Статус проекта '{project.title}' был изменён на '{status}'. Ссылка на проект: {project_url}"

    send_notification(project.manager.email, project.manager.vk_profile, message)

    for mentor in project.mentors:
        send_notification(mentor.email, mentor.vk_profile, message)

def notify_mentors_about_report(project, student):
    project_url = url_for('main.project_detail', project_id=project.id, _external=True)
    message = f"Студент {student.full_name} добавил новый отчёт к проекту '{project.title}'. Ссылка на проект: {project_url}"

    for mentor in project.mentors:
        send_notification(mentor.email, mentor.vk_profile, message)

def send_email(email, subject, message):
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        smtp_user = ""  #  email с которого отсылать письмо
        smtp_password = " "  # пароль приложения, а не обычный пароль от Gmail!!!!! https://seatable.io/ru/docs/integrationen-innerhalb-von-seatable/gmail-fuer-den-versand-von-e-mails-per-smtp-einrichten/

        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {email}")

    except Exception as e:
        print(f"Error sending email to {email}: {e}")


project_status_user = {
    'teacher' : "open_recruitment",
    'admin' : "open_recruitment",
    'mentor' : "not_confirmed"
}