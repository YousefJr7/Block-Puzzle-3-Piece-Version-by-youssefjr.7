"""
block_puzzle.py
Block Puzzle (3 pieces at a time) - pygame implementation

Controls:
- Left click on a grid cell to place the currently selected preview piece (the piece is placed with its top-left at the clicked cell)
- After placing, that piece is consumed (when all 3 used, 3 new pieces spawn)
- R - restart game
- S - save highscore manually
- Esc - quit
- Menu: Up/Down/Enter to navigate

Highscore saved to: block_puzzle_highscore.json
Optional assets folder: put sounds in ./assets/ (place.wav, clear.wav) to enable sfx
"""

import pygame, random, json, os, sys, math
from collections import deque

# ----------------------- Config -----------------------
SCREEN_W, SCREEN_H = 760, 860
FPS = 60

GRID_COLS, GRID_ROWS = 10, 10
CELL = 56
GRID_X = (SCREEN_W - GRID_COLS * CELL) // 2
GRID_Y = 160

HIGHSCORE_FILE = "block_puzzle_highscore.json"
ASSETS = "assets"

# Colors
BG = (14, 17, 22)
BOARD_BG = (24, 26, 32)
CELL_EMPTY = (12, 14, 18)
LINE = (20, 22, 28)
TEXT = (230, 230, 230)
ACCENT = (240, 170, 60)
PARTICLE_COLORS = [(240,80,70), (70,170,250), (120,220,120), (250,200,60), (180,120,240)]

# Scoring
SCORE_PER_BLOCK = 10
ROWCOL_CLEAR_BONUS = 50

# ----------------------- Pieces definitions -----------------------
# Each piece is a list of rows (0/1). Top-left alignment: placing at (x,y) maps 0..w-1 and 0..h-1
PIECES = [
    [[1]],  # single
    [[1,1]],  # 2 horizontal
    [[1,1,1]],  # 3 horizontal
    [[1,1,1,1]],  # 4 horizontal
    [[1],[1]],  # 2 vertical
    [[1],[1],[1]],  # 3 vertical
    [[1,1],[1,1]],  # 2x2 square
    [[1,0],[1,1]],  # small L
    [[0,1],[1,1]],  # mirrored small L
    [[1,1,1],[0,1,0]],  # T
    [[1,0],[1,0],[1,1]],  # L vertical
    [[0,1],[0,1],[1,1]],  # mirrored L vertical
    [[1,0,0],[1,1,1]],    # big L variants
    [[1,1,0],[0,1,1]],    # Z
    [[0,1,1],[1,1,0]],    # S
    [[1,1,1],[1,0,0]],    # other L
    # you can add more shapes
]

# choose random pieces for new preview set
def random_piece():
    return [row[:] for row in random.choice(PIECES)]

# ----------------------- Highscore utilities -----------------------
def load_highscore():
    if os.path.exists(HIGHSCORE_FILE):
        try:
            with open(HIGHSCORE_FILE, "r") as f:
                return json.load(f).get("highscore", 0)
        except Exception:
            return 0
    return 0

def save_highscore(v):
    try:
        with open(HIGHSCORE_FILE, "w") as f:
            json.dump({"highscore": v}, f)
    except Exception:
        pass

# ----------------------- Pygame init -----------------------
pygame.init()
pygame.mixer.pre_init(44100, -16, 2, 512)
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Block Puzzle - 3 Pieces")
clock = pygame.time.Clock()
FONT = pygame.font.SysFont(None, 22)
BIG = pygame.font.SysFont(None, 36)
TITLE = pygame.font.SysFont(None, 56)

# load optional sounds
def load_sound(name):
    p = os.path.join(ASSETS, name)
    if os.path.exists(p):
        try:
            return pygame.mixer.Sound(p)
        except Exception:
            return None
    return None

SND_PLACE = load_sound("place.wav")
SND_CLEAR = load_sound("clear.wav")

