"""
AIgambit.com - Chess Platform
==============================
A browser-based chess game with Stockfish AI, stats tracking, and coaching
Run: python app.py
Open: http://localhost:5000
"""

from flask import Flask, render_template, jsonify, request, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import chess
import chess.engine
import os
import sys
import json
import threading
import time
import math
import uuid
import random
import requests
import hashlib
import re
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'aigambit_secret_key_2025_secure'
app.config['SESSION_COOKIE_SECURE'] = False  # Set True for HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global engine instance
engine = None
engine_lock = threading.Lock()

# Online games storage
online_games = {}  # game_id -> game data
waiting_players = []  # list of players waiting for match
player_sessions = {}  # socket_id -> player data

# Stats file path
STATS_FILE = os.path.join(os.path.dirname(__file__), 'player_stats.json')
GAMES_FILE = os.path.join(os.path.dirname(__file__), 'saved_games.json')
PLAYER_STYLE_FILE = os.path.join(os.path.dirname(__file__), 'player_style.json')
CLONE_MODEL_FILE = os.path.join(os.path.dirname(__file__), 'clone_model.json')
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')
TOURNAMENTS_FILE = os.path.join(os.path.dirname(__file__), 'tournaments.json')
LEADERBOARD_FILE = os.path.join(os.path.dirname(__file__), 'global_leaderboard.json')

# ============== USER AUTHENTICATION ==============

def hash_password(password):
    """Hash password with salt"""
    salt = 'aigambit_salt_2025'
    return hashlib.sha256((password + salt).encode()).hexdigest()

def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_username(username):
    """Username must be 3-20 chars, alphanumeric and underscores only"""
    pattern = r'^[a-zA-Z0-9_]{3,20}$'
    return re.match(pattern, username) is not None

def load_users():
    """Load all users from file"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_users(users):
    """Save users to file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def get_user(username):
    """Get user by username (case-insensitive)"""
    users = load_users()
    username_lower = username.lower()
    for uname, data in users.items():
        if uname.lower() == username_lower:
            return data
    return None

def get_user_by_email(email):
    """Get user by email"""
    users = load_users()
    email_lower = email.lower()
    for uname, data in users.items():
        if data.get('email', '').lower() == email_lower:
            return data
    return None

def create_user(username, email, password):
    """Create a new user account"""
    users = load_users()
    
    # Check if username exists (case-insensitive)
    if any(u.lower() == username.lower() for u in users.keys()):
        return None, "Username already taken"
    
    # Check if email exists
    if any(u.get('email', '').lower() == email.lower() for u in users.values()):
        return None, "Email already registered"
    
    # Create user with default stats
    user_data = {
        'username': username,
        'email': email.lower(),
        'password_hash': hash_password(password),
        'created_at': datetime.now().isoformat(),
        'rating': 1200,
        'stats': {
            'games_played': 0,
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'rating': 1200
        },
        'games': [],
        'clone_model': {},
        'player_style': {
            'opening_moves': {},
            'piece_preferences': {},
            'move_patterns': {},
            'time_usage': [],
            'risk_score': 50
        },
        'settings': {
            'board_theme': 'green',
            'piece_set': 'cburnett',
            'show_coords': True,
            'sound_enabled': True
        }
    }
    
    users[username] = user_data
    save_users(users)
    return user_data, None

def update_user(username, updates):
    """Update user data"""
    users = load_users()
    if username in users:
        users[username].update(updates)
        save_users(users)
        return True
    return False

def get_current_user():
    """Get currently logged in user from session"""
    if 'user' in session:
        return get_user(session['user'])
    return None

def login_required(f):
    """Decorator to require login for API routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'success': False, 'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Auth API Routes
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """Register a new user"""
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    # Validation
    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'All fields are required'})
    
    if not validate_username(username):
        return jsonify({'success': False, 'error': 'Username must be 3-20 characters, letters, numbers and underscores only'})
    
    if not validate_email(email):
        return jsonify({'success': False, 'error': 'Invalid email address'})
    
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'})
    
    # Create user
    user, error = create_user(username, email, password)
    if error:
        return jsonify({'success': False, 'error': error})
    
    # Auto login after signup
    session['user'] = username
    session.permanent = True
    
    return jsonify({
        'success': True,
        'user': {
            'username': user['username'],
            'email': user['email'],
            'rating': user['rating'],
            'stats': user['stats']
        }
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    data = request.json
    login_id = data.get('username', '').strip()  # Can be username or email
    password = data.get('password', '')
    
    if not login_id or not password:
        return jsonify({'success': False, 'error': 'Username/email and password required'})
    
    # Try to find user by username or email
    user = get_user(login_id)
    if not user:
        user = get_user_by_email(login_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Check password
    if user['password_hash'] != hash_password(password):
        return jsonify({'success': False, 'error': 'Incorrect password'})
    
    # Set session
    session['user'] = user['username']
    session.permanent = True
    
    return jsonify({
        'success': True,
        'user': {
            'username': user['username'],
            'email': user['email'],
            'rating': user['rating'],
            'stats': user['stats']
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user"""
    session.pop('user', None)
    return jsonify({'success': True})

@app.route('/api/auth/me', methods=['GET'])
def get_me():
    """Get current logged in user"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'logged_in': False})
    
    return jsonify({
        'success': True,
        'logged_in': True,
        'user': {
            'username': user['username'],
            'email': user['email'],
            'rating': user['rating'],
            'stats': user['stats'],
            'created_at': user.get('created_at'),
            'settings': user.get('settings', {})
        }
    })

@app.route('/api/auth/update-profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile settings"""
    data = request.json
    user = get_current_user()
    
    if not user:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    # Update allowed fields
    updates = {}
    if 'settings' in data:
        updates['settings'] = data['settings']
    
    if updates:
        update_user(session['user'], updates)
    
    return jsonify({'success': True})

# ============== TOURNAMENT SYSTEM ==============

