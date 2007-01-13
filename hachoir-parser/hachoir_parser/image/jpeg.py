"""
JPEG picture parser.

Author: Victor Stinner
"""

from hachoir_core.error import HachoirError
from hachoir_parser import Parser
from hachoir_core.field import (FieldSet, ParserError,
    UInt8, UInt16, Enum, Bits,
    String, RawBytes)
from hachoir_parser.image.common import PaletteRGB
from hachoir_core.endian import BIG_ENDIAN
from hachoir_core.text_handler import hexadecimal
from hachoir_parser.image.exif import Exif
from hachoir_parser.image.photoshop_metadata import PhotoshopMetadata
from hachoir_core.error import warning

# The four tables (hash/sum for color/grayscale JPEG) comes
# from ImageMagick project
QUALITY_HASH_COLOR = (
    1020, 1015,  932,  848,  780,  735,  702,  679,  660,  645,
     632,  623,  613,  607,  600,  594,  589,  585,  581,  571,
     555,  542,  529,  514,  494,  474,  457,  439,  424,  410,
     397,  386,  373,  364,  351,  341,  334,  324,  317,  309,
     299,  294,  287,  279,  274,  267,  262,  257,  251,  247,
     243,  237,  232,  227,  222,  217,  213,  207,  202,  198,
     192,  188,  183,  177,  173,  168,  163,  157,  153,  148,
     143,  139,  132,  128,  125,  119,  115,  108,  104,   99,
      94,   90,   84,   79,   74,   70,   64,   59,   55,   49,
      45,   40,   34,   30,   25,   20,   15,   11,    6,    4,
       0)

QUALITY_SUM_COLOR = (
    32640,32635,32266,31495,30665,29804,29146,28599,28104,27670,
    27225,26725,26210,25716,25240,24789,24373,23946,23572,22846,
    21801,20842,19949,19121,18386,17651,16998,16349,15800,15247,
    14783,14321,13859,13535,13081,12702,12423,12056,11779,11513,
    11135,10955,10676,10392,10208, 9928, 9747, 9564, 9369, 9193,
     9017, 8822, 8639, 8458, 8270, 8084, 7896, 7710, 7527, 7347,
     7156, 6977, 6788, 6607, 6422, 6236, 6054, 5867, 5684, 5495,
     5305, 5128, 4945, 4751, 4638, 4442, 4248, 4065, 3888, 3698,
     3509, 3326, 3139, 2957, 2775, 2586, 2405, 2216, 2037, 1846,
     1666, 1483, 1297, 1109,  927,  735,  554,  375,  201,  128,
        0)

QUALITY_HASH_GRAY = (
    510,  505,  422,  380,  355,  338,  326,  318,  311,  305,
    300,  297,  293,  291,  288,  286,  284,  283,  281,  280,
    279,  278,  277,  273,  262,  251,  243,  233,  225,  218,
    211,  205,  198,  193,  186,  181,  177,  172,  168,  164,
    158,  156,  152,  148,  145,  142,  139,  136,  133,  131,
    129,  126,  123,  120,  118,  115,  113,  110,  107,  105,
    102,  100,   97,   94,   92,   89,   87,   83,   81,   79,
     76,   74,   70,   68,   66,   63,   61,   57,   55,   52,
     50,   48,   44,   42,   39,   37,   34,   31,   29,   26,
     24,   21,   18,   16,   13,   11,    8,    6,    3,    2,
      0)

QUALITY_SUM_GRAY = (
    16320,16315,15946,15277,14655,14073,13623,13230,12859,12560,
    12240,11861,11456,11081,10714,10360,10027, 9679, 9368, 9056,
     8680, 8331, 7995, 7668, 7376, 7084, 6823, 6562, 6345, 6125,
     5939, 5756, 5571, 5421, 5240, 5086, 4976, 4829, 4719, 4616,
     4463, 4393, 4280, 4166, 4092, 3980, 3909, 3835, 3755, 3688,
     3621, 3541, 3467, 3396, 3323, 3247, 3170, 3096, 3021, 2952,
     2874, 2804, 2727, 2657, 2583, 2509, 2437, 2362, 2290, 2211,
     2136, 2068, 1996, 1915, 1858, 1773, 1692, 1620, 1552, 1477,
     1398, 1326, 1251, 1179, 1109, 1031,  961,  884,  814,  736,
      667,  592,  518,  441,  369,  292,  221,  151,   86,   64,
        0)

