from flask import Flask, render_template, request, redirect, session, url_for
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room, leave_room
from itsdangerous import URLSafeTimedSerializer
import redis
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

app = Flask(__name__)
app.secret_key = 'supersecretkey'
socketio = SocketIO(app)

# Configuração do Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Configuração do Flask-Mail usando variáveis de ambiente
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv('SERVER_EMAIL')
app.config['MAIL_PASSWORD'] = os.getenv('APP_PASSWORD')
mail = Mail(app)

# Funções para gerar e verificar token
def generate_token(username):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(username, salt='password-reset-salt')

def verify_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        username = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
    except:
        return None
    return username

# Rota para login
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Verifica se o usuario está cadastrado
        if username and password:
            user_data = redis_client.hget('users', username)
            if user_data:
                stored_email, stored_password, stored_color = user_data.split(':')
                if stored_password == password:
                    session['username'] = username
                    session['color'] = stored_color
                    redis_client.sadd('logged_in_users', username)
                    return redirect(url_for('chat'))
                else:
                    return 'Senha incorreta!', 400
            else:
                return 'Usuário não encontrado!', 400
    return render_template('login.html')

# Rota para Recuperar Senha
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        # Verifica se o email está cadastrado
        username = redis_client.hget('emails', email)
        if username:
            token = generate_token(username)  # Função para gerar token
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message('Recuperação de Senha', sender=os.getenv('SERVER_EMAIL'), recipients=[email])
            msg.body = f'Clique no link para redefinir sua senha: {reset_url}'
            mail.send(msg)
            return 'Email de recuperação enviado com sucesso!'
        else:
            return 'Email não encontrado!', 400
    return render_template('forgot_password.html')

# Rota para Redefinir Senha
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    username = verify_token(token)  # Função para verificar o token
    if not username:
        return 'Token inválido ou expirado!', 400
    if request.method == 'POST':
        new_password = request.form['password']
        # Atualiza a senha do usuário no Redis
        user_data = redis_client.hget('users', username)
        if user_data:
            email, _, color = user_data.split(':')
            redis_client.hset('users', username, f"{email}:{new_password}:{color}")
            return redirect(url_for('login'))
    return render_template('reset_password.html')

# Rota para Logout
@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        redis_client.srem('logged_in_users', username)
    session.clear()
    return redirect(url_for('login'))

# Rota para Cadastro
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            # Verifica se o usuário já está cadastrado
            if redis_client.hexists('users', username):
                return 'Usuário já cadastrado!', 400
            # Armazena as informações do usuário em Redis
            redis_client.hset('users', username, f"{email}:{password}:#000000")
            redis_client.hset('emails', email, username)
            session['username'] = username
            session['color'] = '#000000'
            redis_client.sadd('logged_in_users', username)
            return redirect(url_for('chat'))
        except Exception as e:
            return f"Ocorreu um erro: {str(e)}", 500
    return render_template('register.html')

# Rota para o Chat
@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])

# Evento de conexão do Socket.IO
@socketio.on('connect')
def handle_connect(auth):
    username = session.get('username')
    if username:
        redis_client.sadd('logged_in_users', username)
        update_users_list()
        emit('user_connected', {'username': username}, broadcast=True)

# Evento para desconectar e remover o usuário do Redis
@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')
    if username:
        redis_client.srem('logged_in_users', username)
        update_users_list()
        emit('user_disconnected', {'username': username}, broadcast=True)

# Evento para enviar mensagens
@socketio.on('send_message')
def handle_send_message(data):
    message = data['message']
    username = session.get('username')
    color = session.get('color')
    if username and message:
        redis_client.rpush('chat_messages', f"{username}:{color}:{message}")
        emit('receive_message', {'username': username, 'message': message, 'color': color}, broadcast=True)

# Evento para trocar a cor do usuário
@socketio.on('change_color')
def handle_change_color(data):
    new_color = data['color']
    username = session.get('username')
    if username and new_color:
        user_data = redis_client.hget('users', username)
        if user_data:
            email, password, _ = user_data.split(':')
            redis_client.hset('users', username, f"{email}:{password}:{new_color}")
            session['color'] = new_color
            update_users_list()

# Evento para indicar que o usuário está digitando
@socketio.on('typing')
def handle_typing(data):
    username = data['username']
    emit('typing', {'username': username}, broadcast=True, include_self=False)

# Rota para obter mensagens do Redis
@app.route('/messages')
def get_messages():
    messages = redis_client.lrange('chat_messages', 0, -1)
    return {'messages': messages}

# Função para atualizar a lista de usuários online
def update_users_list():
    users = []
    for username in redis_client.smembers('logged_in_users'):
        user_data = redis_client.hget('users', username)
        if user_data:
            _, _, color = user_data.split(':')
            users.append({'username': username, 'color': color})
    socketio.emit('update_users', users, to=None)

if __name__ == '__main__':
    socketio.run(app)