import socket
import threading
import os
from datetime import datetime

FILES_DIR = "server_files"
DB_FILE = "files_db.txt"
USERS_FILE = "users.txt"

os.makedirs(FILES_DIR, exist_ok=True)

pending_shares = {}
uploads = {}  
online_connections = {}
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
    with lock:
        online_connections.pop(username, None)


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
    user_upload_keys = set()

    try:
        while True:

            line = recv_line(conn)

            if not line:
                break


            print(f"[RECEIVED] {line}")

            parts = line.split("|")

            if len(parts) < 2:
                conn.sendall(b"ERROR invalid command\n")
                continue

            msg_type = parts[0]
            command = parts[1]
            
            if command == "REGISTER" and msg_type == "CTRL":

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format\n")
                    continue

                username = parts[2]
                password = parts[3]

                response = register(username, password) + "\n"
                conn.sendall(response.encode())

            elif command == "LOGIN" and msg_type == "CTRL":
                if current_user:
                    conn.sendall(b'ERROR: you should log out first\n')
                    continue

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format\n")
                    continue

                username = parts[2]
                password = parts[3]

                response = login(username, password) + "\n"

                if response == "AUTH SUCCESS\n":
                    current_user = username
                    with lock:
                        online_connections[username] = conn

                conn.sendall(response.encode())

            elif command == "LOGOUT" and msg_type == "CTRL":

                if current_user:
                    logout(current_user)
                    current_user = None
                    conn.sendall(b"LOGGED OUT\n")
                else:
                    conn.sendall(b"ERROR authentication requried\n")    
                

            elif command == "LIST_USERS" and msg_type == "CTRL":
                if not current_user:
                    conn.sendall(b"ERROR authentication required\n")

                else:
                    with lock:
                        users = [user for user in online_users if user != current_user]

                    response = "USER_LIST " + ",".join(users) + "\n"
                    conn.sendall(response.encode())
                

            elif command == "UPLOAD" and msg_type == "CTRL":
                if not current_user:
                    conn.sendall(b"ERROR authentication requried\n")
                    continue

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format\n")
                    continue

                filename = parts[2]

                try:
                    filesize = int(parts[3])
                    if filesize <= 0:
                        raise ValueError
                except:
                    conn.sendall(b"ERROR invalid filesize\n")
                    continue

                # file path on disc
                user_dir = os.path.join(FILES_DIR, current_user)
                os.makedirs(user_dir, exist_ok=True)

                path = os.path.join(user_dir, filename)

                with lock:
                    uploads[(current_user, filename)] = {
                        "file": open(path, "wb"),
                        "path": path,
                        "size": filesize,
                        "received": 0,
                        "user": current_user
                    }
                
                user_upload_keys.add((current_user, filename))

                conn.sendall(b"OK\n")
                        
            elif command == "EXIT" and msg_type == "CTRL":

                if current_user:
                    logout(current_user)

                conn.sendall(b"BYE\n")
                break

            elif command == "LIST_FILES" and msg_type == "CTRL":
                if not current_user:
                    conn.sendall(b"ERROR authentication required\n")
                    continue

                files = set()

                if os.path.exists(DB_FILE):
                    with open(DB_FILE, "r") as f:
                        for line in f:
                            line = line.strip()

                            if not line:
                                continue

                            user, filename, size, timestamp = line.split("|")

                            if user == current_user:
                                files.add(filename)

                if not files:
                    conn.sendall(b"FILE_LIST empty\n")
                else:
                    response = "FILE_LIST " + ",".join(files) + "\n"
                    conn.sendall(response.encode())


            elif command == "SHARE" and msg_type == "CTRL":
                if not current_user:
                    conn.sendall(b"ERROR authentication required\n")
                    continue

                if len(parts) != 4:
                    conn.sendall(b"ERROR invalid format\n")
                    continue

                filename = parts[2]
                target_user = parts[3]

                file_path = os.path.join(FILES_DIR, current_user, filename)

                if not os.path.exists(file_path):
                    conn.sendall(b"ERROR file not found\n")
                    continue

                users = load_users()

                if target_user not in users:
                    conn.sendall(b"ERROR target user not found\n")
                    continue

                with lock:
                    if target_user not in online_connections:
                        conn.sendall(b"ERROR target user is offline\n")
                        continue

                target_conn = online_connections[target_user]
                msg = f"SHARE_REQUEST|{current_user}|{filename}\n"
                target_conn.sendall(msg.encode())

                conn.sendall(b"OK\n")

                pending_shares[target_user] = {
                    "from": current_user,
                    "file": filename
                }
            

            elif command == "ACCEPT_FILE" and msg_type == "DATA":
                if not current_user:
                    conn.sendall(b"ERROR authentication required\n")
                    continue

                filename = parts[2]

                if current_user not in pending_shares:
                    conn.sendall(b"ERROR no pending share\n")
                    continue

                share = pending_shares[current_user]

                if share["file"] != filename:
                    conn.sendall(b"ERROR invalid file\n")
                    continue

                # begin sending file
                sender = share["from"]
                path = os.path.join(FILES_DIR, sender, filename)

                conn.sendall(b"SHARE_ACCEPTED\n")


                chunk_size = 1024

                with open(path, "rb") as f:
                    data = f.read()
                
                idx = 1

                for i in range(0, len(data), chunk_size):
                    chunk = data[i:i+chunk_size]

                    header = f"DATA|FILE_CHUNK|{filename}|{idx}|{len(chunk)}|{current_user}\n"
                    conn.sendall(header.encode())
                    conn.sendall(chunk)

                    idx += 1

                conn.sendall(f"DATA|END_FILE|{filename}\n".encode())
                del pending_shares[current_user]


            elif command == "REJECT_FILE" and msg_type == "DATA":
                if not current_user:
                    conn.sendall(b"ERROR authentication required\n")
                    continue

                filename = parts[2]

                if current_user not in pending_shares:
                    conn.sendall(b"ERROR no pending share\n")
                    continue

                share = pending_shares[current_user]

                if share["file"] != filename:
                    conn.sendall(b"ERROR invalid file\n")
                    continue

                del pending_shares[current_user]

                conn.sendall(b"SHARE_REJECTED\n")

            elif command == "FILE_CHUNK" and msg_type == "DATA":

                filename = parts[2]
                chunk_size = int(parts[4])

                if (current_user, filename) not in uploads:
                    conn.sendall(b"ERROR no upload session\n")
                    continue
                
                chunk = recv_exact(conn, chunk_size)


                uploads[(current_user, filename)]["file"].write(chunk)
                uploads[(current_user, filename)]["received"] += len(chunk)



            elif command == "END_FILE" and msg_type == "DATA":
                filename = parts[2]

                if (current_user, filename) not in uploads:
                    conn.sendall(b"ERROR no upload session\n")
                    continue

                file_info = uploads[(current_user, filename)]

                if file_info["received"] != file_info["size"]:
                    file_info["file"].close()
                    del uploads[(current_user, filename)]
                    conn.sendall(b"ERROR incomplete upload\n")
                    continue

                file_info["file"].close()

                save_metadata(file_info["user"], filename, file_info["size"])

                del uploads[(current_user, filename)]

                conn.sendall(b"UPLOAD_SUCCESS\n")


            elif command == "CHAT" and msg_type == "DATA":
                if not current_user:
                    conn.sendall(b"ERROR authentication required\n")
                    continue

                if len(parts) < 4:
                    conn.sendall(b"ERROR invalid format\n")
                    continue

                target_user = parts[2]

                message = "|".join(parts[3:])

                users = load_users()

                if target_user not in users:
                    conn.sendall(b"ERROR target user not found\n")
                    continue

                with lock:
                    if target_user not in online_connections:
                        conn.sendall(b"ERROR target user is offline\n")
                        continue

                    target_conn = online_connections[target_user]
                
                target_conn.sendall(f"CHAT_FROM|{current_user}|{message}\n".encode())
                conn.sendall(b"MESSAGE_SENT\n")


            

            else:
                conn.sendall(b"ERROR unknown command\n")

    except Exception as e:
        print(e)

    finally:
        for key in list(user_upload_keys):
            if key in uploads:
                info = uploads[key]

                try:
                    info["file"].close()
                except:
                    pass

                if info["received"] < info["size"]:
                    print(f"[UPLOAD FAILED] {key[1]} from {key[0]}")

                    try:
                        if os.path.exists(info["path"]):
                            os.remove(info["path"])
                    except:
                        pass

                uploads.pop(key, None)

        if current_user:
            logout(current_user)


        conn.close()
        print(f"[DISCONNECTED] {addr}")




if __name__ == "__main__":
    main()