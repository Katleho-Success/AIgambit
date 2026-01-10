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
import hashlib
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'aigambit_secret_key_2025_secure'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global engine instance
engine = None
engine_lock = threading.Lock()

# Online games storage
online_games = {}  # game_id -> game data
waiting_players = []  # list of players waiting for match
player_sessions = {}  # socket_id -> player data
matchmaking_lock = threading.Lock()

# Time control presets (in seconds)
TIME_PRESETS = {
    'bullet1': 60,      # 1 min
    'bullet2': 120,     # 2 min
    'blitz3': 180,      # 3 min
    'blitz5': 300,      # 5 min
    'rapid10': 600,     # 10 min
    'rapid15': 900,     # 15 min
    'rapid30': 1800,    # 30 min
}

# Tournament storage
tournaments = {}  # tournament_id -> tournament data
TOURNAMENTS_FILE = os.path.join(os.path.dirname(__file__), 'tournaments.json')

# Data directory for user-specific files
DATA_DIR = os.path.join(os.path.dirname(__file__), 'user_data')
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ============== USER AUTHENTICATION ==============

def hash_password(password):
    """Hash password using SHA256 with salt"""
    salt = "aigambit_salt_2025"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def load_users():
    """Load all users"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_users(users):
    """Save users database"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        print(f"Error saving users: {e}")

def get_current_user():
    """Get the current logged-in user from session"""
    return session.get('username', None)

def get_user_data_path(username, filename):
    """Get path to user-specific data file"""
    user_dir = os.path.join(DATA_DIR, username)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return os.path.join(user_dir, filename)

# ============== USER-SPECIFIC DATA FUNCTIONS ==============

def load_user_stats(username=None):
    """Load player statistics for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return get_default_stats()
    
    stats_file = get_user_data_path(username, 'stats.json')
    if os.path.exists(stats_file):
        try:
            with open(stats_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return get_default_stats()

def save_user_stats(stats, username=None):
    """Save player statistics for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return False
    
    stats_file = get_user_data_path(username, 'stats.json')
    try:
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving stats for {username}: {e}")
        return False

