class RtpPacket:
    HEADER_SIZE = 12

    def __init__(self):
        self.header = bytearray(self.HEADER_SIZE)
        self.payload = b""

    def encode(self, version, padding, extension, cc,
               seqnum, marker, payloadType, ssrc, payload):

        self.header = bytearray(self.HEADER_SIZE)

        # Byte 0
        self.header[0] = (version << 6) | (padding << 5) | (extension << 4) | (cc & 0x0F)

        # Byte 1: Marker + Payload Type
        self.header[1] = (marker << 7) | (payloadType & 0x7F)

        # Sequence Number
        self.header[2] = (seqnum >> 8) & 0xFF
        self.header[3] = seqnum & 0xFF

        # Timestamp
        timestamp = seqnum * 3000
        self.header[4] = (timestamp >> 24) & 0xFF
        self.header[5] = (timestamp >> 16) & 0xFF
        self.header[6] = (timestamp >> 8) & 0xFF
        self.header[7] = timestamp & 0xFF

        # SSRC
        self.header[8] = (ssrc >> 24) & 0xFF
        self.header[9] = (ssrc >> 16) & 0xFF
        self.header[10] = (ssrc >> 8) & 0xFF
        self.header[11] = ssrc & 0xFF

        self.payload = payload

    def decode(self, packet):
        self.header = packet[:self.HEADER_SIZE]
        self.payload = packet[self.HEADER_SIZE:]

    def version(self):
        return self.header[0] >> 6

    def seqNum(self):
        return (self.header[2] << 8) | self.header[3]

    def timestamp(self):
        return (
            (self.header[4] << 24) |
            (self.header[5] << 16) |
            (self.header[6] << 8) |
            self.header[7]
        )

    def payloadType(self):
        return self.header[1] & 0x7F

    def marker(self):
        """Return marker bit (bit 7 của byte 1)."""
        return (self.header[1] >> 7) & 0x01

    def getPayload(self):
        return self.payload

    def getPacket(self):
        return self.header + self.payload
