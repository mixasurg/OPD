from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request
from .models import db, User, Project, StudyGroup, Report, ProjectType, UserStatus, Application, ApplicationStatus, ProjectStatus
from flask_login import login_user, logout_user, login_required, current_user
from . import db, login_manager
import time, random, string, os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import vk_api


main = Blueprint('main', __name__)

vk_session = vk_api.VkApi(token='') ##Ввести токен!!!!

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@main.route('/')
def index():
    projects = Project.query.all()
    
    return render_template('index.html', projects = projects)

@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password'] 
        full_name = request.form['full_name']
        group_id = int(request.form.get('group'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return 'Этот email уже используется. Пожалуйста, выберите другой.'
        
        hashed_password = generate_password_hash(password, method='sha256')

        user = User(full_name=full_name, email=email, password=hashed_password, group_id = group_id)

        db.session.add(user)
        db.session.commit()

        return redirect(url_for('main.index'))
    
    StudyGroups = StudyGroup.query.all()
    return render_template('register.html', groups=StudyGroups)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password'] 
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('main.index'))
        else:
            return 'Неправильная почта или пароль'
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main.route('/dashboard')
@login_required
def dashboard():
    user = current_user

    applications = Application.query.filter_by(user_id=user.id).all()
    projects = [Project.query.get(application.project_id) for application in applications]
    return render_template('cabinet.html',  user=user, projects=projects, applications=applications)

@main.route('/student/<int:student_id>')
@login_required
def student_profile(student_id):
    student = User.query.get_or_404(student_id)
    if student.status != UserStatus.student:
        abort(403)  
    
    applications = Application.query.filter_by(user_id=student.id).all()
    projects = [Project.query.get(application.project_id) for application in applications]
    
    return render_template('student_cabinet.html', student=student, projects=projects)

@main.route('/create_project', methods=['GET', 'POST'])
@login_required
def create_project():

    if request.method == 'POST':
        title = request.form['title']
        
        description = request.form['description']
        poster = request.files['poster']
        photo_url = save_photo(poster)
        
        project_type = request.form['project_type']
        problem = request.form['problem']
        max_participants = request.form['max_participants']
        solution = request.form['solution']
        status = project_status_user[current_user.status.name]
        target_groups = request.form.getlist('target_groups')
        mentors = request.form.getlist('mentors')
        project = Project(title=title, description=description, max_participants=max_participants, project_type = project_type, problem=problem, solution = solution, status=status, poster=photo_url)
        
        db.session.add(project)
        db.session.commit()
        for group_id in target_groups:
            group = StudyGroup.query.get(group_id)
            project.target_groups.append(group)
        
        for mentor_id in mentors:
            mentor = User.query.get(mentor_id)
            project.mentors.append(mentor)

        project.manager_id = current_user.id
        db.session.commit()
        return redirect(url_for('main.index'))
    else:
        mentors = User.query.filter_by(status=UserStatus.mentor)
        StudyGroups = StudyGroup.query.all()
        return render_template('create_project.html', groups=StudyGroups, types=ProjectType, mentors=mentors)

@main.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.id != project.manager_id:
        abort(403)
    
    all_groups = StudyGroup.query.all()
    all_mentors = User.query.filter(User.status.in_([UserStatus.teacher, UserStatus.mentor])).all()

    if request.method == 'POST':
        project.title = request.form['title']
        project.description = request.form['description']
        project.problem = request.form['problem']
        project.solution = request.form['solution']
        poster = request.files['poster']
        project.poster = save_photo(poster)
        project.max_participants = request.form['max_participants']
        project.target_groups.clear()

        target_group_ids = request.form.getlist('target_groups')
        project.target_groups = StudyGroup.query.filter(StudyGroup.id.in_(target_group_ids)).all()

        mentor_ids = request.form.getlist('mentors')
        project.mentors = User.query.filter(User.id.in_(mentor_ids)).all()

        db.session.commit()
        notify_project_changes(project)
        return redirect(url_for('main.project_detail', project_id=project.id))
    
    return render_template('edit_project.html', project=project, groups =all_groups, mentors = all_mentors)
 
@main.route('/project/<int:project_id>', methods=['GET', 'POST'])
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    application = Application.query.filter_by(user_id=current_user.id, project_id=project.id).first()
    reports = Report.query.filter_by(project_id=project_id).all()

    if request.method == 'POST':
        if current_user.status == UserStatus.student:
            if application and application.status == ApplicationStatus.accepted:
                if 'report_file' in request.files:
                    report_file = request.files['report_file']
                    if report_file:
                        filename = save_report(report_file)
                        description = request.form.get('description')
                        report = Report(
                            date=datetime.utcnow(),
                            author_id=current_user.id,
                            file=filename,
                            description=description,
                            project_id=project.id
                        )
                        db.session.add(report)
                        db.session.commit()

                        notify_mentors_about_report(project, current_user)

                        return redirect(url_for('main.project_detail', project_id=project.id))
            else:
                application_count = Application.query.filter_by(user_id=current_user.id).count()
                if application_count >= 5:
                    return redirect(url_for('main.project_detail', project_id=project_id))

                existing_application = Application.query.filter_by(user_id=current_user.id, project_id=project_id).first()
                if existing_application:
                    return redirect(url_for('main.project_detail', project_id=project_id))

                priority = request.form['priority']
                new_application = Application(user_id=current_user.id, project_id=project.id, priority=priority)
                db.session.add(new_application)
                db.session.commit()

                return redirect(url_for('main.project_detail', project_id=project_id))

        # Логика для преподавателей и администраторов
        if current_user.status in [UserStatus.teacher, UserStatus.admin]:
            action = request.form.get('action')
            if action == 'approve':
                project.status = ProjectStatus.open_recruitment  
                notify_project_change(project, ProjectStatus.open_recruitment.value)

            elif action == 'reject':
                project.status = ProjectStatus.rejected
                notify_project_change(project, ProjectStatus.rejected.value)

            db.session.commit()
            return redirect(url_for('main.project_detail', project_id=project.id))

    return render_template('project_detail.html', project=project, application=application, reports=reports)

@main.route('/delete_application/<int:application_id>', methods=['POST'])
def delete_application(application_id):
    application = Application.query.get_or_404(application_id)

    if application.user_id != current_user.id:
        return redirect(url_for('main.project_detail', project_id=application.project_id))

    db.session.delete(application)
    db.session.commit()
    return redirect(url_for('main.project_detail', project_id=application.project_id))

@main.route('/application/<int:application_id>/process', methods=['POST'])
@login_required
def process_application(application_id):
    application = Application.query.get_or_404(application_id)
    project_id = application.project_id
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.manager_id and current_user not in project.mentors:
        abort(403)

    action = request.form.get('action')
    project_url = url_for('main.project_detail', project_id=project.id, _external=True)
    
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

    return redirect(url_for('main.project_detail', project_id=project.id))

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
    print('Сообщения для ',email)
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

project_status_user = {
    'teacher' : "open_recruitment",
    'admin' : "open_recruitment",
    'mentor' : "not_confirmed"
}