import socket

HOST = socket.gethostbyname(socket.gethostname())
PORT = 7777

def main():

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    client.connect((HOST, PORT))

    while True:

        print("\n1. Register")
        print("2. Login")
        print("3. Logout")
        print("4. List users")
        print("5. Upload file")
        print("6. Exit")

        choice = input("Choice: ")

        if choice == "1":

            username = input("Username: ")
            password = input("Password: ")

            msg = f"CTRL|REGISTER|{username}|{password}\n"

            send_command(client, msg)

        elif choice == "2":
            username = input("Username: ")
            password = input("Password: ")

            msg = f"CTRL|LOGIN|{username}|{password}\n"

            send_command(client, msg)

        elif choice == "3":
            send_command(client, "CTRL|LOGOUT\n")

        elif choice == "4":
            send_command(client, "CTRL|LIST_USERS\n")
                        
        elif choice == "5":
            upload(client)

        elif choice == "6":
            send_command(client, "CTRL|EXIT\n")
            break

    client.close()


def send_command(sock, command):

    sock.sendall(command.encode())

    response = sock.recv(1024).decode()

    print("SERVER:", response)

    return response


def upload(sock):
    chunk_size = 1024

    filename = input("filename: ")
    size = int(input("size: "))

    resp = send_command(sock, f"CTRL|UPLOAD|{filename}|{size}\n")
    if not resp.startswith("OK"):
        return

    with open(filename, "rb") as f:
        data = f.read()
    size = len(data)

    # uploading chunks
    idx = 1

    for i in range(0, size, chunk_size):

        chunk = data[i:i+chunk_size]

        header = f"DATA|FILE_CHUNK|{filename}|{idx}|{len(chunk)}\n"

        sock.sendall(header.encode()) # sending header
        sock.sendall(chunk)       # raw bytes

        idx += 1

    # end of file
    send_command(sock, f"DATA|END_FILE|{filename}\n")


if __name__ == "__main__":
    main()