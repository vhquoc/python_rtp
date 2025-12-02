class VideoStream:
    def __init__(self, filename):
        self.file = open(filename, "rb")
        self.data = self.file.read()
        self.pointer = 0
        self.frameNum = 0

    def nextFrame(self):
        SOI = b"\xff\xd8"  # Start Of Image
        EOI = b"\xff\xd9"  # End Of Image

        start = self.data.find(SOI, self.pointer)
        if start == -1:
            return b''

        end = self.data.find(EOI, start)
        if end == -1:
            return b''

        end += 2  # include EOI bytes

        frame = self.data[start:end]
        self.pointer = end
        self.frameNum += 1
        return frame

    def frameNbr(self):
        return self.frameNum
