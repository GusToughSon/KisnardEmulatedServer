import pygame
import sys
import os
import json
from PIL import Image
from map_renderer import MapRenderer
from network_manager import NetworkManager

# Initialize Pygame
pygame.init()

# Constants for 1:1 Layout
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
MAP_VIEW_WIDTH = 800
MAP_VIEW_HEIGHT = 600
PANEL_WIDTH = 224
FPS = 60

# Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GREY = (80, 80, 80)
COLOR_DARK_GREY = (30, 30, 30)
COLOR_LIGHT_GREY = (160, 160, 160)
COLOR_RED = (200, 0, 0)
COLOR_GREEN = (0, 180, 0)
COLOR_BLUE = (0, 120, 255)
COLOR_YELLOW = (255, 220, 0)

# Game States
STATE_LOGIN = 0
STATE_CHAR_SELECT = 1
STATE_CHAR_CREATE = 2
STATE_GAME = 3

class KisnardClient:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Kisnard Online")
        self.clock = pygame.time.Clock()
        
        client_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_dir = os.path.abspath(os.path.join(client_dir, "..", ".."))
        self.assets_dir = os.path.join(self.project_dir, "game_assets", "images")
        
        # State Management
        self.state = STATE_LOGIN
        
        # Network Manager
        self.network = NetworkManager("127.0.0.1", 34215)
        
        # Load Map Renderer
        self.map_renderer = MapRenderer()
        
        # Player Data
        self.player_name = ""
        self.player_race = "human"
        self.player_gender = "male"
        self.player_x = 670.0
        self.player_y = 490.0
        self.player_speed = 0.08
        self.current_walk = None
        
        # Character Stats
        self.hp = 120
        self.max_hp = 120
        self.mana = 45
        self.max_mana = 45
        self.level = 1
        self.exp = 150
        self.max_exp = 1000
        
        # Character slots (Up to 3 slots)
        self.slots = [
            None,
            None,
            None
        ]
        self.selected_slot = 0
        
        # UI Inputs
        self.input_username = ""
        self.input_password = ""
        self.config_path = os.path.join(os.path.dirname(__file__), "client_config.json")
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    cfg = json.load(f)
                    self.input_username = cfg.get("username", "")
                    self.input_password = cfg.get("password", "")
            except:
                pass
        
        self.input_char_name = ""
        self.active_input = "username"
        
        # Avatar animation
        self.avatar_frames = []
        self.avatar_frame_idx = 0
        self.avatar_timer = 0
        
        # GUI Textures
        self.gui_overlays = {}
        self.load_gui_textures()
        
        # Dummy Inventory & Equipment for 1:1 GUI representation
        self.inventory = [None] * 20 # 20 slots (5x4 grid)
        self.equipment = {
            "helm": None,
            "chest": None,
            "pants": None,
            "weapon": None,
            "shield": None
        }
        self.load_dummy_items()
        
        # Chat log
        self.chat_messages = [
            "Welcome to Kisnard Online!",
            "Use WASD or Arrow keys to move your character.",
            "This is a 1:1 Python client simulation."
        ]
        self.chat_input = ""
        self.chat_active = False
        
        self.last_heartbeat = 0
        
        self.running = True

    def load_gui_textures(self):
        header_path = os.path.join(self.assets_dir, "gui", "gui_header.png")
        if os.path.exists(header_path):
            self.gui_header = pygame.image.load(header_path).convert_alpha()
            self.gui_header = pygame.transform.scale(self.gui_header, (500, 100))
        else:
            self.gui_header = pygame.Surface((500, 100), pygame.SRCALPHA)
        
        # Load Equipment Slot Overlays
        overlays = ["helm", "chest", "pants", "sword", "shield"]
        for ov in overlays:
            path = os.path.join(self.assets_dir, "gui", f"gui_overlay_{ov}.png")
            if os.path.exists(path):
                self.gui_overlays[ov] = pygame.image.load(path).convert_alpha()

    def load_dummy_items(self):
        # Load a few item sprites to populate the inventory/equipment
        try:
            # We can load some basic weapon/armor/item images if they exist
            # For now, we will represent items with colored icons or text,
            # but we will attempt to load actual item sprites if they exist.
            pass
        except Exception as e:
            print(f"Error loading item sprites: {e}")

    def load_avatar(self, race, gender):
        filename = f"sprite_{race}_{gender}.gif"
        path = os.path.join(self.assets_dir, "sprite", filename)
        self.avatar_frames = []
        
        if os.path.exists(path):
            try:
                pil_img = Image.open(path)
                try:
                    while True:
                        frame = pil_img.convert('RGBA')
                        mode = frame.mode
                        size = frame.size
                        data = frame.tobytes()
                        pygame_surface = pygame.image.fromstring(data, size, mode)
                        pygame_surface = pygame.transform.scale(pygame_surface, (32, 32))
                        self.avatar_frames.append(pygame_surface)
                        pil_img.seek(pil_img.tell() + 1)
                except EOFError:
                    pass
            except Exception as e:
                print(f"Error loading animated avatar {filename}: {e}")
                
        if not self.avatar_frames:
            fallback = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.circle(fallback, COLOR_RED, (16, 16), 12)
            self.avatar_frames = [fallback]

    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.render()
            self.clock.tick(FPS)
            
        if self.network:
            self.network.close()
        pygame.quit()
        sys.exit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                else:
                    self.handle_keyboard_input(event)
                    
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.handle_mouse_click(event.pos)

    def handle_keyboard_input(self, event):
        if self.state == STATE_LOGIN:
            if event.key == pygame.K_TAB:
                self.active_input = "password" if self.active_input == "username" else "username"
            elif event.key == pygame.K_RETURN:
                if self.input_username and self.input_password:
                    try:
                        with open(self.config_path, "w") as f:
                            json.dump({"username": self.input_username, "password": self.input_password}, f)
                    except:
                        pass
                    try:
                        self.network.connect(self.input_username, self.input_password)
                    except Exception as e:
                        print(f"Connection failed: {e}")
            elif event.key == pygame.K_BACKSPACE:
                if self.active_input == "username":
                    self.input_username = self.input_username[:-1]
                else:
                    self.input_password = self.input_password[:-1]
            else:
                if event.unicode.isprintable():
                    if self.active_input == "username":
                        self.input_username += event.unicode
                    else:
                        self.input_password += event.unicode
                        
        elif self.state == STATE_CHAR_CREATE:
            if event.key == pygame.K_BACKSPACE:
                self.input_char_name = self.input_char_name[:-1]
            elif event.key == pygame.K_RETURN:
                self.create_character()
            else:
                if event.unicode.isprintable() and len(self.input_char_name) < 15:
                    self.input_char_name += event.unicode
                    
        elif self.state == STATE_GAME:
            if self.chat_active:
                if event.key == pygame.K_RETURN:
                    if self.chat_input.strip():
                        self.network.send_packet(f"{self.player_name}@generalChat|{self.chat_input.strip()}")
                    self.chat_input = ""
                    self.chat_active = False
                elif event.key == pygame.K_BACKSPACE:
                    self.chat_input = self.chat_input[:-1]
                elif event.key == pygame.K_ESCAPE:
                    self.chat_input = ""
                    self.chat_active = False
                else:
                    if event.unicode.isprintable() and len(self.chat_input) < 100:
                        self.chat_input += event.unicode
            else:
                if event.key == pygame.K_RETURN:
                    self.chat_active = True

    def handle_mouse_click(self, pos):
        mx, my = pos
        
        if self.state == STATE_LOGIN:
            if 362 <= mx <= 662 and 320 <= my <= 350:
                self.active_input = "username"
            elif 362 <= mx <= 662 and 380 <= my <= 410:
                self.active_input = "password"
            elif 432 <= mx <= 592 and 440 <= my <= 480:
                if self.input_username and self.input_password:
                    try:
                        with open(self.config_path, "w") as f:
                            json.dump({"username": self.input_username, "password": self.input_password}, f)
                    except:
                        pass
                    try:
                        self.network.connect(self.input_username, self.input_password)
                    except Exception as e:
                        print(f"Connection failed: {e}")
                
        elif self.state == STATE_CHAR_SELECT:
            for i in range(3):
                y_pos = 220 + i * 100
                if 262 <= mx <= 762 and y_pos <= my <= y_pos + 80:
                    self.select_slot(i)
            if 100 <= mx <= 200 and 600 <= my <= 640:
                self.state = STATE_LOGIN
                
        elif self.state == STATE_CHAR_CREATE:
            if 362 <= mx <= 662 and 220 <= my <= 250:
                self.active_input = "char_name"
            elif 312 <= mx <= 432 and 300 <= my <= 330:
                self.player_race = "human"
            elif 452 <= mx <= 572 and 300 <= my <= 330:
                self.player_race = "dwarf"
            elif 592 <= mx <= 712 and 300 <= my <= 330:
                self.player_race = "orc"
            elif 412 <= mx <= 492 and 380 <= my <= 410:
                self.player_gender = "male"
            elif 532 <= mx <= 612 and 380 <= my <= 410:
                self.player_gender = "female"
            elif 432 <= mx <= 592 and 470 <= my <= 510:
                self.create_character()
            elif 100 <= mx <= 200 and 600 <= my <= 640:
                self.state = STATE_CHAR_SELECT

    def select_slot(self, slot_idx):
        self.selected_slot = slot_idx
        char = self.slots[slot_idx]
        if char:
            self.player_name = char["name"]
            self.player_race = char["race"]
            self.player_gender = char["gender"]
            self.level = char["level"]
            self.load_avatar(self.player_race, self.player_gender)
            self.network.send_packet(f"{self.input_username}@playCharacter|{self.player_name}")
        else:
            self.input_char_name = ""
            self.player_race = "human"
            self.player_gender = "male"
            self.state = STATE_CHAR_CREATE

    def create_character(self):
        if len(self.input_char_name.strip()) >= 3:
            name = self.input_char_name.strip()
            gender = self.player_gender[0].upper()
            self.network.send_packet(
                f"{self.input_username}@createCharacter|python|none-{name}|"
                f"{self.player_race}|{gender}|10|10|10|20"
            )

    def is_valid_position(self, x, y):
        padding = 0.15
        for cx in [x + padding, x + 1.0 - padding]:
            for cy in [y + padding, y + 1.0 - padding]:
                if self.map_renderer.is_solid(cx, cy):
                    return False
        return True

    def process_network_packet(self, packet):
        if not isinstance(packet, str):
            return
            
        parts = packet.split("@", 1)
        if len(parts) != 2:
            return
            
        header, payload = parts
        
        if "-getCharacters" in header:
            if payload == "EMPTY":
                self.slots = [None, None, None]
            else:
                data = payload.split("|")
                # Format: id | name | gender | level | race | gender_letter | costume | alignment | guild | title
                self.slots = [None, None, None]
                for i in range(len(data) // 10):
                    idx = i * 10
                    if i < 3:
                        self.slots[i] = {
                            "name": data[idx+1],
                            "gender": data[idx+2].lower(),
                            "level": int(data[idx+3]),
                            "race": data[idx+4].lower()
                        }
            self.state = STATE_CHAR_SELECT
            
        elif "-serverMessages" in header:
            self.chat_messages.append(payload)
            
        elif "-generalChat" in header:
            self.chat_messages.append(f"[General] {payload}")
            
        elif "-serverRates" in header or "-firstLoad" in header:
            self.state = STATE_GAME
            
        elif "-authenticate" in header:
            print(f"Auth Response: {payload}")
            if payload.startswith("true"):
                self.network.status = "Connected"
                self.network.status_error = False
                self.network.send_packet(f"{self.input_username}@getCharacters|python")
            else:
                self.network.status = "Authentication failed"
                self.network.status_error = True

    def update(self):
        import time
        # Process all incoming network packets
        if getattr(self, 'network', None):
            import queue
            while True:
                try:
                    packet = self.network.packet_queue.get_nowait()
                    self.process_network_packet(packet)
                except queue.Empty:
                    break
            
            # Send heartbeat every 15 seconds to prevent server timeout
            now = time.time()
            if now - self.last_heartbeat > 15:
                self.last_heartbeat = now
                if self.input_username:
                    self.network.send_packet(f"{self.input_username}@ping")

        if self.state == STATE_GAME:
            if self.chat_active:
                return # Don't move while chatting
                
            keys = pygame.key.get_pressed()
            dx, dy = 0, 0
            
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                dx -= self.player_speed
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                dx += self.player_speed
            if keys[pygame.K_UP] or keys[pygame.K_w]:
                dy -= self.player_speed
            if keys[pygame.K_DOWN] or keys[pygame.K_s]:
                dy += self.player_speed
                
            if dx != 0 and dy != 0:
                dx *= 0.7071
                dy *= 0.7071
                
            if dx != 0 or dy != 0:
                new_x = self.player_x + dx
                if self.is_valid_position(new_x, self.player_y):
                    self.player_x = new_x
                new_y = self.player_y + dy
                if self.is_valid_position(self.player_x, new_y):
                    self.player_y = new_y
                
                self.avatar_timer += 1
                if self.avatar_timer >= 8:
                    self.avatar_timer = 0
                    self.avatar_frame_idx = (self.avatar_frame_idx + 1) % len(self.avatar_frames)
                    
                # Determine movement direction string
                walk_cmd = None
                if dx < 0: walk_cmd = "walkWest"
                elif dx > 0: walk_cmd = "walkEast"
                elif dy < 0: walk_cmd = "walkNorth"
                elif dy > 0: walk_cmd = "walkSouth"
                
                if walk_cmd and self.current_walk != walk_cmd:
                    self.current_walk = walk_cmd
                    self.network.send_packet(f"{self.player_name}@{walk_cmd}|{self.player_x}|{self.player_y}")
            else:
                self.avatar_frame_idx = 0
                if self.current_walk is not None:
                    self.current_walk = None
                    self.network.send_packet(f"{self.player_name}@walkOff|{self.player_x}|{self.player_y}")

    def render(self):
        self.screen.fill(COLOR_BLACK)
        
        if self.state == STATE_LOGIN:
            self.render_login_screen()
        elif self.state == STATE_CHAR_SELECT:
            self.render_char_select_screen()
        elif self.state == STATE_CHAR_CREATE:
            self.render_char_create_screen()
        elif self.state == STATE_GAME:
            self.render_gameplay()
            
        pygame.display.flip()

    def render_login_screen(self):
        self.screen.blit(self.gui_header, (SCREEN_WIDTH // 2 - 250, 80))
        font = pygame.font.SysFont(None, 28)
        
        u_label = font.render("Username:", True, COLOR_WHITE)
        self.screen.blit(u_label, (362, 290))
        u_bg = COLOR_DARK_GREY if self.active_input == "username" else COLOR_BLACK
        pygame.draw.rect(self.screen, COLOR_WHITE, (362, 320, 300, 30), 1)
        pygame.draw.rect(self.screen, u_bg, (363, 321, 298, 28))
        self.screen.blit(font.render(self.input_username, True, COLOR_WHITE), (372, 326))
        
        p_label = font.render("Password:", True, COLOR_WHITE)
        self.screen.blit(p_label, (362, 355))
        p_bg = COLOR_DARK_GREY if self.active_input == "password" else COLOR_BLACK
        pygame.draw.rect(self.screen, COLOR_WHITE, (362, 380, 300, 30), 1)
        pygame.draw.rect(self.screen, p_bg, (363, 381, 298, 28))
        self.screen.blit(font.render("•" * len(self.input_password), True, COLOR_WHITE), (372, 386))
        
        pygame.draw.rect(self.screen, COLOR_WHITE, (432, 440, 160, 40), 2)
        self.screen.blit(font.render("LOGIN", True, COLOR_WHITE), (482, 450))

        # Login-only connection status bar.
        bar_height = 28
        bar_y = SCREEN_HEIGHT - bar_height
        pygame.draw.rect(self.screen, (18, 18, 18), (0, bar_y, SCREEN_WIDTH, bar_height))
        pygame.draw.line(self.screen, COLOR_GREY, (0, bar_y), (SCREEN_WIDTH, bar_y))
        status = self.network.status
        status_color = COLOR_RED if self.network.status_error else (
            COLOR_GREEN if status == "Connected" else COLOR_LIGHT_GREY
        )
        status_text = pygame.font.SysFont(None, 20).render(
            f"Connection status: {status}", True, status_color
        )
        self.screen.blit(status_text, (12, bar_y + 6))

    def render_char_select_screen(self):
        font = pygame.font.SysFont(None, 32)
        title = font.render("Select Character Slot", True, COLOR_WHITE)
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 120))
        
        for i in range(3):
            y_pos = 220 + i * 100
            pygame.draw.rect(self.screen, COLOR_WHITE, (262, y_pos, 500, 80), 1)
            pygame.draw.rect(self.screen, COLOR_DARK_GREY, (263, y_pos+1, 498, 78))
            
            slot_info = self.slots[i]
            if slot_info:
                text = font.render(f"Slot {i+1}: {slot_info['name']} (Lv. {slot_info['level']} {slot_info['race'].capitalize()})", True, COLOR_WHITE)
            else:
                text = font.render(f"Slot {i+1}: [ Empty Slot - Click to Create ]", True, COLOR_GREY)
            self.screen.blit(text, (292, y_pos + 28))
            
        pygame.draw.rect(self.screen, COLOR_WHITE, (100, 600, 100, 40), 1)
        self.screen.blit(pygame.font.SysFont(None, 24).render("BACK", True, COLOR_WHITE), (128, 612))

    def render_char_create_screen(self):
        font = pygame.font.SysFont(None, 28)
        title = font.render("Character Creation", True, COLOR_WHITE)
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 120))
        
        name_label = font.render("Character Name:", True, COLOR_WHITE)
        self.screen.blit(name_label, (362, 190))
        pygame.draw.rect(self.screen, COLOR_WHITE, (362, 220, 300, 30), 1)
        self.screen.blit(font.render(self.input_char_name, True, COLOR_WHITE), (372, 226))
        
        # Races
        races = ["human", "dwarf", "orc"]
        for idx, r in enumerate(races):
            rx = 312 + idx * 140
            bg = COLOR_GREEN if self.player_race == r else COLOR_DARK_GREY
            pygame.draw.rect(self.screen, COLOR_WHITE, (rx, 300, 120, 30), 1)
            pygame.draw.rect(self.screen, bg, (rx+1, 301, 118, 28))
            self.screen.blit(font.render(r.capitalize(), True, COLOR_WHITE), (rx + 25, 306))
            
        # Genders
        genders = ["male", "female"]
        for idx, g in enumerate(genders):
            gx = 412 + idx * 120
            bg = COLOR_GREEN if self.player_gender == g else COLOR_DARK_GREY
            pygame.draw.rect(self.screen, COLOR_WHITE, (gx, 380, 80, 30), 1)
            pygame.draw.rect(self.screen, bg, (gx+1, 381, 78, 28))
            self.screen.blit(font.render(g.capitalize(), True, COLOR_WHITE), (gx + 15, 386))
            
        pygame.draw.rect(self.screen, COLOR_WHITE, (432, 470, 160, 40), 1)
        self.screen.blit(font.render("CREATE", True, COLOR_WHITE), (477, 482))
        
        pygame.draw.rect(self.screen, COLOR_WHITE, (100, 600, 100, 40), 1)
        self.screen.blit(font.render("BACK", True, COLOR_WHITE), (125, 610))

    def render_gameplay(self):
        # 1. Map Viewport (Left Side)
        map_surf = pygame.Surface((MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT))
        
        half_screen_tiles_x = (MAP_VIEW_WIDTH / 32) / 2
        half_screen_tiles_y = (MAP_VIEW_HEIGHT / 32) / 2
        
        cam_x = max(half_screen_tiles_x, min(self.map_renderer.map_width - half_screen_tiles_x, self.player_x))
        cam_y = max(half_screen_tiles_y, min(self.map_renderer.map_height - half_screen_tiles_y, self.player_y))
        
        self.map_renderer.render(map_surf, cam_x, cam_y, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT)
        
        # Render Player inside Map Viewport
        player_screen_x = int((self.player_x - cam_x) * 32 + (MAP_VIEW_WIDTH / 2) - 16)
        player_screen_y = int((self.player_y - cam_y) * 32 + (MAP_VIEW_HEIGHT / 2) - 16)
        
        if self.avatar_frames:
            map_surf.blit(self.avatar_frames[self.avatar_frame_idx], (player_screen_x, player_screen_y))
            
        # Player Name Label
        font_sm = pygame.font.SysFont(None, 16)
        name_surf = font_sm.render(self.player_name, True, COLOR_YELLOW)
        name_x = player_screen_x + 16 - name_surf.get_width() // 2
        name_y = player_screen_y - 12
        pygame.draw.rect(map_surf, COLOR_BLACK, (name_x - 4, name_y - 2, name_surf.get_width() + 8, name_surf.get_height() + 4))
        map_surf.blit(name_surf, (name_x, name_y))
        
        self.screen.blit(map_surf, (0, 0))
        
        # 2. Chat Box (Bottom Left)
        chat_y = MAP_VIEW_HEIGHT
        chat_height = SCREEN_HEIGHT - MAP_VIEW_HEIGHT
        pygame.draw.rect(self.screen, COLOR_DARK_GREY, (0, chat_y, MAP_VIEW_WIDTH, chat_height))
        pygame.draw.rect(self.screen, COLOR_GREY, (0, chat_y, MAP_VIEW_WIDTH, chat_height), 2)
        
        # Print last 5 chat messages
        font_chat = pygame.font.SysFont(None, 20)
        for idx, msg in enumerate(self.chat_messages[-7:]):
            msg_surf = font_chat.render(msg, True, COLOR_WHITE)
            self.screen.blit(msg_surf, (15, chat_y + 10 + idx * 20))
            
        # Draw Chat Input Box
        input_y = SCREEN_HEIGHT - 25
        pygame.draw.rect(self.screen, COLOR_BLACK, (10, input_y, MAP_VIEW_WIDTH - 20, 20))
        if self.chat_active:
            pygame.draw.rect(self.screen, COLOR_GREEN, (10, input_y, MAP_VIEW_WIDTH - 20, 20), 1)
        else:
            pygame.draw.rect(self.screen, COLOR_GREY, (10, input_y, MAP_VIEW_WIDTH - 20, 20), 1)
            
        input_text = self.chat_input if self.chat_active else "Press ENTER to chat..."
        color = COLOR_WHITE if self.chat_active else COLOR_GREY
        input_surf = font_chat.render(input_text, True, color)
        self.screen.blit(input_surf, (15, input_y + 3))
            
        # 3. 1:1 Side Panel GUI (Right Side)
        panel_x = MAP_VIEW_WIDTH
        pygame.draw.rect(self.screen, COLOR_DARK_GREY, (panel_x, 0, PANEL_WIDTH, SCREEN_HEIGHT))
        pygame.draw.rect(self.screen, COLOR_GREY, (panel_x, 0, PANEL_WIDTH, SCREEN_HEIGHT), 2)
        
        # Header - Player Name, Level
        font_panel = pygame.font.SysFont(None, 22)
        name_label = font_panel.render(self.player_name, True, COLOR_YELLOW)
        level_label = font_panel.render(f"Lv. {self.level} {self.player_race.capitalize()}", True, COLOR_WHITE)
        self.screen.blit(name_label, (panel_x + 15, 15))
        self.screen.blit(level_label, (panel_x + 15, 35))
        
        # HP & Mana Bars
        self.draw_bar(panel_x + 15, 60, 190, 14, self.hp, self.max_hp, COLOR_RED, "HP")
        self.draw_bar(panel_x + 15, 80, 190, 14, self.mana, self.max_mana, COLOR_BLUE, "MP")
        self.draw_bar(panel_x + 15, 100, 190, 10, self.exp, self.max_exp, COLOR_GREEN, "XP")
        
        # 1:1 Player Equipment UI
        eq_y = 130
        pygame.draw.rect(self.screen, COLOR_BLACK, (panel_x + 15, eq_y, 190, 160))
        pygame.draw.rect(self.screen, COLOR_GREY, (panel_x + 15, eq_y, 190, 160), 1)
        
        eq_label = font_panel.render("EQUIPMENT", True, COLOR_WHITE)
        self.screen.blit(eq_label, (panel_x + 15 + 95 - eq_label.get_width()//2, eq_y + 8))
        
        # Equipment Slots Layout (Paperdoll Style)
        slots_layout = [
            ("helm", panel_x + 95, eq_y + 35),
            ("chest", panel_x + 95, eq_y + 75),
            ("pants", panel_x + 95, eq_y + 115),
            ("sword", panel_x + 45, eq_y + 75),  # Weapon Slot
            ("shield", panel_x + 145, eq_y + 75) # Shield Slot
        ]
        
        for slot_name, sx, sy in slots_layout:
            pygame.draw.rect(self.screen, COLOR_GREY, (sx - 16, sy - 16, 32, 32), 1)
            # Draw overlay icon
            overlay_name = "sword" if slot_name == "weapon" else slot_name
            if overlay_name in self.gui_overlays:
                self.screen.blit(self.gui_overlays[overlay_name], (sx - 16, sy - 16))
                
        # 1:1 Inventory (Backpack) Grid
        inv_y = 310
        pygame.draw.rect(self.screen, COLOR_BLACK, (panel_x + 15, inv_y, 190, 240))
        pygame.draw.rect(self.screen, COLOR_GREY, (panel_x + 15, inv_y, 190, 240), 1)
        
        inv_label = font_panel.render("BACKPACK", True, COLOR_WHITE)
        self.screen.blit(inv_label, (panel_x + 15 + 95 - inv_label.get_width()//2, inv_y + 8))
        
        # Draw 5x4 Grid for Inventory
        grid_start_x = panel_x + 25
        grid_start_y = inv_y + 35
        slot_size = 34
        gap = 6
        
        for row in range(5):
            for col in range(4):
                idx = row * 4 + col
                slot_x = grid_start_x + col * (slot_size + gap)
                slot_y = grid_start_y + row * (slot_size + gap)
                
                pygame.draw.rect(self.screen, COLOR_GREY, (slot_x, slot_y, slot_size, slot_size), 1)
                pygame.draw.rect(self.screen, COLOR_DARK_GREY, (slot_x + 1, slot_y + 1, slot_size - 2, slot_size - 2))
                
        # Mini map coordinate display at the very bottom
        coords_label = font_panel.render(f"Map: MyFirstMap (X:{int(self.player_x)}, Y:{int(self.player_y)})", True, COLOR_LIGHT_GREY)
        self.screen.blit(coords_label, (panel_x + 15, SCREEN_HEIGHT - 30))

    def draw_bar(self, x, y, w, h, val, max_val, color, label):
        pygame.draw.rect(self.screen, COLOR_BLACK, (x, y, w, h))
        fill_w = int((val / max_val) * w)
        pygame.draw.rect(self.screen, color, (x, y, fill_w, h))
        pygame.draw.rect(self.screen, COLOR_GREY, (x, y, w, h), 1)
        
        # Render text inside bar
        font_bar = pygame.font.SysFont(None, 12)
        bar_text = font_bar.render(f"{label}: {val}/{max_val}", True, COLOR_WHITE)
        self.screen.blit(bar_text, (x + w//2 - bar_text.get_width()//2, y + h//2 - bar_text.get_height()//2))

if __name__ == "__main__":
    client = KisnardClient()
    if "--smoke-test" in sys.argv:
        print("Kisnard Python client startup check passed.")
        client.network.close()
        pygame.quit()
    else:
        client.run()
