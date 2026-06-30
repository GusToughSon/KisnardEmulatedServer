# How to Connect to your Local Emulated Server

Follow these simple steps to start your local server and connect the original client.

---

### Prerequisites
* **Java**: Ensure Java (JRE/JDK) is installed on your computer to run the client.
* **Python**: (Optional) Required only if running the server via python script rather than the compiled `.exe`.

---

### Step 1: Start the Server
You have two options to run the server:

* **Option A (Recommended)**: Go to the `KisnardEmulatedServer` folder and double-click `run_local_server.bat`. This automatically patches the client's SSL truststore checksums and starts the server.
* **Option B (Compiled)**: Go to the `KisnardEmulatedServer/dist` folder and run `kisnard_server.exe`.

*The server will start its control panel and begin listening for connections on `127.0.0.1:34215`.*

---

### Step 2: Start the Client
1. Open the original client folder:
   [c:\Users\gooro\OneDrive\Desktop\KisnardOnline](file:///c:/Users/gooro/OneDrive/Desktop/KisnardOnline/)
2. Double-click the launcher batch file:
   [KisnardOnline_Launcher.bat](file:///c:/Users/gooro/OneDrive/Desktop/KisnardOnline/KisnardOnline_Launcher.bat)

*This launcher will configure the local hosts redirection to point the client directly to your local emulated server and start the game.*

> [!NOTE]
> If the launcher batch file is missing from your client folder, you can copy the stock example provided in this folder:
> [KisnardOnline_Launcher.bat.example](file:///c:/Users/gooro/OneDrive/Desktop/KisnardFinds/KisnardEmulatedServer/How%20to%20connect/KisnardOnline_Launcher.bat.example) (simply copy it to your client folder and rename it to `KisnardOnline_Launcher.bat`).

---

### Step 3: Log In and Play
1. In the client login window, enter **any username and password** you like.
   * If the account does not exist, the emulated server will automatically register it for you.
2. Click **Login**.
3. Create a character (or select an existing one) and click **Play** to enter the game!