def load_tournaments():
    """Load all tournaments from file"""
    if os.path.exists(TOURNAMENTS_FILE):
        try:
            with open(TOURNAMENTS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_tournaments(tournaments):
    """Save tournaments to file"""
    with open(TOURNAMENTS_FILE, 'w') as f:
        json.dump(tournaments, f, indent=2)

def load_leaderboard():
    """Load global leaderboard"""
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_leaderboard(leaderboard):
    """Save global leaderboard"""
    with open(LEADERBOARD_FILE, 'w') as f:
        json.dump(leaderboard, f, indent=2)

def update_leaderboard(username, tournament_id, placement, points):
    """Update player's global leaderboard stats"""
    leaderboard = load_leaderboard()
    
    if username not in leaderboard:
        leaderboard[username] = {
            'username': username,
            'total_points': 0,
            'tournaments_played': 0,
            'tournaments_won': 0,
            'total_games': 0,
            'total_wins': 0,
            'best_placement': None,
            'history': []
        }
    
    player = leaderboard[username]
    player['total_points'] += points
    player['tournaments_played'] += 1
    if placement == 1:
        player['tournaments_won'] += 1
    if player['best_placement'] is None or placement < player['best_placement']:
        player['best_placement'] = placement
    player['history'].append({
        'tournament_id': tournament_id,
        'placement': placement,
        'points': points,
        'date': datetime.now().isoformat()
    })
    
    save_leaderboard(leaderboard)

def generate_swiss_pairings(players, scores, round_num, previous_pairings):
    """
    Generate Swiss-system pairings.
    Players with similar scores play each other.
    Avoid repeat pairings when possible.
    """
    # Sort players by score (descending)
    sorted_players = sorted(players, key=lambda p: scores.get(p, 0), reverse=True)
    
    pairings = []
    paired = set()
    
    for i, player1 in enumerate(sorted_players):
        if player1 in paired:
            continue
        
        # Find best opponent (similar score, hasn't played before)
        best_opponent = None
        for j in range(i + 1, len(sorted_players)):
            player2 = sorted_players[j]
            if player2 in paired:
                continue
            
            # Check if they've played before
            pair_key = tuple(sorted([player1, player2]))
            if pair_key not in previous_pairings:
                best_opponent = player2
                break
        
        # If no unpaired opponent found, take anyone available
        if not best_opponent:
            for j in range(i + 1, len(sorted_players)):
                player2 = sorted_players[j]
                if player2 not in paired:
                    best_opponent = player2
                    break
        
        if best_opponent:
            # Alternate colors based on round
            if round_num % 2 == 0:
                pairings.append({'white': player1, 'black': best_opponent})
            else:
                pairings.append({'white': best_opponent, 'black': player1})
            paired.add(player1)
            paired.add(best_opponent)
    
    # Handle odd number of players (bye)
    for player in sorted_players:
        if player not in paired:
            pairings.append({'white': player, 'black': None, 'bye': True})
    
    return pairings

def generate_knockout_bracket(players):
    """Generate single-elimination bracket"""
    random.shuffle(players)
    
    # Pad to power of 2
    bracket_size = 1
    while bracket_size < len(players):
        bracket_size *= 2
    
    # Add byes for missing players
    bracket = list(players)
    while len(bracket) < bracket_size:
        bracket.append(None)  # Bye
    
    return bracket

@app.route('/api/tournaments', methods=['GET'])
def list_tournaments():
    """List all tournaments with filtering"""
    status = request.args.get('status', None)  # open, in_progress, completed
    tournaments = load_tournaments()
    
    result = []
    for tid, t in tournaments.items():
        # Filter by status if specified
        if status and t.get('status') != status:
            continue
        
        result.append({
            'id': tid,
            'name': t['name'],
            'host': t['host'],
            'format': t['format'],
            'time_control': t['time_control'],
            'start_time': t['start_time'],
            'status': t['status'],
            'player_count': len(t.get('players', [])),
            'max_players': t.get('max_players', 64),
            'rounds': t.get('total_rounds', 0),
            'current_round': t.get('current_round', 0),
            'created_at': t.get('created_at')
        })
    
    # Sort by start time
    result.sort(key=lambda x: x.get('start_time', ''), reverse=True)
    
    return jsonify({'success': True, 'tournaments': result})

@app.route('/api/tournaments/create', methods=['POST'])
@login_required
def create_tournament():
    """Create a new tournament"""
    data = request.json
    user = get_current_user()
    
    name = data.get('name', '').strip()
    format_type = data.get('format', 'swiss')  # swiss, knockout, arena
    time_control = data.get('time_control', '10+0')  # e.g., "10+0", "5+3", "3+2"
    start_time = data.get('start_time')  # ISO format datetime
    max_players = data.get('max_players', 64)
    rounds = data.get('rounds', 5)  # For Swiss
    description = data.get('description', '')
    
    # Validation
    if not name or len(name) < 3:
        return jsonify({'success': False, 'error': 'Tournament name must be at least 3 characters'})
    if len(name) > 50:
        return jsonify({'success': False, 'error': 'Tournament name too long (max 50 chars)'})
    if format_type not in ['swiss', 'knockout', 'arena']:
        return jsonify({'success': False, 'error': 'Invalid tournament format'})
    if max_players < 4 or max_players > 256:
        return jsonify({'success': False, 'error': 'Max players must be between 4 and 256'})
    if rounds < 1 or rounds > 15:
        return jsonify({'success': False, 'error': 'Rounds must be between 1 and 15'})
    
    # Parse time control
    try:
        if '+' in time_control:
            base, inc = time_control.split('+')
            base_time = int(base)
            increment = int(inc)
        else:
            base_time = int(time_control)
            increment = 0
        if base_time < 1 or base_time > 180:
            raise ValueError("Invalid base time")
    except:
        return jsonify({'success': False, 'error': 'Invalid time control format (use e.g., "10+0" or "5+3")'})
    
    tournament_id = str(uuid.uuid4())[:8]
    
    tournament = {
        'id': tournament_id,
        'name': name,
        'host': user['username'],
        'format': format_type,
        'time_control': time_control,
        'base_time': base_time * 60,  # Convert to seconds
        'increment': increment,
        'start_time': start_time,
        'max_players': max_players,
        'total_rounds': rounds if format_type == 'swiss' else None,
        'current_round': 0,
        'status': 'open',  # open, in_progress, completed
        'players': [user['username']],  # Host auto-joins
        'scores': {user['username']: 0},
        'games': {},  # round -> list of games
        'pairings': {},  # round -> pairings
        'previous_pairings': [],  # Track who played who
        'bracket': None,  # For knockout
        'results': [],
        'description': description,
        'created_at': datetime.now().isoformat(),
        'started_at': None,
        'ended_at': None
    }
    
    tournaments = load_tournaments()
    tournaments[tournament_id] = tournament
    save_tournaments(tournaments)
    
    return jsonify({'success': True, 'tournament': tournament})

@app.route('/api/tournaments/<tournament_id>', methods=['GET'])
def get_tournament(tournament_id):
    """Get tournament details"""
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    return jsonify({'success': True, 'tournament': tournaments[tournament_id]})

@app.route('/api/tournaments/<tournament_id>/join', methods=['POST'])
@login_required
def join_tournament(tournament_id):
    """Join a tournament"""
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if tournament['status'] != 'open':
        return jsonify({'success': False, 'error': 'Tournament is not open for registration'})
    
    if user['username'] in tournament['players']:
        return jsonify({'success': False, 'error': 'Already joined this tournament'})
    
    if len(tournament['players']) >= tournament['max_players']:
        return jsonify({'success': False, 'error': 'Tournament is full'})
    
    tournament['players'].append(user['username'])
    tournament['scores'][user['username']] = 0
    save_tournaments(tournaments)
    
    # Notify all players via WebSocket
    socketio.emit('tournament_update', {
        'type': 'player_joined',
        'tournament_id': tournament_id,
        'player': user['username'],
        'player_count': len(tournament['players'])
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True, 'tournament': tournament})

@app.route('/api/tournaments/<tournament_id>/leave', methods=['POST'])
@login_required
def leave_tournament(tournament_id):
    """Leave a tournament before it starts"""
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if tournament['status'] != 'open':
        return jsonify({'success': False, 'error': 'Cannot leave a tournament in progress'})
    
    if user['username'] not in tournament['players']:
        return jsonify({'success': False, 'error': 'Not in this tournament'})
    
    if user['username'] == tournament['host']:
        return jsonify({'success': False, 'error': 'Host cannot leave. Cancel the tournament instead.'})
    
    tournament['players'].remove(user['username'])
    del tournament['scores'][user['username']]
    save_tournaments(tournaments)
    
    socketio.emit('tournament_update', {
        'type': 'player_left',
        'tournament_id': tournament_id,
        'player': user['username'],
        'player_count': len(tournament['players'])
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True})

@app.route('/api/tournaments/<tournament_id>/start', methods=['POST'])
@login_required
def start_tournament(tournament_id):
    """Start the tournament (host only)"""
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if user['username'] != tournament['host']:
        return jsonify({'success': False, 'error': 'Only the host can start the tournament'})
    
    if tournament['status'] != 'open':
        return jsonify({'success': False, 'error': 'Tournament already started or completed'})
    
    if len(tournament['players']) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 players to start'})
    
    tournament['status'] = 'in_progress'
    tournament['started_at'] = datetime.now().isoformat()
    tournament['current_round'] = 1
    
    # Generate first round pairings
    if tournament['format'] == 'swiss':
        pairings = generate_swiss_pairings(
            tournament['players'],
            tournament['scores'],
            1,
            set()
        )
        tournament['pairings']['1'] = pairings
    elif tournament['format'] == 'knockout':
        bracket = generate_knockout_bracket(tournament['players'])
        tournament['bracket'] = bracket
        # Generate first round from bracket
        pairings = []
        for i in range(0, len(bracket), 2):
            if bracket[i] and bracket[i+1]:
                pairings.append({'white': bracket[i], 'black': bracket[i+1]})
            elif bracket[i]:
                pairings.append({'white': bracket[i], 'black': None, 'bye': True})
            elif bracket[i+1]:
                pairings.append({'white': bracket[i+1], 'black': None, 'bye': True})
        tournament['pairings']['1'] = pairings
    
    save_tournaments(tournaments)
    
    socketio.emit('tournament_update', {
        'type': 'tournament_started',
        'tournament_id': tournament_id,
        'pairings': tournament['pairings']['1']
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True, 'tournament': tournament})

@app.route('/api/tournaments/<tournament_id>/result', methods=['POST'])
@login_required
def report_result(tournament_id):
    """Report a game result"""
    data = request.json
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if tournament['status'] != 'in_progress':
        return jsonify({'success': False, 'error': 'Tournament is not in progress'})
    
    game_id = data.get('game_id')
    result = data.get('result')  # '1-0', '0-1', '1/2-1/2'
    white = data.get('white')
    black = data.get('black')
    
    if result not in ['1-0', '0-1', '1/2-1/2']:
        return jsonify({'success': False, 'error': 'Invalid result'})
    
    # Update scores
    if result == '1-0':
        tournament['scores'][white] = tournament['scores'].get(white, 0) + 1
    elif result == '0-1':
        tournament['scores'][black] = tournament['scores'].get(black, 0) + 1
    else:  # Draw
        tournament['scores'][white] = tournament['scores'].get(white, 0) + 0.5
        tournament['scores'][black] = tournament['scores'].get(black, 0) + 0.5
    
    # Track pairing
    pair_key = tuple(sorted([white, black]))
    if pair_key not in tournament['previous_pairings']:
        tournament['previous_pairings'].append(pair_key)
    
    # Store game result
    round_key = str(tournament['current_round'])
    if round_key not in tournament['games']:
        tournament['games'][round_key] = []
    
    tournament['games'][round_key].append({
        'game_id': game_id,
        'white': white,
        'black': black,
        'result': result,
        'reported_at': datetime.now().isoformat()
    })
    
    save_tournaments(tournaments)
    
    # Notify tournament room
    socketio.emit('tournament_update', {
        'type': 'game_result',
        'tournament_id': tournament_id,
        'round': tournament['current_round'],
        'white': white,
        'black': black,
        'result': result,
        'scores': tournament['scores']
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True, 'scores': tournament['scores']})

@app.route('/api/tournaments/<tournament_id>/next-round', methods=['POST'])
@login_required
def next_round(tournament_id):
    """Advance to next round (host only)"""
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if user['username'] != tournament['host']:
        return jsonify({'success': False, 'error': 'Only the host can advance rounds'})
    
    if tournament['status'] != 'in_progress':
        return jsonify({'success': False, 'error': 'Tournament is not in progress'})
    
    current_round = tournament['current_round']
    
    # Check if tournament should end
    if tournament['format'] == 'swiss':
        if current_round >= tournament['total_rounds']:
            return end_tournament_internal(tournament_id, tournaments)
    elif tournament['format'] == 'knockout':
        # Check if only one player remains
        remaining = [p for p in tournament['players'] if tournament['scores'].get(p, 0) > 0 or current_round == 1]
        if len(remaining) <= 1:
            return end_tournament_internal(tournament_id, tournaments)
    
    # Advance to next round
    tournament['current_round'] = current_round + 1
    
    # Generate new pairings
    if tournament['format'] == 'swiss':
        pairings = generate_swiss_pairings(
            tournament['players'],
            tournament['scores'],
            tournament['current_round'],
            set(tuple(p) for p in tournament['previous_pairings'])
        )
        tournament['pairings'][str(tournament['current_round'])] = pairings
    
    save_tournaments(tournaments)
    
    socketio.emit('tournament_update', {
        'type': 'new_round',
        'tournament_id': tournament_id,
        'round': tournament['current_round'],
        'pairings': tournament['pairings'][str(tournament['current_round'])]
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True, 'tournament': tournament})

@app.route('/api/tournaments/<tournament_id>/end', methods=['POST'])
@login_required
def end_tournament(tournament_id):
    """End the tournament (host only)"""
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if user['username'] != tournament['host']:
        return jsonify({'success': False, 'error': 'Only the host can end the tournament'})
    
    return end_tournament_internal(tournament_id, tournaments)

def end_tournament_internal(tournament_id, tournaments):
    """Internal function to end tournament and update leaderboard"""
    tournament = tournaments[tournament_id]
    tournament['status'] = 'completed'
    tournament['ended_at'] = datetime.now().isoformat()
    
    # Calculate final standings
    standings = sorted(
        tournament['scores'].items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    tournament['final_standings'] = standings
    
    # Update global leaderboard
    for placement, (username, score) in enumerate(standings, 1):
        # Points based on placement and tournament size
        points = max(0, len(standings) - placement + 1) * 10
        if placement == 1:
            points += 50  # Bonus for winning
        elif placement == 2:
            points += 25
        elif placement == 3:
            points += 10
        
        update_leaderboard(username, tournament_id, placement, points)
    
    save_tournaments(tournaments)
    
    socketio.emit('tournament_update', {
        'type': 'tournament_ended',
        'tournament_id': tournament_id,
        'standings': standings
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True, 'standings': standings})

@app.route('/api/tournaments/<tournament_id>/cancel', methods=['POST'])
@login_required
def cancel_tournament(tournament_id):
    """Cancel a tournament (host only, before it starts)"""
    user = get_current_user()
    tournaments = load_tournaments()
    
    if tournament_id not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    tournament = tournaments[tournament_id]
    
    if user['username'] != tournament['host']:
        return jsonify({'success': False, 'error': 'Only the host can cancel the tournament'})
    
    if tournament['status'] == 'in_progress':
        return jsonify({'success': False, 'error': 'Cannot cancel a tournament in progress'})
    
    del tournaments[tournament_id]
    save_tournaments(tournaments)
    
    socketio.emit('tournament_update', {
        'type': 'tournament_cancelled',
        'tournament_id': tournament_id
    }, room=f'tournament_{tournament_id}')
    
    return jsonify({'success': True})

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get global leaderboard"""
    leaderboard = load_leaderboard()
    
    # Sort by total points
    sorted_lb = sorted(
        leaderboard.values(),
        key=lambda x: x['total_points'],
        reverse=True
    )
    
    # Add rank
    for i, player in enumerate(sorted_lb, 1):
        player['rank'] = i
    
    return jsonify({'success': True, 'leaderboard': sorted_lb})

@app.route('/api/leaderboard/<username>', methods=['GET'])
def get_player_ranking(username):
    """Get specific player's ranking info"""
    leaderboard = load_leaderboard()
    
    if username not in leaderboard:
        return jsonify({'success': False, 'error': 'Player not found in leaderboard'})
    
    # Calculate rank
    sorted_lb = sorted(
        leaderboard.items(),
        key=lambda x: x[1]['total_points'],
        reverse=True
    )
    
    rank = 1
    for uname, data in sorted_lb:
        if uname == username:
            break
        rank += 1
    
    player_data = leaderboard[username]
    player_data['rank'] = rank
    player_data['total_players'] = len(leaderboard)
    
    return jsonify({'success': True, 'player': player_data})

# WebSocket handlers for tournaments
@socketio.on('join_tournament_room')
def on_join_tournament_room(data):
    """Join tournament room for real-time updates"""
    tournament_id = data.get('tournament_id')
    if tournament_id:
        join_room(f'tournament_{tournament_id}')
        emit('tournament_room_joined', {'tournament_id': tournament_id})

@socketio.on('leave_tournament_room')
def on_leave_tournament_room(data):
    """Leave tournament room"""
    tournament_id = data.get('tournament_id')
    if tournament_id:
        leave_room(f'tournament_{tournament_id}')

# ============== LICHESS CLOUD API ==============
def get_lichess_move(fen, skill=10):
    """
    Get a move from Lichess Cloud API (free, no API key needed).
    Uses cloud evaluation when local Stockfish is not available.
    """
    try:
        # Lichess cloud evaluation endpoint
        url = f"https://lichess.org/api/cloud-eval?fen={requests.utils.quote(fen)}&multiPv=3"
        response = requests.get(url, timeout=5, headers={'Accept': 'application/json'})
        
        if response.status_code == 200:
            data = response.json()
            if 'pvs' in data and len(data['pvs']) > 0:
                # Get the best move(s)
                pvs = data['pvs']
                
                # For lower skill levels, sometimes pick suboptimal moves
                if skill <= 5 and len(pvs) > 1 and random.random() < 0.4:
                    # Pick 2nd or 3rd best move
                    choice_idx = min(random.randint(1, 2), len(pvs) - 1)
                    pv = pvs[choice_idx]['moves'].split()[0]
                elif skill <= 10 and len(pvs) > 1 and random.random() < 0.2:
                    # Occasionally pick 2nd best
                    pv = pvs[1]['moves'].split()[0]
                else:
                    # Best move
                    pv = pvs[0]['moves'].split()[0]
                
                return pv
        
        # Fallback to Lichess tablebase for endgames (7 pieces or less)
        board = chess.Board(fen)
        if len(board.piece_map()) <= 7:
            tb_url = f"https://tablebase.lichess.ovh/standard?fen={requests.utils.quote(fen)}"
            tb_response = requests.get(tb_url, timeout=5)
            if tb_response.status_code == 200:
                tb_data = tb_response.json()
                if 'moves' in tb_data and len(tb_data['moves']) > 0:
                    return tb_data['moves'][0]['uci']
        
        return None
    except Exception as e:
        print(f"Lichess API error: {e}")
        return None

def get_random_smart_move(board, skill=5):
    """
    Generate a reasonable move without an engine.
    Used as ultimate fallback when no API/engine available.
    """
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return None
    
    # Categorize moves
    checkmates = []
    checks = []
    captures = []
    promotions = []
    center_moves = []
    other_moves = []
    
    center_squares = [chess.D4, chess.E4, chess.D5, chess.E5]
    
    for move in legal_moves:
        board.push(move)
        if board.is_checkmate():
            board.pop()
            checkmates.append(move)
            continue
        board.pop()
        
        if board.gives_check(move):
            checks.append(move)
        if board.is_capture(move):
            captures.append(move)
        if move.promotion:
            promotions.append(move)
        if move.to_square in center_squares:
            center_moves.append(move)
        else:
            other_moves.append(move)
    
    # Priority order based on skill
    if checkmates:
        return random.choice(checkmates)
    
    if skill >= 8:
        # Higher skill: prioritize captures and checks
        if promotions and random.random() < 0.9:
            return random.choice(promotions)
        if captures and random.random() < 0.7:
            return random.choice(captures)
        if checks and random.random() < 0.5:
            return random.choice(checks)
    elif skill >= 4:
        # Medium skill: sometimes good moves
        if promotions and random.random() < 0.7:
            return random.choice(promotions)
        if captures and random.random() < 0.5:
            return random.choice(captures)
    else:
        # Low skill: mostly random
        if promotions and random.random() < 0.3:
            return random.choice(promotions)
    
    # Prefer center moves in opening
    if center_moves and random.random() < 0.4:
        return random.choice(center_moves)
    
    return random.choice(legal_moves)

def load_stats(username=None):
    """Load player statistics - user-specific if logged in"""
    # If username provided, get user-specific stats
    if username:
        user = get_user(username)
        if user and 'stats' in user:
            stats = user['stats']
            # Ensure all fields exist
            default_stats = get_default_stats()
            for key in default_stats:
                if key not in stats:
                    stats[key] = default_stats[key]
            return stats
    
    # Fall back to global stats file for anonymous users
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return get_default_stats()

def get_default_stats():
    """Return default stats structure"""
    return {
        'rating': 1200,
        'games_played': 0,
        'wins': 0,
        'losses': 0,
        'draws': 0,
        'total_accuracy': 0,
        'best_accuracy': 0,
        'current_streak': 0,
        'best_streak': 0,
        'rating_history': [{'date': datetime.now().strftime('%Y-%m-%d'), 'rating': 1200}],
        'achievements': []
    }

def save_stats(stats, username=None):
    """Save player statistics - user-specific if logged in"""
    if username:
        users = load_users()
        if username in users:
            users[username]['stats'] = stats
            users[username]['rating'] = stats.get('rating', 1200)
            save_users(users)
            return
    
    # Fall back to global stats file
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        print(f"Error saving stats: {e}")

def load_games(username=None):
    """Load saved games - user-specific if logged in"""
    if username:
        user = get_user(username)
        if user and 'games' in user:
            return user['games']
        return []
    
    # Fall back to global games file
    if os.path.exists(GAMES_FILE):
        try:
            with open(GAMES_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_games(games, username=None):
    """Save games list - user-specific if logged in"""
    games = games[-50:]  # Keep last 50 games
    
    if username:
        users = load_users()
        if username in users:
            users[username]['games'] = games
            save_users(users)
            return
    
    # Fall back to global games file
    try:
        with open(GAMES_FILE, 'w') as f:
            json.dump(games, f, indent=2)
    except Exception as e:
        print(f"Error saving games: {e}")

def load_player_style(username=None):
    """Load player style profile for clone AI - user-specific if logged in"""
    if username:
        user = get_user(username)
        if user and 'player_style' in user:
            return user['player_style']
        return init_player_style()
    
    # Fall back to global file
    if os.path.exists(PLAYER_STYLE_FILE):
        try:
            with open(PLAYER_STYLE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return init_player_style()

def init_player_style():
    """Initialize comprehensive player style tracking"""
    return {
        # Opening preferences
        'favorite_openings': {},  # opening_name -> count
        'first_moves_white': {},  # first move as white -> count
        'first_moves_black': {},  # response to e4/d4 as black -> count
        
        # Game phase tendencies
        'phase_performance': {
            'opening': {'aggressive': 0, 'solid': 0, 'gambit': 0},
            'middlegame': {'tactical': 0, 'positional': 0, 'attacking': 0, 'defensive': 0},
            'endgame': {'technical': 0, 'active': 0, 'passive': 0}
        },
        
        # Risk profile
        'risk_profile': {
            'base_risk': 0.5,
            'sacrifices_attempted': 0,
            'aggressive_moves': 0,
            'defensive_moves': 0,
            'quiet_moves': 0,
            'captures': 0,
            'checks': 0,
            'total_moves': 0
        },
        
        # Piece preferences
        'piece_activity': {
            'knight_moves': 0,
            'bishop_moves': 0,
            'rook_moves': 0,
            'queen_moves': 0,
            'king_moves': 0,
            'pawn_pushes': 0
        },
        
        # Positional tendencies
        'positional': {
            'castles_kingside': 0,
            'castles_queenside': 0,
            'no_castle': 0,
            'early_queen_development': 0,
            'fianchetto': 0,
            'center_control': 0,
            'flank_play': 0
        },
        
        # Time usage patterns
        'time_usage': {
            'fast_moves': 0,  # moves made quickly
            'slow_moves': 0   # moves that took time
        },
        
        # Games analyzed
        'games_analyzed': 0,
        'total_moves_analyzed': 0
    }

def save_player_style(style, username=None):
    """Save player style profile - user-specific if logged in"""
    if username:
        users = load_users()
        if username in users:
            users[username]['player_style'] = style
            save_users(users)
            return
    
    # Fall back to global file
    try:
        with open(PLAYER_STYLE_FILE, 'w') as f:
            json.dump(style, f, indent=2)
    except Exception as e:
        print(f"Error saving player style: {e}")

def load_clone_model(username=None):
    """Load the clone model (position -> move preferences) - user-specific if logged in"""
    if username:
        user = get_user(username)
        if user and 'clone_model' in user:
            return user['clone_model']
        return {}
    
    # Fall back to global file
    if os.path.exists(CLONE_MODEL_FILE):
        try:
            with open(CLONE_MODEL_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_clone_model(model, username=None):
    """Save clone model - user-specific if logged in"""
    if username:
        users = load_users()
        if username in users:
            users[username]['clone_model'] = model
            save_users(users)
            return
    
    # Fall back to global file
    try:
        with open(CLONE_MODEL_FILE, 'w') as f:
            json.dump(model, f, indent=2)
    except Exception as e:
        print(f"Error saving clone model: {e}")

def analyze_move_type(board, move):
    """Analyze what type of move this is"""
    move_info = {
        'is_capture': board.is_capture(move),
        'is_check': False,
        'is_castle': board.is_castling(move),
        'is_promotion': move.promotion is not None,
        'piece_moved': board.piece_at(move.from_square),
        'is_aggressive': False,
        'is_defensive': False,
        'is_forced': False,  # Was this move forced (only option or responding to check)?
        'was_in_check': board.is_check(),  # Was player in check before this move?
        'num_legal_moves': len(list(board.legal_moves))  # How many options did player have?
    }
    
    # Check if move is forced (only 1 legal move or player was in check)
    if move_info['num_legal_moves'] == 1:
        move_info['is_forced'] = True
    elif move_info['was_in_check']:
        # When in check, moves are often forced or severely limited
        move_info['is_forced'] = True
    
    # Check if move gives check
    board_copy = board.copy()
    board_copy.push(move)
    move_info['is_check'] = board_copy.is_check()
    
    # Only categorize as aggressive/defensive if not forced
    if not move_info['is_forced']:
        if move_info['is_capture'] or move_info['is_check']:
            move_info['is_aggressive'] = True
        
        piece = move_info['piece_moved']
        if piece:
            # Defensive if moving piece to back ranks (retreating)
            to_rank = chess.square_rank(move.to_square)
            from_rank = chess.square_rank(move.from_square)
            if board.turn == chess.WHITE and to_rank < from_rank:
                move_info['is_defensive'] = True
            elif board.turn == chess.BLACK and to_rank > from_rank:
                move_info['is_defensive'] = True
    
    return move_info

def update_player_style_from_game(game_data, username=None):
    """Update player style based on a completed game - user-specific if logged in"""
    style = load_player_style(username)
    moves = game_data.get('moves', [])
    player_color = game_data.get('player_color', 'white')
    
    if not moves:
        return
    
    # Create a board to replay moves
    board = chess.Board()
    move_number = 0
    player_moves_in_game = 0
    
    for move_san in moves:
        try:
            move = board.parse_san(move_san)
            is_player_move = (board.turn == chess.WHITE and player_color == 'white') or \
                           (board.turn == chess.BLACK and player_color == 'black')
            
            if is_player_move:
                player_moves_in_game += 1
                move_info = analyze_move_type(board, move)
                
                # Track piece movements (always track, even for forced moves)
                piece = move_info['piece_moved']
                if piece:
                    piece_type = piece.piece_type
                    if piece_type == chess.KNIGHT:
                        style['piece_activity']['knight_moves'] += 1
                    elif piece_type == chess.BISHOP:
                        style['piece_activity']['bishop_moves'] += 1
                    elif piece_type == chess.ROOK:
                        style['piece_activity']['rook_moves'] += 1
                    elif piece_type == chess.QUEEN:
                        style['piece_activity']['queen_moves'] += 1
                    elif piece_type == chess.KING:
                        style['piece_activity']['king_moves'] += 1
                    elif piece_type == chess.PAWN:
                        style['piece_activity']['pawn_pushes'] += 1
                
                # Track risk profile - ONLY for non-forced moves (where player had real choice)
                # Skip forced moves: only 1 legal option, or responding to check, or recapture
                is_choice_move = not move_info['is_forced'] and move_info['num_legal_moves'] >= 3
                
                style['risk_profile']['total_moves'] += 1
                if move_info['is_capture']:
                    style['risk_profile']['captures'] += 1
                if move_info['is_check']:
                    style['risk_profile']['checks'] += 1
                
                # Only count towards aggressive/defensive style if it was a real choice
                if is_choice_move:
                    if 'choice_moves' not in style['risk_profile']:
                        style['risk_profile']['choice_moves'] = 0
                        style['risk_profile']['choice_aggressive'] = 0
                        style['risk_profile']['choice_defensive'] = 0
                        style['risk_profile']['choice_quiet'] = 0
                    
                    style['risk_profile']['choice_moves'] += 1
                    if move_info['is_aggressive']:
                        style['risk_profile']['choice_aggressive'] += 1
                    elif move_info['is_defensive']:
                        style['risk_profile']['choice_defensive'] += 1
                    else:
                        style['risk_profile']['choice_quiet'] += 1
                
                # Still track all moves for general stats (but with is_forced flag noted)
                if move_info['is_aggressive']:
                    style['risk_profile']['aggressive_moves'] += 1
                elif move_info['is_defensive']:
                    style['risk_profile']['defensive_moves'] += 1
                else:
                    style['risk_profile']['quiet_moves'] += 1
                
                # Track castling
                if move_info['is_castle']:
                    if 'O-O-O' in move_san or 'queenside' in str(move).lower():
                        style['positional']['castles_queenside'] += 1
                    else:
                        style['positional']['castles_kingside'] += 1
                
                # Track opening moves (first 5 moves)
                if move_number < 10:  # First 10 half-moves (5 full moves)
                    if move_number == 0 and player_color == 'white':
                        style['first_moves_white'][move_san] = style['first_moves_white'].get(move_san, 0) + 1
                    elif move_number == 1 and player_color == 'black':
                        # Response to white's first move
                        style['first_moves_black'][move_san] = style['first_moves_black'].get(move_san, 0) + 1
                
                # Update clone model with position -> move mapping
                update_clone_model_position(board.fen(), move.uci(), player_color, username)
                
                # Determine game phase
                if move_number < 10:
                    phase = 'opening'
                elif len(board.piece_map()) > 10:
                    phase = 'middlegame'
                else:
                    phase = 'endgame'
                
                # Track phase tendencies
                if move_info['is_aggressive']:
                    if phase == 'opening':
                        style['phase_performance']['opening']['aggressive'] += 1
                    elif phase == 'middlegame':
                        style['phase_performance']['middlegame']['tactical'] += 1
                        style['phase_performance']['middlegame']['attacking'] += 1
                else:
                    if phase == 'opening':
                        style['phase_performance']['opening']['solid'] += 1
                    elif phase == 'middlegame':
                        style['phase_performance']['middlegame']['positional'] += 1
            
            board.push(move)
            move_number += 1
            
        except Exception as e:
            print(f"Error analyzing move {move_san}: {e}")
            continue
    
    # Update risk tolerance based on CHOICE moves only (not forced moves)
    # This gives a more accurate picture of the player's actual playing style
    choice_total = style['risk_profile'].get('choice_moves', 0)
    if choice_total >= 5:  # Need at least 5 choice moves to assess style
        choice_aggressive = style['risk_profile'].get('choice_aggressive', 0)
        aggression_ratio = choice_aggressive / choice_total
        # Scale: 0.2 = very passive, 0.5 = balanced, 0.8 = very aggressive
        style['risk_profile']['base_risk'] = min(1.0, max(0.0, 0.2 + aggression_ratio * 0.6))
    else:
        # Fallback to old method if not enough choice data
        total = style['risk_profile']['aggressive_moves'] + style['risk_profile']['defensive_moves'] + style['risk_profile']['quiet_moves']
        if total > 0:
            aggression_ratio = style['risk_profile']['aggressive_moves'] / total
            style['risk_profile']['base_risk'] = min(1.0, max(0.0, 0.3 + aggression_ratio * 0.5))
    
    style['games_analyzed'] += 1
    style['total_moves_analyzed'] += player_moves_in_game
    
    save_player_style(style, username)

def update_clone_model_position(fen, move_uci, player_color, username=None):
    """Update clone model with a position -> move mapping - user-specific if logged in"""
    model = load_clone_model(username)
    
    # Use board position only (not turn info, castling rights, etc for simpler matching)
    board_key = fen.split()[0]
    composite_key = f"{board_key}::{player_color[0]}"  # e.g. "rnbqkb.../..." + "::w"
    
    if composite_key not in model:
        model[composite_key] = {}
    
    if move_uci not in model[composite_key]:
        model[composite_key][move_uci] = {'count': 0, 'weight': 0.0}
    
    model[composite_key][move_uci]['count'] += 1
    model[composite_key][move_uci]['weight'] += 1.0
    
    # Keep model size manageable (limit to 5000 positions)
    if len(model) > 5000:
        # Remove oldest/least used positions
        sorted_keys = sorted(model.keys(), key=lambda k: sum(m['count'] for m in model[k].values()))
        for key in sorted_keys[:500]:
            del model[key]
    
    save_clone_model(model, username)

def get_skill_adjusted_move(board, skill):
    """
    Get a move adjusted for skill level (1-20).
    Lower skill = more mistakes, random moves, misses tactics.
    Uses Lichess Cloud API as fallback when local Stockfish unavailable.
    NOTE: This function should be called WITHOUT engine_lock held.
    """
    
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return None
    
    # Skill 1-3: Very beginner - often random, rarely finds good moves
    if skill <= 3:
        # 70% chance of random move at skill 1, 40% at skill 3
        random_chance = 0.7 - (skill - 1) * 0.15
        if random.random() < random_chance:
            # Prefer non-hanging moves if possible
            safe_moves = []
            for move in legal_moves:
                board.push(move)
                # Check if we're hanging a piece
                is_safe = True
                for opp_move in board.legal_moves:
                    if board.is_capture(opp_move):
                        # We might be hanging something
                        is_safe = False
                        break
                board.pop()
                if is_safe:
                    safe_moves.append(move)
            
            if safe_moves and random.random() < 0.5:
                return random.choice(safe_moves)
            return random.choice(legal_moves)
        
        # Otherwise use engine with very low skill
        if engine:
            with engine_lock:
                try:
                    engine.configure({"Skill Level": 0})
                    result = engine.play(board, chess.engine.Limit(depth=1, time=0.05))
                    return result.move
                except:
                    pass
        
        # Fallback: try Lichess cloud API or smart random
        cloud_move = get_lichess_move(board.fen(), skill)
        if cloud_move:
            try:
                move = chess.Move.from_uci(cloud_move)
                if move in legal_moves:
                    # For low skill, sometimes ignore the cloud move
                    if random.random() < 0.4:
                        return get_random_smart_move(board, skill)
                    return move
            except:
                pass
        return get_random_smart_move(board, skill)
    
    # Skill 4-6: Beginner - makes many mistakes
    elif skill <= 6:
        random_chance = 0.4 - (skill - 4) * 0.1  # 40% to 20%
        if random.random() < random_chance:
            # Pick a capture if available, otherwise random
            captures = [m for m in legal_moves if board.is_capture(m)]
            if captures and random.random() < 0.6:
                return random.choice(captures)
            return random.choice(legal_moves)
        
        if engine:
            with engine_lock:
                try:
                    engine.configure({"Skill Level": skill - 2})
                    depth = max(1, skill - 3)  # depth 1-3
                    result = engine.play(board, chess.engine.Limit(depth=depth, time=0.08))
                    return result.move
                except:
                    pass
        
        # Fallback: Lichess cloud API
        cloud_move = get_lichess_move(board.fen(), skill)
        if cloud_move:
            try:
                move = chess.Move.from_uci(cloud_move)
                if move in legal_moves:
                    if random.random() < 0.25:
                        return get_random_smart_move(board, skill)
                    return move
            except:
                pass
        return get_random_smart_move(board, skill)
    
    # Skill 7-10: Intermediate beginner - occasional blunders
    elif skill <= 10:
        random_chance = 0.15 - (skill - 7) * 0.03  # 15% to 6%
        if random.random() < random_chance:
            captures = [m for m in legal_moves if board.is_capture(m)]
            checks = [m for m in legal_moves if board.gives_check(m)]
            good_moves = list(set(captures + checks))
            if good_moves:
                return random.choice(good_moves)
            return random.choice(legal_moves)
        
        if engine:
            with engine_lock:
                try:
                    engine.configure({"Skill Level": skill})
                    depth = skill - 4  # depth 3-6
                    result = engine.play(board, chess.engine.Limit(depth=depth, time=0.15))
                    return result.move
                except:
                    pass
        
        # Fallback: Lichess cloud API
        cloud_move = get_lichess_move(board.fen(), skill)
        if cloud_move:
            try:
                move = chess.Move.from_uci(cloud_move)
                if move in legal_moves:
                    return move
            except:
                pass
        return get_random_smart_move(board, skill)
    
    # Skill 11-14: Intermediate - plays reasonably
    elif skill <= 14:
        if engine:
            with engine_lock:
                try:
                    engine.configure({"Skill Level": skill})
                    depth = skill - 3  # depth 8-11
                    think_time = 0.15 + (skill - 11) * 0.05  # 0.15s to 0.3s
                    result = engine.play(board, chess.engine.Limit(depth=depth, time=think_time))
                    return result.move
                except:
                    pass
        
        # Fallback: Lichess cloud API
        cloud_move = get_lichess_move(board.fen(), skill)
        if cloud_move:
            try:
                move = chess.Move.from_uci(cloud_move)
                if move in legal_moves:
                    return move
            except:
                pass
        return get_random_smart_move(board, skill)
    
    # Skill 15-17: Advanced - plays well
    elif skill <= 17:
        if engine:
            with engine_lock:
                try:
                    engine.configure({"Skill Level": skill})
                    depth = skill - 2  # depth 13-15
                    think_time = 0.25 + (skill - 15) * 0.1  # 0.25s to 0.45s
                    result = engine.play(board, chess.engine.Limit(depth=depth, time=think_time))
                    return result.move
                except:
                    pass
        
        # Fallback: Lichess cloud API
        cloud_move = get_lichess_move(board.fen(), skill)
        if cloud_move:
            try:
                move = chess.Move.from_uci(cloud_move)
                if move in legal_moves:
                    return move
            except:
                pass
        return get_random_smart_move(board, skill)
    
    # Skill 18-20: Expert/Master - very strong
    else:
        if engine:
            with engine_lock:
                try:
                    engine.configure({"Skill Level": 20})
                    depth = 15 + (skill - 18)  # depth 15-17
                    think_time = 0.5 + (skill - 18) * 0.25  # 0.5s to 1.0s
                    result = engine.play(board, chess.engine.Limit(depth=depth, time=think_time))
                    return result.move
                except:
                    pass
        
        # Fallback: Lichess cloud API (best move for high skill)
        cloud_move = get_lichess_move(board.fen(), skill)
        if cloud_move:
            try:
                move = chess.Move.from_uci(cloud_move)
                if move in legal_moves:
                    return move
            except:
                pass
        return get_random_smart_move(board, skill)

def get_stockfish_path():
    """Find Stockfish engine - supports Windows and Linux"""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if we're on Linux (cloud deployment) or Windows (local)
    if sys.platform.startswith('linux'):
        possible_paths = [
            "/usr/games/stockfish",           # Ubuntu/Debian apt install
            "/usr/bin/stockfish",             # Some Linux distros
            "/usr/local/bin/stockfish",       # Manual install
            os.path.join(app_dir, "stockfish"),
        ]
    else:
        possible_paths = [
            os.path.join(app_dir, "stockfish.exe"),
            os.path.join(app_dir, "..", "dist", "stockfish.exe"),
            r"C:\Stockfish\stockfish\stockfish-windows-x86-64.exe",
            r"C:\Stockfish\stockfish.exe",
        ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def init_engine():
    """Initialize Stockfish engine"""
    global engine
    stockfish_path = get_stockfish_path()
    if stockfish_path:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
            print(f"✓ Stockfish loaded from: {stockfish_path}")
            return True
        except Exception as e:
            print(f"✗ Could not load Stockfish: {e}")
    else:
        print("✗ Stockfish not found")
    return False

# ============== ONLINE MULTIPLAYER (SOCKET.IO) ==============

@socketio.on('connect')
def handle_connect():
    print(f"Player connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Player disconnected: {sid}")
    
    # Remove from waiting list
    global waiting_players
    waiting_players = [p for p in waiting_players if p['sid'] != sid]
    
    # Handle if in a game
    if sid in player_sessions:
        game_id = player_sessions[sid].get('game_id')
        if game_id and game_id in online_games:
            game = online_games[game_id]
            opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
            emit('opponent_disconnected', {'message': 'Your opponent has disconnected'}, room=opponent_sid)
            del online_games[game_id]
        del player_sessions[sid]

@socketio.on('find_game')
def handle_find_game(data):
    """Player looking for a game"""
    username = data.get('username', 'Anonymous')
    time_control = data.get('time_control', 600)
    sid = request.sid
    
    player_data = {
        'sid': sid,
        'username': username,
        'time_control': time_control
    }
    player_sessions[sid] = player_data
    
    # Look for a matching player
    for waiting in waiting_players:
        if waiting['time_control'] == time_control and waiting['sid'] != sid:
            # Found a match! Create game
            game_id = str(uuid.uuid4())[:8]
            
            # Randomly assign colors
            import random
            if random.random() < 0.5:
                white_player, black_player = waiting, player_data
            else:
                white_player, black_player = player_data, waiting
            
            game = {
                'id': game_id,
                'board': chess.Board(),
                'white_sid': white_player['sid'],
                'black_sid': black_player['sid'],
                'white_username': white_player['username'],
                'black_username': black_player['username'],
                'white_time': time_control,
                'black_time': time_control,
                'time_control': time_control,
                'turn': 'white',
                'last_move_time': time.time(),
                'started': True
            }
            online_games[game_id] = game
            
            # Update player sessions
            player_sessions[white_player['sid']]['game_id'] = game_id
            player_sessions[white_player['sid']]['color'] = 'white'
            player_sessions[black_player['sid']]['game_id'] = game_id
            player_sessions[black_player['sid']]['color'] = 'black'
            
            # Remove matched player from waiting
            waiting_players.remove(waiting)
            
            # Notify both players
            emit('game_found', {
                'game_id': game_id,
                'color': 'white',
                'opponent': black_player['username'],
                'time_control': time_control,
                'fen': game['board'].fen()
            }, room=white_player['sid'])
            
            emit('game_found', {
                'game_id': game_id,
                'color': 'black',
                'opponent': white_player['username'],
                'time_control': time_control,
                'fen': game['board'].fen()
            }, room=black_player['sid'])
            
            print(f"Game started: {white_player['username']} vs {black_player['username']}")
            return
    
    # No match found, add to waiting list
    waiting_players.append(player_data)
    emit('waiting_for_opponent', {'message': 'Looking for an opponent...'})
    print(f"{username} is waiting for a game")

@socketio.on('cancel_search')
def handle_cancel_search():
    """Cancel game search"""
    global waiting_players
    sid = request.sid
    waiting_players = [p for p in waiting_players if p['sid'] != sid]
    emit('search_cancelled', {'message': 'Search cancelled'})

@socketio.on('online_move')
def handle_online_move(data):
    """Handle move in online game"""
    sid = request.sid
    game_id = data.get('game_id')
    move_uci = data.get('move')
    
    if game_id not in online_games:
        emit('error', {'message': 'Game not found'})
        return
    
    game = online_games[game_id]
    board = game['board']
    
    # Verify it's this player's turn
    is_white = game['white_sid'] == sid
    if (board.turn == chess.WHITE) != is_white:
        emit('error', {'message': 'Not your turn'})
        return
    
    try:
        move = chess.Move.from_uci(move_uci)
        if move not in board.legal_moves:
            emit('error', {'message': 'Illegal move'})
            return
        
        # Update time
        now = time.time()
        elapsed = now - game['last_move_time']
        if is_white:
            game['white_time'] -= elapsed
            if game['white_time'] <= 0:
                emit('game_over', {'result': 'loss', 'reason': 'timeout'}, room=sid)
                emit('game_over', {'result': 'win', 'reason': 'opponent timeout'}, room=game['black_sid'])
                del online_games[game_id]
                return
        else:
            game['black_time'] -= elapsed
            if game['black_time'] <= 0:
                emit('game_over', {'result': 'loss', 'reason': 'timeout'}, room=sid)
                emit('game_over', {'result': 'win', 'reason': 'opponent timeout'}, room=game['white_sid'])
                del online_games[game_id]
                return
        
        game['last_move_time'] = now
        
        # Make the move
        board.push(move)
        game['turn'] = 'black' if is_white else 'white'
        
        # Get opponent
        opponent_sid = game['black_sid'] if is_white else game['white_sid']
        
        # Check for game end
        if board.is_game_over():
            if board.is_checkmate():
                winner_sid = sid
                loser_sid = opponent_sid
                emit('game_over', {'result': 'win', 'reason': 'checkmate', 'fen': board.fen()}, room=winner_sid)
                emit('game_over', {'result': 'loss', 'reason': 'checkmate', 'fen': board.fen()}, room=loser_sid)
            else:
                emit('game_over', {'result': 'draw', 'reason': 'stalemate', 'fen': board.fen()}, room=sid)
                emit('game_over', {'result': 'draw', 'reason': 'stalemate', 'fen': board.fen()}, room=opponent_sid)
            del online_games[game_id]
            return
        
        # Send move to opponent
        emit('opponent_move', {
            'move': move_uci,
            'fen': board.fen(),
            'white_time': game['white_time'],
            'black_time': game['black_time']
        }, room=opponent_sid)
        
        # Confirm move to player
        emit('move_confirmed', {
            'fen': board.fen(),
            'white_time': game['white_time'],
            'black_time': game['black_time']
        })
        
    except Exception as e:
        emit('error', {'message': str(e)})

@socketio.on('resign_online')
def handle_resign():
    """Handle resignation"""
    sid = request.sid
    if sid not in player_sessions:
        return
    
    game_id = player_sessions[sid].get('game_id')
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('game_over', {'result': 'loss', 'reason': 'resignation'}, room=sid)
        emit('game_over', {'result': 'win', 'reason': 'opponent resigned'}, room=opponent_sid)
        del online_games[game_id]

@socketio.on('offer_draw')
def handle_draw_offer():
    """Handle draw offer"""
    sid = request.sid
    if sid not in player_sessions:
        return
    
    game_id = player_sessions[sid].get('game_id')
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('draw_offered', {'from': player_sessions[sid].get('username', 'Opponent')}, room=opponent_sid)

@socketio.on('accept_draw')
def handle_accept_draw():
    """Accept draw offer"""
    sid = request.sid
    if sid not in player_sessions:
        return
    
    game_id = player_sessions[sid].get('game_id')
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('game_over', {'result': 'draw', 'reason': 'agreement'}, room=sid)
        emit('game_over', {'result': 'draw', 'reason': 'agreement'}, room=opponent_sid)
        del online_games[game_id]

@socketio.on('decline_draw')
def handle_decline_draw():
    """Decline draw offer"""
    sid = request.sid
    if sid not in player_sessions:
        return
    
    game_id = player_sessions[sid].get('game_id')
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('draw_declined', {}, room=opponent_sid)

# ============== VOICE CHAT SIGNALING ==============

@socketio.on('voice_offer')
def handle_voice_offer(data):
    """Relay WebRTC offer to opponent"""
    sid = request.sid
    game_id = data.get('game_id')
    
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('voice_offer', {'offer': data['offer']}, room=opponent_sid)

@socketio.on('voice_answer')
def handle_voice_answer(data):
    """Relay WebRTC answer to opponent"""
    sid = request.sid
    game_id = data.get('game_id')
    
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('voice_answer', {'answer': data['answer']}, room=opponent_sid)

@socketio.on('voice_ice_candidate')
def handle_voice_ice_candidate(data):
    """Relay ICE candidates to opponent"""
    sid = request.sid
    game_id = data.get('game_id')
    
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('voice_ice_candidate', {'candidate': data['candidate']}, room=opponent_sid)

@socketio.on('talking_status')
def handle_talking_status(data):
    """Notify opponent when player is talking"""
    sid = request.sid
    game_id = data.get('game_id')
    
    if game_id and game_id in online_games:
        game = online_games[game_id]
        opponent_sid = game['white_sid'] if game['black_sid'] == sid else game['black_sid']
        emit('opponent_talking', {'talking': data['talking']}, room=opponent_sid)

# ============== ROUTES ==============

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/play')
def play():
    return render_template('index.html')

@app.route('/learn')
def learn():
    return render_template('learn.html')

@app.route('/review')
def review():
    return render_template('review.html')

# ============== API ENDPOINTS ==============

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get player statistics - user-specific if logged in"""
    username = session.get('user')
    stats = load_stats(username)
    return jsonify({'success': True, 'stats': stats, 'logged_in': username is not None})

@app.route('/api/stats/update', methods=['POST'])
def update_stats():
    """Update player statistics after a game"""
    data = request.json
    username = session.get('user')
    stats = load_stats(username)
    
    result = data.get('result', 'draw')
    accuracy = data.get('accuracy', 0)
    opponent_level = data.get('opponent_level', 10)
    
    stats['games_played'] += 1
    
    if result == 'win':
        stats['wins'] += 1
        stats['current_streak'] += 1
        rating_change = int(15 + opponent_level)
    elif result == 'loss' or result == 'lose':  # Accept both 'loss' and 'lose'
        stats['losses'] += 1
        stats['current_streak'] = 0
        rating_change = -int(10 + (20 - opponent_level) / 2)
    else:
        stats['draws'] += 1
        rating_change = int(5 if opponent_level > 10 else -2)
    
    stats['rating'] = max(100, stats['rating'] + rating_change)
    
    if stats['current_streak'] > stats['best_streak']:
        stats['best_streak'] = stats['current_streak']
    
    if accuracy > 0:
        if stats['games_played'] > 1:
            stats['total_accuracy'] = (stats['total_accuracy'] * (stats['games_played'] - 1) + accuracy) / stats['games_played']
        else:
            stats['total_accuracy'] = accuracy
        if accuracy > stats['best_accuracy']:
            stats['best_accuracy'] = accuracy
    
    stats['rating_history'].append({
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'rating': stats['rating']
    })
    stats['rating_history'] = stats['rating_history'][-100:]
    
    check_achievements(stats)
    save_stats(stats, username)
    return jsonify({'success': True, 'stats': stats, 'rating_change': rating_change})

def check_achievements(stats):
    """Check and award achievements"""
    achievements = stats.get('achievements', [])
    
    if stats['wins'] >= 1 and 'first_win' not in achievements:
        achievements.append('first_win')
    if stats['wins'] >= 10 and 'ten_wins' not in achievements:
        achievements.append('ten_wins')
    if stats['best_accuracy'] >= 90 and 'accuracy_90' not in achievements:
        achievements.append('accuracy_90')
    if stats['best_streak'] >= 5 and 'streak_5' not in achievements:
        achievements.append('streak_5')
    if stats['rating'] >= 1500 and 'rating_1500' not in achievements:
        achievements.append('rating_1500')
    
    stats['achievements'] = achievements

@app.route('/api/games', methods=['GET'])
def get_games():
    """Get saved games for review - user-specific if logged in"""
    username = session.get('user')
    games = load_games(username)
    return jsonify({'success': True, 'games': games})

@app.route('/api/games/save', methods=['POST'])
def save_game():
    """Save a completed game and update player style - user-specific if logged in"""
    data = request.json
    username = session.get('user')
    games = load_games(username)
    
    game_data = {
        'id': len(games) + 1,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'moves': data.get('moves', []),
        'result': data.get('result', ''),
        'player_color': data.get('player_color', 'white'),
        'opponent_level': data.get('opponent_level', 10),
        'accuracy': data.get('accuracy', 0),
        'move_evaluations': data.get('move_evaluations', [])
    }
    
    games.append(game_data)
    save_games(games, username)
    
    # Update player style for AI Clone learning
    try:
        update_player_style_from_game(game_data, username)
    except Exception as e:
        print(f"Error updating player style: {e}")
    
    return jsonify({'success': True, 'game_id': game_data['id']})

@app.route('/api/games/<int:game_id>', methods=['GET'])
def get_game(game_id):
    """Get a specific game for review - user-specific if logged in"""
    username = session.get('user')
    games = load_games(username)
    for game in games:
        if game.get('id') == game_id:
            return jsonify({'success': True, 'game': game})
    return jsonify({'success': False, 'error': 'Game not found'})

@app.route('/api/new_game', methods=['POST'])
def new_game():
    """Start a new game"""
    data = request.json or {}
    color = data.get('color', 'white')
    skill = data.get('skill', 10)
    
    if engine:
        with engine_lock:
            engine.configure({"Skill Level": skill})
    
    return jsonify({
        'success': True,
        'fen': chess.STARTING_FEN,
        'color': color,
        'skill': skill
    })

@app.route('/api/move', methods=['POST'])
def make_move():
    """Make a move and get engine response"""
    data = request.json
    fen = data.get('fen')
    move_uci = data.get('move')
    get_engine_move = data.get('get_engine_move', False)
    skill = data.get('skill', 10)
    
    board = chess.Board(fen)
    
    try:
        move = chess.Move.from_uci(move_uci)
        if move not in board.legal_moves:
            return jsonify({'success': False, 'error': 'Illegal move'})
        
        player_eval = analyze_move(board, move, skill)
        board.push(move)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    result = {
        'success': True,
        'fen': board.fen(),
        'player_eval': player_eval,
        'game_over': board.is_game_over(),
        'result': get_game_result(board) if board.is_game_over() else None
    }
    
    if get_engine_move and not board.is_game_over() and engine:
        try:
            engine_move = get_skill_adjusted_move(board, skill)
            if engine_move:
                board.push(engine_move)
                
                result['engine_move'] = engine_move.uci()
                result['fen'] = board.fen()
                result['game_over'] = board.is_game_over()
                result['result'] = get_game_result(board) if board.is_game_over() else None
        except Exception as e:
            result['engine_error'] = str(e)
    
    return jsonify(result)

@app.route('/api/engine_move', methods=['POST'])
def get_engine_move():
    """Get engine's move for current position"""
    data = request.json
    fen = data.get('fen')
    skill = data.get('skill', 10)
    
    if not engine:
        return jsonify({'success': False, 'error': 'Engine not available'})
    
    board = chess.Board(fen)
    
    if board.is_game_over():
        return jsonify({'success': False, 'error': 'Game is over'})
    
    try:
        # Use skill-adjusted move selection
        move = get_skill_adjusted_move(board, skill)
        
        if not move:
            return jsonify({'success': False, 'error': 'No legal moves'})
        
        # Get evaluation for display
        eval_cp = None
        with engine_lock:
            try:
                info = engine.analyse(board, chess.engine.Limit(time=0.1))
                score = info.get('score')
                if score:
                    if score.relative.is_mate():
                        eval_cp = 10000 if score.relative.mate() > 0 else -10000
                    else:
                        eval_cp = score.relative.score()
            except:
                pass
        
        board.push(move)
        
        return jsonify({
            'success': True,
            'move': move.uci(),
            'fen': board.fen(),
            'evaluation': eval_cp,
            'game_over': board.is_game_over(),
            'result': get_game_result(board) if board.is_game_over() else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/analyze', methods=['POST'])
def analyze_position():
    """Analyze a position"""
    data = request.json
    fen = data.get('fen')
    
    if not engine:
        return jsonify({'success': False, 'error': 'Engine not available'})
    
    board = chess.Board(fen)
    
    with engine_lock:
        try:
            info = engine.analyse(board, chess.engine.Limit(time=0.5))
            score = info.get('score')
            
            eval_cp = 0
            eval_display = "0.0"
            if score:
                if score.white().is_mate():
                    mate_in = score.white().mate()
                    eval_display = f"M{abs(mate_in)}" if mate_in > 0 else f"-M{abs(mate_in)}"
                    eval_cp = 10000 if mate_in > 0 else -10000
                else:
                    eval_cp = score.white().score()
                    eval_display = f"{eval_cp / 100:+.1f}"
            
            best_move = info.get('pv', [None])[0]
            
            return jsonify({
                'success': True,
                'evaluation': eval_cp,
                'eval_display': eval_display,
                'best_move': best_move.uci() if best_move else None
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

@app.route('/api/legal_moves', methods=['POST'])
def get_legal_moves():
    """Get legal moves for a position"""
    data = request.json
    fen = data.get('fen')
    square = data.get('square')
    
    board = chess.Board(fen)
    moves = []
    
    for move in board.legal_moves:
        if square is None or chess.square_name(move.from_square) == square:
            moves.append({
                'from': chess.square_name(move.from_square),
                'to': chess.square_name(move.to_square),
                'uci': move.uci(),
                'san': board.san(move),
                'is_capture': board.is_capture(move),
                'is_check': board.gives_check(move)
            })
    
    return jsonify({
        'success': True,
        'moves': moves,
        'turn': 'white' if board.turn else 'black'
    })

@app.route('/api/tips', methods=['GET'])
def get_tips():
    """Get chess learning tips"""
    tips = [
        {'category': 'Opening', 'title': 'Control the Center', 'content': 'Fight for control of e4, d4, e5, d5. Central pieces are stronger!', 'icon': '♟️'},
        {'category': 'Opening', 'title': 'Develop Your Pieces', 'content': 'Get knights and bishops out early. Develop a new piece each move.', 'icon': '♞'},
        {'category': 'Opening', 'title': 'Castle Early', 'content': 'Castle within 10 moves to protect your king and connect rooks.', 'icon': '♔'},
        {'category': 'Tactics', 'title': 'Look for Forks', 'content': 'Attack two pieces at once. Knights are excellent forking pieces!', 'icon': '⚔️'},
        {'category': 'Tactics', 'title': 'Pin and Win', 'content': 'Pin pieces to the king or queen. They cannot move without losing material.', 'icon': '📌'},
        {'category': 'Tactics', 'title': 'Checks First', 'content': 'Always look for checks. They force your opponent to respond.', 'icon': '✓'},
        {'category': 'Strategy', 'title': 'Piece Activity', 'content': 'Active pieces are powerful. Make sure all pieces have good squares.', 'icon': '🎯'},
        {'category': 'Strategy', 'title': 'Pawn Structure', 'content': 'Avoid doubled and isolated pawns. Strong pawns = strong position.', 'icon': '🏰'},
        {'category': 'Endgame', 'title': 'Activate Your King', 'content': 'In endgames, your king is a fighting piece. Bring it forward!', 'icon': '👑'},
        {'category': 'Endgame', 'title': 'Push Passed Pawns', 'content': 'Passed pawns are precious. Push them to promote to a queen!', 'icon': '🚀'}
    ]
    return jsonify({'success': True, 'tips': tips})

def analyze_move(board, move, skill=10):
    """Analyze quality of a move - fast version"""
    if not engine:
        return {'quality': 'unknown', 'cpl': 0}
    
    with engine_lock:
        try:
            # Fast analysis - just check if move matches engine's choice
            best_move_info = engine.play(board, chess.engine.Limit(time=0.05))
            best_move = best_move_info.move
            
            info_before = engine.analyse(board, chess.engine.Limit(depth=8))
            score_before = info_before.get('score')
            
            board.push(move)
            info_after = engine.analyse(board, chess.engine.Limit(depth=8))
            score_after = info_after.get('score')
            board.pop()
            
            if score_before and score_after:
                eval_before = get_cp_score(score_before, board.turn)
                
                board.push(best_move)
                info_best = engine.analyse(board, chess.engine.Limit(depth=6))
                score_best = info_best.get('score')
                board.pop()
                
                eval_best = get_cp_score(score_best, not board.turn) if score_best else eval_before
                eval_after = get_cp_score(score_after, not board.turn)
                
                cpl = max(0, eval_best - eval_after)
                
                if move == best_move:
                    quality = 'best'
                elif cpl <= 10:
                    quality = 'excellent'
                elif cpl <= 25:
                    quality = 'good'
                elif cpl <= 50:
                    quality = 'inaccuracy'
                elif cpl <= 100:
                    quality = 'mistake'
                else:
                    quality = 'blunder'
                
                return {
                    'quality': quality,
                    'cpl': cpl,
                    'best_move': best_move.uci() if best_move != move else None
                }
        except Exception as e:
            print(f"Analysis error: {e}")
    
    return {'quality': 'unknown', 'cpl': 0}

def get_cp_score(score, is_white_perspective):
    """Get centipawn score from perspective"""
    if score.is_mate():
        return 10000 if (score.white().mate() > 0) == is_white_perspective else -10000
    return score.white().score() if is_white_perspective else -score.white().score()

def get_game_result(board):
    """Get game result string"""
    if board.is_checkmate():
        return "Black wins by checkmate" if board.turn else "White wins by checkmate"
    elif board.is_stalemate():
        return "Draw by stalemate"
    elif board.is_insufficient_material():
        return "Draw by insufficient material"
    elif board.is_fifty_moves():
        return "Draw by fifty-move rule"
    elif board.is_repetition():
        return "Draw by repetition"
    return "Game over"

# ============== CLONE AI ENDPOINTS ==============

@app.route('/api/clone/move', methods=['POST'])
def get_clone_move():
    """Get AI Clone's move based on learned player style"""
    data = request.json
    fen = data.get('fen')
    player_color = data.get('clone_color', 'white')  # What color the clone is playing as
    
    board = chess.Board(fen)
    
    if board.is_game_over():
        return jsonify({'success': False, 'error': 'Game is over'})
    
    # Get learned clone move
    move, move_source = get_clone_best_move(board, player_color)
    
    if move:
        return jsonify({
            'success': True,
            'move': move.uci(),
            'move_san': board.san(move),
            'source': move_source  # 'learned', 'style', or 'engine_fallback'
        })
    else:
        return jsonify({'success': False, 'error': 'Could not determine move'})

@app.route('/api/clone/style', methods=['GET'])
def get_clone_style():
    """Get the current player style profile"""
    style = load_player_style()
    return jsonify({'success': True, 'style': style})

@app.route('/api/clone/status', methods=['GET'])
def get_clone_status():
    """Check if clone is unlocked and get learning progress"""
    stats = load_stats()
    style = load_player_style()
    model = load_clone_model()
    
    games_played = stats.get('games_played', 0)
    games_needed = 10
    is_unlocked = games_played >= games_needed
    
    return jsonify({
        'success': True,
        'unlocked': is_unlocked,
        'games_played': games_played,
        'games_needed': games_needed,
        'games_analyzed': style.get('games_analyzed', 0),
        'positions_learned': len(model),
        'risk_profile': style.get('risk_profile', {}).get('base_risk', 0.5),
        'favorite_openings': style.get('favorite_openings', {}),
        'first_moves_white': style.get('first_moves_white', {}),
        'first_moves_black': style.get('first_moves_black', {})
    })

def get_clone_best_move(board, clone_color):
    """Determine the best move for the clone based on learned style + engine verification"""
    import random
    
    style = load_player_style()
    model = load_clone_model()
    
    # Get position key for lookup
    board_key = board.fen().split()[0]
    color_char = clone_color[0] if clone_color else ('w' if board.turn else 'b')
    composite_key = f"{board_key}::{color_char}"
    
    legal_moves = list(board.legal_moves)
    
    if not legal_moves:
        return None, 'no_moves'
    
    # Get engine evaluation for all legal moves to filter out blunders
    move_evaluations = {}
    if engine:
        with engine_lock:
            try:
                # Get the current position evaluation
                info = engine.analyse(board, chess.engine.Limit(time=0.1))
                base_score = info.get('score')
                base_eval = 0
                if base_score:
                    pov = base_score.white() if board.turn == chess.WHITE else base_score.black()
                    if pov.is_mate():
                        base_eval = 10000 if pov.mate() > 0 else -10000
                    else:
                        base_eval = pov.score() or 0
                
                # Evaluate each move quickly
                for move in legal_moves:
                    board.push(move)
                    try:
                        info = engine.analyse(board, chess.engine.Limit(time=0.05))
                        score = info.get('score')
                        if score:
                            # Get from opponent's perspective after move
                            pov = score.white() if board.turn == chess.WHITE else score.black()
                            if pov.is_mate():
                                eval_cp = -10000 if pov.mate() > 0 else 10000
                            else:
                                eval_cp = -(pov.score() or 0)  # Negate because it's opponent's turn
                            move_evaluations[move] = eval_cp
                    except:
                        move_evaluations[move] = 0
                    board.pop()
            except Exception as e:
                print(f"Engine analysis error: {e}")
    
    # Filter out blunders (moves that lose more than 200 centipawns)
    if move_evaluations:
        best_eval = max(move_evaluations.values()) if move_evaluations else 0
        good_moves = [m for m in legal_moves if move_evaluations.get(m, 0) >= best_eval - 200]
        if good_moves:
            legal_moves = good_moves
    
    # 1. First, check if we have an exact position match in learned model
    if composite_key in model:
        position_moves = model[composite_key]
        # Weight moves by how often player chose them
        weighted_moves = []
        for move_uci, data in position_moves.items():
            try:
                move = chess.Move.from_uci(move_uci)
                if move in legal_moves:  # Only consider non-blunder moves
                    weight = data.get('count', 1) * data.get('weight', 1.0)
                    # Boost weight if engine says it's a good move
                    if move in move_evaluations and move_evaluations[move] >= best_eval - 50:
                        weight *= 2.0
                    weighted_moves.append((move, weight))
            except:
                continue
        
        if weighted_moves:
            # Select move probabilistically based on weights
            total_weight = sum(w for _, w in weighted_moves)
            r = random.random() * total_weight
            cumulative = 0
            for move, weight in weighted_moves:
                cumulative += weight
                if r <= cumulative:
                    return move, 'learned'
            return weighted_moves[0][0], 'learned'
    
    # 2. If no exact match, use style-based selection on good moves
    move_scores = []
    risk_tolerance = style.get('risk_profile', {}).get('base_risk', 0.5)
    
    for move in legal_moves:
        score = 0.0
        move_info = analyze_move_type(board, move)
        piece = move_info['piece_moved']
        
        # Score based on player's piece preferences
        piece_activity = style.get('piece_activity', {})
        total_piece_moves = sum(piece_activity.values()) or 1
        
        if piece:
            if piece.piece_type == chess.KNIGHT:
                score += piece_activity.get('knight_moves', 0) / total_piece_moves
            elif piece.piece_type == chess.BISHOP:
                score += piece_activity.get('bishop_moves', 0) / total_piece_moves
            elif piece.piece_type == chess.ROOK:
                score += piece_activity.get('rook_moves', 0) / total_piece_moves
            elif piece.piece_type == chess.QUEEN:
                score += piece_activity.get('queen_moves', 0) / total_piece_moves
            elif piece.piece_type == chess.PAWN:
                score += piece_activity.get('pawn_pushes', 0) / total_piece_moves
        
        # Score based on risk profile
        risk_profile = style.get('risk_profile', {})
        total_moves = risk_profile.get('total_moves', 1) or 1
        
        if move_info['is_capture']:
            capture_rate = risk_profile.get('captures', 0) / total_moves
            score += capture_rate * 2 * risk_tolerance
        
        if move_info['is_check']:
            check_rate = risk_profile.get('checks', 0) / total_moves
            score += check_rate * 3 * risk_tolerance
        
        if move_info['is_aggressive']:
            agg_rate = risk_profile.get('aggressive_moves', 0) / total_moves
            score += agg_rate * risk_tolerance
        
        if move_info['is_defensive']:
            def_rate = risk_profile.get('defensive_moves', 0) / total_moves
            score += def_rate * (1 - risk_tolerance)
        
        # Opening phase: use learned first moves
        move_number = len(board.move_stack)
        if move_number < 2:
            san = board.san(move)
            if board.turn == chess.WHITE:
                first_moves = style.get('first_moves_white', {})
                if san in first_moves:
                    score += first_moves[san] * 0.5
            else:
                first_moves = style.get('first_moves_black', {})
                if san in first_moves:
                    score += first_moves[san] * 0.5
        
        # Castling preference
        if move_info['is_castle']:
            positional = style.get('positional', {})
            total_castles = positional.get('castles_kingside', 0) + positional.get('castles_queenside', 0) + 1
            if 'O-O-O' in board.san(move):
                score += positional.get('castles_queenside', 0) / total_castles * 0.3
            else:
                score += positional.get('castles_kingside', 0) / total_castles * 0.3
        
        # Boost score for moves that are objectively good
        if move in move_evaluations and move_evaluations:
            best_eval = max(move_evaluations.values())
            move_eval = move_evaluations[move]
            # Normalize engine evaluation to 0-1 range
            eval_bonus = max(0, (move_eval - (best_eval - 200)) / 200)
            score += eval_bonus * 0.5
        
        # Add some randomness to make it less predictable
        score += random.random() * 0.15
        
        move_scores.append((move, score))
    
    if move_scores:
        # Sort by score and pick from top moves with some randomness
        move_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Pick from top 3 moves probabilistically
        top_moves = move_scores[:min(3, len(move_scores))]
        total_score = sum(s for _, s in top_moves) or 1
        
        r = random.random() * total_score
        cumulative = 0
        for move, score in top_moves:
            cumulative += score
            if r <= cumulative:
                return move, 'style'
        
        return top_moves[0][0], 'style'
    
    # 3. Fallback to engine - match user's approximate skill level
    if engine:
        with engine_lock:
            try:
                # Use skill level 10-12 for reasonable challenge
                stats = load_stats()
                user_rating = stats.get('rating', 1200)
                # Map rating to skill level (rough estimate)
                skill = min(15, max(5, int((user_rating - 800) / 100)))
                engine.configure({"Skill Level": skill})
                result = engine.play(board, chess.engine.Limit(time=0.3))
                return result.move, 'engine_fallback'
            except:
                pass
    
    # Last resort: random legal move from good moves
    return random.choice(legal_moves), 'random'

if __name__ == '__main__':
    print("="*50)
    print("♟️  AIgambit.com - Your Chess Platform")
    print("="*50)
    
    init_engine()
    
    print("\n🌐 Starting server with WebSocket support...")
    print("   Open in browser: http://localhost:5000")
    print("   Press Ctrl+C to stop\n")
    
    import webbrowser
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
