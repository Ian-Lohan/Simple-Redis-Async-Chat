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
        color = request.form['color']
        if username and color:
            session['username'] = username
            session['color'] = color
            # Armazena o usuário logado em Redis
            redis_client.sadd('logged_in_users', username)
            return redirect(url_for('chat'))
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
        color = request.form['color']
        if username and email and color:
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