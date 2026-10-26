from models import db,User , Company , Student , Placement_Drive , Application
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
import click
import os
import uuid

# Initialize Flask app and database
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///placement_portal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False    
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['RESUME_UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'resumes')


db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) 


@app.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(error):
    if request.endpoint == 'apply_drive' and request.view_args:
        flash('The resume must be 5 MB or smaller.', 'danger')
        return redirect(url_for('apply_drive', drive_id=request.view_args['drive_id']))
    return 'The uploaded file exceeds the 5 MB limit.', 413


# routes

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        user_id = user.id if user else None
        if user and user.check_password(password):
            if user.is_approved == True:
                login_user(user)
                flash('Logged in successfully.', 'success')
                
                if user.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user.role == 'company': 
                    Com=Company.query.filter_by(user_id=user_id).first()
                    if Com.is_blacklisted:
                        flash('Your company is blacklisted. Contact admin for more info.', 'danger')
                        logout_user()
                        return redirect(url_for('login'))
                    return redirect(url_for('company_dashboard'))
                elif user.role == 'student':
                    Stu=Student.query.filter_by(user_id=user_id).first()
                    if Stu.is_blacklisted:
                        flash('Your account is blacklisted. Contact admin for more info.', 'danger')
                        logout_user()
                        return redirect(url_for('login'))
                    return redirect(url_for('student_dashboard'))
                
            else:
                flash('Your account is pending approval.', 'warning')
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Route to choose between Student and Company
@app.route('/register')
def register_choice():
    return render_template('register_choice.html')

# Student Registration
@app.route('/register/student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register_student'))

        try:
            new_user = User(username=username, role='student', is_approved=True)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            new_profile = Student(
                user_id=new_user.id,
                full_name=request.form.get('full_name'),
                roll_no=request.form.get('roll_no'),
                cgpa=request.form.get('cgpa', 0)
            )
            if new_profile.roll_no and Student.query.filter_by(roll_no=new_profile.roll_no).first():
                flash('Roll number already exists.', 'danger')
                db.session.rollback()
                return redirect(url_for('register_student'))
            
            db.session.add(new_profile)
            db.session.commit()
            flash('Student registered successfully! You can now login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
            
    return render_template('register_student.html')

# Company Registration
@app.route('/register/company', methods=['GET', 'POST'])
def register_company():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register_company'))

        try:
            new_user = User(username=username, role='company', is_approved=False)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            new_profile = Company(
                user_id=new_user.id,
                company_name=request.form.get('company_name'),
                hr_contact=request.form.get('hr_contact'),
                website=request.form.get('website', '')
            )
            db.session.add(new_profile)
            db.session.commit()
            flash('Company registered. Please wait for Admin approval.', 'info')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
            
    return render_template('register_company.html')

# Admin Routes

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('home'))

    # --- 1. UNIVERSAL SEARCH LOGIC ---
    search_query = request.args.get('search_query', '').strip()
    
    searched_students = []
    searched_companies = []

    if search_query:
        # Search Students (Name or Roll No)
        searched_students = Student.query.filter(
            or_(Student.full_name.ilike(f'%{search_query}%'), 
                Student.roll_no.ilike(f'%{search_query}%'))
        ).all()
        
        # Search Companies (Name)
        searched_companies = Company.query.filter(
            Company.company_name.ilike(f'%{search_query}%')
        ).all()

    # --- 2. THE SUMMARY STATS ---
    stats = {
        'total_students': Student.query.count(),
        'total_companies': Company.query.count(),
        'total_drives': Placement_Drive.query.count(),
        'total_apps': Application.query.count(),
        'total_selected': Application.query.filter_by(application_status='Selected').count() # New stat
    }

    # --- 3. THE MANAGEMENT LISTS ---
    # Pending
    pending_companies = Company.query.join(User).filter(User.is_approved == False, Company.is_blacklisted == False).all()
    pending_drives = Placement_Drive.query.filter_by(status='Pending').all()

    # Active (Approved and NOT Blacklisted)
    active_students = Student.query.filter_by(is_blacklisted=False).all()
    active_companies = Company.query.join(User).filter(User.is_approved == True, Company.is_blacklisted == False).all()

    # Blacklisted (The section you requested)
    blacklisted_students = Student.query.filter_by(is_blacklisted=True).all()
    blacklisted_companies = Company.query.filter_by(is_blacklisted=True).all()

    # Active Drives and Applications (Approved and NOT Blacklisted)
    active_drives = Placement_Drive.query.join(Company).join(User).filter(
        Placement_Drive.status == 'Approved',
        Company.is_blacklisted == False,
        User.is_approved == True
    ).all()
    applications = Application.query.join(Placement_Drive).join(Company).join(User).filter(
        Placement_Drive.status == 'Approved',
        Company.is_blacklisted == False,
        User.is_approved == True
    ).all()
    

    return render_template('admin_dashboard.html', 
                           stats=stats,
                           search_query=search_query,
                           searched_students=searched_students,
                           searched_companies=searched_companies,
                           pending_companies=pending_companies,
                           pending_drives=pending_drives,
                           active_students=active_students, 
                           active_companies=active_companies,
                           blacklisted_students=blacklisted_students,
                           blacklisted_companies=blacklisted_companies,
                           active_drives=active_drives,
                           applications=applications)

