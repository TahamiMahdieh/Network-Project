import socket
import threading
import os
from datetime import datetime

FILES_DIR = "server_files"
DB_FILE = "files_db.txt"
USERS_FILE = "users.txt"

os.makedirs(FILES_DIR, exist_ok=True)

uploads = {}  
online_users = set()
lock = threading.Lock()

HOST = socket.gethostbyname(socket.gethostname())
PORT = 7777


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.bind((HOST, PORT))
    server.listen()

    print(f"[LISTENING] {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()

        thread = threading.Thread(target=handle_client, args=(conn, addr))

        thread.start()



def load_users():
    users = {}

    if not os.path.exists(USERS_FILE):
        open(USERS_FILE, "w").close()

    with open(USERS_FILE, "r") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            username, password = line.split(":", 1)
            users[username] = password

    return users


def save_user(username, password):
    with open(USERS_FILE, "a") as f:
        f.write(f"{username}:{password}\n")


def register(username, password):
    users = load_users()

    if username in users:
        return "ERROR username already exists"

    save_user(username, password)
    return "OK"


def login(username, password):
    users = load_users()

    if username not in users:
        return "AUTH FAILED. USERNAME NOT FOUND"

    if users[username] != password:
        return "AUTH FAILED. WRONG PASSWORD"

    with lock:
        if username in online_users:
            return "ERROR user already logged in"

        online_users.add(username)

    return "AUTH SUCCESS"


def logout(username):
    with lock:
        online_users.discard(username)


def save_metadata(user, filename, size):

    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(DB_FILE, "a") as f:
        f.write(f"{user}|{filename}|{size}|{time}\n")

def recv_exact(conn, size):
    data = b""
    while len(data) < size:
        packet = conn.recv(size - len(data))
        if not packet:
            raise ConnectionError("client disconnected")
        data += packet
    return data

def recv_line(conn):
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(1)
        if not chunk:
            return None
        data += chunk
    return data.decode().strip()


def handle_client(conn, addr):
    print(f"[CONNECTED] {addr}")

    current_user = None

    try:
        while True:

            line = recv_line(conn)

            if not line:
                break


            print(f"[RECEIVED] {line}")

            parts = line.split("|")

            if len(parts) < 2:
                conn.sendall(b"ERROR invalid command")
                continue

            msg_type = parts[0]
            command = parts[1]
            
            if command == "REGISTER" and msg_type == "CTRL":

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format")
                    continue

                username = parts[2]
                password = parts[3]

                response = register(username, password)
                conn.sendall(response.encode())

            elif command == "LOGIN" and msg_type == "CTRL":
                if current_user:
                    conn.sendall(b'ERROR: you should log out first')
                    continue

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format")
                    continue

                username = parts[2]
                password = parts[3]

                response = login(username, password)

                if response == "AUTH SUCCESS":
                    current_user = username

                conn.sendall(response.encode())

            elif command == "LOGOUT" and msg_type == "CTRL":

                if current_user:
                    logout(current_user)
                    current_user = None
                    conn.sendall(b"LOGGED OUT")
                else:
                    conn.sendall(b"ERROR AUTH REQUIRED")    
                

            elif command == "LIST_USERS" and msg_type == "CTRL":
                
                if not current_user:
                    conn.sendall(b"ERROR AUTH REQUIRED")

                else:
                    with lock:
                        users = [user for user in online_users if user != current_user]

                    response = "USER_LIST " + ",".join(users)
                    conn.sendall(response.encode())
                

            elif command == "UPLOAD" and msg_type == "CTRL":
                if not current_user:
                    conn.sendall(b"ERROR AUTH REQUIRED")
                    continue

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format")
                    continue

                filename = parts[2]

                try:
                    filesize = int(parts[3])
                    if filesize <= 0:
                        raise ValueError
                except:
                    conn.sendall(b"ERROR invalid filesize")
                    continue

                # file path on disc
                path = os.path.join(FILES_DIR, filename)

                with lock:
                    uploads[filename] = {
                        "file": open(path, "wb"),
                        "size": filesize,
                        "received": 0,
                        "user": current_user
                    }

                conn.sendall(b"OK\n")
                        
            elif command == "EXIT" and msg_type == "CTRL":

                if current_user:
                    logout(current_user)

                conn.sendall(b"BYE\n")
                break


            elif command == "FILE_CHUNK" and msg_type == "DATA":

                filename = parts[2]
                chunk_size = int(parts[4])

                if filename not in uploads:
                    conn.sendall(b"ERROR no upload session\n")
                    continue

                chunk = recv_exact(conn, chunk_size)

                uploads[filename]["file"].write(chunk)
                uploads[filename]["received"] += len(chunk)



            elif command == "END_FILE" and msg_type == "DATA":
                filename = parts[2]

                if filename not in uploads:
                    conn.sendall(b"ERROR no upload session\n")
                    continue

                file_info = uploads[filename]

                if file_info["received"] != file_info["size"]:
                    file_info["file"].close()
                    del uploads[filename]
                    conn.sendall(b"ERROR incomplete upload\n")
                    continue

                file_info["file"].close()

                save_metadata(file_info["user"], filename, file_info["size"])

                del uploads[filename]

                conn.sendall(b"UPLOAD_SUCCESS\n")


            else:
                conn.sendall(b"ERROR unknown command")

    except Exception as e:
        print(e)

    finally:

        if current_user:
            logout(current_user)

        conn.close()
        print(f"[DISCONNECTED] {addr}")




if __name__ == "__main__":
    main()