/**
 * Chess.js - Client-side chess logic
 * Pure JavaScript chess library (no dependencies)
 */

const PIECES = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
};

const PIECE_VALUES = {
    'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9, 'k': 0,
    'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0
};

class Chess {
    constructor(fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1') {
        this.reset(fen);
    }

    reset(fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1') {
        this.board = [];
        this.turn = 'w';
        this.castling = { K: true, Q: true, k: true, q: true };
        this.enPassant = null;
        this.halfMoves = 0;
        this.fullMoves = 1;
        this.moveHistory = [];
        this.positions = [];
        this.loadFEN(fen);
    }

    loadFEN(fen) {
        const parts = fen.split(' ');
        const rows = parts[0].split('/');
        
        this.board = [];
        for (let r = 0; r < 8; r++) {
            const row = [];
            for (const char of rows[r]) {
                if (isNaN(char)) {
                    row.push(char);
                } else {
                    for (let i = 0; i < parseInt(char); i++) {
                        row.push(null);
                    }
                }
            }
            this.board.push(row);
        }

        this.turn = parts[1] || 'w';
        
        const castling = parts[2] || '-';
        this.castling = {
            K: castling.includes('K'),
            Q: castling.includes('Q'),
            k: castling.includes('k'),
            q: castling.includes('q')
        };

        this.enPassant = parts[3] === '-' ? null : parts[3];
        this.halfMoves = parseInt(parts[4]) || 0;
        this.fullMoves = parseInt(parts[5]) || 1;
        
        this.positions.push(this.getFEN());
    }

    getFEN() {
        let fen = '';
        
        for (let r = 0; r < 8; r++) {
            let empty = 0;
            for (let c = 0; c < 8; c++) {
                const piece = this.board[r][c];
                if (piece) {
                    if (empty > 0) {
                        fen += empty;
                        empty = 0;
                    }
                    fen += piece;
                } else {
                    empty++;
                }
            }
            if (empty > 0) fen += empty;
            if (r < 7) fen += '/';
        }

        fen += ' ' + this.turn;
        
        let castling = '';
        if (this.castling.K) castling += 'K';
        if (this.castling.Q) castling += 'Q';
        if (this.castling.k) castling += 'k';
        if (this.castling.q) castling += 'q';
        fen += ' ' + (castling || '-');
        
        fen += ' ' + (this.enPassant || '-');
        fen += ' ' + this.halfMoves;
        fen += ' ' + this.fullMoves;

        return fen;
    }

    getPiece(square) {
        const { row, col } = this.squareToCoords(square);
        return this.board[row][col];
    }

    squareToCoords(square) {
        const col = square.charCodeAt(0) - 97;
        const row = 8 - parseInt(square[1]);
        return { row, col };
    }

    coordsToSquare(row, col) {
        return String.fromCharCode(97 + col) + (8 - row);
    }

    isWhitePiece(piece) {
        return piece && piece === piece.toUpperCase();
    }

    isBlackPiece(piece) {
        return piece && piece === piece.toLowerCase();
    }

    isOwnPiece(piece) {
        if (!piece) return false;
        return (this.turn === 'w' && this.isWhitePiece(piece)) ||
               (this.turn === 'b' && this.isBlackPiece(piece));
    }

    isEnemyPiece(piece) {
        if (!piece) return false;
        return (this.turn === 'w' && this.isBlackPiece(piece)) ||
               (this.turn === 'b' && this.isWhitePiece(piece));
    }

