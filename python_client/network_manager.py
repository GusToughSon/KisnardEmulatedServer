import socket
import ssl
import threading
import queue
import time
import hashlib
from java_serialization import JavaObjectInputStream, JavaObjectOutputStream

class NetworkManager:
    def __init__(self, host="107.20.157.19", port=34215):
        self.host = host
        self.port = port
        self.raw_socket = None
        self.ssl_socket = None
        self.out_stream = None
        
        self.packet_queue = queue.Queue()
        self.running = False
        self.listener_thread = None
        self.status = "Disconnected"
        self.status_error = False

    def connect(self, username, password, version="1.3.4"):
        self.close()
        self.status = "Connecting..."
        self.status_error = False
        print(f"Connecting to {self.host}:{self.port}...")
        try:
            # Create socket
            self.raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.raw_socket.settimeout(10)
            
            # Configure SSL context to bypass cert verification (since server uses a custom truststore)
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Wrap socket
            self.ssl_socket = context.wrap_socket(self.raw_socket, server_hostname=self.host)
            self.ssl_socket.connect((self.host, self.port))
            
            # Remove the timeout so the listener thread can block indefinitely waiting for packets
            self.ssl_socket.settimeout(None)
            self.status = "Connected - authenticating..."
            print("SSL Handshake successful!")
        except Exception as exc:
            self.status = f"Connection failed: {exc}"
            self.status_error = True
            self.close(preserve_status=True)
            raise
        
        # Initialize output stream and send the header
        self.out_stream = JavaObjectOutputStream(write_header=True)
        self.bytes_sent = 0
        
        # Send the header bytes
        header_bytes = self.out_stream.get_bytes()
        self.ssl_socket.sendall(header_bytes)
        self.bytes_sent = len(header_bytes)
        
        # Send initial login string immediately
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        login_string = f"{username}@authenticate|{password_hash}|{version}"
        print(f"Sending authentication request for {username}")
        self.send_packet(login_string)

        self.running = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()

    def send_packet(self, obj):
        if not self.ssl_socket:
            return
        
        # Write the object to the continuous stream
        self.out_stream.write_object(obj)
        
        # Get all bytes and send only the unsent portion
        all_bytes = self.out_stream.get_bytes()
        new_bytes = all_bytes[self.bytes_sent:]
        
        self.ssl_socket.sendall(new_bytes)
        self.bytes_sent = len(all_bytes)

    def _listen_loop(self):
        # We need to read the stream header first.
        # But wait, JavaObjectInputStream reads the header in __init__.
        # Because we are reading from a streaming socket, we can wrap the socket's read into a stream.
        # Let's read the stream header (4 bytes) first.
        try:
            header = self.ssl_socket.recv(4)
            if len(header) < 4:
                print("Failed to read stream header.")
                self.running = False
                return
            
            # Now we loop, reading objects.
            # Java Object streams are continuous. We can feed bytes to JavaObjectInputStream.
            # A simple way to handle streaming is to read a chunk of bytes, and if the parser needs more, read more.
            # Let's implement a socket-backed stream reader or just pass a buffer.
            # To do this cleanly, we can write a class that wraps the socket recv into a file-like object.
            socket_file = SocketFile(self.ssl_socket, header)
            in_stream = JavaObjectInputStream(socket_file)
            
            while self.running:
                try:
                    obj = in_stream.read_object()
                    if obj is not None:
                        self.packet_queue.put(obj)
                except Exception as e:
                    print(f"Error parsing incoming packet: {e}")
                    break
        except Exception as e:
            print(f"Socket listener error: {e}")
        finally:
            self.running = False
            if not self.status_error:
                self.status = "Disconnected"
            print("Network listener thread stopped.")

    def close(self, preserve_status=False):
        self.running = False
        if self.ssl_socket:
            try:
                self.ssl_socket.close()
            except OSError:
                pass
        if self.raw_socket:
            try:
                self.raw_socket.close()
            except OSError:
                pass
        self.ssl_socket = None
        self.raw_socket = None
        self.out_stream = None
        if not preserve_status:
            self.status = "Disconnected"
            self.status_error = False


class SocketFile:
    """A file-like object that reads directly from a socket, starting with pre-read bytes."""
    def __init__(self, sock, initial_bytes=b""):
        self.sock = sock
        self.buffer = initial_bytes

    def read(self, size):
        while len(self.buffer) < size:
            data = self.sock.recv(max(4096, size - len(self.buffer)))
            if not data:
                raise EOFError("Socket closed")
            self.buffer += data
        
        res = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return res
