import socket
import ssl
import sys
import os
import threading
import queue
import time
import random
import tkinter as tk
from tkinter import scrolledtext, ttk

# PyInstaller-safe path resolution
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(__file__)
    BUNDLE_DIR = BASE_DIR

# Add java_serialization to path to import Java serialization helpers
sys.path.insert(0, os.path.abspath(os.path.join(BUNDLE_DIR, "java_serialization")))
from java_serialization import JavaObjectInputStream, JavaObjectOutputStream

PORT = 34215
HOST = "0.0.0.0"

# SSL Certificate files in PEM format
KEY_PATH = os.path.abspath(os.path.join(BASE_DIR, "scratch", "server.key"))
CRT_PATH = os.path.abspath(os.path.join(BASE_DIR, "scratch", "server.crt"))

import json

DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "scratch", "database.json"))

def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading database: {e}")
    return {"accounts": {}}

def save_db(data):
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with open(DB_PATH, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving database: {e}")

db = load_db()

ITEMS = {
    1: {"id": 1, "type": "W", "name": "Apprentice Sword", "sprite": "apprentice_sword.png", "value": 50, "weight": 2.0, "damage": "3,6"},
    2: {"id": 2, "type": "A", "name": "Bronze Curiass", "sprite": "bronze_curiass.png", "value": 75, "weight": 3.5, "ac": "3", "ac_block": "0,3"},
    3: {"id": 3, "type": "I", "name": "Small Health Vial", "sprite": "health_vial_small.png", "value": 15, "weight": 0.2, "use_type": "Potion", "description": "Heals 50 HP"}
}

SHOPS_PATH = os.path.abspath(os.path.join(BASE_DIR, "scratch", "shops.json"))

def load_shops():
    if os.path.exists(SHOPS_PATH):
        try:
            with open(SHOPS_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading shops: {e}")
    return {
        "Alchemist Shop": [
            {"id": 3, "price": 30}
        ],
        "Blacksmith Shop": [
            {"id": 1, "price": 100},
            {"id": 2, "price": 150}
        ]
    }

def save_shops(data):
    try:
        os.makedirs(os.path.dirname(SHOPS_PATH), exist_ok=True)
        with open(SHOPS_PATH, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving shops: {e}")

SHOPS = load_shops()

def serialize_item(item_data, unique_id):
    if not item_data:
        return "-1"
    item_def = ITEMS.get(item_data["id"])
    if not item_def:
        return "-1"
    
    itype = item_def["type"]
    name = item_def["name"]
    rarity = item_def.get("rarity", "Common")
    sprite = item_def["sprite"]
    value = str(item_def.get("value", 0))
    weight = str(item_def.get("weight", 0.0))
    lvl = str(item_def.get("level", 1))
    quantity = str(item_data.get("quantity", 1))
    
    if itype == "W":
        fields = [
            "W", name, rarity, sprite,
            item_def.get("damage", "1,2"),
            quantity, value, weight, lvl,
            "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
            str(unique_id), "no", "no", "0"
        ]
    elif itype == "A":
        fields = [
            "A", name, rarity, sprite,
            item_def.get("ac_block", "0,5"),
            quantity, value, weight, lvl,
            "0", "0", "0", "0",
            item_def.get("ac", "5"),
            "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
            str(unique_id), "no", "no", "0", "0", "0", "0", "0", "0", "0", "0", "0"
        ]
    else:
        fields = [
            "I", name, rarity, sprite,
            item_def.get("description", "A useful item."),
            quantity, value, weight, lvl,
            "0", "0", "0", "0", "0",
            item_def.get("use_type", "Potion"),
            "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
            str(unique_id)
        ]
    return "|".join(fields)

class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Kisnard Online - Emulated Server Control Panel")
        self.root.geometry("900x550")
        self.root.configure(bg="#2b2b2b")
        
        # Create Log folder and open log file in write mode ('w' overwrites the previous log)
        log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "Log"))
        os.makedirs(log_dir, exist_ok=True)
        self.log_file_path = os.path.join(log_dir, "server.log")
        self.log_file = open(self.log_file_path, "w", encoding="utf-8")
        
        # Handle clean window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # UI Queue for thread-safe updates
        self.log_queue = queue.Queue()
        self.chat_queue = queue.Queue()
        self.player_queue = queue.Queue()
        
        self.verbose_logs = tk.BooleanVar(value=False)
        
        # Load movement cooldown from database, default to 200 ms
        self.movement_cooldown_ms = db.get("movement_cooldown_ms", 200)
        
        # Dirty flag for debounced database saving (save every 5 seconds instead of every packet)
        self._db_dirty = False
        
        # Combat states & Tradeskills initialization
        self.active_combat = {}  # char_name -> monster_id
        self.monster_hps = {}    # monster_id -> current HP
        self.player_hps = {}     # char_name -> current HP (max 100)
        self.player_exps = {}    # char_name -> current EXP
        self.player_levels = {}  # char_name -> current Level
        self.depleted_nodes = {}  # coords -> respawn_timestamp
        self.tradeskill_cooldown_sec = db.get("tradeskill_cooldown_sec", 30.0)
        
        # Time of day (0-7, 0=dawn, 1-4=day, 5=dusk, 6-7=night)
        self.time_of_day = 3
        
        # Load dialogues and signs/books from database
        self.dialogues = db.setdefault("dialogues", {
            "Alchemist": [
                {"min_level": 1, "type": "quest", "id": 148},
                {"min_level": 1, "type": "quest", "id": 157},
                {"min_level": 1, "type": "quest", "id": 158}
            ]
        })
        default_signs = {f"{79 - i},105": i + 1 for i in range(52)}
        self.signs_books = db.setdefault("signs_books", default_signs)

        # Load map data (NPCs, monsters, objects, tradeskills)
        self.load_map_data()

        self.setup_styles()
        self.create_widgets()
        
        # Start queue polling
        self.root.after(100, self.poll_queues)
        
        # Active players set & Connection registry
        self.active_players = set()
        self.active_connections = {}
        self.connections_lock = threading.Lock()
        
        # Movement queue for dedicated thread
        self.movement_queue = queue.Queue()
        self.movement_thread = threading.Thread(target=self.movement_worker)
        self.movement_thread.daemon = True
        self.movement_thread.start()
        
        # Start background threads for combat and time of day (keeps them out of GUI thread)
        self.combat_thread = threading.Thread(target=self.combat_worker)
        self.combat_thread.daemon = True
        self.combat_thread.start()
        
        self.tod_thread = threading.Thread(target=self.tod_worker)
        self.tod_thread.daemon = True
        self.tod_thread.start()
        
        # Start timer-based loop for DB save
        self.root.after(5000, self.tick_db_save)         # Debounced DB save every 5s
        
        # Start TCP Server in a daemon thread (this one must be a thread for accept())
        self.server_thread = threading.Thread(target=self.start_tcp_server)
        self.server_thread.daemon = True
        self.server_thread.start()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#2b2b2b", foreground="#ffffff")
        style.configure("TFrame", background="#2b2b2b")
        style.configure("TLabel", background="#2b2b2b", foreground="#ffffff", font=("Consolas", 10))
        style.configure("Header.TLabel", font=("Consolas", 14, "bold"), foreground="#00ff00")

    def create_widgets(self):
        # Top Status Bar
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)
        
        header = ttk.Label(top_frame, text="KISNARD EMULATED SERVER", style="Header.TLabel")
        header.pack(side=tk.LEFT)
        
        self.edit_shops_btn = ttk.Button(top_frame, text="Edit Shops", command=self.open_shop_editor)
        self.edit_shops_btn.pack(side=tk.LEFT, padx=20)
        
        self.status_label = ttk.Label(top_frame, text="Status: Running | Port: 34215", foreground="#00ff00")
        self.status_label.pack(side=tk.RIGHT)
        
        # Cooldown Slider Frame
        slider_frame = ttk.Frame(self.root, padding=10)
        slider_frame.pack(fill=tk.X)
        
        ttk.Label(slider_frame, text="Movement Cooldown (ms):").pack(side=tk.LEFT, padx=5)
        self.cooldown_scale = tk.Scale(
            slider_frame,
            from_=10,
            to=1500,
            orient=tk.HORIZONTAL,
            bg="#2b2b2b",
            fg="#ffffff",
            troughcolor="#1e1e1e",
            highlightbackground="#2b2b2b",
            command=self.on_cooldown_change
        )
        self.cooldown_scale.set(self.movement_cooldown_ms)
        self.cooldown_scale.bind("<ButtonRelease-1>", self.on_cooldown_release)
        self.cooldown_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.verbose_cb = ttk.Checkbutton(
            slider_frame,
            text="Verbose Logs",
            variable=self.verbose_logs
        )
        self.verbose_cb.pack(side=tk.RIGHT, padx=10)
        
        # Time of Day Controls
        ttk.Label(slider_frame, text="Time:").pack(side=tk.RIGHT, padx=5)
        self.tod_var = tk.StringVar()
        self.tod_combobox = ttk.Combobox(
            slider_frame,
            textvariable=self.tod_var,
            values=["Dawn", "Day 1", "Day 2", "Day 3", "Day 4", "Dusk", "Night 1", "Night 2"],
            state="readonly",
            width=8
        )
        self.tod_combobox.current(self.time_of_day)
        self.tod_combobox.bind("<<ComboboxSelected>>", self.on_tod_change)
        self.tod_combobox.pack(side=tk.RIGHT, padx=5)
        
        # Main Body Split
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#1e1e1e", bd=0)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left Panel - Notebook for Players and Guilds
        left_frame = tk.Frame(paned_window, bg="#2b2b2b")
        
        notebook = ttk.Notebook(left_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Players
        players_tab = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(players_tab, text="Players")
        
        self.player_listbox = tk.Listbox(
            players_tab, 
            bg="#1e1e1e", 
            fg="#ffffff", 
            selectbackground="#00ff00",
            selectforeground="#000000",
            font=("Consolas", 11), 
            bd=1, 
            highlightthickness=0
        )
        self.player_listbox.pack(fill=tk.BOTH, expand=True)
        self.player_listbox.bind("<<ListboxSelect>>", self.on_player_select)
        
        self.edit_player_btn = ttk.Button(players_tab, text="Edit Selected Player", command=self.open_player_editor)
        self.edit_player_btn.pack(fill=tk.X, pady=5)
        
        # Tab 2: Guilds
        guilds_tab = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(guilds_tab, text="Guilds")
        
        self.guild_listbox = tk.Listbox(
            guilds_tab, 
            bg="#1e1e1e", 
            fg="#ffffff", 
            selectbackground="#00ff00",
            selectforeground="#000000",
            font=("Consolas", 11), 
            bd=1, 
            highlightthickness=0
        )
        self.guild_listbox.pack(fill=tk.BOTH, expand=True)
        
        self.edit_guild_btn = ttk.Button(guilds_tab, text="Edit/Rename Guild", command=self.open_guild_editor)
        self.edit_guild_btn.pack(fill=tk.X, pady=5)

        # Tab 3: Interactables (Signs & Books)
        interact_tab = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(interact_tab, text="Interactables")

        add_frame = ttk.Frame(interact_tab, padding=5)
        add_frame.pack(fill=tk.X)
        ttk.Label(add_frame, text="Coords (X,Y):").grid(row=0, column=0, sticky=tk.W)
        self.interact_coords_entry = ttk.Entry(add_frame, width=10)
        self.interact_coords_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(add_frame, text="Read ID:").grid(row=0, column=2, sticky=tk.W)
        self.interact_id_entry = ttk.Entry(add_frame, width=5)
        self.interact_id_entry.grid(row=0, column=3, padx=5)

        self.add_interact_btn = ttk.Button(add_frame, text="Add/Update", command=self.add_sign_book)
        self.add_interact_btn.grid(row=0, column=4, padx=5)

        self.interact_listbox = tk.Listbox(
            interact_tab,
            bg="#1e1e1e",
            fg="#ffffff",
            selectbackground="#00ff00",
            selectforeground="#000000",
            font=("Consolas", 11),
            bd=1,
            highlightthickness=0
        )
        self.interact_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.interact_listbox.bind("<Double-1>", self.on_interact_double_click)

        self.remove_interact_btn = ttk.Button(interact_tab, text="Remove Selected", command=self.remove_sign_book)
        self.remove_interact_btn.pack(fill=tk.X)

        self.update_sign_book_listbox()
        
        # Tab 3: Tradeskills
        ts_tab = tk.Frame(notebook, bg="#2b2b2b")
        notebook.add(ts_tab, text="Tradeskills")
        
        self.ts_listbox = tk.Listbox(
            ts_tab, 
            bg="#1e1e1e", 
            fg="#ffffff", 
            selectbackground="#00ff00",
            selectforeground="#000000",
            font=("Consolas", 10), 
            bd=1, 
            highlightthickness=0
        )
        self.ts_listbox.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = tk.Frame(ts_tab, bg="#2b2b2b")
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.reset_node_btn = ttk.Button(btn_frame, text="Reset Node", command=self.reset_selected_node)
        self.reset_node_btn.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        
        self.reset_all_nodes_btn = ttk.Button(btn_frame, text="Reset All", command=self.reset_all_nodes)
        self.reset_all_nodes_btn.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        
        self.config_cooldown_btn = ttk.Button(btn_frame, text="Set Cooldown", command=self.open_cooldown_config)
        self.config_cooldown_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=2, pady=2)
        
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        self.update_guild_list()
        self.update_ts_list()
        
        # Right Panel - Notebook for Console and Chat Logs
        right_frame = tk.Frame(paned_window, bg="#2b2b2b")
        
        right_notebook = ttk.Notebook(right_frame)
        right_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Console Logs
        console_tab = tk.Frame(right_notebook, bg="#2b2b2b")
        right_notebook.add(console_tab, text="Console Logs")
        
        self.log_area = scrolledtext.ScrolledText(
            console_tab, 
            bg="#1e1e1e", 
            fg="#ffffff", 
            insertbackground="white",
            font=("Consolas", 10),
            bd=1,
            highlightthickness=0
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # Tab 2: Chat Logs
        chat_tab = tk.Frame(right_notebook, bg="#2b2b2b")
        right_notebook.add(chat_tab, text="Chat Logs")
        
        self.chat_area = scrolledtext.ScrolledText(
            chat_tab, 
            bg="#1e1e1e", 
            fg="#00ffff",
            insertbackground="white",
            font=("Consolas", 10),
            bd=1,
            highlightthickness=0
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True)
        
        # Add to paned window
        paned_window.add(left_frame, width=250)
        paned_window.add(right_frame, width=650)

    def on_cooldown_change(self, val):
        self.movement_cooldown_ms = int(val)

    def on_cooldown_release(self, event):
        val_int = self.cooldown_scale.get()
        self.movement_cooldown_ms = val_int
        db["movement_cooldown_ms"] = val_int
        save_db(db)
        self.log(f"[*] Movement cooldown adjusted to {val_int} ms")

    def on_tod_change(self, event):
        idx = self.tod_combobox.current()
        if idx != -1:
            self.time_of_day = idx
            self.broadcast_packet(f"updateTimeOfDay@{self.time_of_day}")
            self.log(f"[*] Time of Day manually set to: {self.tod_combobox.get()}")

    def add_sign_book(self):
        coords = self.interact_coords_entry.get().strip()
        read_id_str = self.interact_id_entry.get().strip()
        if not coords or not read_id_str:
            messagebox.showerror("Error", "Please enter both coordinates (X,Y) and a Read ID.")
            return
        try:
            read_id = int(read_id_str)
        except ValueError:
            messagebox.showerror("Error", "Read ID must be an integer.")
            return
        self.signs_books[coords] = read_id
        db["signs_books"] = self.signs_books
        save_db(db)
        self.update_sign_book_listbox()
        self.log(f"[*] Registered sign/book at {coords} with Read ID {read_id}")

    def remove_sign_book(self):
        selection = self.interact_listbox.curselection()
        if not selection:
            return
        item_text = self.interact_listbox.get(selection[0])
        coords = item_text.split("->")[0].strip()
        if coords in self.signs_books:
            del self.signs_books[coords]
            db["signs_books"] = self.signs_books
            save_db(db)
            self.update_sign_book_listbox()
            self.log(f"[*] Removed sign/book at {coords}")

    def update_sign_book_listbox(self):
        self.interact_listbox.delete(0, tk.END)
        for coords, read_id in sorted(self.signs_books.items()):
            self.interact_listbox.insert(tk.END, f"{coords} -> Read ID: {read_id}")

    def on_interact_double_click(self, event):
        selection = self.interact_listbox.curselection()
        if not selection:
            return
        item_text = self.interact_listbox.get(selection[0])
        parts = item_text.split("->")
        if len(parts) == 2:
            coords = parts[0].strip()
            read_id_str = parts[1].replace("Read ID:", "").strip()
            
            self.interact_coords_entry.delete(0, tk.END)
            self.interact_coords_entry.insert(0, coords)
            
            self.interact_id_entry.delete(0, tk.END)
            self.interact_id_entry.insert(0, read_id_str)
            
            self.interact_id_entry.focus_set()

    def on_player_select(self, event):
        selection = self.player_listbox.curselection()
        if not selection:
            return
        item_text = self.player_listbox.get(selection[0])
        username = item_text.strip().split()[0]
        
        char_data = None
        for acc_name, acc in db.get("accounts", {}).items():
            for c in acc.get("characters", []):
                if c["name"].lower() == username.lower():
                    char_data = c
                    break
            if char_data:
                break
                
        if char_data:
            self.log(f"=== Character Info: {char_data['name']} ===")
            self.log(f"Level: {char_data.get('level', 1)} | Race: {char_data.get('race', 'Human')} | Gender: {char_data.get('gender', 'M')}")
            self.log(f"Position: ({char_data.get('x')}, {char_data.get('y')}) | Gold: {char_data.get('gold', 0)} | Bank Gold: {char_data.get('bank_gold', 0)}")
            
            inv = char_data.get("inventory", [None]*25)
            self.log("--- Backpack ---")
            for idx, item in enumerate(inv):
                if item:
                    item_def = ITEMS.get(item["id"])
                    if item_def:
                        self.log(f"  Slot {idx:02d}: {item_def['name']} (x{item.get('quantity', 1)}) [UID: {item.get('unique_id')}]")
                else:
                    self.log(f"  Slot {idx:02d}: Empty")
                    
            eq = char_data.get("equipment", [None]*14)
            self.log("--- Equipment ---")
            for idx, item in enumerate(eq):
                if item:
                    item_def = ITEMS.get(item["id"])
                    if item_def:
                        self.log(f"  Slot {idx:02d}: {item_def['name']} [UID: {item.get('unique_id')}]")
                else:
                    self.log(f"  Slot {idx:02d}: Empty")
                    
            bank = char_data.get("bank", [None]*256)
            self.log("--- Bank Items (Non-Empty) ---")
            has_bank_items = False
            for idx, item in enumerate(bank):
                if item:
                    item_def = ITEMS.get(item["id"])
                    if item_def:
                        self.log(f"  Slot {idx:03d}: {item_def['name']} (x{item.get('quantity', 1)}) [UID: {item.get('unique_id')}]")
                        has_bank_items = True
            if not has_bank_items:
                self.log("  Bank is empty")
            self.log("=================================")

    def update_guild_list(self):
        self.guild_listbox.delete(0, tk.END)
        guilds = db.get("guilds", {})
        for g_name in guilds:
            self.guild_listbox.insert(tk.END, g_name)

    def open_guild_editor(self):
        from tkinter import messagebox
        selection = self.guild_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a guild from the list first.")
            return
        guild_name = self.guild_listbox.get(selection[0])
        
        guilds = db.setdefault("guilds", {})
        g_info = guilds.get(guild_name)
        if not g_info:
            messagebox.showerror("Error", "Guild not found in database.")
            return
            
        editor = tk.Toplevel(self.root)
        editor.title(f"Edit Guild: {guild_name}")
        editor.geometry("400x400")
        editor.configure(bg="#2b2b2b")
        
        tk.Label(editor, text="Guild Name:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=10, pady=5)
        name_entry = ttk.Entry(editor, width=30)
        name_entry.pack(fill=tk.X, padx=10)
        name_entry.insert(0, guild_name)
        
        tk.Label(editor, text="Guild Tag:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=10, pady=5)
        tag_entry = ttk.Entry(editor, width=10)
        tag_entry.pack(fill=tk.X, padx=10)
        tag_entry.insert(0, g_info.get("tag", ""))
        
        tk.Label(editor, text="MOTD:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=10, pady=5)
        motd_entry = ttk.Entry(editor, width=40)
        motd_entry.pack(fill=tk.X, padx=10)
        motd_entry.insert(0, g_info.get("motd", ""))
        
        tk.Label(editor, text="Description:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=10, pady=5)
        desc_entry = ttk.Entry(editor, width=40)
        desc_entry.pack(fill=tk.X, padx=10)
        desc_entry.insert(0, g_info.get("description", ""))
        
        def save_guild_changes():
            new_name = name_entry.get().strip()
            new_tag = tag_entry.get().strip()
            new_motd = motd_entry.get().strip()
            new_desc = desc_entry.get().strip()
            
            if not new_name or not new_tag:
                messagebox.showerror("Error", "Name and Tag cannot be empty.")
                return
                
            if new_name != guild_name and new_name in guilds:
                messagebox.showerror("Error", "A guild with that name already exists.")
                return
                
            g_data = guilds.pop(guild_name)
            g_data["tag"] = new_tag
            g_data["motd"] = new_motd
            g_data["description"] = new_desc
            
            guilds[new_name] = g_data
            
            for acc_name, acc in db.get("accounts", {}).items():
                for c in acc.get("characters", []):
                    if c.get("guild") == guild_name:
                        c["guild"] = new_name
                        
            save_db(db)
            self.update_guild_list()
            messagebox.showinfo("Success", "Guild updated successfully!")
            
            with self.connections_lock:
                for o_name, conn in self.active_connections.items():
                    o_char = None
                    for acc_name, acc in db.get("accounts", {}).items():
                        for oc in acc.get("characters", []):
                            if oc["name"].lower() == o_name.lower():
                                o_char = oc
                                break
                        if o_char:
                            break
                    if o_char and o_char.get("guild") == new_name:
                        members_payload = []
                        for m in g_data.get("members", []):
                            members_payload.extend([m["name"], m["rank"], str(m["level"]), m["last_login"]])
                        header = [
                            str(g_data.get("id", 1)),
                            new_name,
                            new_tag,
                            new_motd,
                            new_desc,
                            str(g_data.get("level", 1)),
                            g_data.get("leader"),
                            g_data.get("created_at"),
                            "-1", "-1", "-1", "-1", "-1", "-1"
                        ]
                        payload = "|".join(header + members_payload)
                        conn["send"](f"{o_name}-guildWindow@{payload}")
            editor.destroy()
            
        ttk.Button(editor, text="Save Changes", command=save_guild_changes).pack(pady=20)

    def update_ts_list(self):
        selected = self.ts_listbox.curselection()
        selected_text = self.ts_listbox.get(selected[0]) if selected else None
        
        self.ts_listbox.delete(0, tk.END)
        now = time.time()
        for val, x, y in self.map_tradeskills:
            coords = f"{x},{y}"
            sprite = self.tradeskill_sprites[val % len(self.tradeskill_sprites)] if self.tradeskill_sprites else "ore_copper.png"
            name = sprite.replace(".gif", "").replace(".png", "").replace("_", " ").title()
            
            if coords in self.depleted_nodes:
                remaining = max(0, int(self.depleted_nodes[coords] - now))
                status = f"Depleted ({remaining}s)"
            else:
                status = "Active"
                
            entry_text = f"{coords} - {name} ({status})"
            self.ts_listbox.insert(tk.END, entry_text)
            
        if selected_text:
            for i in range(self.ts_listbox.size()):
                if self.ts_listbox.get(i).split(" - ")[0] == selected_text.split(" - ")[0]:
                    self.ts_listbox.selection_set(i)
                    break

    def reset_selected_node(self):
        selection = self.ts_listbox.curselection()
        if not selection:
            return
        coords = self.ts_listbox.get(selection[0]).split(" - ")[0]
        if coords in self.depleted_nodes:
            del self.depleted_nodes[coords]
            self.log(f"[*] Admin reset tradeskill node at {coords}")
            with self.connections_lock:
                for o_name, conn in self.active_connections.items():
                    self.send_all_entities(o_name, conn["send"])
            self.update_ts_list()

    def reset_all_nodes(self):
        if self.depleted_nodes:
            self.depleted_nodes.clear()
            self.log("[*] Admin reset all depleted tradeskill nodes")
            with self.connections_lock:
                for o_name, conn in self.active_connections.items():
                    self.send_all_entities(o_name, conn["send"])
            self.update_ts_list()

    def open_cooldown_config(self):
        from tkinter import simpledialog, messagebox
        val = simpledialog.askfloat("Set Cooldown", "Enter new tradeskill respawn cooldown (seconds):", initialvalue=self.tradeskill_cooldown_sec)
        if val is not None:
            if val < 1.0:
                messagebox.showerror("Error", "Cooldown must be at least 1 second.")
                return
            self.tradeskill_cooldown_sec = val
            db["tradeskill_cooldown_sec"] = val
            save_db(db)
            self.log(f"[*] Tradeskill respawn cooldown adjusted to {val} seconds")

    def open_player_editor(self):
        from tkinter import messagebox
        selection = self.player_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a player from the list first.")
            return
        item_text = self.player_listbox.get(selection[0])
        username = item_text.strip().split()[0]
        
        char_data = None
        for a_name, acc in db.get("accounts", {}).items():
            for c in acc.get("characters", []):
                if c["name"].lower() == username.lower():
                    char_data = c
                    break
            if char_data:
                break
                
        if not char_data:
            messagebox.showerror("Error", "Character not found in database.")
            return
            
        editor = tk.Toplevel(self.root)
        editor.title(f"Edit Player: {char_data['name']}")
        editor.geometry("600x600")
        editor.configure(bg="#2b2b2b")
        
        form_frame = tk.Frame(editor, bg="#2b2b2b")
        form_frame.pack(fill=tk.X, pady=10, padx=10)
        
        tk.Label(form_frame, text="Level:", bg="#2b2b2b", fg="#ffffff").grid(row=0, column=0, sticky=tk.W, pady=2)
        level_entry = ttk.Entry(form_frame, width=10)
        level_entry.insert(0, str(char_data.get("level", 1)))
        level_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        
        tk.Label(form_frame, text="Gold:", bg="#2b2b2b", fg="#ffffff").grid(row=1, column=0, sticky=tk.W, pady=2)
        gold_entry = ttk.Entry(form_frame, width=15)
        gold_entry.insert(0, str(char_data.get("gold", 0)))
        gold_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)
        
        tk.Label(form_frame, text="Bank Gold:", bg="#2b2b2b", fg="#ffffff").grid(row=2, column=0, sticky=tk.W, pady=2)
        bgold_entry = ttk.Entry(form_frame, width=15)
        bgold_entry.insert(0, str(char_data.get("bank_gold", 0)))
        bgold_entry.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)
        
        tk.Label(form_frame, text="X Coord:", bg="#2b2b2b", fg="#ffffff").grid(row=3, column=0, sticky=tk.W, pady=2)
        x_entry = ttk.Entry(form_frame, width=10)
        x_entry.insert(0, str(char_data.get("x", 79)))
        x_entry.grid(row=3, column=1, sticky=tk.W, pady=2, padx=5)
        
        tk.Label(form_frame, text="Y Coord:", bg="#2b2b2b", fg="#ffffff").grid(row=4, column=0, sticky=tk.W, pady=2)
        y_entry = ttk.Entry(form_frame, width=10)
        y_entry.insert(0, str(char_data.get("y", 107)))
        y_entry.grid(row=4, column=1, sticky=tk.W, pady=2, padx=5)
        
        tk.Label(editor, text="Inventory / Equipment / Bank (JSON format):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=10, pady=5)
        
        combined_json = {
            "inventory": char_data.get("inventory", [None]*25),
            "equipment": char_data.get("equipment", [None]*14),
            "bank": char_data.get("bank", [None]*256)
        }
        
        text_area = scrolledtext.ScrolledText(editor, width=70, height=20, bg="#1e1e1e", fg="#ffffff", insertbackground="white")
        text_area.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        text_area.insert(tk.END, json.dumps(combined_json, indent=4))
        
        def save_player_data():
            try:
                new_level = int(level_entry.get())
                new_gold = int(gold_entry.get())
                new_bgold = int(bgold_entry.get())
                new_x = int(x_entry.get())
                new_y = int(y_entry.get())
                
                json_data = json.loads(text_area.get("1.0", tk.END).strip())
                if "inventory" not in json_data or "equipment" not in json_data or "bank" not in json_data:
                    messagebox.showerror("Error", "JSON must contain 'inventory', 'equipment', and 'bank' fields.")
                    return
                    
                char_data["level"] = new_level
                char_data["gold"] = new_gold
                char_data["bank_gold"] = new_bgold
                char_data["x"] = new_x
                char_data["y"] = new_y
                char_data["inventory"] = json_data["inventory"]
                char_data["equipment"] = json_data["equipment"]
                char_data["bank"] = json_data["bank"]
                
                save_db(db)
                messagebox.showinfo("Success", "Player data saved successfully!")
                
                conn = None
                with self.connections_lock:
                    conn = self.active_connections.get(username.lower())
                if conn:
                    conn["x"] = new_x
                    conn["y"] = new_y
                    send_pkt = conn["send"]
                    
                    send_pkt(f"{char_data['name']}-updatePlayerLocations@{char_data['name']}|{new_x},{new_y}|{conn['race']}|{conn['gender']}|no|N|0|0.0|None|0|{new_x},{new_y}|n|0|0")
                    
                    inv = char_data["inventory"]
                    response = f"{char_data['name']}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                    send_pkt(response)
                    
                    bank = char_data["bank"]
                    response_bk = f"{char_data['name']}-bankWindow@40-37-32|y|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 30000+i) for i, it in enumerate(bank)])
                    send_pkt(response_bk)
                    
                    exp = self.player_exps.get(char_data['name'], 0)
                    next_exp = new_level * 300
                    start_exp = (new_level - 1) * 300
                    stats = [
                        "40-37-32",
                        "10", "0", "10", "0", "10", "0", "10", "0", "10",
                        str(exp),
                        str(new_level),
                        str(start_exp),
                        str(next_exp),
                        "10", "0",
                        "10", "10", "10", "10", "10", "10",
                        "0", "12", "10", "100/100", "0", "None",
                        "0", "5", "0/150", "0,0",
                        "0", "0,0", "0", "None", "0", "m", "1.0"
                    ]
                    eq = char_data["equipment"]
                    stats.extend([serialize_item(it, it.get("unique_id") if it else 20000+i) for i, it in enumerate(eq)])
                    send_pkt(f"{char_data['name']}-characterWindow@{'|'.join(stats)}")
                    
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save data: {e}")
                
        ttk.Button(editor, text="Save Changes", command=save_player_data).pack(pady=10)

    def open_shop_editor(self):
        from tkinter import messagebox
        editor = tk.Toplevel(self.root)
        editor.title("Shop Editor")
        editor.geometry("500x400")
        editor.configure(bg="#2b2b2b")
        
        ttk.Label(editor, text="Select Shop:", background="#2b2b2b", foreground="#ffffff").pack(pady=10)
        shop_var = tk.StringVar(value=list(SHOPS.keys())[0] if SHOPS else "")
        shop_cb = ttk.Combobox(editor, textvariable=shop_var, values=list(SHOPS.keys()), state="readonly")
        shop_cb.pack(pady=5)
        
        ttk.Label(editor, text="Shop Items (JSON format):", background="#2b2b2b", foreground="#ffffff").pack(pady=10)
        
        text_area = scrolledtext.ScrolledText(editor, width=50, height=12, bg="#1e1e1e", fg="#ffffff", insertbackground="white")
        text_area.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        
        def load_selected_shop(*args):
            shop_data = SHOPS.get(shop_var.get(), [])
            text_area.delete("1.0", tk.END)
            text_area.insert(tk.END, json.dumps(shop_data, indent=4))
            
        shop_cb.bind("<<ComboboxSelected>>", load_selected_shop)
        load_selected_shop()
        
        def save_selected_shop():
            try:
                new_data = json.loads(text_area.get("1.0", tk.END).strip())
                if not isinstance(new_data, list):
                    messagebox.showerror("Error", "Shop items must be a JSON list of objects.")
                    return
                for item in new_data:
                    if "id" not in item or "price" not in item:
                        messagebox.showerror("Error", "Each item must have 'id' and 'price' fields.")
                        return
                SHOPS[shop_var.get()] = new_data
                save_shops(SHOPS)
                messagebox.showinfo("Success", f"Saved {shop_var.get()} successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Invalid JSON: {e}")
                
        ttk.Button(editor, text="Save Shop", command=save_selected_shop).pack(pady=10)

    def log(self, message):
        print(message)
        self.log_queue.put(message + "\n")
        if hasattr(self, "log_file") and not self.log_file.closed:
            self.log_file.write(message + "\n")
            self.log_file.flush()

    def log_chat(self, message):
        print(message)
        self.chat_queue.put(message + "\n")
        if hasattr(self, "log_file") and not self.log_file.closed:
            self.log_file.write(message + "\n")
            self.log_file.flush()

    def on_closing(self):
        if hasattr(self, "log_file") and not self.log_file.closed:
            self.log_file.close()
        self.root.destroy()

    def add_player(self, username):
        self.player_queue.put(("add", username))

    def remove_player(self, username):
        self.player_queue.put(("remove", username))

    def poll_queues(self):
        # Process Logs
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_area.insert(tk.END, msg)
            self.log_area.see(tk.END)
            
        # Process Chat Logs
        while not self.chat_queue.empty():
            msg = self.chat_queue.get_nowait()
            self.chat_area.insert(tk.END, msg)
            self.chat_area.see(tk.END)
            
        # Process Player List Updates
        while not self.player_queue.empty():
            action, username = self.player_queue.get_nowait()
            if action == "add":
                if username not in self.active_players:
                    self.active_players.add(username)
                    self.player_listbox.insert(tk.END, f" {username} (Online)")
            elif action == "remove":
                if username in self.active_players:
                    self.active_players.remove(username)
                    # Refresh Listbox
                    self.player_listbox.delete(0, tk.END)
                    for p in self.active_players:
                        self.player_listbox.insert(tk.END, f" {p} (Online)")
                        
        # Process Tradeskill Respawns
        now = time.time()
        respawned = []
        for coords, respawn_time in list(self.depleted_nodes.items()):
            if now >= respawn_time:
                respawned.append(coords)
                del self.depleted_nodes[coords]
        if respawned:
            with self.connections_lock:
                for o_name, conn in self.active_connections.items():
                    self.send_all_entities(o_name, conn["send"])
                    
        # Update Tradeskill Listbox in GUI every 1 second (10 ticks of 100ms)
        self.ts_update_ticks = getattr(self, "ts_update_ticks", 0) + 1
        if self.ts_update_ticks >= 10:
            self.ts_update_ticks = 0
            self.update_ts_list()
                        
        self.root.after(100, self.poll_queues)

    def load_map_data(self):
        self.log("[*] Loading map layer data (NPCs, mobs, objects, tradeskills)...")
        base_img_path = r"c:\Users\gooro\OneDrive\Desktop\KisnardOnline\res\images"
        base_tile_path = r"c:\Users\gooro\OneDrive\Desktop\KisnardFinds\game_assets\images\tiles"
        
        # Load sprite lists
        npc_dir = os.path.join(base_img_path, "npc")
        self.npc_sprites = sorted([f.replace("npc_", "") for f in os.listdir(npc_dir) if f.startswith("npc_")]) if os.path.exists(npc_dir) else []
        
        monster_dir = os.path.join(base_img_path, "monster")
        self.monster_sprites = sorted([f.replace("monster_", "") for f in os.listdir(monster_dir) if f.startswith("monster_")]) if os.path.exists(monster_dir) else []
        
        object_dir = os.path.join(base_img_path, "object")
        self.object_sprites = sorted([f.replace("object_", "") for f in os.listdir(object_dir) if f.startswith("object_")]) if os.path.exists(object_dir) else []
        
        tradeskill_dir = os.path.join(base_img_path, "tradeskill")
        self.tradeskill_sprites = sorted([f.replace("tradeskill_", "") for f in os.listdir(tradeskill_dir) if f.startswith("tradeskill_")]) if os.path.exists(tradeskill_dir) else []
        
        self.log(f"[*] Loaded sprites - NPCs: {len(self.npc_sprites)}, Mobs: {len(self.monster_sprites)}, Objects: {len(self.object_sprites)}, Tradeskills: {len(self.tradeskill_sprites)}")
        
        # Parse map layers
        self.map_npcs = self.parse_layer_file(os.path.join(base_tile_path, "MyFirstMap-npcs-p.json"))
        self.map_objects = self.parse_layer_file(os.path.join(base_tile_path, "MyFirstMap-object-p.json"))
        self.map_mobs = self.parse_layer_file(os.path.join(base_tile_path, "MyFirstMap-mobs-p.json"))
        self.map_tradeskills = self.parse_layer_file(os.path.join(base_tile_path, "MyFirstMap-tradeskills-p.json"))
        self.map_collision = self.parse_layer_file(os.path.join(base_tile_path, "MyFirstMap-collision-p.json"))
        self.blocked_coords = {(x, y) for _, x, y in self.map_collision}
        
        self.log(f"[*] Map entities loaded - NPCs: {len(self.map_npcs)}, Mobs: {len(self.map_mobs)}, Objects: {len(self.map_objects)}, Tradeskills: {len(self.map_tradeskills)}, Collision tiles: {len(self.blocked_coords)}")

    def parse_layer_file(self, filepath):
        if not os.path.exists(filepath):
            self.log(f"[-] Warning: Map layer file not found: {filepath}")
            return []
        with open(filepath, "r") as f:
            content = f.read().strip()
        tokens = [t.strip() for t in content.split(",") if t.strip()]
        values = [int(t) for t in tokens]
        
        entities = []
        width = 1440
        for idx, val in enumerate(values):
            if val != 0 and val != -1:
                x = idx % width
                y = idx // width
                entities.append((val, x, y))
        return entities

    def disconnect_client(self, char_name):
        username_to_remove = None
        with self.connections_lock:
            conn = self.active_connections.get(char_name.lower())
            if conn:
                username_to_remove = conn.get("char_id")
                try:
                    conn["socket"].close()
                except Exception:
                    pass
                del self.active_connections[char_name.lower()]
            if char_name in self.active_combat:
                del self.active_combat[char_name]
        if username_to_remove:
            self.remove_player(username_to_remove)
            self.log(f"[*] Client '{username_to_remove}' disconnected and cleaned up due to socket error.")

    def broadcast_packet(self, packet_body):
        with self.connections_lock:
            conns = list(self.active_connections.items())
        for char_name, conn in conns:
            try:
                conn["send"](f"{conn['char_id']}-{packet_body}")
            except Exception as e:
                self.log(f"[-] Error broadcasting to {char_name}: {e}")
                self.disconnect_client(char_name)

    def whisper_packet(self, target_name, packet_body):
        with self.connections_lock:
            conn = self.active_connections.get(target_name.lower())
        if conn:
            try:
                conn["send"](f"{conn['char_id']}-{packet_body}")
                return True
            except Exception:
                self.disconnect_client(target_name)
        return False

    def mark_db_dirty(self):
        """Mark the database as needing a save. The periodic tick_db_save will flush it."""
        self._db_dirty = True

    def tick_db_save(self):
        """Periodically flush dirty database to disk (every 5 seconds)."""
        if self._db_dirty:
            save_db(db)
            self._db_dirty = False
        self.root.after(5000, self.tick_db_save)

    def tod_worker(self):
        """Thread-based time-of-day cycle."""
        while True:
            time.sleep(45.0)
            self.time_of_day = (self.time_of_day + 1) % 8
            self.broadcast_packet(f"updateTimeOfDay@{self.time_of_day}")
            # Update GUI safely
            self.root.after(0, lambda: self.tod_combobox.current(self.time_of_day))

    def combat_worker(self):
        """Thread-based combat loop."""
        while True:
            time.sleep(2.0)
            with self.connections_lock:
                combat_list = list(self.active_combat.items())
                    
            for char_name, monster_id in combat_list:
                with self.connections_lock:
                    conn = self.active_connections.get(char_name.lower())
                if not conn:
                    continue
                    
                char_id = conn["char_id"]
                    
                try:
                    # Initialize HP and EXP
                    if monster_id not in self.monster_hps:
                        self.monster_hps[monster_id] = 100
                    if char_name not in self.player_hps:
                        self.player_hps[char_name] = 100
                    if char_name not in self.player_exps:
                        self.player_exps[char_name] = 0
                    if char_name not in self.player_levels:
                        self.player_levels[char_name] = 1
                        
                    # 1. Player hits monster
                    damage_dealt = random.randint(10, 25)
                    self.monster_hps[monster_id] -= damage_dealt
                    exp_gained = damage_dealt * 3
                    self.player_exps[char_name] += exp_gained
                        
                    # Send dealtHit
                    dealt_packet = f"dealtHit@{monster_id}|Melee|{damage_dealt}|None|0|{exp_gained}|0|false|false"
                    conn["send"](f"{char_id}-{dealt_packet}")
                    
                    # Play hit sound
                    conn["send"](f"{char_id}-onScreenNoise@hit_sword.mp3|0.0|0.0")
                        
                    # Check monster death
                    if self.monster_hps[monster_id] <= 0:
                        self.log(f"[*] Player '{char_name}' defeated monster '{monster_id}'!")
                        conn["send"](f"{char_id}-slayed@{monster_id}")
                        conn["send"](f"{char_id}-onScreenNoise@game_death.mp3|0.0|0.0")
                            
                        # Level up check (every 300 EXP)
                        new_level = (self.player_exps[char_name] // 300) + 1
                        if new_level > self.player_levels[char_name]:
                            self.player_levels[char_name] = new_level
                            conn["send"](f"{char_id}-lvledUp@LevelUp")
                            conn["send"](f"{char_id}-onScreenNoise@game_major_levelup.mp3|0.0|0.0")
                            coords = f"{conn['x']},{conn['y']}"
                            conn["send"](f"{char_id}-onScreenPaint@levelup|major|{coords}|{coords}|0|0|0|0")
                            conn["send"](f"{char_id}-serverMessages@Congratulations! You leveled up to Level {new_level}!")
                            
                        # Update bestiary kill count in database
                        account_name = conn.get("username", "").lower() if hasattr(self, "active_connections") else ""
                        if not account_name:
                            # Fallback to look up account in db
                            for acc_name, acc in db.get("accounts", {}).items():
                                for oc in acc.get("characters", []):
                                    if oc["name"].lower() == char_name.lower():
                                        account_name = acc_name.lower()
                                        break
                                if account_name:
                                    break
                        if account_name:
                            account_data = db.setdefault("accounts", {}).setdefault(account_name, {})
                            for c in account_data.setdefault("characters", []):
                                if c["name"].lower() == char_name.lower():
                                    bestiary = c.setdefault("bestiary", {})
                                    m_type = monster_id.split("_")[0]
                                    bestiary[m_type] = bestiary.get(m_type, 0) + 1
                                    self.mark_db_dirty()
                                    break
                            
                        with self.connections_lock:
                            if self.active_combat.get(char_name) == monster_id:
                                del self.active_combat[char_name]
                            
                        del self.monster_hps[monster_id]
                        continue
                        
                    # 2. Monster hits player back
                    damage_taken = random.randint(5, 12)
                    self.player_hps[char_name] = max(0, self.player_hps[char_name] - damage_taken)
                        
                    # Send receivedHit and update health bar
                    conn["send"](f"{char_id}-receivedHit@{monster_id}|Melee|{damage_taken}|None|0")
                    
                    # Play hurt/hit sound
                    grunt = "grunt_male_1.mp3" if conn.get("gender", "M") == "M" else "grunt_female_1.mp3"
                    conn["send"](f"{char_id}-onScreenNoise@{grunt}|0.0|0.0")
                    conn["send"](f"{char_id}-onScreenNoise@hit_none.mp3|0.0|0.0")
                    
                    conn["send"](f"{char_id}-updatePlayerHealthAndMana@{self.player_hps[char_name]},100|100,100")
                        
                    # Check player death
                    if self.player_hps[char_name] <= 0:
                        self.log(f"[-] Player '{char_name}' was defeated by '{monster_id}'!")
                        conn["send"](f"{char_id}-onScreenNoise@game_death.mp3|0.0|0.0")
                            
                        # Reset HP & Warp to Town Center
                        self.player_hps[char_name] = 100
                        with self.connections_lock:
                            conn["x"] = 79
                            conn["y"] = 107
                            if self.active_combat.get(char_name) == monster_id:
                                del self.active_combat[char_name]
                                    
                        conn["send"](f"{char_id}-youDied@You were defeated in battle!|79,107")
                        conn["send"](f"{char_id}-updatePlayerHealthAndMana@100,100|100,100")
                        conn["send"](f"{char_id}-updatePlayerLocations@{char_id}|79,107|{conn['race']}|{conn['gender']}|no|N|0|0.0|None|0|79,107|n|0|0")
                except Exception as e:
                    self.log(f"[-] Combat connection error for {char_name}: {e}")
                    self.disconnect_client(char_name)

    def movement_worker(self):
        """Dedicated high-priority thread to process player movement continuously and fluidly."""
        while True:
            try:
                # 1. Process all pending tasks in the queue non-blockingly
                while not self.movement_queue.empty():
                    try:
                        task = self.movement_queue.get_nowait()
                        if task is None:
                            return
                        
                        char_name, cmd_name, cmd_meta, send_packet, username = task
                        
                        with self.connections_lock:
                            conn = self.active_connections.get(char_name.lower())
                            if conn:
                                # Keep reference to send_packet and username for background ticking
                                conn["send"] = send_packet
                                conn["username"] = username
                                if cmd_name == "walkOff":
                                    conn["current_walk"] = None
                                elif cmd_name.startswith("walk"):
                                    conn["current_walk"] = cmd_name
                    except queue.Empty:
                        break

                # 2. Process continuous movement for all active players
                now = time.time()
                cooldown = self.movement_cooldown_ms / 1000.0
                
                with self.connections_lock:
                    active_conns = list(self.active_connections.values())

                for conn in active_conns:
                    current_walk = conn.get("current_walk")
                    if not current_walk:
                        continue
                        
                    last_move = conn.get("last_move_time", 0.0)
                    if now - last_move >= cooldown:
                        conn["last_move_time"] = now
                        char_name = conn["char_id"]
                        username = conn.get("username")
                        send_packet = conn["send"]
                        race = conn.get("race", "Human")
                        gender = conn.get("gender", "M")
                        
                        dx = 0
                        dy = 0
                        if "North" in current_walk:
                            dy = -1
                        elif "South" in current_walk:
                            dy = 1
                        if "East" in current_walk:
                            dx = 1
                        elif "West" in current_walk:
                            dx = -1
                            
                        curr_x, curr_y = conn["x"], conn["y"]
                        target_x = curr_x + dx
                        target_y = curr_y + dy
                        
                        # Check if target is blocked by a wall/collision tile
                        if (target_x, target_y) in self.blocked_coords:
                            # Try to wall slide if it was a diagonal move
                            if dx != 0 and dy != 0:
                                # Try horizontal slide
                                if (curr_x + dx, curr_y) not in self.blocked_coords:
                                    target_x = curr_x + dx
                                    target_y = curr_y
                                # Try vertical slide
                                elif (curr_x, curr_y + dy) not in self.blocked_coords:
                                    target_x = curr_x
                                    target_y = curr_y + dy
                                else:
                                    # Both slide directions are blocked
                                    target_x, target_y = curr_x, curr_y
                            else:
                                # Straight move blocked
                                target_x, target_y = curr_x, curr_y
                                
                        conn["x"] = target_x
                        conn["y"] = target_y
                        px, py = target_x, target_y
                        
                        # Check for portals
                        PORTALS = {
                            (70, 107): (58, 98, "Cave Entrance"),
                            (58, 98): (79, 107, "Cave Exit"),
                        }
                        if (px, py) in PORTALS:
                            dest_x, dest_y, desc = PORTALS[(px, py)]
                            conn["x"] = dest_x
                            conn["y"] = dest_y
                            px, py = dest_x, dest_y
                            self.log(f"[*] Player '{char_name}' went through portal: {desc} to ({px}, {py})")
                            send_packet(f"{char_name}-serverMessages@You passed through a portal: {desc}")
                            
                        self.log(f"[*] Player '{char_name}' moved to ({px}, {py}) via {current_walk}")
                        
                        # Save new position to database
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                c["x"] = px
                                c["y"] = py
                                break
                        self.mark_db_dirty()
                        
                        # Send walk confirmation
                        response = f"{char_name}-{current_walk}@true|{px},{py}"
                        send_packet(response)
                        
                        # Send location update to refresh local player sprite position
                        response = f"{char_name}-updatePlayerLocations@{char_name}|{px},{py}|{race}|{gender}|no|N|0|0.0|None|0|{px},{py}|n|0|0"
                        send_packet(response)
                        
                # Short sleep to prevent CPU pegging (20ms tick rate)
                time.sleep(0.02)
            except Exception as e:
                self.log(f"[-] Error in movement worker thread: {e}")
                time.sleep(0.1)
        
    def handle_client(self, client_socket, client_address):
        self.log(f"[*] New connection from {client_address[0]}:{client_address[1]}")
        client_socket.settimeout(30.0)
        username = None
        character_id = None
        bytes_sent = 0
        try:
            obj_in = JavaObjectInputStream(client_socket)
            obj_out = JavaObjectOutputStream(client_socket)
            
            # Initial handshakes
            obj_out.write_object("handshake")
            all_bytes = obj_out.get_bytes()
            client_socket.sendall(all_bytes)
            self.log(f"[*] SSL Handshake and Stream headers initialized with {client_address[0]}:{client_address[1]}")
            bytes_sent = len(all_bytes)
            
            send_lock = threading.Lock()
            def send_packet(obj):
                nonlocal bytes_sent
                with send_lock:
                    obj_str = str(obj)
                    if self.verbose_logs.get() or not ("heart" in obj_str or "walk" in obj_str or "ping" in obj_str or "updatePlayerLocations" in obj_str):
                        self.log(f"[Server -> Client]: Sending packet: {obj}")
                    obj_out.write_object(obj)
                    all_bytes = obj_out.get_bytes()
                    new_bytes = all_bytes[bytes_sent:]
                    client_socket.sendall(new_bytes)
                    bytes_sent = len(all_bytes)
                    if self.verbose_logs.get() or not ("heart" in obj_str or "walk" in obj_str or "ping" in obj_str or "updatePlayerLocations" in obj_str):
                        self.log(f"[Server -> Client]: Sent {len(new_bytes)} bytes. Total sent: {bytes_sent} bytes.")

            def send_map_entities(char_name):
                """Send map entities within a 40-tile radius of the player in a single updateEntityLocations packet."""
                def clean_sprite(sprite, prefix):
                    if sprite.startswith(prefix):
                        return sprite[len(prefix):]
                    return sprite

                # Get player's current coordinates
                px, py = 79, 107
                with self.connections_lock:
                    conn = self.active_connections.get(char_name.lower())
                    if conn:
                        px, py = conn["x"], conn["y"]

                # Build monster entries (7 fields each) - Filtered by 40-tile radius
                mobs_fields = []
                visible_mobs_count = 0
                for val, x, y in self.map_mobs:
                    if abs(x - px) <= 40 and abs(y - py) <= 40:
                        visible_mobs_count += 1
                        sprite = self.monster_sprites[val % len(self.monster_sprites)] if self.monster_sprites else "wolf.gif"
                        sprite = clean_sprite(sprite, "monster_")
                        name = sprite.replace(".gif", "").replace(".png", "").replace("_", " ").title()
                        level = val % 10 + 1
                        mobs_fields.extend([f"{x},{y}", str(level), sprite, name, "100,100", "100", f"{x},{y}"])

                # Build NPC entries (7 fields each) - Filtered by 40-tile radius
                npcs_fields = []
                visible_npcs_count = 0
                for val, x, y in self.map_npcs:
                    if abs(x - px) <= 40 and abs(y - py) <= 40:
                        visible_npcs_count += 1
                        sprite = self.npc_sprites[val % len(self.npc_sprites)] if self.npc_sprites else "alchemist.gif"
                        sprite = clean_sprite(sprite, "npc_")
                        name = sprite.replace(".gif", "").replace(".png", "").replace("_", " ").title()
                        npcs_fields.extend([f"{x},{y}", "1", sprite, name, "100,100", "100", "0"])

                # Build tradeskill entries (6 fields each) - Filtered by 40-tile radius
                ts_fields = []
                visible_ts_count = 0
                for val, x, y in self.map_tradeskills:
                    if f"{x},{y}" in self.depleted_nodes:
                        continue
                    if abs(x - px) <= 40 and abs(y - py) <= 40:
                        visible_ts_count += 1
                        sprite = self.tradeskill_sprites[val % len(self.tradeskill_sprites)] if self.tradeskill_sprites else "ore_copper.png"
                        sprite = clean_sprite(sprite, "tradeskill_")
                        name = sprite.replace(".gif", "").replace(".png", "").replace("_", " ").title()
                        ts_fields.extend([f"{x},{y}", "1", sprite, name, f"{x},{y}", "100"])

                # Assemble single updateEntityLocations packet
                parts = []
                parts.append("monsters")
                parts.append(str(visible_mobs_count))
                parts.extend(mobs_fields)
                parts.append("npcs")
                parts.append(str(visible_npcs_count))
                parts.extend(npcs_fields)
                parts.append("objects")
                parts.append("0")  # objects in entity packet (map d) — we send via updateObjectLocations
                parts.append("tradeskills")
                parts.append(str(visible_ts_count))
                parts.extend(ts_fields)
                parts.append("corpses")
                parts.append("0")
                parts.append("plantings")
                parts.append("0")

                payload = "|".join(parts)
                response = f"{char_name}-updateEntityLocations@{payload}"
                self.log(f"[*] Sending updateEntityLocations: {visible_mobs_count} monsters, {visible_npcs_count} NPCs, {visible_ts_count} tradeskills ({len(response)} bytes)")
                send_packet(response)

                # Build object entries for updateObjectLocations (5 fields each) - Filtered by 40-tile radius
                objs_fields = []
                visible_objs_count = 0
                for val, x, y in self.map_objects:
                    if abs(x - px) <= 40 and abs(y - py) <= 40:
                        visible_objs_count += 1
                        sprite = self.object_sprites[val % len(self.object_sprites)] if self.object_sprites else "campfire.gif"
                        sprite = clean_sprite(sprite, "object_")
                        name = sprite.replace(".gif", "").replace(".png", "").replace("_", " ").title()
                        objs_fields.extend([f"{x},{y}", sprite, name, f"{x},{y}", "100"])

                obj_parts = [str(visible_objs_count)]
                obj_parts.extend(objs_fields)
                obj_payload = "|".join(obj_parts)
                response = f"{char_name}-updateObjectLocations@{obj_payload}"
                self.log(f"[*] Sending updateObjectLocations: {visible_objs_count} objects ({len(response)} bytes)")
                send_packet(response)
            
            while True:
                if self.verbose_logs.get():
                    self.log("[*] Waiting for packet from client...")
                packet = obj_in.read_object()
                if packet is None:
                    self.log("[*] Received EOF/None from client. Connection might be closing.")
                    break
                packet_str = str(packet)
                if self.verbose_logs.get() or not ("heart" in packet_str or "walk" in packet_str or "ping" in packet_str):
                    self.log(f"[Client -> Server]: Received packet: {packet} (Type: {type(packet)})")
                
                if not isinstance(packet, str):
                    self.log(f"[*] Warning: Packet is not a string, skipping processing.")
                    continue
                    
                def send_character_window(char_n, a_char):
                    exp = self.player_exps.get(char_n, 0)
                    level = self.player_levels.get(char_n, 1)
                    next_exp = level * 300
                    start_exp = (level - 1) * 300
                    
                    stats = [
                        "40-37-32",
                        "10", "0", "10", "0", "10", "0", "10", "0", "10",
                        str(exp),
                        str(level),
                        str(start_exp),
                        str(next_exp),
                        "10", "0",
                        "10", "10", "10", "10", "10", "10",
                        "0", "12", "10", "100/100", "0", "None",
                        "0", "5", "0/150", "0,0",
                        "0", "0,0", "0", "None", "0", "m", "1.0"
                    ]
                    eq = a_char.setdefault("equipment", [None] * 14)
                    stats.extend([serialize_item(it, it.get("unique_id") if it else 20000+i) for i, it in enumerate(eq)])
                    send_packet(f"{char_n}-characterWindow@{'|'.join(stats)}")

                if "@" in packet:
                    parts = packet.split("@")
                    cmd_meta = parts[0]
                    cmd_args = parts[1].split("|")
                    cmd_name = cmd_args[0]
                    
                    if cmd_name == "authenticate":
                        username = cmd_meta
                        password = cmd_args[1] if len(cmd_args) > 1 else ""
                        self.log(f"[*] Authenticating user: {username}")
                        
                        account_name = username.lower()
                        if account_name in db.get("accounts", {}):
                            self.log(f"[*] User '{username}' authenticated successfully")
                            response = f"{username}-authenticate@true|{password}"
                        else:
                            self.log(f"[*] Account '{username}' not found. Registering new account...")
                            db.setdefault("accounts", {})[account_name] = {
                                "password_hash": password,
                                "characters": []
                            }
                            save_db(db)
                            response = f"{username}-authenticate@true|{password}"
                            
                        self.log(f"[Server -> Client]: Sending packet: {response}")
                        send_packet(response)
                        
                    elif cmd_name == "getCharacters":
                        self.log(f"[*] Fetching characters for user: {username}")
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        
                        if not characters:
                            response = f"{cmd_meta}-getCharacters@EMPTY"
                        else:
                            char_list = []
                            for c in characters:
                                char_list.extend([
                                    str(c.get('id', 1)),
                                    c.get('name', 'Unknown'),
                                    c.get('gender', 'Male'),
                                    str(c.get('level', 1)),
                                    c.get('race', 'Human'),
                                    c.get('gender_letter', 'M'),
                                    "no" if c.get("hide_costume", False) else c.get('costume_gif', 'no'),
                                    str(c.get('alignment', 0)),
                                    c.get('guild') or 'None',
                                    c.get('title') or 'N'
                                ])
                            payload = "|".join(str(x) for x in char_list)
                            response = f"{cmd_meta}-getCharacters@{payload}"
                        self.log(f"[Server -> Client]: Sending packet: {response}")
                        send_packet(response)
                        
                    elif cmd_name == "createCharacter":
                        # Client format: createCharacter|<session_key>|none-<name> or override-<name>|<race>|<gender>|...
                        raw_name = cmd_args[2]
                        # Strip 'none-' or 'override-' prefix from character name
                        if raw_name.startswith("none-"):
                            char_name = raw_name[5:]
                        elif raw_name.startswith("override-"):
                            char_name = raw_name[9:]
                        else:
                            char_name = raw_name
                        race = cmd_args[3]
                        gender = cmd_args[4]
                        self.log(f"[*] Creating character - Name: {char_name} (raw: {raw_name}), Gender: {gender}, Race: {race}")
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.setdefault("accounts", {}).setdefault(account_name, {"characters": []})
                        characters = account_data.setdefault("characters", [])
                        
                        # Generate unique ID
                        new_id = len(characters) + 1
                        new_char = {
                            "id": new_id,
                            "name": char_name,
                            "gender": "Male" if gender == "M" else "Female",
                            "level": 1,
                            "race": race,
                            "gender_letter": gender,
                            "costume_gif": "no",
                            "alignment": 0,
                            "guild": "None",
                            "title": "N",
                            "x": 79,
                            "y": 107,
                            "inventory": [
                                {"id": 1, "unique_id": 10001, "quantity": 1},
                                {"id": 2, "unique_id": 10002, "quantity": 1},
                                {"id": 3, "unique_id": 10003, "quantity": 5},
                                *([None] * 22)
                            ],
                            "equipment": [None] * 14,
                            "bank": [None] * 256,
                            "bank_gold": 0,
                            "gold": 500,
                            "hp": 100,
                            "max_hp": 100,
                            "mana": 100,
                            "max_mana": 100,
                            "skills": {
                                "mining": {"level": 1, "exp": 0},
                                "lumberjacking": {"level": 1, "exp": 0},
                                "blacksmithing": {"level": 1, "exp": 0},
                                "alchemy": {"level": 1, "exp": 0},
                                "cooking": {"level": 1, "exp": 0},
                                "fishing": {"level": 1, "exp": 0},
                                "tailoring": {"level": 1, "exp": 0}
                            },
                            "guild_name": None,
                            "friends": [],
                            "rivals": [],
                            "mailbox": [
                                {
                                    "id": 1,
                                    "sender": "System",
                                    "recipient": char_name,
                                    "type": "ul",
                                    "subject": "Welcome!",
                                    "body": "Welcome to Kisnard Online! Have fun playing!",
                                    "date": "2026-06-30 00:00:00",
                                    "claimed": "n"
                                }
                            ]
                        }
                        characters.append(new_char)
                        save_db(db)
                        
                        self.log(f"[*] Character '{char_name}' created successfully")
                        response = f"{cmd_meta}-createCharacter@{char_name}|true|dummy"
                        self.log(f"[Server -> Client]: Sending packet: {response}")
                        send_packet(response)
                        
                    elif cmd_name == "deleteCharacter":
                        char_name = cmd_args[1]
                        self.log(f"[*] Requesting deletion of character: {char_name}")
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        
                        new_characters = [c for c in characters if c["name"].lower() != char_name.lower()]
                        if len(new_characters) < len(characters):
                            db["accounts"][account_name]["characters"] = new_characters
                            save_db(db)
                            self.log(f"[*] Character '{char_name}' successfully deleted for user '{username}'")
                            response = f"{cmd_meta}-deleteCharacter@{char_name}|true|dummy"
                        else:
                            self.log(f"[*] Character '{char_name}' not found for deletion")
                            response = f"{cmd_meta}-deleteCharacter@{char_name}|false|not_found"
                            
                        self.log(f"[Server -> Client]: Sending packet: {response}")
                        send_packet(response)
                        
                    elif cmd_name == "playCharacter":
                        character_id = cmd_args[1]
                        self.log(f"[*] Player '{username}' entering game with character ID: {character_id}")
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == character_id.lower():
                                active_char = c
                                break
                        if not active_char:
                            active_char = {"race": "Human", "gender": "M", "x": 79, "y": 107}
                            
                        race = active_char.get("race", "Human")
                        gender = active_char.get("gender", "M")
                        px = active_char.get("x", 79)
                        py = active_char.get("y", 107)
                        
                        if "inventory" not in active_char:
                            active_char["inventory"] = [
                                {"id": 1, "unique_id": 10001, "quantity": 1},
                                {"id": 2, "unique_id": 10002, "quantity": 1},
                                {"id": 3, "unique_id": 10003, "quantity": 5},
                                *([None] * 22)
                            ]
                        if "equipment" not in active_char:
                            active_char["equipment"] = [None] * 14
                        if "bank" not in active_char:
                            active_char["bank"] = [None] * 256
                        if "bank_gold" not in active_char:
                            active_char["bank_gold"] = 0
                        if "gold" not in active_char:
                            active_char["gold"] = 500
                        if "hp" not in active_char:
                            active_char["hp"] = 100
                        if "max_hp" not in active_char:
                            active_char["max_hp"] = 100
                        if "mana" not in active_char:
                            active_char["mana"] = 100
                        if "max_mana" not in active_char:
                            active_char["max_mana"] = 100
                        if "skills" not in active_char:
                            active_char["skills"] = {
                                "mining": {"level": 1, "exp": 0},
                                "lumberjacking": {"level": 1, "exp": 0},
                                "blacksmithing": {"level": 1, "exp": 0},
                                "alchemy": {"level": 1, "exp": 0},
                                "cooking": {"level": 1, "exp": 0},
                                "fishing": {"level": 1, "exp": 0},
                                "tailoring": {"level": 1, "exp": 0}
                            }
                        if "guild" not in active_char:
                            active_char["guild"] = None
                        if "friends" not in active_char:
                            active_char["friends"] = []
                        if "rivals" not in active_char:
                            active_char["rivals"] = []
                        if "mailbox" not in active_char:
                            active_char["mailbox"] = [
                                {
                                    "id": 1,
                                    "sender": "System",
                                    "recipient": character_id,
                                    "type": "ul",
                                    "subject": "Welcome!",
                                    "body": "Welcome to Kisnard Online! Have fun playing!",
                                    "date": "2026-06-30 00:00:00",
                                    "claimed": "n"
                                }
                            ]
                        save_db(db)
                        
                        # Register connection
                        conn_info = {
                            "char_id": character_id,
                            "send": send_packet,
                            "socket": client_socket,
                            "x": px,
                            "y": py,
                            "race": race,
                            "gender": gender,
                            "current_walk": None,
                            "last_move_time": 0.0
                        }
                        with self.connections_lock:
                            self.active_connections[character_id.lower()] = conn_info
                        self.add_player(character_id)
                        
                        response = f"{cmd_meta}-playCharacter@{character_id}|true|1440,1080|1|{px},{py}"
                        send_packet(response)
                        
                        # Send firstLoad immediately to pre-initialize client variables (prevent NPE)
                        php = f"{active_char.get('hp', 100)},{active_char.get('max_hp', 100)}"
                        pmn = f"{active_char.get('mana', 100)},{active_char.get('max_mana', 100)}"
                        costume = "no" if active_char.get("hide_costume", False) else active_char.get("costume_gif", "no")
                        response = f"{character_id}-firstLoad@{px},{py}|false|{race}|{gender}|{costume}|N|0|{php}|{pmn}|0/100|0.0|0|79,107|79,107"
                        send_packet(response)
                        
                        # Send buffsAppliedData@0 to clear buffs on login
                        send_packet(f"{character_id}-buffsAppliedData@0")
                        
                        # Send updatePlayerLocations immediately
                        response = f"{character_id}-updatePlayerLocations@{character_id}|{px},{py}|{race}|{gender}|{costume}|N|0|0.0|None|0|{px},{py}|n|0|0"
                        send_packet(response)
                        
                    elif cmd_name == "firstLoad":
                        self.log(f"[*] Handling firstLoad request for character: {cmd_meta}")
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        
                        char_name = cmd_meta
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        
                        if not active_char:
                            active_char = {"race": "Human", "gender": "M", "level": 1, "x": 79, "y": 107}
                            
                        race = active_char.get("race", "Human")
                        gender = active_char.get("gender", "M")
                        
                        with self.connections_lock:
                            conn = self.active_connections.get(char_name.lower())
                            if conn:
                                px, py = conn["x"], conn["y"]
                            else:
                                px, py = active_char.get("x", 79), active_char.get("y", 107)
                        
                        # 1. Send firstLoad
                        costume = "no" if active_char.get("hide_costume", False) else active_char.get("costume_gif", "no")
                        response = f"{char_name}-firstLoad@{px},{py}|false|{race}|{gender}|{costume}|N|0|100,100|100,100|0/100|0.0|0|79,107|79,107"
                        send_packet(response)
                        
                        # Send buffsAppliedData@0 to clear buffs
                        send_packet(f"{char_name}-buffsAppliedData@0")
                        
                        # 2. Send updatePlayerLocations
                        response = f"{char_name}-updatePlayerLocations@{char_name}|{px},{py}|{race}|{gender}|{costume}|N|0|0.0|None|0|{px},{py}|n|0|0"
                        send_packet(response)
                        
                        # Send NPCs and objects
                        send_map_entities(char_name)
                        
                    elif cmd_name == "serverRates":
                        char_name = cmd_meta
                        rates = []
                        for _ in range(7):
                            rates.extend(["1.0", "n", "n", "-1", "-1"])
                        payload = "|".join(rates)
                        response = f"{char_name}-serverRates@{payload}"
                        send_packet(response)
                        
                    elif cmd_name == "serverMessages":
                        char_name = cmd_meta
                        response = f"{char_name}-serverMessages@Welcome to Kisnard Online Local Dev Server!"
                        send_packet(response)
                        
                    elif cmd_name == "playerMessageQueue":
                        char_name = cmd_meta
                        response = f"{char_name}-playerMessageQueue@empty"
                        send_packet(response)
                        
                    elif cmd_name == "mailboxMessageInfo":
                        char_name = cmd_meta
                        # Check for unread mail and unclaimed packages on login
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            mailbox = active_char.get("mailbox", [])
                            inbox = [m for m in mailbox if m.get("recipient", "").lower() == char_name.lower()]
                            statuses = []
                            for m in inbox:
                                mtype = m.get("type", "ol")
                                if mtype == "ul":
                                    statuses.append("unread")
                                elif mtype in ("up", "op"):
                                    # Package with unclaimed gifts
                                    gifts = m.get("gifts", [])
                                    if any(g.get("claimed", "n") == "n" for g in gifts if g):
                                        statuses.append("unclaimed")
                            if statuses:
                                response = f"{char_name}-mailboxMessageInfo@{'|'.join(statuses)}"
                            else:
                                response = f"{char_name}-mailboxMessageInfo@empty"
                        else:
                            response = f"{char_name}-mailboxMessageInfo@empty"
                        send_packet(response)
                        
                    elif cmd_name == "ping":
                        char_name = cmd_meta
                        timestamp = cmd_args[1] if len(cmd_args) > 1 else "0"
                        response = f"{char_name}-ping@{timestamp}"
                        send_packet(response)
                        
                    elif cmd_name == "switchCharacter":
                        char_name = cmd_meta
                        self.log(f"[*] Player '{char_name}' requested switchCharacter")
                        response = f"{char_name}-switchCharacter@true"
                        send_packet(response)
                        
                    elif cmd_name in ["walkNorth", "walkNorthEast", "walkNorthWest", "walkEast", "walkSouth", "walkSouthEast", "walkSouthWest", "walkWest"]:
                        char_name = cmd_meta
                        # Queue the movement task to be processed by the dedicated movement thread
                        self.movement_queue.put((char_name, cmd_name, cmd_meta, send_packet, username))
                        
                    elif cmd_name in ["generalChat", "globalChat", "whisperChat", "guildChat"]:
                        char_name = cmd_meta
                        message_text = cmd_args[1] if len(cmd_args) > 1 else ""
                        
                        # Intercept Developer Teleport Command
                        if message_text.startswith("/tp "):
                            try:
                                coords = message_text.replace("/tp ", "").strip().split()
                                tp_x = int(coords[0])
                                tp_y = int(coords[1])
                                with self.connections_lock:
                                    conn = self.active_connections.get(char_name.lower())
                                    if conn:
                                        conn["x"] = tp_x
                                        conn["y"] = tp_y
                                        px, py = tp_x, tp_y
                                    else:
                                        px, py = tp_x, tp_y
                                self.log(f"[*] Developer '{char_name}' teleported to ({px}, {py})")
                                send_packet(f"{char_name}-updatePlayerLocations@{char_name}|{px},{py}|{race}|{gender}|no|N|0|0.0|None|0|{px},{py}|n|0|0")
                                send_packet(f"{char_name}-serverMessages@Teleported to {px}, {py}")
                                continue
                            except Exception as e:
                                send_packet(f"{char_name}-serverMessages@Error teleporting: {e}")
                                continue
                                
                        if cmd_name == "generalChat":
                            self.log_chat(f"[General Chat] {char_name}: {message_text}")
                            self.broadcast_packet(f"generalChat@{char_name}|{message_text}")
                        elif cmd_name == "globalChat":
                            self.log_chat(f"[Global Chat] {char_name}: {message_text}")
                            self.broadcast_packet(f"globalChat@{char_name}|{message_text}")
                        elif cmd_name == "whisperChat":
                            if "|" in message_text:
                                target_name, whisper_msg = message_text.split("|", 1)
                                self.log_chat(f"[Whisper] {char_name} -> {target_name}: {whisper_msg}")
                                success = self.whisper_packet(target_name, f"whisperChat@{char_name}|{whisper_msg}")
                                if success:
                                    send_packet(f"{char_name}-whisperChat@{target_name}|{whisper_msg}")
                                else:
                                    send_packet(f"{char_name}-serverMessages@Player '{target_name}' is offline.")
                        elif cmd_name == "guildChat":
                            account_name = username.lower() if username else "unknown_user"
                            account_data = db.get("accounts", {}).get(account_name, {})
                            characters = account_data.get("characters", [])
                            active_char = None
                            for c in characters:
                                if c["name"].lower() == char_name.lower():
                                    active_char = c
                                    break
                            if active_char and active_char.get("guild"):
                                g_name = active_char["guild"]
                                self.log_chat(f"[Guild Chat] ({g_name}) {char_name}: {message_text}")
                                with self.connections_lock:
                                    for o_name, conn in self.active_connections.items():
                                        o_char = None
                                        for acc_name, acc in db.get("accounts", {}).items():
                                            for oc in acc.get("characters", []):
                                                if oc["name"].lower() == o_name.lower():
                                                    o_char = oc
                                                    break
                                            if o_char:
                                                break
                                        if o_char and o_char.get("guild") == g_name:
                                            conn["send"](f"{o_name}-guildChat@{char_name}|{message_text}")
                            
                    elif cmd_name == "backpackWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            serialized_inv = []
                            for idx, item in enumerate(inv):
                                uid = item.get("unique_id", 10000 + idx) if item else 0
                                serialized_inv.append(serialize_item(item, uid))
                            
                            payload = "|".join(serialized_inv)
                            response = f"{char_name}-backpackWindow@40-37-32|y|y|{payload}"
                            send_packet(response)
                        
                    elif cmd_name == "characterWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            send_character_window(char_name, active_char)
                        
                    elif cmd_name in ["questsWindow", "skillsWindow", "spellsWindow", "actionsWindow", "friendsWindow"]:
                        char_name = cmd_meta
                        if cmd_name == "questsWindow":
                            send_packet(f"{char_name}-questsWindow@0|0|0|0|0|0|0|2026-06-30 12:00:00.0|2026-06-30 12:00:00.0|2026-06-30 12:00:00.0|None|None|None|2026-06-30 12:00:00.0|None|0|0")
                        elif cmd_name == "skillsWindow":
                            account_name = username.lower() if username else "unknown_user"
                            account_data = db.get("accounts", {}).get(account_name, {})
                            characters = account_data.get("characters", [])
                            active_char = None
                            for c in characters:
                                if c["name"].lower() == char_name.lower():
                                    active_char = c
                                    break
                            if active_char:
                                skills_data = active_char.setdefault("skills", {
                                    "mining": {"level": 1, "exp": 0},
                                    "lumberjacking": {"level": 1, "exp": 0},
                                    "blacksmithing": {"level": 1, "exp": 0},
                                    "alchemy": {"level": 1, "exp": 0},
                                    "cooking": {"level": 1, "exp": 0},
                                    "fishing": {"level": 1, "exp": 0},
                                    "tailoring": {"level": 1, "exp": 0}
                                })
                                skills_list = [
                                    "mining", "lumberjacking", "blacksmithing", "alchemy", "cooking", "fishing", "tailoring"
                                ]
                                payload_parts = []
                                for idx, sname in enumerate(skills_list):
                                    s_info = skills_data.get(sname, {"level": 1, "exp": 0})
                                    level = s_info.get("level", 1)
                                    exp = s_info.get("exp", 0)
                                    start_exp = (level - 1) * 100
                                    next_exp = level * 100
                                    payload_parts.extend([
                                        str(idx), sname, str(exp), str(start_exp), str(next_exp), str(level), str(idx + 1)
                                    ])
                                payload = "|".join(payload_parts)
                                send_packet(f"{char_name}-skillsWindow@{payload}")
                        elif cmd_name == "spellsWindow":
                            bless_fields = [
                                "0", "1", "0",
                                "A", "Y", "1", "0", "Bless", "Heals the caster for 25 HP.", "bless.png",
                                "10", "0",
                                "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
                                "10",
                                "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
                                "1.0"
                            ]
                            payload = "|".join(bless_fields)
                            send_packet(f"{char_name}-spellsWindow@{payload}")
                        elif cmd_name == "actionsWindow":
                            slots = ["y", "y", "y", "y", "y", "y", "y"]
                            slots.extend(["S", "1", "bless.png", "0", "10", "0", "Y", "Y"])
                            slots.extend(["I", "3", "health_vial_small.png", "5", "0", "0", "N", "N"])
                            for _ in range(88):
                                slots.append("-1")
                            payload = "|".join(slots)
                            send_packet(f"{char_name}-actionsWindow@{payload}")
                        elif cmd_name == "friendsWindow":
                            account_name = username.lower() if username else "unknown_user"
                            account_data = db.get("accounts", {}).get(account_name, {})
                            characters = account_data.get("characters", [])
                            active_char = None
                            for c in characters:
                                if c["name"].lower() == char_name.lower():
                                    active_char = c
                                    break
                            if active_char:
                                friends_list = active_char.setdefault("friends", [])
                                online_chars = []
                                with self.connections_lock:
                                    for o_name, conn in self.active_connections.items():
                                        if o_name.lower() != char_name.lower():
                                            ol_char = None
                                            for acc_name, acc in db.get("accounts", {}).items():
                                                for oc in acc.get("characters", []):
                                                    if oc["name"].lower() == o_name.lower():
                                                        ol_char = oc
                                                        break
                                                if ol_char:
                                                    break
                                            lvl = ol_char.get("level", 1) if ol_char else 1
                                            gld = ol_char.get("guild", "N") if ol_char else "N"
                                            if not gld:
                                                gld = "N"
                                            act = "R" if conn["char_id"] in friends_list else "A"
                                            online_chars.append(f"{gld}-{conn['char_id']}-{lvl}-C-{act}")
                                
                                friends_status = []
                                for f_name in friends_list:
                                    f_char = None
                                    for acc_name, acc in db.get("accounts", {}).items():
                                        for oc in acc.get("characters", []):
                                            if oc["name"].lower() == f_name.lower():
                                                f_char = oc
                                                break
                                        if f_char:
                                            break
                                    lvl = f_char.get("level", 1) if f_char else 1
                                    gld = f_char.get("guild", "N") if f_char else "N"
                                    if not gld:
                                        gld = "N"
                                    friends_status.append(f"{gld}-{f_name}-{lvl}")
                                
                                online_payload = "-".join(online_chars) if online_chars else "N-None-1-C-A"
                                friends_payload = "-".join(friends_status) if friends_status else ""
                                response = f"{char_name}-friendsWindow@{len(online_chars)}|{online_payload}|{len(friends_list)}|{friends_payload}"
                                send_packet(response)

                    elif cmd_name in ["addFriend", "removeFriend"]:
                        char_name = cmd_meta
                        target_name = cmd_args[1] if len(cmd_args) > 1 else ""
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char and target_name:
                            friends_list = active_char.setdefault("friends", [])
                            if cmd_name == "addFriend":
                                if target_name not in friends_list:
                                    friends_list.append(target_name)
                                    save_db(db)
                                    send_packet(f"{char_name}-serverMessages@{target_name} has been added to your friends list.")
                            elif cmd_name == "removeFriend":
                                if target_name in friends_list:
                                    friends_list.remove(target_name)
                                    save_db(db)
                                    send_packet(f"{char_name}-serverMessages@{target_name} has been removed from your friends list.")

                    elif cmd_name == "guildWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            guild_name = active_char.get("guild")
                            guilds = db.setdefault("guilds", {})
                            g_info = guilds.get(guild_name) if guild_name else None
                            if g_info:
                                members_payload = []
                                for m in g_info.get("members", []):
                                    members_payload.extend([m["name"], m["rank"], str(m["level"]), m["last_login"]])
                                header = [
                                    str(g_info.get("id", 1)),
                                    guild_name,
                                    g_info.get("tag", "TAG"),
                                    g_info.get("motd", "Welcome!"),
                                    g_info.get("description", "A great guild"),
                                    str(g_info.get("level", 1)),
                                    g_info.get("leader", char_name),
                                    g_info.get("created_at", "2026-06-30 00:00:00"),
                                    "-1", "-1", "-1", "-1", "-1", "-1"
                                ]
                                payload = "|".join(header + members_payload)
                                send_packet(f"{char_name}-guildWindow@{payload}")
                            else:
                                send_packet(f"{char_name}-guildWindow@none")

                    elif cmd_name == "guildCreate":
                        char_name = cmd_meta
                        g_name = cmd_args[1] if len(cmd_args) > 1 else ""
                        g_tag = cmd_args[2] if len(cmd_args) > 2 else ""
                        g_desc = cmd_args[3] if len(cmd_args) > 3 else ""
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            guilds = db.setdefault("guilds", {})
                            if g_name in guilds:
                                send_packet(f"{char_name}-modalMessage@guildcreateframe_failure_name_taken|guildcreateframe_failure_title")
                            else:
                                new_id = len(guilds) + 1
                                guilds[g_name] = {
                                    "id": new_id,
                                    "tag": g_tag,
                                    "motd": "Welcome to our new guild!",
                                    "description": g_desc,
                                    "level": 1,
                                    "leader": char_name,
                                    "created_at": "2026-06-30 00:00:00",
                                    "members": [
                                        {"name": char_name, "rank": "Leader", "level": active_char.get("level", 1), "last_login": "2026-06-30 00:00:00"}
                                    ]
                                }
                                active_char["guild"] = g_name
                                save_db(db)
                                self.update_guild_list()
                                send_packet(f"{char_name}-modalMessage@guildcreateframe_success_text|guildcreateframe_success_title")
                                
                                g_info = guilds[g_name]
                                members_payload = []
                                for m in g_info.get("members", []):
                                    members_payload.extend([m["name"], m["rank"], str(m["level"]), m["last_login"]])
                                header = [
                                    str(g_info.get("id", 1)),
                                    g_name,
                                    g_tag,
                                    g_info.get("motd"),
                                    g_info.get("description"),
                                    str(g_info.get("level")),
                                    g_info.get("leader"),
                                    g_info.get("created_at"),
                                    "-1", "-1", "-1", "-1", "-1", "-1"
                                ]
                                payload = "|".join(header + members_payload)
                                send_packet(f"{char_name}-guildWindow@{payload}")

                    elif cmd_name == "mailboxWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            from datetime import datetime
                            mailbox = active_char.setdefault("mailbox", [])
                            inbox_mails = [m for m in mailbox if m.get("recipient", "").lower() == char_name.lower()]
                            sent_mails = [m for m in mailbox if m.get("sender", "").lower() == char_name.lower()]
                            
                            # Build inbox fields: each mail = [id, type, sender, subject, timestamp]
                            inbox_parts = []
                            for m in inbox_mails:
                                inbox_parts.extend([
                                    str(m["id"]),
                                    m.get("type", "ul"),
                                    m.get("sender", "System"),
                                    m.get("subject", "No Subject"),
                                    m.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                                ])
                            
                            # Build sent fields: each mail = [id, type, recipient, subject, timestamp]
                            sent_parts = []
                            for m in sent_mails:
                                sent_parts.extend([
                                    str(m["id"]),
                                    m.get("type", "ol"),
                                    m.get("recipient", ""),
                                    m.get("subject", "No Subject"),
                                    m.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                                ])
                            
                            # Protocol: inbox_count | inbox_fields... | sent_count | sent_fields...
                            # When count is 0 and there are no fields, we still need exactly count then the next count
                            if inbox_parts:
                                inbox_payload = "|".join(inbox_parts)
                                response_parts = [str(len(inbox_mails)), inbox_payload]
                            else:
                                response_parts = ["0", ""]
                            
                            if sent_parts:
                                sent_payload = "|".join(sent_parts)
                                response_parts.extend([str(len(sent_mails)), sent_payload])
                            else:
                                response_parts.extend(["0"])
                            
                            response = f"{char_name}-mailboxWindow@{'|'.join(response_parts)}"
                            send_packet(response)

                    elif cmd_name == "mailDetails":
                        char_name = cmd_meta
                        mail_id_str = cmd_args[1] if len(cmd_args) > 1 else "0"
                        mail_box_type = cmd_args[2] if len(cmd_args) > 2 else "inbox"
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            mailbox = active_char.setdefault("mailbox", [])
                            mail = None
                            for m in mailbox:
                                if str(m["id"]) == mail_id_str:
                                    mail = m
                                    break
                            if mail:
                                # Mark as opened
                                if mail.get("type") == "ul":
                                    mail["type"] = "ol"
                                    save_db(db)
                                elif mail.get("type") == "up":
                                    mail["type"] = "op"
                                    save_db(db)
                                
                                from datetime import datetime
                                # Build payload: id | sender | recipient | type | subject | body | [4 gift slots] | timestamp
                                payload = [
                                    str(mail["id"]),
                                    mail.get("sender", "System"),
                                    mail.get("recipient", char_name),
                                    mail.get("type", "ol"),
                                    mail.get("subject", ""),
                                    mail.get("body", "")
                                ]
                                
                                # 4 gift attachment slots
                                # Each gift: name | image_path | quantity | gem1 | gem2 | enchant_level | rarity | stars | claimed
                                # If empty: -1
                                gifts = mail.get("gifts", [])
                                for slot_idx in range(4):
                                    if slot_idx < len(gifts) and gifts[slot_idx]:
                                        g = gifts[slot_idx]
                                        item_id = g.get("item_id", "")
                                        item_def = ITEMS.get(item_id, {}) if item_id else {}
                                        item_name = g.get("name", item_def.get("name", "Unknown"))
                                        item_type = item_def.get("type", "I")
                                        
                                        if item_type == "W":
                                            img_path = f"weapon/weapon_{item_def.get('image', 'unknown.png')}"
                                        elif item_type == "A":
                                            img_path = f"armor/armor_{item_def.get('image', 'unknown.png')}"
                                        else:
                                            img_path = f"item/item_{item_def.get('image', 'unknown.png')}"
                                        
                                        payload.extend([
                                            item_name,
                                            img_path,
                                            str(g.get("quantity", 1)),
                                            g.get("gem1", "no"),
                                            g.get("gem2", "no"),
                                            str(g.get("enchant_level", 0)),
                                            str(g.get("rarity", 0)),
                                            str(g.get("stars", 1)),
                                            g.get("claimed", "n")
                                        ])
                                    else:
                                        payload.append("-1")
                                
                                payload.append(mail.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                send_packet(f"{char_name}-mailDetails@{'|'.join(payload)}")

                    elif cmd_name == "mailboxMessageInfo":
                        char_name = cmd_meta
                        # This is the "send mail" action when cmd_args has parameters
                        if len(cmd_args) > 1:
                            recipient = cmd_args[1] if len(cmd_args) > 1 else ""
                            subject = cmd_args[2] if len(cmd_args) > 2 else ""
                            body = cmd_args[3] if len(cmd_args) > 3 else ""
                            recip_char = None
                            recip_account_data = None
                            for acc_name, acc in db.get("accounts", {}).items():
                                for c in acc.get("characters", []):
                                    if c["name"].lower() == recipient.lower():
                                        recip_char = c
                                        recip_account_data = acc
                                        break
                                if recip_char:
                                    break
                            if recip_char:
                                import random
                                from datetime import datetime
                                mail_id = random.randint(100000, 999999)
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                new_mail = {
                                    "id": mail_id,
                                    "sender": char_name,
                                    "recipient": recipient,
                                    "type": "ul",
                                    "subject": subject,
                                    "body": body,
                                    "date": timestamp,
                                    "gifts": [],
                                    "claimed": "n"
                                }
                                # Add to recipient's mailbox
                                recip_char.setdefault("mailbox", []).append(new_mail)
                                # Add copy to sender's mailbox for Sent tab
                                account_name = username.lower() if username else "unknown_user"
                                account_data = db.get("accounts", {}).get(account_name, {})
                                for c in account_data.get("characters", []):
                                    if c["name"].lower() == char_name.lower():
                                        sent_copy = dict(new_mail)
                                        sent_copy["type"] = "ol"  # Sent mail shows as opened letter
                                        c.setdefault("mailbox", []).append(sent_copy)
                                        break
                                save_db(db)
                                send_packet(f"{char_name}-serverMessages@Mail sent successfully to {recipient}.")
                                # Notify recipient if online
                                with self.connections_lock:
                                    r_conn = self.active_connections.get(recipient.lower())
                                    if r_conn:
                                        r_conn["send"](f"{recipient}-mailboxMessageInfo@unread")
                            else:
                                send_packet(f"{char_name}-serverMessages@Player '{recipient}' does not exist.")
                        else:
                            # Login-time status check (duplicate handler for safety)
                            account_name = username.lower() if username else "unknown_user"
                            account_data = db.get("accounts", {}).get(account_name, {})
                            characters = account_data.get("characters", [])
                            active_char = None
                            for c in characters:
                                if c["name"].lower() == char_name.lower():
                                    active_char = c
                                    break
                            if active_char:
                                mailbox = active_char.get("mailbox", [])
                                inbox = [m for m in mailbox if m.get("recipient", "").lower() == char_name.lower()]
                                statuses = []
                                for m in inbox:
                                    mtype = m.get("type", "ol")
                                    if mtype == "ul":
                                        statuses.append("unread")
                                    elif mtype in ("up", "op"):
                                        gifts = m.get("gifts", [])
                                        if any(g.get("claimed", "n") == "n" for g in gifts if g):
                                            statuses.append("unclaimed")
                                if statuses:
                                    response = f"{char_name}-mailboxMessageInfo@{'|'.join(statuses)}"
                                else:
                                    response = f"{char_name}-mailboxMessageInfo@empty"
                            else:
                                response = f"{char_name}-mailboxMessageInfo@empty"
                            send_packet(response)

                    elif cmd_name == "mailClaimGift":
                        char_name = cmd_meta
                        mail_id_str = cmd_args[1] if len(cmd_args) > 1 else "0"
                        gift_slot = int(cmd_args[2]) if len(cmd_args) > 2 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        
                        if active_char:
                            mailbox = active_char.setdefault("mailbox", [])
                            mail = None
                            for m in mailbox:
                                if str(m["id"]) == mail_id_str:
                                    mail = m
                                    break
                            
                            if mail:
                                gifts = mail.get("gifts", [])
                                if gift_slot < len(gifts) and gifts[gift_slot]:
                                    gift = gifts[gift_slot]
                                    if gift.get("claimed", "n") == "n":
                                        # Try to add item to player inventory
                                        inv = active_char.setdefault("inventory", [None] * 25)
                                        added = False
                                        for i in range(25):
                                            if inv[i] is None:
                                                import random
                                                uid = random.randint(100000, 999999)
                                                inv[i] = {
                                                    "id": gift.get("item_id", ""),
                                                    "unique_id": uid,
                                                    "quantity": gift.get("quantity", 1)
                                                }
                                                added = True
                                                break
                                        
                                        if added:
                                            gift["claimed"] = "y"
                                            # Check if all gifts are claimed, mark mail as empty package
                                            all_claimed = all(g.get("claimed", "n") == "y" for g in gifts if g)
                                            if all_claimed:
                                                mail["type"] = "ep"
                                            save_db(db)
                                            
                                            item_def = ITEMS.get(gift.get("item_id", ""), {})
                                            item_name = gift.get("name", item_def.get("name", "Unknown"))
                                            send_packet(f"{char_name}-mailClaimGift@true|{item_name}")
                                            
                                            # Update backpack
                                            response_bp = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                            send_packet(response_bp)
                                        else:
                                            send_packet(f"{char_name}-serverMessages@Your backpack is full!")
                                    else:
                                        send_packet(f"{char_name}-serverMessages@This gift has already been claimed.")
                                else:
                                    send_packet(f"{char_name}-serverMessages@No gift in this slot.")
                            else:
                                send_packet(f"{char_name}-serverMessages@Mail not found.")

                    elif cmd_name == "marketplaceWindow":
                        char_name = cmd_meta
                        # Send categories tree structure: 1 Buy group, 1 Sell group, 1 Other group
                        send_packet(f"{char_name}-marketplaceWindow@1|1|1|1|1|1")

                    elif cmd_name == "marketplaceListWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        gold = active_char.get("gold", 0) if active_char else 0
                        # Format: gold | listing_fee | active_count | placeholder | sold_count
                        send_packet(f"{char_name}-marketplaceListDetails@{gold}|10|0|0|0")

                    elif cmd_name == "marketplaceBuyList":
                        char_name = cmd_meta
                        # Format: field_lengths | placeholder | active_count
                        send_packet(f"{char_name}-marketplaceBuyList@30,30,30|0|0")

                    elif cmd_name == "marketplaceListCreateListing":
                        char_name = cmd_meta
                        send_packet(f"{char_name}-marketplaceListCreateListing@true|1")

                    elif cmd_name == "marketplaceBuyPurchase":
                        char_name = cmd_meta
                        send_packet(f"{char_name}-marketplaceBuyPurchase@true|1")

                    elif cmd_name == "marketplaceBuyCancelListing":
                        char_name = cmd_meta
                        send_packet(f"{char_name}-marketplaceBuyCancelListing@true|1")

                    elif cmd_name == "enchantingWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            backpack = active_char.setdefault("inventory", [None] * 25)
                            enchantables = []
                            for idx, item in enumerate(backpack):
                                if item:
                                    item_def = ITEMS.get(item["id"])
                                    if item_def and item_def["type"] in ["W", "A"]:
                                        enchantables.append((idx, item, item_def))
                            
                            parts = ["40-37", str(len(enchantables))]
                            for idx, item, item_def in enchantables:
                                parts.append(str(idx))
                                parts.append(serialize_item(item, item.get("unique_id", 10000 + idx)))
                                elvl = item.get("enchant_level", 0)
                                req_shards = (elvl + 1) * 2
                                success_chance = max(10, 100 - elvl * 10)
                                if item_def["type"] == "W":
                                    parts.extend([str(elvl), str(req_shards), str(success_chance)])
                                else:
                                    parts.extend([str(elvl), str(req_shards), str(success_chance), "0", "0", "0", "0", "0", "0", "0", "0"])
                            
                            send_packet(f"{char_name}-enchantingWindow@{'|'.join(parts)}")

                    elif cmd_name == "enchantingMergeWindow":
                        char_name = cmd_meta
                        send_packet(f"{char_name}-enchantingMergeWindow@40-37|0|0")

                    elif cmd_name == "enchantLevel":
                        char_name = cmd_meta
                        slot_idx = int(cmd_args[1]) if len(cmd_args) > 1 else -1
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char and slot_idx >= 0:
                            backpack = active_char.setdefault("inventory", [None] * 25)
                            item = backpack[slot_idx]
                            if item:
                                item_def = ITEMS.get(item["id"])
                                if item_def and item_def["type"] in ["W", "A"]:
                                    old_level = item.get("enchant_level", 0)
                                    new_level = old_level + 1
                                    old_name = f"{item_def['name']}" + (f" +{old_level}" if old_level > 0 else "")
                                    new_name = f"{item_def['name']} +{new_level}"
                                    item["enchant_level"] = new_level
                                    save_db(db)
                                    
                                    send_packet(f"{char_name}-enchantingOutcomeLevel@{old_name}|{new_name}")
                                    send_packet(f"{char_name}-serverMessages@Enchantment successful! {old_name} became {new_name}.")

                    elif cmd_name == "enchantMerge":
                        char_name = cmd_meta
                        slot_1 = int(cmd_args[1]) if len(cmd_args) > 1 else -1
                        slot_2 = int(cmd_args[2]) if len(cmd_args) > 2 else -1
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char and slot_1 >= 0 and slot_2 >= 0:
                            backpack = active_char.setdefault("inventory", [None] * 25)
                            item_1 = backpack[slot_1]
                            item_2 = backpack[slot_2]
                            if item_1 and item_2:
                                backpack[slot_2] = None
                                old_level = item_1.get("enchant_level", 0)
                                new_level = old_level + 1
                                item_1["enchant_level"] = new_level
                                save_db(db)
                                
                                new_name = f"{ITEMS.get(item_1['id'])['name']} +{new_level}"
                                send_packet(f"{char_name}-enchantingOutcomeMerge@{new_name}")
                                send_packet(f"{char_name}-serverMessages@Merge successful! Created {new_name}.")

                    elif cmd_name == "bestiaryWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            bestiary = active_char.setdefault("bestiary", {})
                            wolf_kills = bestiary.get("wolf", 0)
                            bear_kills = bestiary.get("bear", 0)
                            slime_kills = bestiary.get("slime", 0)
                            
                            # Format: counts | unlocked_tabs | mob_details | npc_details | faction_details
                            # counts: mobs_count-npcs_count-factions_count
                            # unlocked_tabs: y-y-y
                            payload = [
                                "3-1-1", "y-y-y",
                                "wolf.gif", "Wolf", str(wolf_kills),
                                "bear.gif", "Bear", str(bear_kills),
                                "slime.gif", "Slime", str(slime_kills),
                                "alchemist.gif", "Alchemist", "1",
                                "faction_knight.png", "Knights", "100", "5"
                            ]
                            send_packet(f"{char_name}-bestiaryWindow@{'|'.join(payload)}")

                    elif cmd_name == "collectionsWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            collected = active_char.setdefault("collections", [])
                            
                            c_w1 = "y" if 1 in collected else "n"
                            c_w2 = "y" if 2 in collected else "n"
                            c_a10 = "y" if 10 in collected else "n"
                            c_i3 = "y" if 3 in collected else "n"
                            
                            # Format: counts | unlocked_tabs | weapon_details | armor_details | item_details
                            # counts: weapons-armor-items
                            # unlocked_tabs: y-y-y
                            payload = [
                                "2-1-1", "y-y-y",
                                "1", "wooden_club.png", "Wooden Club", c_w1,
                                "2", "apprentice_sword.png", "Apprentice Sword", c_w2,
                                "10", "cloth_footwraps.png", "Cloth Footwraps", c_a10,
                                "3", "copper_ore.png", "Copper Ore", c_i3
                            ]
                            send_packet(f"{char_name}-collectionsWindow@{'|'.join(payload)}")

                    elif cmd_name == "collectionsWindowTurnIn":
                        char_name = cmd_meta
                        category = cmd_args[1] if len(cmd_args) > 1 else ""
                        item_id = int(cmd_args[2]) if len(cmd_args) > 2 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        if active_char:
                            collected = active_char.setdefault("collections", [])
                            item_def = ITEMS.get(item_id)
                            item_name = item_def["name"] if item_def else "Unknown Item"
                            
                            if item_id in collected:
                                # Already turned in (duplicate)
                                send_packet(f"{char_name}-collectionsWindowTurnIn@false|{item_name}|duplicate")
                            else:
                                # Check if player has the item in their backpack
                                backpack = active_char.setdefault("inventory", [None] * 25)
                                found_idx = -1
                                for idx, slot in enumerate(backpack):
                                    if slot and slot["id"] == item_id:
                                        found_idx = idx
                                        break
                                if found_idx == -1:
                                    # No item in backpack
                                    send_packet(f"{char_name}-collectionsWindowTurnIn@false|{item_name}|noitem")
                                else:
                                    # Remove from backpack and add to collections
                                    backpack[found_idx] = None
                                    collected.append(item_id)
                                    save_db(db)
                                    
                                    send_packet(f"{char_name}-collectionsWindowTurnIn@true|{item_name}")
                                    send_packet(f"{char_name}-serverMessages@Successfully turned in {item_name} to your collection!")
                                    
                                    # Refresh collectionsWindow
                                    c_w1 = "y" if 1 in collected else "n"
                                    c_w2 = "y" if 2 in collected else "n"
                                    c_a10 = "y" if 10 in collected else "n"
                                    c_i3 = "y" if 3 in collected else "n"
                                    
                                    payload = [
                                        "2-1-1", "y-y-y",
                                        "1", "wooden_club.png", "Wooden Club", c_w1,
                                        "2", "apprentice_sword.png", "Apprentice Sword", c_w2,
                                        "10", "cloth_footwraps.png", "Cloth Footwraps", c_a10,
                                        "3", "copper_ore.png", "Copper Ore", c_i3
                                    ]
                                    send_packet(f"{char_name}-collectionsWindow@{'|'.join(payload)}")
                            
                    elif cmd_name == "attack":
                        char_name = cmd_meta
                        monster_id = cmd_args[1] if len(cmd_args) > 1 else ""
                        self.log(f"[*] Player '{char_name}' started attacking monster '{monster_id}'")
                        with self.connections_lock:
                            self.active_combat[char_name] = monster_id
                            
                    elif cmd_name == "attackOff":
                        char_name = cmd_meta
                        self.log(f"[*] Player '{char_name}' stopped attacking")
                        with self.connections_lock:
                            if char_name in self.active_combat:
                                del self.active_combat[char_name]

                    elif cmd_name == "logout":
                        char_name = cmd_meta
                        self.log(f"[*] Player '{char_name}' requested logout")
                        # Graceful disconnect — break out of the loop
                        break

                    elif cmd_name == "doubleClickOnMap":
                        char_name = cmd_meta
                        target_key = cmd_args[1] if len(cmd_args) > 1 else ""
                        self.log(f"[*] Player '{char_name}' double-clicked on map target: {target_key}")
                        
                        # Check if it's an NPC
                        npc_found = False
                        for val, x, y in self.map_npcs:
                            if f"{x},{y}" == target_key:
                                sprite = self.npc_sprites[val % len(self.npc_sprites)] if self.npc_sprites else "alchemist.gif"
                                if sprite.startswith("npc_"):
                                    sprite = sprite[4:]
                                npc_name = sprite.replace(".gif", "").replace(".png", "").replace("_", " ").title()
                                
                                if "banker" in sprite.lower():
                                    account_name = username.lower() if username else "unknown_user"
                                    account_data = db.get("accounts", {}).get(account_name, {})
                                    characters = account_data.get("characters", [])
                                    active_char = None
                                    for c in characters:
                                        if c["name"].lower() == char_name.lower():
                                            active_char = c
                                            break
                                    if active_char:
                                        # Character Bank
                                        bank = active_char.setdefault("bank", [None] * 256)
                                        serialized_bank = []
                                        for idx, item in enumerate(bank):
                                            uid = item.get("unique_id", 30000 + idx) if item else 0
                                            serialized_bank.append(serialize_item(item, uid))
                                        response_bk = f"{char_name}-bankWindow@40-37-32|y|y|y|" + "|".join(serialized_bank)
                                        send_packet(response_bk)
                                        
                                        # Account Bank
                                        account_bank = account_data.setdefault("account_bank", [None] * 256)
                                        serialized_ab = []
                                        for idx, item in enumerate(account_bank):
                                            uid = item.get("unique_id", 40000 + idx) if item else 0
                                            serialized_ab.append(serialize_item(item, uid))
                                        response_ab = f"{char_name}-accountBankWindow@40-37-32|y|y|y|" + "|".join(serialized_ab)
                                        send_packet(response_ab)
                                    
                                    npc_found = True
                                    break
                                
                                # Fetch dynamic NPC dialogues from database
                                npc_key = npc_name.split()[0] # e.g. "Alchemist"
                                opts = self.dialogues.get(npc_key, [
                                    {"min_level": 1, "type": "quest", "id": 148},
                                    {"min_level": 1, "type": "quest", "id": 157},
                                    {"min_level": 1, "type": "quest", "id": 158}
                                ])
                                
                                opt_fields = []
                                for opt in opts:
                                    opt_fields.extend([
                                        str(opt.get("min_level", 1)),
                                        opt.get("type", "quest"),
                                        str(opt.get("id", 0))
                                    ])
                                
                                response = f"{char_name}-dialogWindow@{len(opts)}|{npc_name}|{sprite}|1|" + "|".join(opt_fields)
                                send_packet(response)
                                npc_found = True
                                break
                        
                        if not npc_found:
                            # Check if it's a Sign or Book
                            if target_key in self.signs_books:
                                read_id = self.signs_books[target_key]
                                send_packet(f"{char_name}-readWindow@{read_id}")
                            else:
                                send_packet(f"{char_name}-serverMessages@Nothing to interact with there.")

                    elif cmd_name in ["questAccept", "questReject", "questProceed"]:
                        char_name = cmd_meta
                        option_id = int(cmd_args[1]) if len(cmd_args) > 1 else 0
                        self.log(f"[*] Player '{char_name}' action '{cmd_name}' on option {option_id}")
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            quests = active_char.setdefault("quests", {})
                            if cmd_name == "questAccept":
                                quests[str(option_id)] = "accepted"
                                save_db(db)
                                send_packet(f"{char_name}-serverMessages@Quest accepted!")
                            elif cmd_name == "questReject":
                                send_packet(f"{char_name}-serverMessages@Quest declined.")
                            elif cmd_name == "questProceed":
                                send_packet(f"{char_name}-serverMessages@Quest completed or proceeded.")

                    elif cmd_name == "autoPickupToggle":
                        char_name = cmd_meta
                        toggle_type = cmd_args[1] if len(cmd_args) > 1 else "Gold"
                        toggle_state = cmd_args[2] if len(cmd_args) > 2 else "on"
                        self.log(f"[*] Player '{char_name}' toggled auto-pickup {toggle_type} to {toggle_state}")
                        send_packet(f"{char_name}-autoPickupToggle@{toggle_type}|{toggle_state}")

                    elif cmd_name == "hideCostumeToggle":
                        char_name = cmd_meta
                        toggle_state = cmd_args[1] if len(cmd_args) > 1 else "on"
                        self.log(f"[*] Player '{char_name}' toggled hide costume to {toggle_state}")
                        
                        # Save costume hiding preference to database
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        for c in account_data.get("characters", []):
                            if c["name"].lower() == char_name.lower():
                                c["hide_costume"] = (toggle_state == "on")
                                self.mark_db_dirty()
                                break
                                
                        send_packet(f"{char_name}-hideCostumeToggle@{toggle_state}")

                    elif cmd_name == "useTradeskillItem":
                        char_name = cmd_meta
                        skill = cmd_args[1] if len(cmd_args) > 1 else "Mining"
                        target = cmd_args[2] if len(cmd_args) > 2 else ""
                        self.log(f"[*] Player '{char_name}' used tradeskill '{skill}' on '{target}'")
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            # Check if the node is depleted
                            if target in self.depleted_nodes:
                                send_packet(f"{char_name}-tradeskillAction@{skill}|NoResourcesLeft")
                            else:
                                # Give resource item & EXP
                                import random
                                success = random.random() < 0.75
                                if success:
                                    # Deplete the node using the configured cooldown
                                    self.depleted_nodes[target] = time.time() + self.tradeskill_cooldown_sec
                                    
                                    # Give item to backpack
                                    backpack = active_char.setdefault("inventory", [None] * 25)
                                    item_given = "Copper Ore"
                                    # Find empty slot
                                    slot_found = False
                                    for idx, slot in enumerate(backpack):
                                        if slot is None:
                                            backpack[idx] = {"id": 3, "unique_id": random.randint(20000, 29999), "quantity": 1}
                                            slot_found = True
                                            break
                                    if not slot_found:
                                        send_packet(f"{char_name}-serverMessages@Backpack is full!")
                                    else:
                                        save_db(db)
                                        # Update skills exp
                                        skills = active_char.setdefault("skills", {})
                                        skill_key = skill.lower()
                                        s_data = skills.setdefault(skill_key, {"level": 1, "exp": 0})
                                        s_data["exp"] += 15
                                        if s_data["exp"] >= s_data["level"] * 100:
                                            s_data["level"] += 1
                                            send_packet(f"{char_name}-serverMessages@Your {skill} skill leveled up to {s_data['level']}!")
                                        save_db(db)
                                        
                                    # Send success packet: useTradeskillItem|success|skill|exp|silent|status|item_name
                                    send_packet(f"{char_name}-useTradeskillItem@true|{skill}|15|false|NoErrors|{item_given}")
                                    
                                    # Broadcast updated entity locations to remove the node
                                    with self.connections_lock:
                                        for o_name, conn in self.active_connections.items():
                                            self.send_all_entities(o_name, conn["send"])
                                else:
                                    # Fail exp
                                    send_packet(f"{char_name}-useTradeskillItem@false|{skill}|3|false|BadLuck")

                    elif cmd_name == "useAction":
                        char_name = cmd_meta
                        action_name = cmd_args[1] if len(cmd_args) > 1 else ""
                        action_slot = int(cmd_args[2]) if len(cmd_args) > 2 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            if action_slot == 0:
                                mana = active_char.get("mana", 100)
                                if mana >= 10:
                                    active_char["mana"] = mana - 10
                                    active_char["hp"] = min(active_char.get("max_hp", 100), active_char.get("hp", 100) + 25)
                                    self.player_hps[char_name] = active_char["hp"]
                                    save_db(db)
                                    send_packet(f"{char_name}-castSpell@true|{char_name}|{char_name}|Bless")
                                    send_packet(f"{char_name}-updatePlayerHealthAndMana@{active_char['hp']},{active_char.get('max_hp', 100)}|{active_char['mana']},{active_char.get('max_mana', 100)}")
                                else:
                                    send_packet(f"{char_name}-castSpell@false|notEnoughMana|Bless|10")
                            elif action_slot == 1:
                                inv = active_char.setdefault("inventory", [None] * 25)
                                potion_idx = -1
                                for idx, item in enumerate(inv):
                                    if item and item["id"] == 3:
                                        potion_idx = idx
                                        break
                                        
                                if potion_idx != -1:
                                    item_data = inv[potion_idx]
                                    if item_data.get("quantity", 1) > 1:
                                        item_data["quantity"] -= 1
                                    else:
                                        inv[potion_idx] = None
                                        
                                    active_char["hp"] = min(active_char.get("max_hp", 100), active_char.get("hp", 100) + 50)
                                    self.player_hps[char_name] = active_char["hp"]
                                    save_db(db)
                                    
                                    send_packet(f"{char_name}-useBackpackItem@true|Potion|true|50|0|Small Health Vial")
                                    send_packet(f"{char_name}-updatePlayerHealthAndMana@{active_char['hp']},{active_char.get('max_hp', 100)}|{active_char.get('mana', 100)},{active_char.get('max_mana', 100)}")
                                    response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                    send_packet(response)
                                else:
                                    send_packet(f"{char_name}-serverMessages@You do not have any Small Health Vials left!")
                            else:
                                send_packet(f"{char_name}-serverMessages@Action slot {action_slot} is not yet configured.")

                    elif cmd_name == "castSpell":
                        char_name = cmd_meta
                        spell_id = cmd_args[1] if len(cmd_args) > 1 else ""
                        target = cmd_args[2] if len(cmd_args) > 2 else char_name
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char and spell_id == "1":
                            mana = active_char.get("mana", 100)
                            if mana >= 10:
                                active_char["mana"] = mana - 10
                                active_char["hp"] = min(active_char.get("max_hp", 100), active_char.get("hp", 100) + 25)
                                self.player_hps[char_name] = active_char["hp"]
                                save_db(db)
                                
                                send_packet(f"{char_name}-castSpell@true|{char_name}|{target}|Bless")
                                send_packet(f"{char_name}-updatePlayerHealthAndMana@{active_char['hp']},{active_char.get('max_hp', 100)}|{active_char['mana']},{active_char.get('max_mana', 100)}")
                            else:
                                send_packet(f"{char_name}-castSpell@false|notEnoughMana|Bless|10")

                    elif cmd_name == "ctrlClickOnMap":
                        char_name = cmd_meta
                        coords = cmd_args[1] if len(cmd_args) > 1 else ""
                        self.log(f"[*] Player '{char_name}' ctrl-clicked on map at {coords}")

                    elif cmd_name == "useBackpackItem":
                        char_name = cmd_meta
                        slot_idx = int(cmd_args[1]) if len(cmd_args) > 1 else -1
                        item_uid = int(cmd_args[2]) if len(cmd_args) > 2 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            item_data = None
                            if 0 <= slot_idx < 25:
                                item_data = inv[slot_idx]
                                
                            if item_data and item_data.get("unique_id") == item_uid:
                                item_def = ITEMS.get(item_data["id"])
                                if item_def and item_def.get("use_type") == "Potion":
                                    if item_data.get("quantity", 1) > 1:
                                        item_data["quantity"] -= 1
                                    else:
                                        inv[slot_idx] = None
                                        
                                    self.player_hps[char_name] = min(100, self.player_hps.get(char_name, 100) + 50)
                                    save_db(db)
                                    
                                    response = f"{char_name}-useBackpackItem@true|Potion|true|50|0|{item_def['name']}"
                                    send_packet(response)
                                    
                                    send_packet(f"{char_name}-updatePlayerHealthAndMana@{self.player_hps[char_name]},100|100,100")
                                    
                                    response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                    send_packet(response)

                    elif cmd_name == "groundMoveOrPickupItem":
                        char_name = cmd_meta
                        dest_area = cmd_args[2] if len(cmd_args) > 2 else ""
                        dest_slot = cmd_args[3] if len(cmd_args) > 3 else ""
                        item_uid = int(cmd_args[4]) if len(cmd_args) > 4 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            eq = active_char.setdefault("equipment", [None] * 14)
                            
                            src_area = None
                            src_idx = -1
                            item_data = None
                            
                            for idx, it in enumerate(inv):
                                if it and it.get("unique_id") == item_uid:
                                    src_area = "backpack"
                                    src_idx = idx
                                    item_data = it
                                    break
                            
                            if not src_area:
                                for idx, it in enumerate(eq):
                                    if it and it.get("unique_id") == item_uid:
                                        src_area = "character"
                                        src_idx = idx
                                        item_data = it
                                        break
                                        
                            if item_data:
                                if src_area == "backpack":
                                    inv[src_idx] = None
                                elif src_area == "character":
                                    eq[src_idx] = None
                                    
                                if dest_area == "backpack":
                                    d_idx = int(dest_slot)
                                    if d_idx == -1:
                                        for i in range(25):
                                            if inv[i] is None:
                                                d_idx = i
                                                break
                                    if 0 <= d_idx < 25:
                                        inv[d_idx] = item_data
                                elif dest_area == "character":
                                    d_idx = int(dest_slot)
                                    if 0 <= d_idx < 14:
                                        eq[d_idx] = item_data
                                elif dest_area == "ground":
                                    pass
                                    
                                save_db(db)
                                
                                response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                send_packet(response)
                                
                                stats = [
                                     "40-37-32",
                                     "10", "0", "10", "0", "10", "0", "10", "0", "10",
                                     str(self.player_exps.get(char_name, 0)),
                                     str(self.player_levels.get(char_name, 1)),
                                     str((self.player_levels.get(char_name, 1) - 1) * 300),
                                     str(self.player_levels.get(char_name, 1) * 300),
                                     "10", "0",
                                     "10", "10", "10", "10", "10", "10",
                                     "0", "12", "10", "100/100", "0", "None", "0", "5", "0/150", "0,0",
                                     "0", "0,0", "0", "None", "0", "m", "1.0"
                                 ]
                                stats.extend([serialize_item(it, it.get("unique_id") if it else 20000+i) for i, it in enumerate(eq)])
                                send_packet(f"{char_name}-characterWindow@{'|'.join(stats)}")
                                
                                send_packet(f"{char_name}-groundMoveOrPickupItem@true|success")

                    elif cmd_name == "useBackpackItem":
                        char_name = cmd_meta
                        slot_idx = int(cmd_args[1]) if len(cmd_args) > 1 else -1
                        item_uid = int(cmd_args[2]) if len(cmd_args) > 2 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            item_data = None
                            if 0 <= slot_idx < 25:
                                item_data = inv[slot_idx]
                                
                            if item_data and item_data.get("unique_id") == item_uid:
                                item_def = ITEMS.get(item_data["id"])
                                if item_def and item_def.get("use_type") == "Potion":
                                    if item_data.get("quantity", 1) > 1:
                                        item_data["quantity"] -= 1
                                    else:
                                        inv[slot_idx] = None
                                        
                                    self.player_hps[char_name] = min(100, self.player_hps.get(char_name, 100) + 50)
                                    save_db(db)
                                    
                                    response = f"{char_name}-useBackpackItem@true|Potion|true|50|0|{item_def['name']}"
                                    send_packet(response)
                                    
                                    send_packet(f"{char_name}-updatePlayerHealthAndMana@{self.player_hps[char_name]},100|100,100")
                                    
                                    response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                    send_packet(response)

                    elif cmd_name == "groundMoveOrPickupItem":
                        char_name = cmd_meta
                        dest_area = cmd_args[2] if len(cmd_args) > 2 else ""
                        dest_slot = cmd_args[3] if len(cmd_args) > 3 else ""
                        item_uid = int(cmd_args[4]) if len(cmd_args) > 4 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            eq = active_char.setdefault("equipment", [None] * 14)
                            
                            src_area = None
                            src_idx = -1
                            item_data = None
                            
                            for idx, it in enumerate(inv):
                                if it and it.get("unique_id") == item_uid:
                                    src_area = "backpack"
                                    src_idx = idx
                                    item_data = it
                                    break
                            
                            if not src_area:
                                for idx, it in enumerate(eq):
                                    if it and it.get("unique_id") == item_uid:
                                        src_area = "character"
                                        src_idx = idx
                                        item_data = it
                                        break
                                        
                            if item_data:
                                if src_area == "backpack":
                                    inv[src_idx] = None
                                elif src_area == "character":
                                    eq[src_idx] = None
                                    
                                if dest_area == "backpack":
                                    d_idx = int(dest_slot)
                                    if d_idx == -1:
                                        for i in range(25):
                                            if inv[i] is None:
                                                d_idx = i
                                                break
                                    if 0 <= d_idx < 25:
                                        inv[d_idx] = item_data
                                elif dest_area == "character":
                                    d_idx = int(dest_slot)
                                    if 0 <= d_idx < 14:
                                        eq[d_idx] = item_data
                                elif dest_area == "ground":
                                    pass
                                    
                                save_db(db)
                                
                                response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                send_packet(response)
                                
                                send_character_window(char_name, active_char)
                                
                                send_packet(f"{char_name}-groundMoveOrPickupItem@true|success")

                    elif cmd_name == "shopBuyWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                        
                        shop_name = "Alchemist Shop"
                        if active_char:
                            px = active_char.get("x", 79)
                            if px > 70:
                                shop_name = "Blacksmith Shop"
                        
                        shop_items = SHOPS.get(shop_name, [])
                        serialized_items = []
                        for idx, s_item in enumerate(shop_items):
                            item_def = ITEMS.get(s_item["id"])
                            if item_def:
                                item_data = {"id": s_item["id"], "quantity": s_item["price"]}
                                serialized_items.append(serialize_item(item_data, 30000 + idx))
                        
                        payload = "|".join(serialized_items)
                        response = f"{char_name}-shopBuyWindow@40-37-32|{len(shop_items)}|{payload}"
                        send_packet(response)

                    elif cmd_name == "shopBuyWindowPurchase":
                        char_name = cmd_meta
                        item_name = cmd_args[1] if len(cmd_args) > 1 else ""
                        quantity = int(cmd_args[2]) if len(cmd_args) > 2 else 1
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            px = active_char.get("x", 79)
                            shop_name = "Alchemist Shop" if px < 70 else "Blacksmith Shop"
                            shop_items = SHOPS.get(shop_name, [])
                            
                            shop_item = None
                            item_def = None
                            for s_item in shop_items:
                                idef = ITEMS.get(s_item["id"])
                                if idef and idef["name"].lower() == item_name.lower():
                                    shop_item = s_item
                                    item_def = idef
                                    break
                                    
                            if shop_item and item_def:
                                total_cost = shop_item["price"] * quantity
                                current_gold = active_char.get("gold", 0)
                                
                                if current_gold >= total_cost:
                                    inv = active_char.setdefault("inventory", [None] * 25)
                                    added = False
                                    for i in range(25):
                                        if inv[i] is None:
                                            import random
                                            uid = random.randint(100000, 999999)
                                            inv[i] = {"id": item_def["id"], "unique_id": uid, "quantity": quantity}
                                            added = True
                                            break
                                            
                                    if added:
                                        active_char["gold"] = current_gold - total_cost
                                        save_db(db)
                                        
                                        # Send official client confirmation packet
                                        send_packet(f"{char_name}-shopBuyWindowPurchase@true|[QUANTITY]={quantity}-[WAI_NAME]={item_def['name']}")
                                        
                                        response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                        send_packet(response)
                                        
                                        send_character_window(char_name, active_char)
                                    else:
                                        send_packet(f"{char_name}-shopBuyWindowPurchase@false|backpack_space")
                                else:
                                    send_packet(f"{char_name}-shopBuyWindowPurchase@false|not_enough_gold")

                    elif cmd_name == "shopSellWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            sellable_items = []
                            for idx, item in enumerate(inv):
                                if item:
                                    item_def = ITEMS.get(item["id"])
                                    if item_def:
                                        sellable_items.append(str(idx))
                                        sellable_items.append(str(item.get("quantity", 1)))
                                        sellable_items.append(serialize_item(item, item.get("unique_id", 10000+idx)))
                            
                            payload = "|".join(sellable_items)
                            response = f"{char_name}-shopSellWindow@40-37-32|{len(sellable_items)//3}|{payload}"
                            send_packet(response)

                    elif cmd_name == "shopSellWindowSale":
                        char_name = cmd_meta
                        slot_idx = int(cmd_args[1]) if len(cmd_args) > 1 else -1
                        quantity = int(cmd_args[2]) if len(cmd_args) > 2 else 1
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char and 0 <= slot_idx < 25:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            item_data = inv[slot_idx]
                            
                            if item_data:
                                item_def = ITEMS.get(item_data["id"])
                                if item_def:
                                    sell_qty = min(quantity, item_data.get("quantity", 1))
                                    sell_value = item_def.get("value", 0) * sell_qty
                                    
                                    if item_data.get("quantity", 1) > sell_qty:
                                        item_data["quantity"] -= sell_qty
                                    else:
                                        inv[slot_idx] = None
                                        
                                    active_char["gold"] = active_char.get("gold", 0) + sell_value
                                    save_db(db)
                                    
                                    # Send official client confirmation packet
                                    send_packet(f"{char_name}-shopSellWindowSale@true|[QUANTITY]={sell_qty}-[WAI_NAME]={item_def['name']}")
                                    
                                    response = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                    send_packet(response)
                                    
                                    sellable_items = []
                                    for idx, item in enumerate(inv):
                                        if item:
                                            idef = ITEMS.get(item["id"])
                                            if idef:
                                                sellable_items.append(str(idx))
                                                sellable_items.append(str(item.get("quantity", 1)))
                                                sellable_items.append(serialize_item(item, item.get("unique_id", 10000+idx)))
                                    payload = "|".join(sellable_items)
                                    send_packet(f"{char_name}-shopSellWindow@40-37-32|{len(sellable_items)//3}|{payload}")
                                    
                                    send_character_window(char_name, active_char)

                    elif cmd_name == "bankWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            bank = active_char.setdefault("bank", [None] * 256)
                            serialized_bank = []
                            for idx, item in enumerate(bank):
                                uid = item.get("unique_id", 30000 + idx) if item else 0
                                serialized_bank.append(serialize_item(item, uid))
                            
                            payload = "|".join(serialized_bank)
                            response = f"{char_name}-bankWindow@40-37-32|y|y|y|{payload}"
                            send_packet(response)

                    elif cmd_name == "accountBankWindow":
                        char_name = cmd_meta
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.setdefault("accounts", {}).setdefault(account_name, {})
                        
                        account_bank = account_data.setdefault("account_bank", [None] * 256)
                        serialized_bank = []
                        for idx, item in enumerate(account_bank):
                            uid = item.get("unique_id", 40000 + idx) if item else 0
                            serialized_bank.append(serialize_item(item, uid))
                        
                        payload = "|".join(serialized_bank)
                        response = f"{char_name}-accountBankWindow@40-37-32|y|y|y|{payload}"
                        send_packet(response)

                    elif cmd_name == "bankMoveOrDropItem":
                        char_name = cmd_meta
                        dest_area = cmd_args[2] if len(cmd_args) > 2 else ""
                        dest_slot = cmd_args[3] if len(cmd_args) > 3 else ""
                        item_uid = int(cmd_args[4]) if len(cmd_args) > 4 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            inv = active_char.setdefault("inventory", [None] * 25)
                            bank = active_char.setdefault("bank", [None] * 256)
                            account_bank = account_data.setdefault("account_bank", [None] * 256)
                            
                            src_area = None
                            src_idx = -1
                            item_data = None
                            
                            for idx, it in enumerate(inv):
                                if it and it.get("unique_id") == item_uid:
                                    src_area = "backpack"
                                    src_idx = idx
                                    item_data = it
                                    break
                            
                            if not src_area:
                                for idx, it in enumerate(bank):
                                    if it and it.get("unique_id") == item_uid:
                                        src_area = "bank"
                                        src_idx = idx
                                        item_data = it
                                        break
                                        
                            if not src_area:
                                for idx, it in enumerate(account_bank):
                                    if it and it.get("unique_id") == item_uid:
                                        src_area = "accountBank"
                                        src_idx = idx
                                        item_data = it
                                        break
                                        
                            if item_data:
                                if src_area == "backpack":
                                    inv[src_idx] = None
                                elif src_area == "bank":
                                    bank[src_idx] = None
                                elif src_area == "accountBank":
                                    account_bank[src_idx] = None
                                    
                                if dest_area == "backpack":
                                    d_idx = int(dest_slot)
                                    if d_idx == -1:
                                        for i in range(25):
                                            if inv[i] is None:
                                                d_idx = i
                                                break
                                    if 0 <= d_idx < 25:
                                        inv[d_idx] = item_data
                                elif dest_area == "bank":
                                    d_idx = int(dest_slot)
                                    if 0 <= d_idx < 256:
                                        bank[d_idx] = item_data
                                elif dest_area == "accountBank":
                                    d_idx = int(dest_slot)
                                    if 0 <= d_idx < 256:
                                        account_bank[d_idx] = item_data
                                        
                                save_db(db)
                                
                                response_bp = f"{char_name}-backpackWindow@40-37-32|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 10000+i) for i, it in enumerate(inv)])
                                send_packet(response_bp)
                                
                                response_bk = f"{char_name}-bankWindow@40-37-32|y|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 30000+i) for i, it in enumerate(bank)])
                                send_packet(response_bk)
                                
                                response_ab = f"{char_name}-accountBankWindow@40-37-32|y|y|y|" + "|".join([serialize_item(it, it.get("unique_id") if it else 40000+i) for i, it in enumerate(account_bank)])
                                send_packet(response_ab)
                                
                                send_packet(f"{char_name}-bankMoveOrDropItem@true|success")

                    elif cmd_name == "bankRegisterAction":
                        char_name = cmd_meta
                        action = cmd_args[1] if len(cmd_args) > 1 else ""
                        amount = int(cmd_args[2]) if len(cmd_args) > 2 else 0
                        
                        account_name = username.lower() if username else "unknown_user"
                        account_data = db.get("accounts", {}).get(account_name, {})
                        characters = account_data.get("characters", [])
                        active_char = None
                        for c in characters:
                            if c["name"].lower() == char_name.lower():
                                active_char = c
                                break
                                
                        if active_char:
                            current_gold = active_char.get("gold", 0)
                            current_bank_gold = active_char.get("bank_gold", 0)
                            
                            if action == "deposit":
                                if current_gold >= amount:
                                    active_char["gold"] = current_gold - amount
                                    active_char["bank_gold"] = current_bank_gold + amount
                                    save_db(db)
                                    send_packet(f"{char_name}-serverMessages@Deposited {amount} gold into the bank.")
                                else:
                                    send_packet(f"{char_name}-serverMessages@You do not have enough gold to deposit!")
                            elif action == "withdraw":
                                if current_bank_gold >= amount:
                                    active_char["gold"] = current_gold + amount
                                    active_char["bank_gold"] = current_bank_gold - amount
                                    save_db(db)
                                    send_packet(f"{char_name}-serverMessages@Withdrew {amount} gold from the bank.")
                                else:
                                    send_packet(f"{char_name}-serverMessages@You do not have enough gold in the bank to withdraw!")
                                    
                            send_character_window(char_name, active_char)

                    elif cmd_name in ["shopTradesWindow"]:
                        char_name = cmd_meta
                        self.log(f"[*] Player '{char_name}' requested {cmd_name}")
                        send_packet(f"{char_name}-serverMessages@There is no shop nearby.")

                    elif cmd_name in ["bestiaryWindow", "collectionsWindow", "craftingWindow",
                                      "enchantingWindow", "enchantingMergeWindow",
                                      "premiumShopBuyWindow",
                                      "guildWindow", "guildLevelWindow",
                                      "marketplaceListWindow", "rivalsWindow",
                                      "petStableWindow"]:
                        char_name = cmd_meta
                        self.log(f"[*] Player '{char_name}' requested {cmd_name} (stub)")
                        send_packet(f"{char_name}-{cmd_name}@0")

                    elif cmd_name == "heart":
                        # Heartbeat keepalive — no response needed
                        pass

                    elif cmd_name == "walkOff":
                        char_name = cmd_meta
                        # Queue the stop walking task to be processed by the dedicated movement thread
                        self.movement_queue.put((char_name, "walkOff", None, send_packet, username))

                    else:
                        self.log(f"[*] Warning: Unknown command '{cmd_name}' received.")
                else:
                    self.log(f"[*] Warning: Packet does not contain '@': '{packet}'")
                        
        except Exception as e:
            self.log(f"[-] Connection Error with {client_address[0]}:{client_address[1]}: {e}")
            import traceback
            self.log(traceback.format_exc())
        finally:
            if username:
                self.remove_player(username)
            # Remove from connection registry
            if 'character_id' in locals() and character_id:
                with self.connections_lock:
                    if character_id.lower() in self.active_connections:
                        del self.active_connections[character_id.lower()]
                    if character_id in self.active_combat:
                        del self.active_combat[character_id]
            client_socket.close()
            self.log(f"[*] Connection with {client_address[0]} closed.")

    def start_tcp_server(self):
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=CRT_PATH, keyfile=KEY_PATH)
            
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((HOST, PORT))
            server_socket.listen(5)
            
            self.log(f"[*] Server listening on {HOST}:{PORT} (SSL)...")
            
            while True:
                client_conn, client_addr = server_socket.accept()
                try:
                    ssl_conn = context.wrap_socket(client_conn, server_side=True)
                    client_thread = threading.Thread(target=self.handle_client, args=(ssl_conn, client_addr))
                    client_thread.daemon = True
                    client_thread.start()
                except Exception as handshake_err:
                    self.log(f"[-] SSL Handshake or Connection failed: {handshake_err}")
                    try:
                        client_conn.close()
                    except Exception:
                        pass
        except Exception as e:
            self.log(f"[-] Server Error: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ServerGUI(root)
    root.mainloop()
