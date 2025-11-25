import sys
from Client import Client

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: ClientLauncher.py <Server Addr> <Server Port> <RTP Port> <Video File>")
        sys.exit(0)

    serverAddr = sys.argv[1]
    serverPort = sys.argv[2]
    rtpPort = sys.argv[3]
    fileName = sys.argv[4]

    # GỌI ĐÚNG 4 THAM SỐ
    Client(serverAddr, serverPort, rtpPort, fileName)