@app.route('/blacklist/<string:role>/<int:id>')
@login_required
def blacklist(role, id):
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    if role == 'student':
        student = Student.query.get_or_404(id)
        student.is_blacklisted = True
        db.session.commit()
        flash(f'Student {student.full_name} has been blacklisted.', 'warning')
    elif role == 'company':
        company = Company.query.get_or_404(id)
        company.is_blacklisted = True
        db.session.commit()
        flash(f'Company {company.company_name} has been blacklisted.', 'warning')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/unblacklist/<string:role>/<int:id>')
@login_required
def unblacklist(role, id):
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    if role == 'student':
        student = Student.query.get_or_404(id)
        student.is_blacklisted = False
        db.session.commit()
        flash(f'Student {student.full_name} has been unblacklisted.', 'success')
    elif role == 'company':
        company = Company.query.get_or_404(id)
        company.is_blacklisted = False
        db.session.commit()
        flash(f'Company {company.company_name} has been unblacklisted.', 'success')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_company/<int:user_id>')
@login_required
def approve_company(user_id):
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash('Company has been approved.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/view_drive/<int:drive_id>')
@login_required
def view_drive(drive_id):
    if current_user.role != 'admin': return redirect(url_for('home'))

    drive = Placement_Drive.query.get_or_404(drive_id)
    return render_template('view_drive.html', drive=drive)


@app.route('/admin/manage_drive/<int:drive_id>/<string:action>')
@login_required
def manage_drive(drive_id, action):
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    drive = Placement_Drive.query.get_or_404(drive_id)
    if action == 'approve':
        drive.status = 'Approved'
    else:
        drive.status = 'Rejected'
    
    db.session.commit()
    flash(f'Drive status updated to {action}.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/review_student/<int:id>') # The URL path
@login_required
def review_student(id): # This function name MUST match the url_for string
    if current_user.role not in ['admin', 'company']:
        return redirect(url_for('home'))
    
    student = Student.query.get_or_404(id)
    if current_user.role == 'company':
        company = Company.query.filter_by(user_id=current_user.id).first()
        if not company or not Application.query.join(Placement_Drive).filter(
            Application.student_id == student.id,
            Placement_Drive.company_id == company.id,
        ).first():
            flash('You are not authorized to review this student.', 'danger')
            return redirect(url_for('company_dashboard'))

    return render_template('review_student.html', student=student)



# Company Routes

@app.route('/company/dashboard')
@login_required
def company_dashboard():
    if current_user.role != 'company':
        return redirect(url_for('home'))
    
    company = Company.query.filter_by(user_id=current_user.id).first()
    drives = Placement_Drive.query.filter_by(company_id=company.id).all()


    return render_template('company_dashboard.html', company=company, drives=drives)

@app.route('/company/create_drive', methods=['GET', 'POST'])
@login_required
def create_drive():
    if current_user.role != 'company':
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        company = Company.query.filter_by(user_id=current_user.id).first()
        new_drive = Placement_Drive(
            company_id=company.id,
            job_title=request.form['job_title'],
            job_description=request.form['job_description'],
            eligibility_criteria=request.form['eligibility_criteria'],
            application_deadline = datetime.strptime(request.form['application_deadline'], '%Y-%m-%d').date()
        )
        db.session.add(new_drive)
        db.session.commit()
        flash('Placement drive created successfully!', 'success')
        return redirect(url_for('company_dashboard'))
    
    return render_template('create_drive.html')

