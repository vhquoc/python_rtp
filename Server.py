import socket, threading, sys, os, time
from RtpPacket import RtpPacket
from VideoStream import VideoStream

class Server:
    def __init__(self, serverPort=8554, videoFile="movie.MJPEG"):
        self.serverPort = serverPort
        self.videoFile = videoFile

        self.clientAddr = None
        self.rtpPort = 0
        self.state = 0
        self.rtspSeq = 0
        self.sessionId = 123456
        self.frameNbr = 0

        self.teardownEvent = threading.Event()
        self.clientInfo = {}

    def main(self):
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rtspSocket.bind(('', self.serverPort))
        self.rtspSocket.listen(5)

        print(f"[INFO] RTSP Server listening on port {self.serverPort}")

        while True:
            clientSocket, clientAddr = self.rtspSocket.accept()
            print(f"[INFO] Client connected from {clientAddr}")

            threading.Thread(
                target=self.clientHandler, args=(clientSocket, clientAddr), daemon=True
            ).start()

    def clientHandler(self, clientSocket, clientAddr):
        self.clientAddr = clientAddr[0]
        self.clientInfo['rtspSocket'] = clientSocket

        while True:
            try:
                data = clientSocket.recv(1024).decode()
                if data:
                    print("\nData received:\n" + data)
                    self.processRtspRequest(data)
            except:
                break

    def processRtspRequest(self, data):
        lines = data.split('\n')
        requestType = lines[0].split(' ')[0]

        if requestType == "SETUP":
            transportLine = [line for line in lines if "Transport" in line][0]
            self.rtpPort = int(transportLine.split('client_port=')[1])

            print(f"processing SETUP, RTP port {self.rtpPort}")
            self.state = 1
            self.rtspSeq += 1

            # Load MJPEG file
            self.videoStream = VideoStream(self.videoFile)
            self.replyRtsp(200)

        elif requestType == "PLAY":
            print("processing PLAY")
            self.state = 2
            self.rtspSeq += 1
            self.replyRtsp(200)

            self.teardownEvent.clear()
            threading.Thread(target=self.sendRtp, daemon=True).start()

        elif requestType == "PAUSE":
            print("processing PAUSE")
            self.state = 1
            self.teardownEvent.set()
            self.rtspSeq += 1
            self.replyRtsp(200)

        elif requestType == "TEARDOWN":
            print("processing TEARDOWN")
            self.state = 0
            self.teardownEvent.set()
            self.rtspSeq += 1
            self.replyRtsp(200)

    def replyRtsp(self, code):
        reply = (
            f"RTSP/1.0 {code} OK\n"
            f"CSeq: {self.rtspSeq}\n"
            f"Session: {self.sessionId}\n"
        )
        self.clientInfo['rtspSocket'].send(reply.encode())

    def sendRtp(self):
        rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        print("[INFO] Starting RTP stream...")

        while self.state == 2:
            frame = self.videoStream.nextFrame()
            if not frame:
                break

            self.frameNbr = self.videoStream.frameNbr()

            rtpPacket = RtpPacket()
            rtpPacket.encode(
                2, 0, 0, 0,
                self.frameNbr,
                0,
                26,       # MJPEG payload
                0,
                frame
            )

            try:
                rtpSocket.sendto(
                    rtpPacket.getPacket(),
                    (self.clientAddr, self.rtpPort)
                )
                print(f"[INFO] Sent RTP frame #{self.frameNbr}")
            except:
                print("[ERROR] Cannot send RTP packet")
                break

            time.sleep(0.05)

            if self.teardownEvent.is_set():
                break

        rtpSocket.close()
        print("[INFO] RTP stream ended.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: Server.py Server_port")
        sys.exit(1)

    serverPort = int(sys.argv[1])
    server = Server(serverPort)
    server.main()
