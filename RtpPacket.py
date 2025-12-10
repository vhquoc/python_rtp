class RtpPacket:
    HEADER_SIZE = 12  # Fixed RTP header size

    def __init__(self):
        self.header = bytearray(self.HEADER_SIZE)
        self.payload = b""

    def encode(self, version, padding, extension, cc,
               seqnum, marker, payloadType, ssrc, payload):
        """
        Encode RTP Header + Payload according to RTP format:

         0                   1                   2                   3
         0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |V=2|P|X|  CC   |M|     PT      |       Sequence Number         |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |                           Timestamp                           |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |           SSRC (synchronization source identifier)            |
        +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        |                           Payload ...                         |
        """

        self.header = bytearray(self.HEADER_SIZE)

        # -------------------------
        # Byte 0: V(2) | P(1) | X(1) | CC(4)
        # -------------------------
        self.header[0] = (
            (version << 6) |      # Version, always 2
            (padding << 5) |      # Padding (=0)
            (extension << 4) |    # Extension (=0)
            (cc & 0x0F)           # CSRC count (=0)
        )

        # -------------------------
        # Byte 1: Marker bit + Payload Type
        # Marker = 1 nếu là mảnh cuối của frame
        # PT = 26 cho MJPEG
        # -------------------------
        self.header[1] = (
            (marker << 7) |         # Marker bit (1 = end of frame)
            (payloadType & 0x7F)    # Payload Type
        )

        # -------------------------
        # Sequence Number: 16-bit
        # -------------------------
        self.header[2] = (seqnum >> 8) & 0xFF
        self.header[3] = seqnum & 0xFF

        # -------------------------
        # Timestamp: theo lab dùng seqnum * 3000
        # (Không cần real-time timestamp)
        # -------------------------
        timestamp = seqnum * 3000
        self.header[4] = (timestamp >> 24) & 0xFF
        self.header[5] = (timestamp >> 16) & 0xFF
        self.header[6] = (timestamp >> 8) & 0xFF
        self.header[7] = timestamp & 0xFF

        # -------------------------
        # SSRC: 32-bit ID của server
        # -------------------------
        self.header[8] = (ssrc >> 24) & 0xFF
        self.header[9] = (ssrc >> 16) & 0xFF
        self.header[10] = (ssrc >> 8) & 0xFF
        self.header[11] = ssrc & 0xFF

        # -------------------------
        # Payload (JPEG frame hoặc mảnh)
        # -------------------------
        self.payload = payload

    # ==========================================================
    # Decode / Getter Functions
    # ==========================================================

    def decode(self, packet):
        """Split packet into header + payload."""
        self.header = packet[:self.HEADER_SIZE]
        self.payload = packet[self.HEADER_SIZE:]

    def version(self):
        """Extract RTP version."""
        return self.header[0] >> 6

    def seqNum(self):
        """Extract sequence number."""
        return (self.header[2] << 8) | self.header[3]

    def timestamp(self):
        """Extract timestamp."""
        return (
            (self.header[4] << 24) |
            (self.header[5] << 16) |
            (self.header[6] << 8) |
            self.header[7]
        )

    def payloadType(self):
        """Extract payload type."""
        return self.header[1] & 0x7F

    def marker(self):
        """Return marker bit (bit 7 của byte 1)."""
        return (self.header[1] >> 7) & 0x01

    def getPayload(self):
        """Return payload data (JPEG bytes)."""
        return self.payload

    def getPacket(self):
        """Return complete RTP packet: header + payload."""
        return self.header + self.payload