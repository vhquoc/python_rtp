import sys
import socket
import threading
import traceback
from collections import deque   # dùng cho buffer frames
from RtpPacket import RtpPacket
from PIL import Image, ImageTk
import tkinter as tk
import io


class Client:
    # Các trạng thái RTSP
    INIT = 0
    READY = 1
    PLAYING = 2

    # Các loại request RTSP
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

        # Socket
        self.rtpSocket = None
        self.rtspSocket = None

        # ====== CLIENT-SIDE CACHING ======
        # Hàng đợi chứa payload JPEG đã nhận
        self.frameBuffer = deque()
        # Lock để tránh race giữa thread nhận RTP và thread UI
        self.bufferLock = threading.Lock()
        # Số frame cần nạp trước khi bắt đầu play
        self.bufferPrefill = 40
        # Biến dùng để ghép nhiều gói RTP thành 1 frame JPEG hoàn chỉnh
        self.currentFrameBytes = bytearray()
        self.expectedSeq = None

        # Khoảng thời gian giữa hai frame khi hiển thị (ms)
        self.playIntervalMs = 50   # ~20 fps

        # ================== GUI ==================
        self.root = tk.Tk()
        self.root.title("RTP Video Client")

        # Vùng video
        self.frame = tk.Frame(self.root, width=600, height=450, bg="white")
        self.frame.pack(padx=10, pady=10)

        self.display = tk.Label(self.frame, bg="white")
        self.display.place(relx=0.5, rely=0.5, anchor="center")

        # Label hiển thị trạng thái (buffering, v.v.)
        self.statusLabel = tk.Label(self.root, text="", fg="gray")
        self.statusLabel.pack()

        # Khung nút điều khiển
        btnFrame = tk.Frame(self.root)
        btnFrame.pack(pady=10)

        tk.Button(btnFrame, width=15, text="SETUP",
                  command=self.setupMovie).pack(side="left", padx=5)
        tk.Button(btnFrame, width=15, text="PLAY",
                  command=self.playMovie).pack(side="left", padx=5)
        tk.Button(btnFrame, width=15, text="PAUSE",
                  command=self.pauseMovie).pack(side="left", padx=5)
        tk.Button(btnFrame, width=15, text="TEARDOWN",
                  command=self.exitClient).pack(side="left", padx=5)

        # Vòng lặp update frame từ buffer (chạy trên main thread Tkinter)
        self.root.after(self.playIntervalMs, self.updateFrameLoop)

        self.root.protocol("WM_DELETE_WINDOW", self.exitClient)
        self.root.mainloop()

    # =====================================================
    #                       RTSP
    # =====================================================
    def setupMovie(self):
        """Gửi request SETUP lần đầu để thiết lập session."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def sendRtspRequest(self, requestType):
        """Tạo và gửi 1 RTSP request tới server."""
        self.rtspSeq += 1
        request = f"{requestType} {self.fileName} RTSP/1.0\n"
        request += f"CSeq: {self.rtspSeq}\n"

        if requestType == self.SETUP:
            # Trong SETUP cần header Transport, chưa có Session
            request += f"Transport: RTP/UDP; client_port={self.rtpPort}\n"
        else:
            # Các request còn lại đều cần Session
            request += f"Session: {self.sessionId}\n"

        print("\nRTSP Sent:\n" + request)

        # Tạo socket RTSP nếu chưa có
        if self.rtspSocket is None:
            self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SETUP thì cần connect TCP
        if requestType == self.SETUP:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))

        # Gửi request
        self.rtspSocket.send(request.encode())

        # Nhận và xử lý reply
        self.recvRtspReply(requestType)

    def recvRtspReply(self, requestType):
        """Nhận và xử lý RTSP reply từ server."""
        reply = self.rtspSocket.recv(1024).decode()
        print("\nRTSP Received:\n" + reply)

        # Lấy Session ID (nếu có)
        if "Session" in reply:
            try:
                self.sessionId = int(reply.split("Session: ")[1].split("\n")[0])
            except:
                pass

        # Cập nhật state theo loại request
        if requestType == self.SETUP and self.state == self.INIT:
            self.openRtpPort()
            self.state = self.READY

        elif requestType == self.PLAY and self.state == self.READY:
            self.state = self.PLAYING

        elif requestType == self.PAUSE and self.state == self.PLAYING:
            self.state = self.READY

        elif requestType == self.TEARDOWN:
            self.teardownAcked = True
            try:
                self.rtspSocket.close()
            except:
                pass

    # =====================================================
    #                   PLAY / PAUSE
    # =====================================================
    def playMovie(self):
        """Gửi request PLAY."""
        if self.state == self.READY:
            self.sendRtspRequest(self.PLAY)

    def pauseMovie(self):
        """Gửi request PAUSE."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    # =====================================================
    #                       EXIT
    # =====================================================
    def exitClient(self):
        """Gửi TEARDOWN rồi thoát ứng dụng."""
        if self.state != self.INIT:
            try:
                self.sendRtspRequest(self.TEARDOWN)
            except:
                pass

        # Dọn buffer và đóng socket RTP nếu còn mở
        with self.bufferLock:
            self.frameBuffer.clear()

        if self.rtpSocket:
            try:
                self.rtpSocket.close()
            except:
                pass

        self.root.destroy()
        sys.exit(0)

    # =====================================================
    #                        RTP
    # =====================================================
    def openRtpPort(self):
        """Mở cổng UDP để nhận RTP."""
        print("[INFO] Opening RTP port...")
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        self.rtpSocket.bind(('', self.rtpPort))

        # Thread nhận RTP packet
        threading.Thread(target=self.listenRtp, daemon=True).start()


    def listenRtp(self):
        """Lắng nghe gói RTP, ghép các mảnh lại thành 1 frame rồi mới đẩy vào buffer."""
        while True:
            try:
                data = self.rtpSocket.recv(65535)
                if data:
                    rtp = RtpPacket()
                    rtp.decode(data)
                    payload = rtp.getPayload()

                    seq = rtp.seqNum()
                    marker = rtp.marker()

                    # Nếu là packet đầu tiên hoặc bị nhảy số thứ tự -> reset ghép frame
                    if self.expectedSeq is None or seq != self.expectedSeq:
                        self.currentFrameBytes = bytearray()

                    # Ghép payload của packet hiện tại vào frame đang xây dựng
                    self.currentFrameBytes.extend(payload)

                    # Cập nhật sequence mong đợi tiếp theo (mod 65536)
                    self.expectedSeq = (seq + 1) & 0xFFFF

                    # Nếu marker = 1 -> đây là mảnh cuối cùng của frame
                    if marker == 1:
                        full_frame = bytes(self.currentFrameBytes)
                        with self.bufferLock:
                            self.frameBuffer.append(full_frame)

                        # Reset cho frame kế tiếp
                        self.currentFrameBytes = bytearray()

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
        """Giải mã JPEG và hiển thị lên Label Tkinter."""
        try:
            image = Image.open(io.BytesIO(payload))
            photo = ImageTk.PhotoImage(image)
            self.display.configure(image=photo)
            self.display.image = photo
        except:
            # Nếu frame lỗi thì bỏ qua
            pass

    def updateFrameLoop(self):
        """
        Hàm này chạy trên main thread Tkinter (dùng after),
        mỗi 50ms sẽ cố lấy 1 frame từ buffer để hiển thị.
        """
        if self.state == self.PLAYING:
            # Kiểm tra độ dài buffer
            with self.bufferLock:
                buf_len = len(self.frameBuffer)

            if buf_len < self.bufferPrefill:
                # Chưa đủ frame để play -> hiện trạng thái buffering
                self.statusLabel.config(
                    text=f"Buffering... ({buf_len}/{self.bufferPrefill})"
                )
            else:
                # Đã đủ frame -> play bình thường
                self.statusLabel.config(text="")
                with self.bufferLock:
                    payload = self.frameBuffer.popleft()
                self.displayFrame(payload)
        else:
            # Không ở trạng thái PLAYING (INIT / READY / PAUSE)
            self.statusLabel.config(text="")

        # Đăng ký gọi lại sau playIntervalMs
        self.root.after(self.playIntervalMs, self.updateFrameLoop)