    getLegalMoves(square) {
        const piece = this.getPiece(square);
        if (!piece || !this.isOwnPiece(piece)) return [];

        const { row, col } = this.squareToCoords(square);
        const moves = [];
        const pieceType = piece.toLowerCase();

        const addMove = (toRow, toCol, isCapture = false, special = null) => {
            if (toRow < 0 || toRow > 7 || toCol < 0 || toCol > 7) return false;
            const target = this.board[toRow][toCol];
            if (target && this.isOwnPiece(target)) return false;
            
            const toSquare = this.coordsToSquare(toRow, toCol);
            
            // Check if move leaves king in check
            if (!this.wouldBeInCheck(square, toSquare)) {
                moves.push({
                    from: square,
                    to: toSquare,
                    piece: piece,
                    captured: target,
                    isCapture: !!target || special === 'enpassant',
                    special: special
                });
            }
            
            return !target; // Continue sliding if empty
        };

        // Pawn moves
        if (pieceType === 'p') {
            const dir = this.isWhitePiece(piece) ? -1 : 1;
            const startRow = this.isWhitePiece(piece) ? 6 : 1;
            const promoRow = this.isWhitePiece(piece) ? 0 : 7;

            // Forward
            if (!this.board[row + dir]?.[col]) {
                if (row + dir === promoRow) {
                    ['q', 'r', 'b', 'n'].forEach(p => {
                        const toSquare = this.coordsToSquare(row + dir, col);
                        if (!this.wouldBeInCheck(square, toSquare)) {
                            moves.push({
                                from: square,
                                to: toSquare,
                                piece: piece,
                                special: 'promotion',
                                promotion: this.isWhitePiece(piece) ? p.toUpperCase() : p
                            });
                        }
                    });
                } else {
                    addMove(row + dir, col);
                }
                
                // Double move
                if (row === startRow && !this.board[row + 2 * dir]?.[col]) {
                    addMove(row + 2 * dir, col, false, 'double');
                }
            }

            // Captures
            [-1, 1].forEach(dc => {
                const target = this.board[row + dir]?.[col + dc];
                if (target && this.isEnemyPiece(target)) {
                    if (row + dir === promoRow) {
                        ['q', 'r', 'b', 'n'].forEach(p => {
                            const toSquare = this.coordsToSquare(row + dir, col + dc);
                            if (!this.wouldBeInCheck(square, toSquare)) {
                                moves.push({
                                    from: square,
                                    to: toSquare,
                                    piece: piece,
                                    captured: target,
                                    isCapture: true,
                                    special: 'promotion',
                                    promotion: this.isWhitePiece(piece) ? p.toUpperCase() : p
                                });
                            }
                        });
                    } else {
                        addMove(row + dir, col + dc, true);
                    }
                }
                
                // En passant
                const epSquare = this.coordsToSquare(row + dir, col + dc);
                if (this.enPassant === epSquare) {
                    addMove(row + dir, col + dc, true, 'enpassant');
                }
            });
        }

        // Knight moves
        if (pieceType === 'n') {
            [[-2,-1], [-2,1], [-1,-2], [-1,2], [1,-2], [1,2], [2,-1], [2,1]].forEach(([dr, dc]) => {
                addMove(row + dr, col + dc);
            });
        }

        // Bishop moves
        if (pieceType === 'b' || pieceType === 'q') {
            [[-1,-1], [-1,1], [1,-1], [1,1]].forEach(([dr, dc]) => {
                for (let i = 1; i < 8; i++) {
                    if (!addMove(row + dr*i, col + dc*i)) break;
                }
            });
        }

        // Rook moves
        if (pieceType === 'r' || pieceType === 'q') {
            [[-1,0], [1,0], [0,-1], [0,1]].forEach(([dr, dc]) => {
                for (let i = 1; i < 8; i++) {
                    if (!addMove(row + dr*i, col + dc*i)) break;
                }
            });
        }

        // King moves
        if (pieceType === 'k') {
            [[-1,-1], [-1,0], [-1,1], [0,-1], [0,1], [1,-1], [1,0], [1,1]].forEach(([dr, dc]) => {
                addMove(row + dr, col + dc);
            });

            // Castling
            if (!this.isInCheck()) {
                if (this.turn === 'w') {
                    if (this.castling.K && !this.board[7][5] && !this.board[7][6]) {
                        if (!this.isSquareAttacked('f1', 'b') && !this.isSquareAttacked('g1', 'b')) {
                            addMove(7, 6, false, 'castle-k');
                        }
                    }
                    if (this.castling.Q && !this.board[7][3] && !this.board[7][2] && !this.board[7][1]) {
                        if (!this.isSquareAttacked('d1', 'b') && !this.isSquareAttacked('c1', 'b')) {
                            addMove(7, 2, false, 'castle-q');
                        }
                    }
                } else {
                    if (this.castling.k && !this.board[0][5] && !this.board[0][6]) {
                        if (!this.isSquareAttacked('f8', 'w') && !this.isSquareAttacked('g8', 'w')) {
                            addMove(0, 6, false, 'castle-k');
                        }
                    }
                    if (this.castling.q && !this.board[0][3] && !this.board[0][2] && !this.board[0][1]) {
                        if (!this.isSquareAttacked('d8', 'w') && !this.isSquareAttacked('c8', 'w')) {
                            addMove(0, 2, false, 'castle-q');
                        }
                    }
                }
            }
        }

        return moves;
    }

