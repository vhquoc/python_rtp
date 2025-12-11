from random import randint
import sys, traceback, threading, socket
import math

from VideoStream import VideoStream
from RtpPacket import RtpPacket


class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'

    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    clientInfo = {}

    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        # Sequence number RTP dùng cho từng gói (packet), KHÔNG phải từng frame
        self.seqnum = 0
        # SSRC định danh nguồn phát (server). Chọn random một lần cho mỗi phiên.
        self.ssrc = randint(100000, 999999)
        # Kích thước tối đa payload cho mỗi gói RTP (bytes)
        self.maxPayloadSize = 1400

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()

    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:
            try:
                data = connSocket.recv(256)
            except:
                # Socket lỗi hoặc bị đóng
                print("RTSP socket closed or error.")
                break

            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))
            else:
                # Client đóng kết nối
                print("RTSP connection closed by client.")
                break

    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]

        # Get the media file name
        filename = line1[1]

        # Get the RTSP sequence number
        seq = request[1].split(' ')

        # Process SETUP request
        if requestType == self.SETUP:
            if self.state == self.INIT:
                # Update state
                print("processing SETUP\n")

                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                    return

                # Generate a randomized RTSP session ID
                self.clientInfo['session'] = randint(100000, 999999)

                # Send RTSP reply
                self.replyRtsp(self.OK_200, seq[1])

                # Get the RTP/UDP port from the last line
                # Ví dụ: Transport: RTP/UDP; client_port=25000
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]

        # Process PLAY request
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING

                # Create a new socket for RTP/UDP
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                self.replyRtsp(self.OK_200, seq[1])

                # Create a new thread and start sending RTP packets
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker'] = threading.Thread(target=self.sendRtp)
                self.clientInfo['worker'].start()

        # Process PAUSE request
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY

                # Dừng thread sendRtp thông qua event
                if 'event' in self.clientInfo:
                    self.clientInfo['event'].set()

                self.replyRtsp(self.OK_200, seq[1])

        # Process TEARDOWN request
        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            # Báo cho thread sendRtp dừng
            if 'event' in self.clientInfo:
                self.clientInfo['event'].set()

            self.replyRtsp(self.OK_200, seq[1])

            # Close the RTP socket
            if 'rtpSocket' in self.clientInfo:
                try:
                    self.clientInfo['rtpSocket'].close()
                except:
                    pass

            # Close RTSP TCP socket luôn cho sạch
            try:
                self.clientInfo['rtspSocket'][0].close()
            except:
                pass

    def sendRtp(self):
        """
        Send RTP packets over UDP.

        Ở đây đã hỗ trợ:
        - Đọc frame MJPEG từ VideoStream
        - Fragmentation: nếu frame > maxPayloadSize, chia thành nhiều gói RTP
        - Sequence number tăng cho mỗi gói
        - Marker bit = 1 cho gói cuối cùng của mỗi frame
        """
        while True:
            # Đợi 50ms giữa các lần gửi (tốc độ khung hình ~20 fps)
            # Hàm wait(timeout) sẽ trả về True nếu event đã set, False nếu timeout
            if self.clientInfo['event'].wait(0.05):
                # Nếu event set (PAUSE/TEARDOWN) thì dừng
                break

            data = self.clientInfo['videoStream'].nextFrame()
            if not data:
                # Hết video
                print("End of video stream.")
                break

            frameLength = len(data)
            # Tính số mảnh cần gửi cho frame này
            nFragments = max(1, math.ceil(frameLength / self.maxPayloadSize))

            try:
                address = self.clientInfo['rtspSocket'][1][0]
                port = int(self.clientInfo['rtpPort'])
            except Exception:
                print("Connection Error when resolving client address/port")
                traceback.print_exc(file=sys.stdout)
                break

            # Gửi từng fragment
            for i in range(nFragments):
                # Nếu trong lúc gửi mà PAUSE/TEARDOWN -> dừng luôn
                if self.clientInfo['event'].isSet():
                    break

                start = i * self.maxPayloadSize
                end = min(frameLength, (i + 1) * self.maxPayloadSize)
                chunk = data[start:end]

                # Sequence number tăng theo từng packet (0–65535)
                self.seqnum = (self.seqnum + 1) % 65536

                # Marker bit = 1 chỉ ở packet cuối cùng của frame
                marker = 1 if i == nFragments - 1 else 0

                packet = self.makeRtp(chunk, self.seqnum, marker)
                try:
                    self.clientInfo['rtpSocket'].sendto(packet, (address, port))
                except Exception:
                    print("Connection Error when sending RTP packet")
                    traceback.print_exc(file=sys.stdout)
                    break

    def makeRtp(self, payload, seqnum, marker):
        """RTP-packetize the video data (1 gói – có thể là 1 phần frame)."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        pt = 26  # MJPEG type
        ssrc = self.ssrc

        rtpPacket = RtpPacket()
        rtpPacket.encode(
            version, padding, extension, cc,
            seqnum, marker, pt, ssrc, payload
        )

        return rtpPacket.getPacket()

    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            # 200 OK
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())

        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")