# ----------------------- Game state classes -----------------------
class Particle:
    def __init__(self, x, y, color):
        self.x = x; self.y = y
        self.vx = random.uniform(-140,140)
        self.vy = random.uniform(-260,-80)
        self.life = random.uniform(0.45, 0.9)
        self.color = color
        self.size = random.uniform(3,6)
    def update(self, dt):
        self.vy += 700 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        self.size *= 0.99
    def draw(self, surf):
        if self.life>0:
            r = max(1, int(self.size))
            pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), r)

class Game:
    def __init__(self):
        self.grid = [[0]*GRID_ROWS for _ in range(GRID_COLS)]  # 0 empty, >0 color index
        self.score = 0
        self.highscore = load_highscore()
        self.pieces = [random_piece(), random_piece(), random_piece()]
        self.piece_colors = [random.randrange(len(PARTICLE_COLORS)) for _ in range(3)]
        self.used = [False, False, False]
        self.particles = []
        self.game_over = False

    def reset(self):
        self.grid = [[0]*GRID_ROWS for _ in range(GRID_COLS)]
        self.score = 0
        self.pieces = [random_piece(), random_piece(), random_piece()]
        self.piece_colors = [random.randrange(len(PARTICLE_COLORS)) for _ in range(3)]
        self.used = [False, False, False]
        self.particles.clear()
        self.game_over = False

    def spawn_new_triplet(self):
        self.pieces = [random_piece(), random_piece(), random_piece()]
        self.piece_colors = [random.randrange(len(PARTICLE_COLORS)) for _ in range(3)]
        self.used = [False, False, False]

    def can_place_piece(self, piece, drop_x, drop_y):
        # piece is matrix of rows; place top-left at drop_x, drop_y
        h = len(piece)
        w = len(piece[0])
        if drop_x < 0 or drop_y < 0 or drop_x + w > GRID_COLS or drop_y + h > GRID_ROWS:
            return False
        for px in range(w):
            for py in range(h):
                if piece[py][px]:
                    if self.grid[drop_x+px][drop_y+py] != 0:
                        return False
        return True

    def any_valid_for_index(self, index):
        # check if piece at index (0..2) has any valid placement on grid
        if self.used[index]:
            return False
        piece = self.pieces[index]
        h = len(piece); w = len(piece[0])
        for gx in range(GRID_COLS - w + 1):
            for gy in range(GRID_ROWS - h + 1):
                if self.can_place_piece(piece, gx, gy):
                    return True
        return False

    def any_move_exists(self):
        # if any of the three has a possible place
        for i in range(3):
            if self.any_valid_for_index(i):
                return True
        return False

    def place_piece(self, index, gx, gy):
        if index < 0 or index > 2 or self.used[index]:
            return False
        piece = self.pieces[index]
        if not self.can_place_piece(piece, gx, gy):
            return False
        color_id = self.piece_colors[index] + 1  # store 1..n in grid
        placed_blocks = 0
        for py in range(len(piece)):
            for px in range(len(piece[0])):
                if piece[py][px]:
                    self.grid[gx+px][gy+py] = color_id
                    placed_blocks += 1
        self.used[index] = True
        # particles
        for _ in range(12):
            cx = GRID_X + (gx + len(piece[0])/2)*CELL
            cy = GRID_Y + (gy + len(piece)/2)*CELL
            self.particles.append(Particle(cx + random.uniform(-8,8), cy + random.uniform(-8,8),
                                           PARTICLE_COLORS[self.piece_colors[index]]))
        # score for placing
        self.score += placed_blocks * SCORE_PER_BLOCK
        if SND_PLACE: SND_PLACE.play()
        # after placement, clear full rows/cols
        clears = self.clear_full_lines()
        if clears > 0:
            if SND_CLEAR: SND_CLEAR.play()
            self.score += ROWCOL_CLEAR_BONUS * clears
        # if all three used, spawn new triplet
        if all(self.used):
            self.spawn_new_triplet()
        # update highscore
        if self.score > self.highscore:
            self.highscore = self.score
            save_highscore(self.highscore)
        return True

    def clear_full_lines(self):
        # check rows and cols; remove and cause collapse: standard block-puzzle clears entire row or column (set to 0)
        cleared = 0
        # rows
        rows_to_clear = []
        for y in range(GRID_ROWS):
            full = True
            for x in range(GRID_COLS):
                if self.grid[x][y] == 0:
                    full = False; break
            if full:
                rows_to_clear.append(y)
        for y in rows_to_clear:
            for x in range(GRID_COLS):
                self.grid[x][y] = 0
            cleared += 1
        # columns
        cols_to_clear = []
        for x in range(GRID_COLS):
            full = True
            for y in range(GRID_ROWS):
                if self.grid[x][y] == 0:
                    full = False; break
            if full:
                cols_to_clear.append(x)
        for x in cols_to_clear:
            for y in range(GRID_ROWS):
                self.grid[x][y] = 0
            cleared += 1
        # gravity collapse columns (blocks fall down within each column)
        if cleared > 0:
            for x in range(GRID_COLS):
                col = [self.grid[x][y] for y in range(GRID_ROWS) if self.grid[x][y] != 0]
                newcol = [0]*(GRID_ROWS - len(col)) + col
                for y in range(GRID_ROWS):
                    self.grid[x][y] = newcol[y]
        return cleared

    def update_particles(self, dt):
        for p in self.particles[:]:
            p.update(dt)
            if p.life <= 0:
                try: self.particles.remove(p)
                except ValueError: pass