def load_user_games(username=None):
    """Load saved games for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return []
    
    games_file = get_user_data_path(username, 'games.json')
    if os.path.exists(games_file):
        try:
            with open(games_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_user_games(games, username=None):
    """Save games list for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return False
    
    games_file = get_user_data_path(username, 'games.json')
    try:
        games = games[-50:]  # Keep last 50 games
        with open(games_file, 'w') as f:
            json.dump(games, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving games for {username}: {e}")
        return False

def load_user_style(username=None):
    """Load player style for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return init_player_style()
    
    style_file = get_user_data_path(username, 'player_style.json')
    if os.path.exists(style_file):
        try:
            with open(style_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return init_player_style()

def save_user_style(style, username=None):
    """Save player style for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return False
    
    style_file = get_user_data_path(username, 'player_style.json')
    try:
        with open(style_file, 'w') as f:
            json.dump(style, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving style for {username}: {e}")
        return False

def load_user_clone_model(username=None):
    """Load clone model for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return {}
    
    model_file = get_user_data_path(username, 'clone_model.json')
    if os.path.exists(model_file):
        try:
            with open(model_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_clone_model(model, username=None):
    """Save clone model for specific user"""
    if username is None:
        username = get_current_user()
    if username is None:
        return False
    
    model_file = get_user_data_path(username, 'clone_model.json')
    try:
        with open(model_file, 'w') as f:
            json.dump(model, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving clone model for {username}: {e}")
        return False

def get_default_stats():
    """Return default stats for new users"""
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

# Legacy compatibility functions (redirect to user-specific)
def load_stats():
    return load_user_stats()

def save_stats(stats):
    return save_user_stats(stats)

def load_games():
    return load_user_games()

def save_games(games):
    return save_user_games(games)

def load_player_style():
    return load_user_style()

def save_player_style(style):
    return save_user_style(style)

def load_clone_model():
    return load_user_clone_model()

def save_clone_model(model):
    return save_user_clone_model(model)

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

def save_player_style(style):
    """Save player style profile - redirects to user-specific version"""
    return save_user_style(style)

def load_clone_model():
    """Load the clone model - redirects to user-specific version"""
    return load_user_clone_model()

def save_clone_model(model):
    """Save clone model - redirects to user-specific version"""
    return save_user_clone_model(model)

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

def update_player_style_from_game(game_data):
    """Update player style based on a completed game"""
    style = load_player_style()
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
                update_clone_model_position(board.fen(), move.uci(), player_color)
                
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
    
    save_player_style(style)

def update_clone_model_position(fen, move_uci, player_color):
    """Update clone model with a position -> move mapping"""
    model = load_clone_model()
    
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
    
    save_clone_model(model)

def get_skill_adjusted_move(board, skill):
    """
    Get a move adjusted for skill level (1-20).
    Lower skill = more mistakes, random moves, misses tactics.
    NOTE: This function should be called WITHOUT engine_lock held.
    """
    import random
    
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
        
        return random.choice(legal_moves)
    
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
        
        return random.choice(legal_moves)
    
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
        
        return random.choice(legal_moves)
    
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
        
        return random.choice(legal_moves)
    
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
        
        return random.choice(legal_moves)
    
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
        
        return random.choice(legal_moves)

def get_stockfish_path():
    """Find Stockfish engine"""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
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
    flexible = data.get('flexible', False)  # Accept flexible matching
    rating = data.get('rating', 1200)
    sid = request.sid
    
    player_data = {
        'sid': sid,
        'username': username,
        'time_control': time_control,
        'flexible': flexible,
        'rating': rating,
        'search_start': time.time()
    }
    player_sessions[sid] = player_data
    
    with matchmaking_lock:
        # First try exact time control match
        for waiting in waiting_players:
            if waiting['time_control'] == time_control and waiting['sid'] != sid:
                # Found an exact match! Create game
                create_online_game(waiting, player_data, time_control)
                return
        
        # If flexible matching is enabled, try to find any match
        if flexible:
            for waiting in waiting_players:
                if waiting['sid'] != sid and waiting.get('flexible', False):
                    # Both players are flexible - find middle ground
                    avg_time = (waiting['time_control'] + time_control) // 2
                    # Round to nearest standard time
                    standard_times = [60, 120, 180, 300, 600, 900, 1800]
                    matched_time = min(standard_times, key=lambda x: abs(x - avg_time))
                    create_online_game(waiting, player_data, matched_time)
                    return
        
        # No match found, add to waiting list
        waiting_players.append(player_data)
        emit('waiting_for_opponent', {
            'message': 'Looking for an opponent...',
            'queue_position': len(waiting_players),
            'time_control': time_control,
            'flexible': flexible
        })
        print(f"{username} is waiting for a game ({time_control}s, flexible={flexible})")

def create_online_game(player1, player2, time_control):
    """Create a game between two players"""
    import random
    
    game_id = str(uuid.uuid4())[:8]
    
    # Randomly assign colors
    if random.random() < 0.5:
        white_player, black_player = player1, player2
    else:
        white_player, black_player = player2, player1
    
    game = {
        'id': game_id,
        'board': chess.Board(),
        'white_sid': white_player['sid'],
        'black_sid': black_player['sid'],
        'white_username': white_player['username'],
        'black_username': black_player['username'],
        'white_rating': white_player.get('rating', 1200),
        'black_rating': black_player.get('rating', 1200),
        'white_time': time_control,
        'black_time': time_control,
        'time_control': time_control,
        'original_white_time': player1['time_control'],
        'original_black_time': player2['time_control'],
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
    global waiting_players
    waiting_players = [p for p in waiting_players if p['sid'] not in [player1['sid'], player2['sid']]]
    
    # Format time for display
    def format_time(seconds):
        if seconds >= 60:
            return f"{seconds // 60} min"
        return f"{seconds} sec"
    
    matched_msg = ""
    if player1['time_control'] != time_control or player2['time_control'] != time_control:
        matched_msg = f" (matched at {format_time(time_control)})"
    
    # Notify both players
    socketio.emit('game_found', {
        'game_id': game_id,
        'color': 'white',
        'opponent': black_player['username'],
        'opponent_rating': black_player.get('rating', 1200),
        'time_control': time_control,
        'time_display': format_time(time_control),
        'matched_message': matched_msg,
        'fen': game['board'].fen()
    }, room=white_player['sid'])
    
    socketio.emit('game_found', {
        'game_id': game_id,
        'color': 'black',
        'opponent': white_player['username'],
        'opponent_rating': white_player.get('rating', 1200),
        'time_control': time_control,
        'time_display': format_time(time_control),
        'matched_message': matched_msg,
        'fen': game['board'].fen()
    }, room=black_player['sid'])
    
    print(f"Game started: {white_player['username']} vs {black_player['username']} ({format_time(time_control)}{matched_msg})")

@socketio.on('enable_flexible_matching')
def handle_enable_flexible(data):
    """Enable flexible matching for a waiting player"""
    sid = request.sid
    
    with matchmaking_lock:
        # Update player's flexible status
        for player in waiting_players:
            if player['sid'] == sid:
                player['flexible'] = True
                
                # Try to find a flexible match now
                for other in waiting_players:
                    if other['sid'] != sid and other.get('flexible', False):
                        # Found another flexible player
                        avg_time = (player['time_control'] + other['time_control']) // 2
                        standard_times = [60, 120, 180, 300, 600, 900, 1800]
                        matched_time = min(standard_times, key=lambda x: abs(x - avg_time))
                        create_online_game(player, other, matched_time)
                        return
                
                emit('flexible_enabled', {'message': 'Flexible matching enabled'})
                return
        
        emit('error', {'message': 'Not in queue'})

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

# ============== AUTHENTICATION ENDPOINTS ==============

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """Register a new user"""
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    
    # Validation
    if len(username) < 3 or len(username) > 20:
        return jsonify({'success': False, 'error': 'Username must be 3-20 characters'})
    
    if not username.isalnum():
        return jsonify({'success': False, 'error': 'Username must be alphanumeric'})
    
    if len(password) < 4:
        return jsonify({'success': False, 'error': 'Password must be at least 4 characters'})
    
    users = load_users()
    
    if username in users:
        return jsonify({'success': False, 'error': 'Username already taken'})
    
    # Create user
    users[username] = {
        'password_hash': hash_password(password),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'display_name': data.get('display_name', username)
    }
    save_users(users)
    
    # Initialize user data
    save_user_stats(get_default_stats(), username)
    save_user_games([], username)
    save_user_style(init_player_style(), username)
    save_user_clone_model({}, username)
    
    # Log them in
    session['username'] = username
    session['display_name'] = users[username]['display_name']
    
    return jsonify({
        'success': True,
        'message': 'Account created successfully!',
        'user': {
            'username': username,
            'display_name': users[username]['display_name']
        }
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Log in a user"""
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    
    users = load_users()
    
    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'})
    
    if users[username]['password_hash'] != hash_password(password):
        return jsonify({'success': False, 'error': 'Incorrect password'})
    
    # Set session
    session['username'] = username
    session['display_name'] = users[username].get('display_name', username)
    
    # Load user stats
    stats = load_user_stats(username)
    
    return jsonify({
        'success': True,
        'message': 'Login successful!',
        'user': {
            'username': username,
            'display_name': users[username].get('display_name', username)
        },
        'stats': stats
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Log out current user"""
    session.pop('username', None)
    session.pop('display_name', None)
    return jsonify({'success': True, 'message': 'Logged out'})

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Check if user is logged in"""
    username = get_current_user()
    if username:
        users = load_users()
        display_name = users.get(username, {}).get('display_name', username)
        stats = load_user_stats(username)
        return jsonify({
            'logged_in': True,
            'user': {
                'username': username,
                'display_name': display_name
            },
            'stats': stats
        })
    return jsonify({'logged_in': False})

@app.route('/api/auth/change-password', methods=['POST'])
def change_password():
    """Change user password"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    data = request.json
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    users = load_users()
    
    if users[username]['password_hash'] != hash_password(old_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect'})
    
    if len(new_password) < 4:
        return jsonify({'success': False, 'error': 'New password must be at least 4 characters'})
    
    users[username]['password_hash'] = hash_password(new_password)
    save_users(users)
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})

# ============== TOURNAMENT SYSTEM ==============

def load_tournaments():
    """Load all tournaments from file"""
    global tournaments
    if os.path.exists(TOURNAMENTS_FILE):
        try:
            with open(TOURNAMENTS_FILE, 'r') as f:
                tournaments = json.load(f)
        except:
            tournaments = {}
    return tournaments

def save_tournaments():
    """Save tournaments to file"""
    try:
        with open(TOURNAMENTS_FILE, 'w') as f:
            json.dump(tournaments, f, indent=2)
    except Exception as e:
        print(f"Error saving tournaments: {e}")

def generate_tournament_id():
    """Generate unique tournament ID"""
    return str(uuid.uuid4())[:8].upper()

def get_tournament_status(tournament):
    """Determine tournament status based on time"""
    now = datetime.now()
    start_time = datetime.strptime(tournament['start_time'], '%Y-%m-%dT%H:%M')
    
    if tournament.get('finished'):
        return 'finished'
    elif tournament.get('started'):
        return 'in_progress'
    elif now >= start_time:
        return 'starting'
    else:
        return 'upcoming'

def calculate_swiss_pairings(tournament):
    """Generate Swiss-system pairings for next round"""
    players = tournament['players']
    standings = tournament.get('standings', {})
    
    # Sort players by score
    sorted_players = sorted(players, key=lambda p: standings.get(p['username'], {}).get('score', 0), reverse=True)
    
    pairings = []
    paired = set()
    
    for i, player in enumerate(sorted_players):
        if player['username'] in paired:
            continue
            
        # Find opponent (next unpaired player)
        for j in range(i + 1, len(sorted_players)):
            opponent = sorted_players[j]
            if opponent['username'] not in paired:
                pairings.append({
                    'white': player,
                    'black': opponent,
                    'game_id': str(uuid.uuid4())[:8],
                    'result': None
                })
                paired.add(player['username'])
                paired.add(opponent['username'])
                break
    
    # Handle bye if odd number of players
    for player in sorted_players:
        if player['username'] not in paired:
            pairings.append({
                'white': player,
                'black': None,  # Bye
                'game_id': None,
                'result': 'bye'
            })
            # Player with bye gets 1 point
            if player['username'] not in standings:
                standings[player['username']] = {'score': 0, 'games': 0, 'wins': 0, 'draws': 0, 'losses': 0}
            standings[player['username']]['score'] += 1
    
    return pairings

def calculate_arena_standings(tournament):
    """Calculate arena tournament standings"""
    standings = tournament.get('standings', {})
    players = tournament['players']
    
    result = []
    for player in players:
        username = player['username']
        stats = standings.get(username, {'score': 0, 'games': 0, 'wins': 0, 'draws': 0, 'losses': 0})
        result.append({
            'username': username,
            'display_name': player.get('display_name', username),
            'rating': player.get('rating', 1200),
            **stats
        })
    
    return sorted(result, key=lambda x: (-x['score'], -x['wins']))

@app.route('/api/tournaments', methods=['GET'])
def list_tournaments():
    """List all tournaments"""
    load_tournaments()
    
    result = []
    for tid, t in tournaments.items():
        status = get_tournament_status(t)
        result.append({
            'id': tid,
            'name': t['name'],
            'creator': t['creator'],
            'format': t['format'],
            'time_control': t['time_control'],
            'start_time': t['start_time'],
            'max_players': t['max_players'],
            'player_count': len(t['players']),
            'status': status,
            'rated': t.get('rated', True),
            'description': t.get('description', '')
        })
    
    # Sort by start time (upcoming first)
    result.sort(key=lambda x: x['start_time'])
    return jsonify({'success': True, 'tournaments': result})

@app.route('/api/tournaments/create', methods=['POST'])
def create_tournament():
    """Create a new tournament"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'error': 'Must be logged in to create tournaments'})
    
    data = request.json
    
    # Validate required fields
    name = data.get('name', '').strip()
    if not name or len(name) < 3:
        return jsonify({'success': False, 'error': 'Tournament name must be at least 3 characters'})
    
    format_type = data.get('format', 'arena')
    if format_type not in ['arena', 'swiss', 'elimination']:
        return jsonify({'success': False, 'error': 'Invalid tournament format'})
    
    # Time control: minutes + increment
    time_minutes = int(data.get('time_minutes', 10))
    time_increment = int(data.get('time_increment', 0))
    if time_minutes < 1 or time_minutes > 180:
        return jsonify({'success': False, 'error': 'Time control must be 1-180 minutes'})
    
    # Start time
    start_time = data.get('start_time')
    try:
        start_dt = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
        if start_dt < datetime.now():
            return jsonify({'success': False, 'error': 'Start time must be in the future'})
    except:
        return jsonify({'success': False, 'error': 'Invalid start time format'})
    
    max_players = int(data.get('max_players', 64))
    if max_players < 4 or max_players > 256:
        return jsonify({'success': False, 'error': 'Max players must be 4-256'})
    
    # Create tournament
    tid = generate_tournament_id()
    users = load_users()
    creator_display = users.get(username, {}).get('display_name', username)
    creator_stats = load_user_stats(username)
    
    tournaments[tid] = {
        'id': tid,
        'name': name,
        'creator': username,
        'creator_display': creator_display,
        'format': format_type,
        'time_control': f"{time_minutes}+{time_increment}",
        'time_minutes': time_minutes,
        'time_increment': time_increment,
        'start_time': start_time,
        'max_players': max_players,
        'rated': data.get('rated', True),
        'description': data.get('description', ''),
        'players': [{
            'username': username,
            'display_name': creator_display,
            'rating': creator_stats.get('rating', 1200),
            'joined_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }],
        'rounds': [],
        'standings': {},
        'current_round': 0,
        'started': False,
        'finished': False,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    save_tournaments()
    
    return jsonify({
        'success': True,
        'tournament_id': tid,
        'message': f'Tournament "{name}" created!'
    })

@app.route('/api/tournaments/<tid>', methods=['GET'])
def get_tournament(tid):
    """Get tournament details"""
    load_tournaments()
    
    if tid not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    t = tournaments[tid]
    status = get_tournament_status(t)
    standings = calculate_arena_standings(t) if t['format'] == 'arena' else []
    
    return jsonify({
        'success': True,
        'tournament': {
            **t,
            'status': status,
            'standings': standings
        }
    })

@app.route('/api/tournaments/<tid>/join', methods=['POST'])
def join_tournament(tid):
    """Join a tournament"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'error': 'Must be logged in to join tournaments'})
    
    load_tournaments()
    
    if tid not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    t = tournaments[tid]
    
    # Check if already joined
    for p in t['players']:
        if p['username'] == username:
            return jsonify({'success': False, 'error': 'Already joined this tournament'})
    
    # Check if full
    if len(t['players']) >= t['max_players']:
        return jsonify({'success': False, 'error': 'Tournament is full'})
    
    # Check if started
    if t['started']:
        return jsonify({'success': False, 'error': 'Tournament has already started'})
    
    # Add player
    users = load_users()
    display_name = users.get(username, {}).get('display_name', username)
    stats = load_user_stats(username)
    
    t['players'].append({
        'username': username,
        'display_name': display_name,
        'rating': stats.get('rating', 1200),
        'joined_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    
    save_tournaments()
    
    # Notify other players
    socketio.emit('tournament_update', {
        'tournament_id': tid,
        'type': 'player_joined',
        'player': {'username': username, 'display_name': display_name}
    }, room=f'tournament_{tid}')
    
    return jsonify({'success': True, 'message': 'Joined tournament!'})

@app.route('/api/tournaments/<tid>/leave', methods=['POST'])
def leave_tournament(tid):
    """Leave a tournament"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'error': 'Must be logged in'})
    
    load_tournaments()
    
    if tid not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    t = tournaments[tid]
    
    if t['started']:
        return jsonify({'success': False, 'error': 'Cannot leave a started tournament'})
    
    # Remove player
    t['players'] = [p for p in t['players'] if p['username'] != username]
    
    # If creator left and no players, delete tournament
    if len(t['players']) == 0:
        del tournaments[tid]
    elif t['creator'] == username and len(t['players']) > 0:
        # Transfer ownership to first player
        t['creator'] = t['players'][0]['username']
    
    save_tournaments()
    
    # Notify other players
    socketio.emit('tournament_update', {
        'tournament_id': tid,
        'type': 'player_left',
        'username': username
    }, room=f'tournament_{tid}')
    
    return jsonify({'success': True, 'message': 'Left tournament'})

@app.route('/api/tournaments/<tid>/start', methods=['POST'])
def start_tournament(tid):
    """Start a tournament (creator only)"""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'error': 'Must be logged in'})
    
    load_tournaments()
    
    if tid not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    t = tournaments[tid]
    
    if t['creator'] != username:
        return jsonify({'success': False, 'error': 'Only the creator can start the tournament'})
    
    if len(t['players']) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 players to start'})
    
    if t['started']:
        return jsonify({'success': False, 'error': 'Tournament already started'})
    
    # Initialize standings
    t['standings'] = {}
    for p in t['players']:
        t['standings'][p['username']] = {
            'score': 0,
            'games': 0,
            'wins': 0,
            'draws': 0,
            'losses': 0
        }
    
    # Generate first round pairings
    if t['format'] == 'swiss':
        t['current_round'] = 1
        t['rounds'].append({
            'round': 1,
            'pairings': calculate_swiss_pairings(t),
            'completed': False
        })
    
    t['started'] = True
    t['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    save_tournaments()
    
    # Notify all players
    socketio.emit('tournament_update', {
        'tournament_id': tid,
        'type': 'tournament_started',
        'tournament': t
    }, room=f'tournament_{tid}')
    
    return jsonify({'success': True, 'message': 'Tournament started!'})

@app.route('/api/tournaments/<tid>/pairings', methods=['GET'])
def get_tournament_pairings(tid):
    """Get current pairings for a tournament"""
    load_tournaments()
    
    if tid not in tournaments:
        return jsonify({'success': False, 'error': 'Tournament not found'})
    
    t = tournaments[tid]
    current_round = t.get('current_round', 0)
    
    if current_round == 0 or not t['rounds']:
        return jsonify({'success': True, 'pairings': [], 'round': 0})
    
    round_data = t['rounds'][current_round - 1]
    return jsonify({
        'success': True,
        'round': current_round,
        'pairings': round_data['pairings']
    })

# WebSocket events for tournaments
@socketio.on('join_tournament_room')
def handle_join_tournament_room(data):
    """Join a tournament room for real-time updates"""
    tid = data.get('tournament_id')
    if tid:
        join_room(f'tournament_{tid}')
        emit('joined_tournament_room', {'tournament_id': tid})

@socketio.on('leave_tournament_room')
def handle_leave_tournament_room(data):
    """Leave a tournament room"""
    tid = data.get('tournament_id')
    if tid:
        leave_room(f'tournament_{tid}')

@socketio.on('tournament_game_result')
def handle_tournament_game_result(data):
    """Handle a game result in a tournament"""
    tid = data.get('tournament_id')
    game_id = data.get('game_id')
    result = data.get('result')  # 'white', 'black', 'draw'
    white = data.get('white')
    black = data.get('black')
    
    load_tournaments()
    
    if tid not in tournaments:
        return
    
    t = tournaments[tid]
    standings = t['standings']
    
    # Update standings
    if white and white in standings:
        standings[white]['games'] += 1
        if result == 'white':
            standings[white]['score'] += 1
            standings[white]['wins'] += 1
        elif result == 'draw':
            standings[white]['score'] += 0.5
            standings[white]['draws'] += 1
        else:
            standings[white]['losses'] += 1
    
    if black and black in standings:
        standings[black]['games'] += 1
        if result == 'black':
            standings[black]['score'] += 1
            standings[black]['wins'] += 1
        elif result == 'draw':
            standings[black]['score'] += 0.5
            standings[black]['draws'] += 1
        else:
            standings[black]['losses'] += 1
    
    save_tournaments()
    
    # Broadcast update
    socketio.emit('tournament_update', {
        'tournament_id': tid,
        'type': 'game_result',
        'game_id': game_id,
        'result': result,
        'standings': calculate_arena_standings(t)
    }, room=f'tournament_{tid}')

# Load tournaments on startup
load_tournaments()

# ============== API ENDPOINTS ==============

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get player statistics"""
    stats = load_stats()
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/stats/update', methods=['POST'])
def update_stats():
    """Update player statistics after a game"""
    data = request.json
    stats = load_stats()
    
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
    save_stats(stats)
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
    """Get saved games for review"""
    games = load_games()
    return jsonify({'success': True, 'games': games})

@app.route('/api/games/save', methods=['POST'])
def save_game():
    """Save a completed game and update player style"""
    data = request.json
    games = load_games()
    
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
    save_games(games)
    
    # Update player style for AI Clone learning
    try:
        update_player_style_from_game(game_data)
    except Exception as e:
        print(f"Error updating player style: {e}")
    
    return jsonify({'success': True, 'game_id': game_data['id']})

@app.route('/api/games/<int:game_id>', methods=['GET'])
def get_game(game_id):
    """Get a specific game for review"""
    games = load_games()
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
