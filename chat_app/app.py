from flask import Flask, render_template, request, redirect, session, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import redis

app = Flask(__name__)
app.secret_key = 'supersecretkey'
socketio = SocketIO(app)

# Configuração do Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Rota para login
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        color = request.form['color']
        # Verifica se o usuario está cadastrado
        if username and password and color:
            user_data = redis_client.hget('users', username)  # Corrigido aqui
            if user_data:
                stored_email, stored_password, stored_color = user_data.split(':')
                if stored_password == password:
                    session['username'] = username  # Corrigido aqui
                    session['color'] = stored_color  # Corrigido aqui
                    # Armazena o usuário logado em Redis
                    redis_client.sadd('logged_in_users', username)
                    return redirect(url_for('chat'))
                else:
                    return 'Senha incorreta!', 400
            else:
                return 'Usuário não encontrado!', 400
    return render_template('login.html')

# Rota para Logout
@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        redis_client.srem('loggen_in_users', username)
        if username:
            redis_client.srem('logged_in_users', username)
        session.clear()
        return redirect(url_for('login'))

# Rota para Cadastro
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        color = request.form['color']
        # Verifica se o usuário já está cadastrado
        if redis_client.hexists('users', username):
            return 'Usuário já cadastrado!', 400
        # Armazena as informações do usuário em Redis
        redis_client.hset('users', username, f"{email}:{password}:{color}")
        session['username'] = username
        session['color'] = color
        redis_client.sadd('logged_in_users', username)
        return redirect(url_for('chat'))
    return render_template('register.html')
    
# Rota para o Chat
@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])

# Evento de conexão do Socket.IO
@socketio.on('connect')
def handle_connect():
    username = session.get('username')
    if username:
        emit('user_connected', {'username': username}, broadcast=True)

# Evento para desconectar e remover o usuário do Redis
@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')
    if username:
        redis_client.srem('logged_in_users', username)
        emit('user_disconnected', {'username': username}, broadcast=True)

# Evento para enviar mensagens
@socketio.on('send_message')
def handle_send_message(data):
    message = data['message']
    username = session.get('username')
    color = session.get('color')
    if username and message:
        # Armazena a mensagem em Redis (como uma lista de mensagens)
        redis_client.rpush('chat_messages', f"{username}:{color}:{message}")
        emit('receive_message', {'username': username, 'message': message, 'color': color}, broadcast=True)

# Rota para obter mensagens do Redis
@app.route('/messages')
def get_messages():
    messages = redis_client.lrange('chat_messages', 0, -1)
    return {'messages': messages}

if __name__ == '__main__':
    socketio.run(app)