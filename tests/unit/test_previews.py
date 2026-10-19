import struct
import unittest

from app import previews


def bif(frames, every_ms=9610):
    """A Roku BIF file with these JPEG payloads, one every every_ms."""
    header = previews.MAGIC + struct.pack("<III", 0, len(frames), 1) + b"\0" * 44
    offset = 64 + 8 * (len(frames) + 1)
    index, body = b"", b""
    for i, f in enumerate(frames):
        index += struct.pack("<II", i * every_ms, offset + len(body))
        body += f
    index += struct.pack("<II", 0xFFFFFFFF, offset + len(body))
    return header + index + body


class PreviewTests(unittest.TestCase):
    def test_frames_and_times_from_a_bif_file(self):
        data = bif([b"\xff\xd8one", b"\xff\xd8two", b"\xff\xd8three"])
        frames = previews.parse(data)
        self.assertEqual([f[0] for f in frames], [0.0, 9.61, 19.22])
        self.assertEqual(data[frames[1][1]:frames[1][2]], b"\xff\xd8two")

    def test_not_a_bif_file(self):
        with self.assertRaises(ValueError):
            previews.parse(b"<html>nope</html>" * 10)


if __name__ == "__main__":
    unittest.main()
