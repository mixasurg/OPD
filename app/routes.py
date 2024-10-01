from flask import Blueprint, render_template, redirect, url_for, request
from .models import db, User, Project, StudyGroup, ProjectType, UserStatus, Application, ApplicationStatus
from flask_login import login_user, logout_user, login_required, current_user
from . import db, login_manager
import time, random, string, os
from werkzeug.security import generate_password_hash, check_password_hash


main = Blueprint('main', __name__)

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
        password = request.form['password'] # СДЕЛАТЬ ХЭШ
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
        password = request.form['password'] # СДЕЛАТЬ ХЭШ
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
    return render_template('cabinet.html',  user=user)

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
        return redirect(url_for('main.project_detail', project_id=project.id))
    
    return render_template('edit_project.html', project=project, groups =all_groups, mentors = all_mentors)
 
@main.route('/project/<int:project_id>', methods=['GET', 'POST'])
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        if current_user.status == UserStatus.student:
            application_count = Application.query.filter_by(user_id=current_user.id).count()
            if application_count >= 5:
                return redirect(url_for('main.project_detail', project_id=project_id))

            existing_application = Application.query.filter_by(user_id=current_user.id, project_id=project_id).first()
            if existing_application:
                return redirect(url_for('main.project_detail', project_id=project_id))

            priority = request.form['priority']
            new_application = Application(user_id=current_user.id, project_id=project.id, priority = priority)
            db.session.add(new_application)
            db.session.commit()
            return redirect(url_for('main.project_detail', project_id=project_id))
    application = Application.query.filter_by(user_id=current_user.id, project_id=project.id).first()
    return render_template('project_detail.html', project=project, application=application)

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
    if action == 'approve':
        application.status = ApplicationStatus.accepted
        db.session.commit()
        send_notification(application.user.email, 'Заявка подтверждена', 'Ваша заявка на проект {} была подтверждена.'.format(project.title))
    elif action == 'reject':
        application.status = ApplicationStatus.rejected
        db.session.commit()
        send_notification(application.user.email, 'Заявка отклонена', 'Ваша заявка на проект {} была отклонена.'.format(project.title))

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

def generate_unique_filename():
    timestamp = str(int(time.time()))  
    random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=8))  
    filename = timestamp + '_' + random_string + '.jpg'  
    return filename

#Сделать Уведомления
def send_notification(email):
    print('Сообщения для ',email)

project_status_user = {
    'teacher' : "open_recruitment",
    'admin' : "open_recruitment",
    'mentor' : "not_confirmed"
}