    getAllLegalMoves() {
        const moves = [];
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const square = this.coordsToSquare(r, c);
                moves.push(...this.getLegalMoves(square));
            }
        }
        return moves;
    }

    findKing(color) {
        const king = color === 'w' ? 'K' : 'k';
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if (this.board[r][c] === king) {
                    return this.coordsToSquare(r, c);
                }
            }
        }
        return null;
    }

    isSquareAttacked(square, byColor) {
        const { row, col } = this.squareToCoords(square);
        
        // Check for pawn attacks
        const pawnDir = byColor === 'w' ? 1 : -1;
        const pawn = byColor === 'w' ? 'P' : 'p';
        if (this.board[row + pawnDir]?.[col - 1] === pawn) return true;
        if (this.board[row + pawnDir]?.[col + 1] === pawn) return true;

        // Check for knight attacks
        const knight = byColor === 'w' ? 'N' : 'n';
        for (const [dr, dc] of [[-2,-1], [-2,1], [-1,-2], [-1,2], [1,-2], [1,2], [2,-1], [2,1]]) {
            if (this.board[row + dr]?.[col + dc] === knight) return true;
        }

        // Check for king attacks
        const king = byColor === 'w' ? 'K' : 'k';
        for (const [dr, dc] of [[-1,-1], [-1,0], [-1,1], [0,-1], [0,1], [1,-1], [1,0], [1,1]]) {
            if (this.board[row + dr]?.[col + dc] === king) return true;
        }

        // Check for diagonal attacks (bishop/queen)
        const bishop = byColor === 'w' ? 'B' : 'b';
        const queen = byColor === 'w' ? 'Q' : 'q';
        for (const [dr, dc] of [[-1,-1], [-1,1], [1,-1], [1,1]]) {
            for (let i = 1; i < 8; i++) {
                const piece = this.board[row + dr*i]?.[col + dc*i];
                if (piece === undefined) break;
                if (piece === bishop || piece === queen) return true;
                if (piece) break;
            }
        }

        // Check for straight attacks (rook/queen)
        const rook = byColor === 'w' ? 'R' : 'r';
        for (const [dr, dc] of [[-1,0], [1,0], [0,-1], [0,1]]) {
            for (let i = 1; i < 8; i++) {
                const piece = this.board[row + dr*i]?.[col + dc*i];
                if (piece === undefined) break;
                if (piece === rook || piece === queen) return true;
                if (piece) break;
            }
        }

        return false;
    }

    isInCheck() {
        const kingSquare = this.findKing(this.turn);
        return this.isSquareAttacked(kingSquare, this.turn === 'w' ? 'b' : 'w');
    }

    wouldBeInCheck(from, to) {
        // Make temporary move
        const { row: fromRow, col: fromCol } = this.squareToCoords(from);
        const { row: toRow, col: toCol } = this.squareToCoords(to);
        
        const piece = this.board[fromRow][fromCol];
        const captured = this.board[toRow][toCol];
        
        this.board[toRow][toCol] = piece;
        this.board[fromRow][fromCol] = null;
        
        // Handle en passant capture
        let epCaptured = null;
        if (piece.toLowerCase() === 'p' && to === this.enPassant) {
            const epRow = this.turn === 'w' ? toRow + 1 : toRow - 1;
            epCaptured = this.board[epRow][toCol];
            this.board[epRow][toCol] = null;
        }
        
        const kingSquare = this.findKing(this.turn);
        const inCheck = this.isSquareAttacked(kingSquare, this.turn === 'w' ? 'b' : 'w');
        
        // Restore
        this.board[fromRow][fromCol] = piece;
        this.board[toRow][toCol] = captured;
        if (epCaptured !== null) {
            const epRow = this.turn === 'w' ? toRow + 1 : toRow - 1;
            this.board[epRow][toCol] = epCaptured;
        }
        
        return inCheck;
    }

    move(from, to, promotion = null) {
        const moves = this.getLegalMoves(from);
        let move = moves.find(m => m.to === to);
        
        if (!move) return null;
        
        // Handle promotion
        if (move.special === 'promotion') {
            if (promotion) {
                move = moves.find(m => m.to === to && m.promotion?.toLowerCase() === promotion.toLowerCase());
            }
            if (!move) return null;
        }

        const { row: fromRow, col: fromCol } = this.squareToCoords(from);
        const { row: toRow, col: toCol } = this.squareToCoords(to);

        // Store for history
        const historyEntry = {
            from: from,
            to: to,
            piece: move.piece,
            captured: move.captured,
            special: move.special,
            promotion: move.promotion,
            fen: this.getFEN(),
            castling: { ...this.castling },
            enPassant: this.enPassant,
            halfMoves: this.halfMoves
        };

        // Make the move
        this.board[toRow][toCol] = move.promotion || move.piece;
        this.board[fromRow][fromCol] = null;

        // Handle special moves
        if (move.special === 'enpassant') {
            const epRow = this.turn === 'w' ? toRow + 1 : toRow - 1;
            historyEntry.epCapture = { row: epRow, col: toCol, piece: this.board[epRow][toCol] };
            this.board[epRow][toCol] = null;
        }

        if (move.special === 'castle-k') {
            const row = this.turn === 'w' ? 7 : 0;
            this.board[row][5] = this.board[row][7];
            this.board[row][7] = null;
        }

        if (move.special === 'castle-q') {
            const row = this.turn === 'w' ? 7 : 0;
            this.board[row][3] = this.board[row][0];
            this.board[row][0] = null;
        }

        // Update castling rights
        if (move.piece === 'K') { this.castling.K = false; this.castling.Q = false; }
        if (move.piece === 'k') { this.castling.k = false; this.castling.q = false; }
        if (from === 'a1' || to === 'a1') this.castling.Q = false;
        if (from === 'h1' || to === 'h1') this.castling.K = false;
        if (from === 'a8' || to === 'a8') this.castling.q = false;
        if (from === 'h8' || to === 'h8') this.castling.k = false;

        // Update en passant
        this.enPassant = null;
        if (move.special === 'double') {
            const epRow = this.turn === 'w' ? toRow + 1 : toRow - 1;
            this.enPassant = this.coordsToSquare(epRow, toCol);
        }

        // Update clocks
        if (move.piece.toLowerCase() === 'p' || move.captured) {
            this.halfMoves = 0;
        } else {
            this.halfMoves++;
        }

        if (this.turn === 'b') {
            this.fullMoves++;
        }

        // Switch turn
        this.turn = this.turn === 'w' ? 'b' : 'w';

        // Generate SAN
        historyEntry.san = this.generateSAN(historyEntry);
        
        this.moveHistory.push(historyEntry);
        this.positions.push(this.getFEN());

        return historyEntry;
    }

    generateSAN(move) {
        let san = '';
        const pieceType = move.piece.toLowerCase();
        
        if (move.special === 'castle-k') return 'O-O';
        if (move.special === 'castle-q') return 'O-O-O';
        
        if (pieceType !== 'p') {
            san += move.piece.toUpperCase();
        }
        
        if (move.captured || move.special === 'enpassant') {
            if (pieceType === 'p') {
                san += move.from[0];
            }
            san += 'x';
        }
        
        san += move.to;
        
        if (move.promotion) {
            san += '=' + move.promotion.toUpperCase();
        }
        
        // Check for check/checkmate
        if (this.isInCheck()) {
            if (this.isCheckmate()) {
                san += '#';
            } else {
                san += '+';
            }
        }
        
        return san;
    }

    undo() {
        if (this.moveHistory.length === 0) return null;
        
        const move = this.moveHistory.pop();
        this.positions.pop();
        this.loadFEN(move.fen);
        
        return move;
    }

    isCheckmate() {
        return this.isInCheck() && this.getAllLegalMoves().length === 0;
    }

    isStalemate() {
        return !this.isInCheck() && this.getAllLegalMoves().length === 0;
    }

    isDraw() {
        // Stalemate
        if (this.isStalemate()) return 'stalemate';
        
        // 50 move rule
        if (this.halfMoves >= 100) return 'fifty-moves';
        
        // Insufficient material
        const pieces = [];
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                if (this.board[r][c]) {
                    pieces.push(this.board[r][c].toLowerCase());
                }
            }
        }
        
        if (pieces.length === 2) return 'insufficient'; // K vs K
        if (pieces.length === 3) {
            if (pieces.includes('b') || pieces.includes('n')) return 'insufficient';
        }
        
        // Threefold repetition
        const currentPos = this.getFEN().split(' ').slice(0, 4).join(' ');
        let count = 0;
        for (const pos of this.positions) {
            if (pos.split(' ').slice(0, 4).join(' ') === currentPos) {
                count++;
                if (count >= 3) return 'repetition';
            }
        }
        
        return false;
    }

    isGameOver() {
        return this.isCheckmate() || this.isDraw();
    }

    getResult() {
        if (this.isCheckmate()) {
            return this.turn === 'w' ? '0-1' : '1-0';
        }
        if (this.isDraw()) {
            return '1/2-1/2';
        }
        return '*';
    }

    getCapturedPieces() {
        const initial = {
            white: { P: 8, N: 2, B: 2, R: 2, Q: 1 },
            black: { p: 8, n: 2, b: 2, r: 2, q: 1 }
        };
        
        // Count current pieces
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const piece = this.board[r][c];
                if (piece && piece !== 'K' && piece !== 'k') {
                    if (this.isWhitePiece(piece)) {
                        initial.white[piece]--;
                    } else {
                        initial.black[piece]--;
                    }
                }
            }
        }
        
        // Convert to captured arrays
        const captured = { white: [], black: [] };
        
        for (const [piece, count] of Object.entries(initial.white)) {
            for (let i = 0; i < count; i++) {
                captured.white.push(piece);
            }
        }
        
        for (const [piece, count] of Object.entries(initial.black)) {
            for (let i = 0; i < count; i++) {
                captured.black.push(piece);
            }
        }
        
        return captured;
    }

    getMaterialAdvantage() {
        let white = 0, black = 0;
        
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const piece = this.board[r][c];
                if (piece) {
                    const value = PIECE_VALUES[piece] || 0;
                    if (this.isWhitePiece(piece)) {
                        white += value;
                    } else {
                        black += value;
                    }
                }
            }
        }
        
        return white - black;
    }
}

// Export for use
window.Chess = Chess;
window.PIECES = PIECES;
