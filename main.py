import os
import json
import pyrebase
from flask import Flask, redirect, request, session, url_for, render_template, send_file
from google.cloud import storage
import google.generativeai as genai
from functools import wraps

app = Flask(__name__)
app.secret_key = 'Mamatabang69'
bucket_name = 'project0image'


firebase_config = json.load(open("firebaseConfig.json"))
firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()


genai.configure(api_key="AIzaSyCnBoGR_jl4OMeY7lewWkJZ7O9ylF1b0NQ")

firebase_admin_storage = storage.Client()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    user_id = session['user']['localId']
    files = list_files(user_id)  

    
    sync_local_files(user_id)

    
    file_info = []
    for file in files:
        description_filename = f"{os.path.splitext(file)[0]}.txt"
        description_file_path = os.path.join(f"./files/{user_id}", description_filename)
        if os.path.exists(description_file_path):
            with open(description_file_path, "r") as f:
                title_description = json.load(f)
                title = title_description.get("title", "Untitled")
                description = title_description.get("description", "No description available.")
        else:
            title = "Untitled"
            description = "No description available."

        file_info.append({
            'filename': file,
            'title': title,
            'description': description
        })

   
    return render_template('index.html', files=file_info, user_id=user_id)

def sync_local_files(user_id):
    """Sync local files with Google Cloud Storage by deleting local files that are no longer in the cloud."""
    user_dir = os.path.join("./files", user_id)
    if os.path.exists(user_dir):
        local_files = os.listdir(user_dir)
        bucket = firebase_admin_storage.bucket(bucket_name)
        
        for local_file in local_files:
            blob = bucket.blob(f"{user_id}/{local_file}")
            if not blob.exists():
               
                os.remove(os.path.join(user_dir, local_file))
                description_filename = f"{os.path.splitext(local_file)[0]}.txt"
                description_file_path = os.path.join(user_dir, description_filename)
                if os.path.exists(description_file_path):
                    os.remove(description_file_path)




@app.route('/view/<filename>')
@login_required
def view_file(filename):
    user_id = session['user']['localId']
    
   
    description_filename = f"{os.path.splitext(filename)[0]}.txt"
    description_file_path = os.path.join(f"./files/{user_id}", description_filename)

    
    if os.path.exists(description_file_path):
        with open(description_file_path, "r") as f:
            title_description = json.load(f)
            title = title_description.get("title", "Untitled")
            description = title_description.get("description", "No description available.")
    else:
        title = "Untitled"
        description = "No description available."

    
    image_path = url_for('get_file', user_id=user_id, filename=filename)

    
    return render_template('view_image.html', image_path=image_path, user_id=user_id, title=title, description=description)



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.create_user_with_email_and_password(email, password)
            session['user'] = user  # Store user data in session
            return redirect(url_for('index'))
        except Exception as e:
            return f"Error creating account: {e}"
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['user'] = user
            return redirect(url_for('index'))
        except:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/upload', methods=["POST"])
@login_required
def upload():
    user_id = session['user']['localId']
    file = request.files.get('form_file')
    if not file:
        print("No file part in the request.")
        return redirect(url_for('index'))

    filename = file.filename
    user_dir = os.path.join("./files", user_id)
    os.makedirs(user_dir, exist_ok=True)

    local_file_path = os.path.join(user_dir, filename)
    if os.path.exists(local_file_path):
        print(f"File {filename} already exists. Not uploading.")
        return redirect(url_for('index'))

    try:
        file.save(local_file_path)
        title_description = generate_title_and_description(local_file_path)

        description_filename = f"{os.path.splitext(filename)[0]}.txt"
        description_file_path = os.path.join(user_dir, description_filename)
        with open(description_file_path, "w") as f:
            json.dump(title_description, f)

        upload_blob(user_id, open(description_file_path, "rb"), description_filename)
        file.seek(0)
        upload_blob(user_id, file, filename)

        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error uploading file: {e}")
        return redirect(url_for('index'))

def upload_blob(user_id, file, destination_blob_name):
    bucket = firebase_admin_storage.bucket(bucket_name)
    blob = bucket.blob(f"{user_id}/{destination_blob_name}")
    blob.upload_from_file(file)

from flask import send_from_directory



@app.route('/files/<user_id>/<filename>')
@login_required
def get_file(user_id, filename):
    
    if session['user']['localId'] != user_id:
        return "Unauthorized", 403

    
    image_file_path = os.path.join(f"./files/{user_id}", filename)

    
    if not os.path.exists(image_file_path):
        return "File not found", 404

    
    return send_file(image_file_path)




def list_files(user_id):
    user_dir = os.path.join("./files", user_id)
    if os.path.exists(user_dir):
        files = os.listdir(user_dir)
        return [file for file in files if file.lower().endswith((".jpeg", ".jpg"))]
    return []

def generate_title_and_description(file_path):
    uploaded_file = upload_to_gemini(file_path, mime_type="image/jpeg")
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }
    model = genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config=generation_config)
    chat_session = model.start_chat(history=[
        {"role": "user", "parts": [uploaded_file]},
        {"role": "user", "parts": ["Please generate a title and description for the uploaded image in JSON format."]},
    ])

    response = chat_session.send_message("Can you provide a title and description for the uploaded image in JSON format?")
    response_text = response.text.strip("```json\n").strip("```").strip()
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        print("Failed to decode JSON, received response:", response_text)
        return {"title": "Untitled", "description": "No description available."}

def upload_to_gemini(file_path, mime_type="image/jpeg"):
    uploaded_file = genai.upload_file(file_path, mime_type=mime_type)
    return uploaded_file

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