@app.route('/company/view_applications/<int:drive_id>')
@login_required
def view_application(drive_id):
    if current_user.role != 'company':
        return redirect(url_for('home'))
    drive = Placement_Drive.query.get_or_404(drive_id)
    if drive.employer.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('company_dashboard'))
    applications = Application.query.filter_by(drive_id=drive_id).all()
    return render_template('view_applications.html', applications=applications, drive=drive)

@app.route('/company/update_application/<int:app_id>/<string:status>')
@login_required
def update_application(app_id, status):
    if current_user.role != 'company':
        return redirect(url_for('home'))
    
    application = Application.query.get_or_404(app_id)
    
    # Security Check: Ensure this company owns the drive
    drive = application.drive
    if drive.employer.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('company_dashboard'))
    
    # FIX: Update 'application_status' (the actual DB column name)
    if status == 'Shortlisted':
        application.application_status = 'Shortlisted' # Match the name in the template
    
    elif status == 'Selected':
        application.application_status = 'Selected'
        # Optional: Mark student as placed if you added that field
        # application.applicant.is_placed = True
    
    elif status == 'Rejected':
        application.application_status = 'Rejected'
    
    try:
        db.session.commit()
        flash(f'Application status updated to {application.application_status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error occurred.', 'danger')
        
    return redirect(url_for('view_application', drive_id=drive.id))

@app.route('/review_company/<int:id>')
@login_required
def review_company(id):
    # Ensure current user is an admin
    if current_user.role != 'admin':
        return redirect(url_for('home'))
        
    company = Company.query.get_or_404(id)
    # Get all drives where company_id matches
    company_drives = Placement_Drive.query.filter_by(company_id=company.id).all()
    
    return render_template('review_company.html', 
                           company=company, 
                           company_drives=company_drives)