# ----------------------- UI & drawing -----------------------
def draw_board(game):
    # background board
    pygame.draw.rect(screen, BOARD_BG, (GRID_X-6, GRID_Y-6, GRID_COLS*CELL+12, GRID_ROWS*CELL+12), border_radius=10)
    for x in range(GRID_COLS):
        for y in range(GRID_ROWS):
            rect = pygame.Rect(GRID_X + x*CELL + 3, GRID_Y + y*CELL + 3, CELL-6, CELL-6)
            val = game.grid[x][y]
            if val == 0:
                pygame.draw.rect(screen, CELL_EMPTY, rect, border_radius=8)
            else:
                color = PARTICLE_COLORS[(val-1) % len(PARTICLE_COLORS)]
                pygame.draw.rect(screen, color, rect, border_radius=9)
                # gloss
                inner = rect.inflate(-8, -8)
                s = pygame.Surface((inner.w, inner.h), pygame.SRCALPHA)
                pygame.draw.ellipse(s, (255,255,255,26), (0,0,inner.w, inner.h//2))
                screen.blit(s, inner.topleft)
    # grid lines subtle
    for i in range(GRID_COLS+1):
        pygame.draw.line(screen, LINE, (GRID_X + i*CELL, GRID_Y), (GRID_X + i*CELL, GRID_Y + GRID_ROWS*CELL))
    for j in range(GRID_ROWS+1):
        pygame.draw.line(screen, LINE, (GRID_X, GRID_Y + j*CELL), (GRID_X + GRID_COLS*CELL, GRID_Y + j*CELL))

def draw_preview(game):
    # preview area top
    start_x = 60
    start_y = 250
    gap = 220
    for idx in range(3):
        px = start_x + idx*gap
        py = start_y
        # draw box
        pygame.draw.rect(screen, (28,28,34), (px-10, py-10, 180, 140), border_radius=10)
        label = FONT.render(f"Piece {idx+1}" + (" (used)" if game.used[idx] else ""), True, TEXT)
        screen.blit(label, (px, py-34))
        # draw piece cells in center of box
        piece = game.pieces[idx]
        color_idx = game.piece_colors[idx]
        cols = len(piece[0]); rows = len(piece)
        cell_size = 22
        base_x = px + 90 - (cols*cell_size)//2
        base_y = py + 60 - (rows*cell_size)//2
        for ry in range(rows):
            for rx in range(cols):
                rect = pygame.Rect(base_x + rx*cell_size, base_y + ry*cell_size, cell_size-4, cell_size-4)
                if piece[ry][rx]:
                    c = PARTICLE_COLORS[color_idx % len(PARTICLE_COLORS)]
                    pygame.draw.rect(screen, c, rect, border_radius=6)
                else:
                    pygame.draw.rect(screen, (18,18,22), rect, border_radius=4)
    # score and instructions top-left
    score_txt = BIG.render(f"Score: {game.score}", True, TEXT)
    screen.blit(score_txt, (20, 20))
    hs_txt = FONT.render(f"Best: {game.highscore}", True, (200,200,210))
    screen.blit(hs_txt, (20, 64))
    instr = FONT.render("Click a cell to place selected piece (top-left). R restart  S save  Esc quit.", True, (180,180,190))
    screen.blit(instr, (20, 104))

def draw_ghost_piece(game, mouse_pos):
    # if hovering over board and hovering cell and selected piece not used - show ghost placement for piece under mouse when hovering which piece?
    # We'll show best ghost for the first non-used piece that fits at mouse cell.
    mx, my = mouse_pos
    g = screen_to_grid(mx, my)
    if not g:
        return
    gx, gy = g
    # iterate preview indices; if user hovers near preview boxes, we won't choose piece by index; rather show ghost for each piece where mouse is
    for idx in range(3):
        if game.used[idx]:
            continue
        piece = game.pieces[idx]
        h = len(piece); w = len(piece[0])
        # show ghost only if top-left at (gx,gy) would be fully inside grid bounds for the piece
        if gx + w <= GRID_COLS and gy + h <= GRID_ROWS and game.can_place_piece(piece, gx, gy):
            # draw semi-transparent overlay on target cells
            s = pygame.Surface((CELL-6, CELL-6), pygame.SRCALPHA)
            color = PARTICLE_COLORS[game.piece_colors[idx] % len(PARTICLE_COLORS)]
            s.fill((*color, 120))
            for py in range(h):
                for px in range(w):
                    if piece[py][px]:
                        rx = GRID_X + (gx+px)*CELL + 3
                        ry = GRID_Y + (gy+py)*CELL + 3
                        screen.blit(s, (rx, ry))
            # show a small index marker near mouse
            mark = FONT.render(f"P{idx+1}", True, TEXT)
            screen.blit(mark, (mx+12, my+6))
            # only show the first valid ghost (keeps interface clear)
            break

def screen_to_grid(mx, my):
    gx = (mx - GRID_X) // CELL
    gy = (my - GRID_Y) // CELL
    if 0 <= gx < GRID_COLS and 0 <= gy < GRID_ROWS:
        return int(gx), int(gy)
    return None

def draw_game_over(game):
    surf = BIG.render("GAME OVER", True, (240,120,120))
    rect = surf.get_rect(center=(SCREEN_W//2, 100))
    screen.blit(surf, rect)
    info = FONT.render("No possible placement for any piece. Press R to restart or Esc to quit.", True, (220,200,200))
    rect2 = info.get_rect(center=(SCREEN_W//2, 140))
    screen.blit(info, rect2)

# ----------------------- Main Menu -----------------------
def draw_menu(selected):
    screen.fill(BG)
    title_s = TITLE.render("Block Puzzle", True, ACCENT)
    screen.blit(title_s, ((SCREEN_W - title_s.get_width())//2, 60))
    options = ["Start", "Highscore", "Quit"]
    for i, opt in enumerate(options):
        y = 220 + i*86
        color = TEXT if i == selected else (170,170,170)
        txt = BIG.render(opt, True, color)
        screen.blit(txt, ((SCREEN_W - txt.get_width())//2, y))

def draw_highscore_screen(hs):
    screen.fill(BG)
    t = TITLE.render("High Score", True, (210,210,255))
    screen.blit(t, ((SCREEN_W - t.get_width())//2, 60))
    score_txt = BIG.render(str(hs), True, TEXT)
    screen.blit(score_txt, ((SCREEN_W - score_txt.get_width())//2, 220))
    sub = FONT.render("Press Backspace to return", True, (180,180,200))
    screen.blit(sub, ((SCREEN_W - sub.get_width())//2, SCREEN_H - 90))

# ----------------------- Main Loop -----------------------
def main():
    game = Game()
    running = True
    state = "menu"  # menu, play, highscore
    selected_menu = 0
    mouse_pos = (0,0)

    # attempt to play background music if exists
    try:
        bgm_path = os.path.join(ASSETS, "bgm.ogg")
        if os.path.exists(bgm_path):
            pygame.mixer.music.load(bgm_path)
            pygame.mixer.music.play(-1)
    except Exception:
        pass

    while running:
        dt = clock.tick(FPS)/1000.0
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_highscore(game.highscore)
                running = False
            elif event.type == pygame.KEYDOWN:
                if state == "menu":
                    if event.key in (pygame.K_UP, pygame.K_w):
                        selected_menu = (selected_menu - 1) % 3
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected_menu = (selected_menu + 1) % 3
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if selected_menu == 0:
                            game.reset()
                            state = "play"
                        elif selected_menu == 1:
                            state = "highscore"
                        elif selected_menu == 2:
                            save_highscore(game.highscore)
                            running = False
                elif state == "highscore":
                    if event.key in (pygame.K_BACKSPACE, pygame.K_ESCAPE):
                        state = "menu"
                elif state == "play":
                    if event.key == pygame.K_r:
                        game.reset()
                    elif event.key == pygame.K_s:
                        save_highscore(game.highscore)
                    elif event.key == pygame.K_ESCAPE:
                        save_highscore(game.highscore)
                        state = "menu"
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if state == "menu":
                    mx,my = event.pos
                    # clicking option area
                    for i in range(3):
                        rect_y = 220 + i*86
                        text = ["Start","Highscore","Quit"][i]
                        txt = BIG.render(text, True, TEXT)
                        rect = pygame.Rect((SCREEN_W - txt.get_width())//2, rect_y, txt.get_width(), txt.get_height())
                        if rect.collidepoint(mx,my):
                            if i == 0:
                                game.reset(); state = "play"
                            elif i == 1:
                                state = "highscore"
                            else:
                                save_highscore(game.highscore); running = False
                elif state == "play":
                    if event.button == 1 and not game.game_over:
                        pos = event.pos
                        g = screen_to_grid(*pos)
                        if g:
                            gx, gy = g
                            placed_any = False
                            # Try to place on first usable piece that fits at this position (we show ghost for first that fits)
                            for i in range(3):
                                if not game.used[i] and game.can_place_piece(game.pieces[i], gx, gy):
                                    success = game.place_piece(i, gx, gy)
                                    placed_any = placed_any or success
                                    break
                            # after any placement, check game over condition
                            if not game.any_move_exists():
                                game.game_over = True
                    # right-click to optionally cycle through pieces? (not necessary)
        # Update
        if state == "play":
            game.update_particles(dt)
            # update particles positions handled inside game
            if not game.game_over:
                # check if none of the three pieces can be placed -> game over
                if not game.any_move_exists():
                    game.game_over = True
            # update global highscore
            if game.score > game.highscore:
                game.highscore = game.score
                save_highscore(game.highscore)

        # Draw
        screen.fill(BG)
        if state == "menu":
            draw_menu(selected_menu)
        elif state == "highscore":
            draw_highscore_screen(game.highscore)
        elif state == "play":
            draw_preview(game)
            draw_board(game)
            draw_ghost_piece(game, mouse_pos)
            # draw particles
            for p in game.particles:
                p.draw(screen)
            if game.game_over:
                draw_game_over(game)

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