JPEG_NATURAL_ORDER = (
     0,  1,  8, 16,  9,  2,  3, 10,
    17, 24, 32, 25, 18, 11,  4,  5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13,  6,  7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63)

class JpegChunkApp0(FieldSet):
    unit_name = {
        0: "pixels",
        1: "dots per inch",
        2: "dots per cm"
    }

    def createFields(self):
        yield String(self, "jfif", 5, "JFIF string", charset="ASCII")
        if self["jfif"].value != "JFIF\0":
            raise ParserError(
                "Stream doesn't look like JPEG chunk (wrong JFIF signature)")
        yield UInt8(self, "ver_maj", "Major version")
        yield UInt8(self, "ver_min", "Minor version")
        yield Enum(UInt8(self, "units", "Units"), self.unit_name)
        if self["units"].value == 0:
            yield UInt16(self, "aspect_x", "Aspect ratio (X)")
            yield UInt16(self, "aspect_y", "Aspect ratio (Y)")
        else:
            yield UInt16(self, "x_density", "X density")
            yield UInt16(self, "y_density", "Y density")
        yield UInt8(self, "thumb_w", "Thumbnail width")
        yield UInt8(self, "thumb_h", "Thumbnail height")
        thumb_size = self["thumb_w"].value * self["thumb_h"].value
        if thumb_size != 0:
            yield PaletteRGB(self, "thumb_palette", 256)
            yield RawBytes(self, "thumb_data", thumb_size, "Thumbnail data")

class StartOfFrame(FieldSet):
    def createFields(self):
        yield UInt8(self, "precision")
        if self["precision"].value != 8:
            raise ParserError("JPEG error: Only 8-bit precision is supported")

        yield UInt16(self, "height")
        yield UInt16(self, "width")
        yield UInt8(self, "nr_components")
        if self["nr_components"].value not in (1, 3):
            raise ParserError("JPEG error: Only gray or true-color JPGS supported")

        for index in range(self["nr_components"].value):
            yield UInt8(self, "component_id[]")
            yield UInt8(self, "high[]")
            yield UInt8(self, "low[]")

class StartOfScan(FieldSet):
    def createFields(self):
        yield UInt8(self, "nr_components")
        if self["nr_components"].value not in (1, 3):
            raise ParserError("JPEG error: Invalid SOS marker")

        for index in range(self["nr_components"].value):
            comp_id = UInt8(self, "component_id[]")
            if (comp_id.value == 0) or (self["nr_components"].value < comp_id.value):
               raise ParserError("JPEG error: Invalid component-id")
            yield comp_id
            yield UInt8(self, "value[]")
        yield RawBytes(self, "raw", 3) # TODO: What's this???

class RestartInterval(FieldSet):
    def createFields(self):
        yield UInt16(self, "interval", "Restart inteval")

class QuantizationTable(FieldSet):
    def createFields(self):
        # Code based on function get_dqt() (jdmarker.c from libjpeg62)
        yield Bits(self, "is_16bit", 4)
        yield Bits(self, "index", 4)
        if self["index"].value >= 4:
            warning("Invalid quantification index (%s)" % self["index"].value)
        if self["is_16bit"].value:
            coeff_type = UInt16
        else:
            coeff_type = UInt8
        for index in xrange(64):
            natural = JPEG_NATURAL_ORDER[index]
            yield coeff_type(self, "coeff[%u]" % natural)

    def createDescription(self):
        return "Quantification table #%u" % self["index"].value

class DefineQuantizationTable(FieldSet):
    def createFields(self):
        while self.current_size < self.size:
            yield QuantizationTable(self, "qt[]")

