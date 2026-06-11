import socket
import os
import threading
import time

HOST = socket.gethostbyname(socket.gethostname())
PORT = 7777
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
pending_shares = []

def main():
    
    client.connect((HOST, PORT))

    t = threading.Thread(target=receiver, args=(client,), daemon=True)
    t.start()
    
    while True:
        time.sleep(0.1)
        print("\n1. Register")
        print("2. Login")
        print("3. Logout")
        print("4. List users")
        print("5. Upload file")
        print("6. List files")
        print("7. Share")
        print("8. View share requests")
        print("9. Exit")

        choice = input("Choice: ")

        if choice == "1":

            username = input("Username: ")
            password = input("Password: ")

            msg = f"CTRL|REGISTER|{username}|{password}\n"

            send(client, msg)

        elif choice == "2":
            username = input("Username: ")
            password = input("Password: ")

            msg = f"CTRL|LOGIN|{username}|{password}\n"

            send(client, msg)

        elif choice == "3":
            send(client, "CTRL|LOGOUT\n")

        elif choice == "4":
            send(client, "CTRL|LIST_USERS\n")
                        
        elif choice == "5":
            upload(client)

        elif choice == "6":
            send(client, "CTRL|LIST_FILES\n")

        elif choice == "7":
            filename = input("filename: ")
            username = input("Username: ")

            msg = f"CTRL|SHARE|{filename}|{username}\n"

            send(client, msg)

        elif choice == "8":
            if not pending_shares:
                print("No pending share requests")
                continue

            print("\nPending requests:")

            for i, (sender, filename) in enumerate(pending_shares, start=1):
                print(f"{i}. {sender} -> {filename}")

            req_num = int(input("Select request number: "))

            if req_num < 1 or req_num > len(pending_shares):
                print("Invalid request")
                continue

            sender, filename = pending_shares[req_num - 1]

            action = input("Accept (a) or Reject (r)? ")

            if action.lower() == "a":
                send(client, f"DATA|ACCEPT_FILE|{filename}\n")

            elif action.lower() == "r":
                send(client, f"DATA|REJECT_FILE|{filename}\n")

            else:
                print("Invalid action")
                continue

            pending_shares.pop(req_num - 1)


        elif choice == "9":
            send(client, "CTRL|EXIT\n")
            break

    client.close()


def receiver(sock):
    download_files = {}

    while True:
        try:
            msg = recv_line(sock)

            if not msg:
                break

            print("\n[SERVER]:", msg)

            # SHARE handler
            if msg.startswith("SHARE_REQUEST"):
                _, sender, filename = msg.split("|")

                pending_shares.append((sender, filename))
                print(f"\nNew share request from {sender} for {filename}\nChoose menu option 8 to respond.")

            elif msg.startswith("DATA|FILE_CHUNK"):
                parts = msg.split("|")

                filename = parts[2]
                chunk_size = int(parts[4])
                me = parts[5]

                if filename not in download_files:
                    user_dir = os.path.join("downloads", me)
                    os.makedirs(user_dir, exist_ok=True)

                    path = os.path.join(user_dir, filename)

                    download_files[filename] = open(path, "wb")

                chunk = recv_exact(sock, chunk_size)
                download_files[filename].write(chunk)

            elif msg.startswith("DATA|END_FILE"):

                parts = msg.split("|")

                filename = parts[2]

                if filename in download_files:

                    download_files[filename].close()

                    del download_files[filename]

                print(f"\nDownload complete: {filename}")


        except Exception as e:
            print("Receiver stopped:", e)
            break
            

def send(sock, data):
    sock.sendall(data.encode())



def upload(sock):
    chunk_size = 1024

    filename = input("filename: ")

    if not os.path.isfile(filename):
        print("ERROR file not found")
        return

    size = os.path.getsize(filename)

    send(sock, f"CTRL|UPLOAD|{filename}|{size}\n")

    with open(filename, "rb") as f:
        data = f.read()

    idx = 1

    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]

        header = f"DATA|FILE_CHUNK|{filename}|{idx}|{len(chunk)}\n"

        sock.sendall(header.encode())
        sock.sendall(chunk)

        idx += 1

    sock.sendall(f"DATA|END_FILE|{filename}\n".encode())



def recv_exact(sock, size):
    data = b""

    while len(data) < size:
        packet = sock.recv(size - len(data))

        if not packet:
            raise ConnectionError("Disconnected")

        data += packet

    return data


def recv_line(sock):
    data = b""

    while not data.endswith(b"\n"):
        chunk = sock.recv(1)

        if not chunk:
            raise ConnectionError("Disconnected")

        data += chunk

    return data.decode().strip()

if __name__ == "__main__":
    main()