@app.route('/company/edit_drive/<int:drive_id>', methods=['GET', 'POST'])
@login_required
def edit_drive(drive_id):
    if current_user.role != 'company':
        return redirect(url_for('home'))
    
    drive = Placement_Drive.query.get_or_404(drive_id)
    if drive.employer.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('company_dashboard'))
    
    if request.method == 'POST':
        drive.job_title = request.form['job_title']
        drive.job_description = request.form['job_description']
        drive.eligibility_criteria = request.form['eligibility_criteria']
        drive.application_deadline = datetime.strptime(request.form['application_deadline'], '%Y-%m-%d').date()
        
        try:
            db.session.commit()
            flash('Drive updated successfully!', 'success')
            return redirect(url_for('company_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating drive. Please try again.', 'danger')

    return render_template('edit_drive.html', drive=drive)
#Student Routes


@app.route('/student_dashboard')
@login_required
def student_dashboard():
    student = Student.query.filter_by(user_id=current_user.id).first()
    # Fetch all applications for this student
    applications = Application.query.filter_by(student_id=student.id).all()
    
    # Existing logic to hide applied drives
    applied_ids = [a.drive_id for a in applications]
    drives = Placement_Drive.query.filter(
        Placement_Drive.status == 'Approved',
        ~Placement_Drive.id.in_(applied_ids) if applied_ids else True
    ).all()

    return render_template('student_dashboard.html', 
                           student=student, 
                           drives=drives, 
                           applications=applications)


@app.route('/student/apply/<int:drive_id>', methods=['GET', 'POST'])
@login_required
def apply_drive(drive_id):
    if current_user.role != 'student':
        return redirect(url_for('home'))
    
    student = Student.query.filter_by(user_id=current_user.id).first()
    if student is None:
        flash('Your student profile could not be found.', 'danger')
        return redirect(url_for('home'))

    drive = Placement_Drive.query.get_or_404(drive_id)

    if drive.application_deadline < datetime.today().date() or drive.status != 'Approved':
        flash('This drive is not accepting applications.', 'warning')
        return redirect(url_for('student_dashboard'))

    existing_application = Application.query.filter_by(student_id=student.id, drive_id=drive_id).first()
    if existing_application:
        flash('You have already applied for this drive.', 'info')
        return redirect(url_for('student_dashboard'))

    resume_available = bool(
        student.resume_path
        and os.path.isfile(os.path.join(app.config['RESUME_UPLOAD_FOLDER'], student.resume_path))
    )

    if request.method == 'POST':
        if request.form.get('confirm_profile') != 'yes':
            flash('Please confirm your profile details before applying.', 'danger')
            return render_template(
                'apply_preview.html',
                student=student,
                drive=drive,
                resume_available=resume_available,
            )

        resume = request.files.get('resume')
        has_new_resume = resume is not None and bool(resume.filename)
        new_resume_filename = None

        if has_new_resume:
            safe_original_name = secure_filename(resume.filename)
            if not safe_original_name.lower().endswith('.pdf'):
                flash('Please upload your resume as a PDF file.', 'danger')
                return render_template(
                    'apply_preview.html',
                    student=student,
                    drive=drive,
                    resume_available=resume_available,
                )

            if resume.stream.read(5) != b'%PDF-':
                flash('The selected file does not appear to be a valid PDF.', 'danger')
                return render_template(
                    'apply_preview.html',
                    student=student,
                    drive=drive,
                    resume_available=resume_available,
                )
            resume.stream.seek(0)
            new_resume_filename = f'{uuid.uuid4().hex}.pdf'
        elif not resume_available:
            flash('Upload a PDF resume before submitting your application.', 'danger')
            return render_template(
                'apply_preview.html',
                student=student,
                drive=drive,
                resume_available=resume_available,
            )

        resume_folder = app.config['RESUME_UPLOAD_FOLDER']
        saved_resume_path = None
        if new_resume_filename:
            os.makedirs(resume_folder, exist_ok=True)
            saved_resume_path = os.path.join(resume_folder, new_resume_filename)
            resume.save(saved_resume_path)

        if saved_resume_path:
            student.resume_path = new_resume_filename
        db.session.add(Application(
            student_id=student.id,
            drive_id=drive_id,
            application_status='Applied',
        ))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if saved_resume_path and os.path.isfile(saved_resume_path):
                os.remove(saved_resume_path)
            flash('You have already applied for this drive.', 'info')
            return redirect(url_for('student_dashboard'))
        except Exception:
            db.session.rollback()
            if saved_resume_path and os.path.isfile(saved_resume_path):
                os.remove(saved_resume_path)
            raise

        flash('Application submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))

    return render_template(
        'apply_preview.html',
        student=student,
        drive=drive,
        resume_available=resume_available,
    )


@app.route('/student/<int:student_id>/resume')
@login_required
def download_student_resume(student_id):
    student = Student.query.get_or_404(student_id)
    authorized = False

    if current_user.role == 'admin':
        authorized = True
    elif current_user.role == 'student':
        authorized = student.user_id == current_user.id
    elif current_user.role == 'company':
        company = Company.query.filter_by(user_id=current_user.id).first()
        authorized = bool(
            company
            and Application.query.join(Placement_Drive).filter(
                Application.student_id == student.id,
                Placement_Drive.company_id == company.id,
            ).first()
        )

    if not authorized:
        flash('You are not authorized to view this resume.', 'danger')
        return redirect(url_for('home'))

    if not student.resume_path:
        flash('This student has not uploaded a resume.', 'warning')
        return redirect(url_for('student_dashboard') if current_user.role == 'student' else url_for('home'))

    filename = os.path.basename(student.resume_path)
    resume_path = os.path.join(app.config['RESUME_UPLOAD_FOLDER'], filename)
    if filename != student.resume_path or not os.path.isfile(resume_path):
        flash('The resume file is unavailable. Please upload it again.', 'warning')
        return redirect(url_for('student_dashboard') if current_user.role == 'student' else url_for('home'))

    return send_from_directory(
        app.config['RESUME_UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name='resume.pdf',
    )

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # Only students should access this
    if current_user.role != 'student':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    student = Student.query.filter_by(user_id=current_user.id).first()

    if request.method == 'POST':
        # Update the student object with form data
        student.full_name = request.form['full_name']
        student.cgpa = float(request.form['cgpa'])
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('student_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile. Please try again.', 'danger')

    return render_template('edit_profile.html', student=student)
















@app.cli.command('initdb')
def initdb():
    """Initialize the database."""
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin', is_approved=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        click.echo('Admin user created with username "admin" and password "admin123".')    
    else: 
        click.echo('Admin user already exists.')
    click.echo('Initialized the database.')

if __name__ == '__main__':
    app.run(debug=True)