class JpegChunk(FieldSet):
    TAG_SOI = 0xD8
    TAG_EOI = 0xD9
    TAG_SOS = 0xDA
    TAG_DQT = 0xDB
    TAG_DRI = 0xDD
    type_description = {
        0xC0: "Start Of Frame 0 (SOF0)",
        0xC4: "Define Huffman Table (DHT)",
        TAG_SOI: "Start of image (SOI)",
        TAG_EOI: "End of image (EOI)",
        TAG_SOS: "Start Of Scan (SOS)",
        TAG_DQT: "Define Quantization Table (DQT)",
        0xDC: "Define number of Lines (DNL)",
        0xDD: "Define Restart Interval (DRI)",
        0xE0: "APP0",
        0xED: "Photoshop marker",
        0xFE: "Comment"
    }
    type_name = {
        0xC0: "sof",
        0xC4: "dht[]",
        TAG_SOI: "soi",
        TAG_EOI: "eoi",
        TAG_SOS: "sos",
        TAG_DQT: "dqt[]",
        0xDC: "dnl[]",
        TAG_DRI: "dri[]",
        0xE0: "app0",
        0xED: "psd",
        0xFE: "comment[]"
    }
    handler = {
        0xE0: JpegChunkApp0,
        0xC0: StartOfFrame,
        TAG_SOS: StartOfScan,
        TAG_DRI: RestartInterval,
        TAG_DQT: DefineQuantizationTable,
        0xED: PhotoshopMetadata
    }

    def __init__(self, parent, name, description=None):
        FieldSet.__init__(self, parent, name, description)
        tag = self["type"].value
        if tag in self.type_name:
            self._name = self.type_name[tag]
        elif tag == 0xE1:
            bytes = self.stream.readBytes(self.absolute_address + 32, 6)
            if bytes == "Exif\0\0":
                self._name = "exif"
                self._description = "EXIF"
#            else:
#                self._name = "adobe_metadata"
#                self._description = "Adobe Metadata XML"

    def createFields(self):
        yield UInt8(self, "header", "Header", text_handler=hexadecimal)
        if self["header"].value != 0xFF:
            raise ParserError("JPEG: Invalid chunk header!")
        yield Enum(UInt8(self, "type", "Type", text_handler=hexadecimal), self.type_description)
        tag = self["type"].value
        if tag in (self.TAG_SOI, self.TAG_EOI):
            return
        yield UInt16(self, "size", "Size")
        size = (self["size"].value - 2)
        if 0 < size:
            if tag in JpegChunk.handler:
                handler = JpegChunk.handler[tag]
            elif self._name == "exif":
                handler = Exif
            else:
                handler = None
            if handler:
                yield handler(self, "content", "Chunk content", size=size*8)
            else:
                yield RawBytes(self, "data", size, "Data")

    def createDescription(self):
        return "Chunk: %s" % self["type"].display

class JpegFile(Parser):
    endian = BIG_ENDIAN
    tags = {
        "file_ext": ("jpg", "jpeg"),
        "mime": ["image/jpeg"],
        "magic": (
            ("\xFF\xD8\xFF\xE0", 0),   # (Start Of Image, APP0)
            ("\xFF\xD8\xFF\xE1", 0),   # (Start Of Image, EXIF)
        ),
        "min_size": 22*8,
        "description": "JPEG picture"
    }

    def validate(self):
        if self.stream.readBytes(0, 2) != "\xFF\xD8":
            return "Invalid file signature"
        try:
            self.readFirstFields(3)
        except HachoirError:
            return "Unable to parse at least three chunks"
        return True

    def createFields(self):
        while not self.eof:
            chunk = JpegChunk(self, "chunk[]")
            yield chunk
            if chunk["type"].value == JpegChunk.TAG_SOS:
                # TODO: Read JPEG image data...
                break

        # TODO: is it possible to handle piped input?
        if self._size is None:
            raise NotImplementedError

        size = (self._size - self.current_size) // 8
        if size:
            yield RawBytes(self, "data", size, "JPEG data")

    def createDescription(self):
        desc = "JPEG picture"
        if "sof/content" in self:
            header = self["sof/content"]
            desc += ": %ux%u pixels" % (header["width"].value, header["height"].value)
        return desc

    def createContentSize(self):
        if "end" in self:
            return self["end"].absolute_address + self["end"].size
        if "data" not in self:
            return None
        start = self["data"].absolute_address
        end = self.stream.searchBytes("\xff\xd9", start)
        if end is not None:
            return end + 16
        return None
