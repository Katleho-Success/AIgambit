from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def index():
    return "WebRTC Signaling Server Running"

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('joined', {'room': room})

@socketio.on('signal')
def on_signal(data):
    room = data['room']
    signal = data['signal']
    emit('signal', {'signal': signal}, room=room, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001)
