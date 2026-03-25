from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'User'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False) # admin, company, student
    is_approved = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Company(db.Model):
    __tablename__ = 'Company'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    company_name = db.Column(db.String(80), nullable=False)
    hr_contact = db.Column(db.String(80), nullable=False)
    website = db.Column(db.String(80))
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    # Relationship: If company is deleted, delete its drives
    drives = db.relationship('Placement_Drive', backref='employer', cascade="all, delete-orphan", lazy=True)

class Student(db.Model):
    __tablename__ = 'Student'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    full_name = db.Column(db.String(80), nullable=False)
    roll_no = db.Column(db.String(80), unique=True, nullable=False)
    cgpa = db.Column(db.Float, nullable=False)
    resume_path = db.Column(db.String(120))
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    # Relationship: If student is deleted, delete their applications
    applications = db.relationship('Application', backref='applicant', cascade="all, delete-orphan", lazy=True)

class Placement_Drive(db.Model):
    __tablename__ = 'Placement_Drive'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('Company.id'), nullable=False)
    job_title = db.Column(db.String(80), nullable=False)
    job_description = db.Column(db.Text, nullable=False)
    eligibility_criteria = db.Column(db.String(200))
    application_deadline = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Pending')

    # Relationship: If drive is deleted, delete associated applications
    applications = db.relationship('Application', backref='drive', cascade="all, delete-orphan", lazy=True)

class Application(db.Model):
    __tablename__ = 'Application'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('Student.id'), nullable=False)
    drive_id = db.Column(db.Integer, db.ForeignKey('Placement_Drive.id'), nullable=False)
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)
    application_status = db.Column(db.String(20), default='Applied')
    
    # Unique constraint to prevent duplicate applications
    __table_args__ = (db.UniqueConstraint('student_id', 'drive_id', name='_student_drive_uc'),)