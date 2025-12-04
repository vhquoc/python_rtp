import sys
import socket
import threading
import traceback
from RtpPacket import RtpPacket
from PIL import Image, ImageTk
import tkinter as tk
import io


class Client:
    INIT = 0
    READY = 1
    PLAYING = 2

    SETUP = "SETUP"
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    TEARDOWN = "TEARDOWN"

    def __init__(self, serverAddr, serverPort, rtpPort, fileName):
        self.serverAddr = serverAddr
        self.serverPort = int(serverPort)
        self.rtpPort = int(rtpPort)
        self.fileName = fileName

        # RTSP state
        self.rtspSeq = 0
        self.sessionId = 0
        self.state = self.INIT
        self.teardownAcked = False

        # RTP
        self.rtpSocket = None
        self.rtspSocket = None  

        self.root = tk.Tk()
        self.root.title("RTP Video Client")

        # Vùng video
        self.frame = tk.Frame(self.root, width=600, height=450, bg="white")
        self.frame.pack(padx=10, pady=10)

        self.display = tk.Label(self.frame, bg="white")
        self.display.place(relx=0.5, rely=0.5, anchor="center")

        # Khung nút điều khiển
        btnFrame = tk.Frame(self.root)
        btnFrame.pack(pady=10)

        tk.Button(btnFrame, width=15, text="SETUP", command=self.setupMovie).pack(side="left", padx=5)
        tk.Button(btnFrame, width=15, text="PLAY", command=self.playMovie).pack(side="left", padx=5)
        tk.Button(btnFrame, width=15, text="PAUSE", command=self.pauseMovie).pack(side="left", padx=5)
        tk.Button(btnFrame, width=15, text="TEARDOWN", command=self.exitClient).pack(side="left", padx=5)

        self.root.protocol("WM_DELETE_WINDOW", self.exitClient)
        self.root.mainloop()

    # =====================================================
    #                       RTSP
    # =====================================================
    def setupMovie(self):
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def sendRtspRequest(self, requestType):
        self.rtspSeq += 1
        request = f"{requestType} {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\n"

        if requestType == self.SETUP:
            request += f"Transport: RTP/UDP; client_port= {self.rtpPort}\n"
        else:
            request += f"Session: {self.sessionId}\n"

        print("\nRTSP Sent:\n" + request)
        self.rtspSocket = self.rtspSocket or socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if requestType == self.SETUP:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))

        self.rtspSocket.send(request.encode())
        self.recvRtspReply(requestType)

    def recvRtspReply(self, requestType):
        reply = self.rtspSocket.recv(1024).decode()
        print("\nRTSP Received:\n" + reply)

        if "Session" in reply:
            self.sessionId = int(reply.split("Session: ")[1].split("\n")[0])

        if requestType == self.SETUP and self.state == self.INIT:
            self.openRtpPort()
            self.state = self.READY

        elif requestType == self.PLAY:
            self.state = self.PLAYING

        elif requestType == self.PAUSE:
            self.state = self.READY

        elif requestType == self.TEARDOWN:
            self.teardownAcked = True
            self.rtspSocket.close()

    # =====================================================
    #                   PLAY / PAUSE
    # =====================================================
    def playMovie(self):
        if self.state == self.READY:
            self.sendRtspRequest(self.PLAY)

    def pauseMovie(self):
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    # =====================================================
    #                       EXIT
    # =====================================================
    def exitClient(self):
        if self.state != self.INIT:
            self.sendRtspRequest(self.TEARDOWN)

        self.root.destroy()
        sys.exit(0)

    # =====================================================
    #                        RTP
    # =====================================================
    def openRtpPort(self):
        print("[INFO] Opening RTP port...")
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        self.rtpSocket.bind(('', self.rtpPort))

        threading.Thread(target=self.listenRtp, daemon=True).start()

    def listenRtp(self):
        while True:
            try:
                data = self.rtpSocket.recv(65535)
                if data:
                    rtp = RtpPacket()
                    rtp.decode(data)
                    self.displayFrame(rtp.getPayload())

            except socket.timeout:
                if self.teardownAcked:
                    break
                continue
            except:
                traceback.print_exc()
                if self.teardownAcked:
                    break

    # =====================================================
    #                 HIỂN THỊ KHUNG VIDEO
    # =====================================================
    def displayFrame(self, payload):
        try:
            image = Image.open(io.BytesIO(payload))
            photo = ImageTk.PhotoImage(image)
            self.display.configure(image=photo)
            self.display.image = photo
        except:
            pass
