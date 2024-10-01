from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum
from enum import Enum as PyEnum
from . import db


# Enum для статусов
class UserStatus(PyEnum):
    student = "Студент"
    teacher = "Преподаватель"
    admin = "Администратор"
    mentor = "Ментор"

class ProjectType(PyEnum):
    scientific = "Научный"
    technical = "Технический"
    service = "Сервисный"

class ProjectStatus(PyEnum):
    not_confirmed = "Не подтверждён"
    open_recruitment = "Набор открыт"
    closed_recruitment = "Набор закрыт"
    rejected = "Отклонён"

class ApplicationStatus(PyEnum):
    accepted = "Принято"
    rejected = "Отклонено"
    under_review = "На рассмотрении"

class StudyGroupType(PyEnum):
    B = "Б"
    S = "С"
    M = "М"
    A = "А"
    none = ""

project_target_groups = db.Table('project_target_groups',
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'), primary_key=True),
    db.Column('study_group_id', db.Integer, db.ForeignKey('study_group.id'), primary_key=True)
)

# Модель Учебная группа
class StudyGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    year_of_entry = db.Column(db.Integer, nullable=False)
    is_foreign = db.Column(db.Boolean, default=False)
    type = db.Column(Enum(StudyGroupType), nullable=False)
    #Для вывода {group.name} - {group.type}{group.year_of_entry}
     
# Модель Пользователь
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable = False)
    vk_profile = db.Column(db.String(200), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('study_group.id'), nullable=True)
    group = db.relationship('StudyGroup', backref='users')
    status = db.Column(Enum(UserStatus), default=UserStatus.student, nullable=False)
    competency_profile = db.Column(db.String(500), nullable=True)
    consent_to_share_competency = db.Column(db.Boolean, default=False)
    projects = db.relationship('Project', backref='manager')
    applications = db.relationship('Application', backref='user')
    is_active = db.Column(db.Boolean, default=True)  
    
    def get_id(self):
        return str(self.id)
    
    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True
    

# Модель Проект
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    poster = db.Column(db.String(200), nullable=True)
    project_type = db.Column(Enum(ProjectType), nullable=False)
    max_participants = db.Column(db.Integer, nullable=True)
    target_groups = db.relationship('StudyGroup', secondary=project_target_groups, backref='projects')
    problem = db.Column(db.Text, nullable=False)
    solution = db.Column(db.Text, nullable=False)
    status = db.Column(Enum(ProjectStatus), default=ProjectStatus.not_confirmed, nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    mentors = db.relationship('User', secondary='project_mentors', backref='mentored_projects')
    reports = db.relationship('Report', backref='project')
    confirmed_applications = db.relationship('Application', backref='confirmed_project')

# Связующая таблица для менторов проекта
project_mentors = db.Table('project_mentors',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'), primary_key=True)
)


# Модель Отчёт
class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)

# Модель Заявка
class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    status = db.Column(Enum(ApplicationStatus), default=ApplicationStatus.under_review, nullable=False)
