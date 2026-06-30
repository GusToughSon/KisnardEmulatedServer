# Kisnard Emulated Server

A self-contained, multi-threaded Python TCP server designed to emulate the backend of the Java-based MMORPG **Kisnard Online**. It includes a graphical administration dashboard, player database persistence, custom event loops, and an integrated Java Binary Object Serialization deserializer.

---

## 📂 Directory Structure

```text
KisnardEmulatedServer/
│
├── kisnard_server.py         # Main server code (TCP socket listener, GUI Panel, & game logic)
├── run_local_server.bat      # Startup script that patches SSL truststore and launches server
├── compile_to_exe.bat        # Compiles the server into a standalone Windows binary
│
├── dist/                     # Target directory for the compiled server executable
│   └── kisnard_server.exe    # Compiled standalone server executable
│
├── java_serialization/       # Mimics Java native binary object serialization in Python
│   └── java_serialization.py # Handles stats/inventory packets sent by the Java client
│
├── scratch/                  # Critical runtime databases, scripts, and security certificates
│   ├── database.json         # JSON database (Accounts, Characters, Signs & Books)
│   ├── patch_checksums.py    # Auto-patches client's checksums.txt to accept local SSL
│   ├── server.key            # Private SSL Key for TLS handshake
│   └── server.crt            # Public SSL Certificate
│
├── How to connect/           # Client integration guides
│   ├── README.md             # Guide to starting the server and connecting the client
│   └── KisnardOnline_Launcher.bat.example # Backup of the client launcher batch file
│
└── Log/                      # Automatically generated at runtime
    └── server.log            # Running log of server/client packets and socket events
```

---

## ⚙️ Component Explanations

### 🖥️ 1. Main Server Stack (`kisnard_server.py`)
This script contains the core Python server logic and a **Tkinter-based Control Panel**. Key features include:
* **SSL/TLS TCP Socket Server**: Listens on port `34215` and wraps client communication in SSL using `server.key` and `server.crt`.
* **Multi-threaded Architecture**: Runs non-blocking background workers for:
  * **Combat Ticks**: Auto-processes attacks, experience gains, player grunts/damage sounds, death states, and level-up visual effects.
  * **Movement Processing**: Resolves pathfinding coordinates thread-safely via a dedicated movement queue.
  * **Day/Night Cycle Loop**: Auto-advances time through dawn, day, dusk, and night, broadcasting screen-shading packets.
* **Admin Dashboard tabs**:
  * **Players**: View active users, ban/kick players, and view account stats.
  * **Interactables**: Double-click listbox coordinates to instantly populate entry fields and edit signs/books Read IDs.
  * **Verbose Console Logs & Chat Monitor**: Live capture of all network packet transmissions and global game chat logs.

### 🔐 2. Security & Handshaking (`scratch/`)
* **`patch_checksums.py`**: The original Java client requires a secure SSL connection. The client verifies the checksum of its Java truststore against `checksums.txt`. This script computes the SHA-1 of the emulated server's custom truststore certificates and patches the client's local files to prevent SSL handshake errors.
* **SSL Certificates**: The `server.key` and `server.crt` are dynamically generated PEM certificates used by the server's socket wrapper.

### 📦 3. Serialization Layer (`java_serialization/`)
Because the Java client sends binary representations of Java objects (like arrays, classes, and serialization streams) when sending stats and inventories, the Python server uses `java_serialization.py` to parse these streams into Python dictionaries and vice-versa. This is essential for the equipment window, inventories, and bag slot operations.

### 🚀 4. Batch Utility Tools
* **`run_local_server.bat`**: Automates checksum patching and boots the Python server.
* **`compile_to_exe.bat`**: Runs PyInstaller to bundle the code and the `java_serialization` folder into a single-file, console-free Windows executable (`dist/kisnard_server.exe`).

---

## 📖 Connection & Quick Start Guide
To connect your client, refer to the step-by-step instructions in the [How to connect Guide](file:///c:/Users/gooro/OneDrive/Desktop/KisnardFinds/KisnardEmulatedServer/How%20to%20connect/README.md).
