"""
Apple Quicktime Movie (file extension ".mov") parser.

Documents:
- Parsing and Writing QuickTime Files in Java (by Chris Adamson, 02/19/2003)
  http://www.onjava.com/pub/a/onjava/2003/02/19/qt_file_format.html
- QuickTime File Format (official technical reference)
  http://developer.apple.com/documentation/QuickTime/QTFF/qtff.pdf
- Apple QuickTime:
  http://wiki.multimedia.cx/index.php?title=Apple_QuickTime
- File type (ftyp):
  http://www.ftyps.com/
- MPEG4 standard
  http://neuron2.net/library/avc/c041828_ISO_IEC_14496-12_2005%28E%29.pdf

Author: Victor Stinner, Robert Xiao
Creation: 2 august 2006
"""

from hachoir.parser import Parser
from hachoir.parser.common.win32 import GUID
from hachoir.field import (ParserError, FieldSet, MissingField,
                           Enum,
                           Bit, NullBits, Bits, UInt8, Int16, UInt16, Int32, UInt32, Int64, UInt64, TimestampMac32,
                           String, PascalString8, PascalString16, CString,
                           RawBytes, NullBytes, PaddingBits)
from hachoir.field.timestamp import timestampFactory
from hachoir.core.endian import BIG_ENDIAN
from hachoir.core.text_handler import textHandler
from hachoir.core.log import log as hachoir_log
from hachoir.core.tools import MAC_TIMESTAMP_T0, timedelta


def timestampMac64(value):
    if not isinstance(value, (float, int)):
        raise TypeError("an integer or float is required")
    return MAC_TIMESTAMP_T0 + timedelta(seconds=value)


TimestampMac64 = timestampFactory("TimestampMac64", timestampMac64, 64)


def fixedFloatFactory(name, int_bits, float_bits, doc):
    size = int_bits + float_bits

    class Float(FieldSet):
        static_size = size
        __doc__ = doc

        def createFields(self):
            yield Bits(self, "int_part", int_bits)
            yield Bits(self, "float_part", float_bits)

        def createValue(self):
            return self["int_part"].value + float(self["float_part"].value) / (1 << float_bits)
    klass = Float
    klass.__name__ = name
    return klass


QTFloat16 = fixedFloatFactory("QTFloat32", 8, 8, "8.8 fixed point number")
QTFloat32 = fixedFloatFactory("QTFloat32", 16, 16, "16.16 fixed point number")
QTFloat2_30 = fixedFloatFactory(
    "QTFloat2_30", 2, 30, "2.30 fixed point number")


class AtomList(FieldSet):

    def createFields(self):
        while not self.eof:
            yield Atom(self, "atom[]")


class TrackHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version (0 or 1)")
        yield NullBits(self, "flags", 20)
        yield Bit(self, "is_in_poster")
        yield Bit(self, "is_in_preview", "Is this track used when previewing the presentation?")
        yield Bit(self, "is_in_movie", "Is this track used in the presentation?")
        yield Bit(self, "is_enabled", "Is this track enabled?")

        if self['version'].value == 0:
            # 32-bit version
            yield TimestampMac32(self, "creation_date", "Creation time of this track")
            yield TimestampMac32(self, "lastmod_date", "Last modification time of this track")
            yield UInt32(self, "track_id", "Unique nonzero identifier of this track within the presentation")
            yield NullBytes(self, "reserved[]", 4)
            yield UInt32(self, "duration", "Length of track, in movie time-units")
        elif self['version'].value == 1:
            # 64-bit version
            yield TimestampMac64(self, "creation_date", "Creation time of this track")
            yield TimestampMac64(self, "lastmod_date", "Last modification time of this track")
            yield UInt32(self, "track_id", "Unique nonzero identifier of this track within the presentation")
            yield NullBytes(self, "reserved[]", 4)
            yield UInt64(self, "duration", "Length of track, in movie time-units")
        yield NullBytes(self, "reserved[]", 8)
        yield Int16(self, "video_layer", "Middle layer is 0; lower numbers are closer to the viewer")
        yield Int16(self, "alternate_group", "Group ID that this track belongs to (0=no group)")
        yield QTFloat16(self, "volume", "Track relative audio volume (1.0 = full)")
        yield NullBytes(self, "reserved[]", 2)
        yield QTFloat32(self, "geom_a", "Width scale")
        yield QTFloat32(self, "geom_b", "Width rotate")
        yield QTFloat2_30(self, "geom_u", "Width angle")
        yield QTFloat32(self, "geom_c", "Height rotate")
        yield QTFloat32(self, "geom_d", "Height scale")
        yield QTFloat2_30(self, "geom_v", "Height angle")
        yield QTFloat32(self, "geom_x", "Position X")
        yield QTFloat32(self, "geom_y", "Position Y")
        yield QTFloat2_30(self, "geom_w", "Divider scale")
        yield QTFloat32(self, "frame_size_width")
        yield QTFloat32(self, "frame_size_height")


class TrackReferenceType(FieldSet):

    def createFields(self):
        while not self.eof:
            yield UInt32(self, "track_id[]", "Referenced track ID")


class Handler(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield String(self, "creator", 4)
        yield String(self, "subtype", 4)
        yield String(self, "manufacturer", 4)
        yield UInt32(self, "res_flags")
        yield UInt32(self, "res_flags_mask")
        if self.root.is_mpeg4:
            yield CString(self, "name", charset="UTF-8")
        else:
            yield PascalString8(self, "name")


class LanguageCode(FieldSet):
    static_size = 16
    MAC_LANG = {
        0: 'English',
        1: 'French',
        2: 'German',
        3: 'Italian',
        4: 'Dutch',
        5: 'Swedish',
        6: 'Spanish',
        7: 'Danish',
        8: 'Portuguese',
        9: 'Norwegian',
        10: 'Hebrew',
        11: 'Japanese',
        12: 'Arabic',
        13: 'Finnish',
        14: 'Greek',
        15: 'Icelandic',
        16: 'Maltese',
        17: 'Turkish',
        18: 'Croatian',
        19: 'Traditional Chinese',
        20: 'Urdu',
        21: 'Hindi',
        22: 'Thai',
        23: 'Korean',
        24: 'Lithuanian',
        25: 'Polish',
        26: 'Hungarian',
        27: 'Estonian',
        28: 'Latvian',
        29: 'Lappish',
        30: 'Faeroese',
        31: 'Farsi',
        32: 'Russian',
        33: 'Simplified Chinese',
        34: 'Flemish',
        35: 'Irish',
        36: 'Albanian',
        37: 'Romanian',
        38: 'Czech',
        39: 'Slovak',
        40: 'Slovenian',
        41: 'Yiddish',
        42: 'Serbian',
        43: 'Macedonian',
        44: 'Bulgarian',
        45: 'Ukrainian',
        46: 'Byelorussian',
        47: 'Uzbek',
        48: 'Kazakh',
        49: 'Azerbaijani',
        50: 'AzerbaijanAr',
        51: 'Armenian',
        52: 'Georgian',
        53: 'Moldavian',
        54: 'Kirghiz',
        55: 'Tajiki',
        56: 'Turkmen',
        57: 'Mongolian',
        58: 'MongolianCyr',
        59: 'Pashto',
        60: 'Kurdish',
        61: 'Kashmiri',
        62: 'Sindhi',
        63: 'Tibetan',
        64: 'Nepali',
        65: 'Sanskrit',
        66: 'Marathi',
        67: 'Bengali',
        68: 'Assamese',
        69: 'Gujarati',
        70: 'Punjabi',
        71: 'Oriya',
        72: 'Malayalam',
        73: 'Kannada',
        74: 'Tamil',
        75: 'Telugu',
        76: 'Sinhalese',
        77: 'Burmese',
        78: 'Khmer',
        79: 'Lao',
        80: 'Vietnamese',
        81: 'Indonesian',
        82: 'Tagalog',
        83: 'MalayRoman',
        84: 'MalayArabic',
        85: 'Amharic',
        86: 'Tigrinya',
        88: 'Somali',
        89: 'Swahili',
        90: 'Ruanda',
        91: 'Rundi',
        92: 'Chewa',
        93: 'Malagasy',
        94: 'Esperanto',
        128: 'Welsh',
        129: 'Basque',
        130: 'Catalan',
        131: 'Latin',
        132: 'Quechua',
        133: 'Guarani',
        134: 'Aymara',
        135: 'Tatar',
        136: 'Uighur',
        137: 'Dzongkha',
        138: 'JavaneseRom',
    }

    def fieldHandler(self, field):
        if field.value == 0:
            return ' '
        return chr(field.value + 0x60)

    def createFields(self):
        value = self.stream.readBits(self.absolute_address, 16, self.endian)
        if value < 1024:
            yield Enum(UInt16(self, "lang"), self.MAC_LANG)
        else:
            yield NullBits(self, "padding[]", 1)
            yield textHandler(Bits(self, "lang[0]", 5), self.fieldHandler)
            yield textHandler(Bits(self, "lang[1]", 5), self.fieldHandler)
            yield textHandler(Bits(self, "lang[2]", 5), self.fieldHandler)

    def createValue(self):
        if 'lang' in self:
            return self['lang'].display
        return self['lang[0]'].display + self['lang[1]'].display + self['lang[2]'].display


class MediaHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version (0 or 1)")
        yield NullBits(self, "flags", 24)
        if self['version'].value == 0:
            # 32-bit version
            yield TimestampMac32(self, "creation_date", "Creation time of this media")
            yield TimestampMac32(self, "lastmod_date", "Last modification time of this media")
            yield UInt32(self, "time_scale", "Number of time-units per second")
            yield UInt32(self, "duration", "Length of media, in time-units")
        elif self['version'].value == 1:
            # 64-bit version
            yield TimestampMac64(self, "creation_date", "Creation time of this media")
            yield TimestampMac64(self, "lastmod_date", "Last modification time of this media")
            yield UInt32(self, "time_scale", "Number of time-units per second")
            yield UInt64(self, "duration", "Length of media, in time-units")
        yield LanguageCode(self, "language")
        yield Int16(self, "quality")


class VideoMediaHeader(FieldSet):
    GRAPHICSMODE = {
        0: ('Copy', "Copy the source image over the destination"),
        0x20: ('Blend', "Blend of source and destination; blending factor is controlled by op color"),
        0x24: ('Transparent', "Replace destination pixel with source pixel if the source pixel is not the op color"),
        0x40: ('Dither copy', "Dither image if necessary, else copy"),
        0x100: ('Straight alpha', "Blend of source and destination; blending factor is controlled by alpha channel"),
        0x101: ('Premul white alpha', "Remove white from each pixel and blend"),
        0x102: ('Premul black alpha', "Remove black from each pixel and blend"),
        0x103: ('Composition', "Track drawn offscreen and dither copied onto screen"),
        0x104: ('Straight alpha blend', "Blend of source and destination; blending factor is controlled by combining alpha channel and op color")
    }

    def graphicsDisplay(self, field):
        if field.value in self.GRAPHICSMODE:
            return self.GRAPHICSMODE[field.value][0]
        return hex(field.value)

    def graphicsDescription(self, field):
        if field.value in self.GRAPHICSMODE:
            return self.GRAPHICSMODE[field.value][1]
        return ""

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield Bits(self, "flags", 24, "Flags (=1)")
        graphics = UInt16(self, "graphicsmode")
        graphics.createDisplay = lambda: self.graphicsDisplay(graphics)
        graphics.createDescription = lambda: self.graphicsDescription(graphics)
        yield graphics
        yield UInt16(self, "op_red", "Red value for graphics mode")
        yield UInt16(self, "op_green", "Green value for graphics mode")
        yield UInt16(self, "op_blue", "Blue value for graphics mode")


class SoundMediaHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield QTFloat16(self, "balance")
        yield UInt16(self, "reserved[]")


class HintMediaHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield UInt16(self, "max_pdu_size")
        yield UInt16(self, "avg_pdu_size")
        yield UInt32(self, "max_bit_rate")
        yield UInt32(self, "avg_bit_rate")
        yield UInt32(self, "reserved[]")


class DataEntryUrl(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 23)
        yield Bit(self, "is_same_file", "Is the reference to this file?")
        if not self['is_same_file'].value:
            yield CString(self, "location")


class DataEntryUrn(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 23)
        yield Bit(self, "is_same_file", "Is the reference to this file?")
        if not self['is_same_file'].value:
            yield CString(self, "name")
            yield CString(self, "location")


class DataReference(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count")
        for i in range(self['count'].value):
            yield Atom(self, "atom[]")


class EditList(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version (0 or 1)")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count")
        version = self['version'].value
        if version == 0:
            UInt, Int = UInt32, Int32
        elif version == 1:
            UInt, Int = UInt64, Int64
        else:
            raise ParserError("elst version %d not supported" % version)
        for i in range(self['count'].value):
            yield UInt(self, "duration[]", "Duration of this edit segment")
            yield Int(self, "time[]", "Starting time of this edit segment within the media (-1 = empty edit)")
            yield QTFloat32(self, "play_speed[]", "Playback rate (0 = dwell edit, 1 = normal playback)")


class Load(FieldSet):

    def createFields(self):
        yield UInt32(self, "start")
        yield UInt32(self, "length")
        # PreloadAlways = 1 or TrackEnabledPreload = 2
        yield UInt32(self, "flags")
        # KeepInBuffer = 0x00000004; HighQuality = 0x00000100; SingleFieldVideo = 0x00100000
        yield UInt32(self, "hints")


class MovieHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version (0 or 1)")
        yield NullBits(self, "flags", 24)
        if self['version'].value == 0:
            # 32-bit version
            yield TimestampMac32(self, "creation_date", "Creation time of this presentation")
            yield TimestampMac32(self, "lastmod_date", "Last modification time of this presentation")
            yield UInt32(self, "time_scale", "Number of time-units per second")
            yield UInt32(self, "duration", "Length of presentation, in time-units")
        elif self['version'].value == 1:
            # 64-bit version
            yield TimestampMac64(self, "creation_date", "Creation time of this presentation")
            yield TimestampMac64(self, "lastmod_date", "Last modification time of this presentation")
            yield UInt32(self, "time_scale", "Number of time-units per second")
            yield UInt64(self, "duration", "Length of presentation, in time-units")
        yield QTFloat32(self, "play_speed", "Preferred playback speed (1.0 = normal)")
        yield QTFloat16(self, "volume", "Preferred playback volume (1.0 = full)")
        yield NullBytes(self, "reserved[]", 10)
        yield QTFloat32(self, "geom_a", "Width scale")
        yield QTFloat32(self, "geom_b", "Width rotate")
        yield QTFloat2_30(self, "geom_u", "Width angle")
        yield QTFloat32(self, "geom_c", "Height rotate")
        yield QTFloat32(self, "geom_d", "Height scale")
        yield QTFloat2_30(self, "geom_v", "Height angle")
        yield QTFloat32(self, "geom_x", "Position X")
        yield QTFloat32(self, "geom_y", "Position Y")
        yield QTFloat2_30(self, "geom_w", "Divider scale")
        yield UInt32(self, "preview_start")
        yield UInt32(self, "preview_length")
        yield UInt32(self, "still_poster")
        yield UInt32(self, "sel_start")
        yield UInt32(self, "sel_length")
        yield UInt32(self, "current_time")
        yield UInt32(self, "next_track_ID", "Value to use as the track ID for the next track added")


class FileType(FieldSet):

    def createFields(self):
        yield String(self, "brand", 4, "Major brand")
        yield UInt32(self, "version", "Version")
        while not self.eof:
            yield String(self, "compat_brand[]", 4, "Compatible brand")


class SegmentType(FieldSet):

    def createFields(self):
        yield String(self, "brand", 4, "Major brand")
        yield UInt32(self, "version", "Version")
        while not self.eof:
            yield String(self, "compat_brand[]", 4, "Compatible brand")


class MovieFragmentHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "sequence_number")


class TrackFragmentRandomAccess(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "track_id")
        yield NullBits(self, "reserved", 26)
        yield Bits(self, "length_size_of_traf_num", 2)
        yield Bits(self, "length_size_of_trun_num", 2)
        yield Bits(self, "length_size_of_sample_num", 2)
        yield UInt32(self, "number_of_entry")
        for i in range(self['number_of_entry'].value):
            if self['version'].value == 1:
                yield UInt64(self, "time[%i]" % i)
                yield UInt64(self, "moof_offset[%i]" % i)
            else:
                yield UInt32(self, "time[%i]" % i)
                yield UInt32(self, "moof_offset[%i]" % i)

            if self['length_size_of_traf_num'].value == 3:
                yield UInt64(self, "traf_number[%i]" % i)
            elif self['length_size_of_traf_num'].value == 2:
                yield UInt32(self, "traf_number[%i]" % i)
            elif self['length_size_of_traf_num'].value == 1:
                yield UInt16(self, "traf_number[%i]" % i)
            else:
                yield UInt8(self, "traf_number[%i]" % i)

            if self['length_size_of_trun_num'].value == 3:
                yield UInt64(self, "trun_number[%i]" % i)
            elif self['length_size_of_trun_num'].value == 2:
                yield UInt32(self, "trun_number[%i]" % i)
            elif self['length_size_of_trun_num'].value == 1:
                yield UInt16(self, "trun_number[%i]" % i)
            else:
                yield UInt8(self, "trun_number[%i]" % i)

            if self['length_size_of_sample_num'].value == 3:
                yield UInt64(self, "sample_number[%i]" % i)
            elif self['length_size_of_sample_num'].value == 2:
                yield UInt32(self, "sample_number[%i]" % i)
            elif self['length_size_of_sample_num'].value == 1:
                yield UInt16(self, "sample_number[%i]" % i)
            else:
                yield UInt8(self, "sample_number[%i]" % i)


class MovieFragmentRandomAccessOffset(FieldSet):

    def createFields(self):
        yield UInt8(self, "version", "Version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "size")


def findHandler(self):
    ''' find the handler corresponding to this fieldset '''
    while self:
        if self.name in ('media', 'tags'):
            break
        self = self.parent
    else:
        return None
    for atom in self:
        if atom['tag'].value == 'hdlr':
            return atom['hdlr']
    return None


class METATAG(FieldSet):

    def createFields(self):
        yield UInt8(self, "unk[]", "0x80 or 0x00")
        yield PascalString16(self, "tag_name", charset='UTF-8')
        yield UInt16(self, "unk[]", "0x0001")
        yield UInt16(self, "unk[]", "0x0000")
        yield PascalString16(self, "tag_value", charset='UTF-8')


class META(FieldSet):

    def createFields(self):
        # This tag has too many variant forms.
        if '/tags/' in self.path:
            yield UInt32(self, "count")
            for i in range(self['count'].value):
                yield METATAG(self, "tag[]")
        elif self.stream.readBits(self.absolute_address, 32, self.endian) == 0:
            yield UInt8(self, "version")
            yield Bits(self, "flags", 24)
            yield AtomList(self, "tags")
        else:
            yield AtomList(self, "tags")


class Item(FieldSet):

    def createFields(self):
        yield UInt32(self, "size")
        yield UInt32(self, "index")
        yield Atom(self, "value")


class KeyList(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count")
        for i in range(self['count'].value):
            yield Atom(self, "key[]")


class ItemList(FieldSet):

    def createFields(self):
        handler = findHandler(self)
        if handler is None:
            raise ParserError("ilst couldn't find metadata handler")
        if handler['subtype'].value == 'mdir':
            while not self.eof:
                yield Atom(self, "atom[]")
        elif handler['subtype'].value == 'mdta':
            while not self.eof:
                yield Item(self, "item[]")


class NeroChapters(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "unknown")
        yield UInt8(self, "count", description="Number of chapters")
        for i in range(self['count'].value):
            yield UInt64(self, "chapter_start[]")
            yield PascalString8(self, "chapter_name[]", charset='UTF-8')


class SampleDecodeTimeTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Total entries in sample time table")
        for i in range(self['count'].value):
            yield UInt32(self, "sample_count[]", "Number of consecutive samples with this delta")
            yield UInt32(self, "sample_delta[]", "Decode time delta since last sample, in time-units")


class SampleCompositionTimeTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Total entries in sample time table")
        for i in range(self['count'].value):
            yield UInt32(self, "sample_count[]", "Number of consecutive samples with this offset")
            if self["version"].value == 1:
                yield Int32(self, "sample_offset[]", "Difference between decode time and composition time of this sample, in time-units")
            else:
                yield UInt32(self, "sample_offset[]", "Difference between decode time and composition time of this sample, in time-units")


class ChunkOffsetTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Total entries in offset table")
        for i in range(self['count'].value):
            yield UInt32(self, "chunk_offset[]")


class ChunkOffsetTable64(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Total entries in offset table")
        for i in range(self['count'].value):
            yield UInt64(self, "chunk_offset[]")


class SampleEntry(FieldSet):

    def createFields(self):
        yield UInt32(self, "size")
        yield RawBytes(self, "format", 4, "Data Format (codec)")
        yield NullBytes(self, "reserved[]", 6, "Reserved")
        yield UInt16(self, "data_reference_index")
        handler = findHandler(self)
        if not handler:
            raise ParserError("stsd couldn't find track handler")
        if handler['subtype'].value == 'soun':
            # Audio sample entry
            yield NullBytes(self, "reserved[]", 8)
            yield UInt16(self, "channels", "Number of audio channels")
            yield UInt16(self, "samplesize", "Sample size in bits")
            yield UInt16(self, "unknown")
            yield NullBytes(self, "reserved[]", 2)
            yield QTFloat32(self, "samplerate", "Sample rate in Hz")
        elif handler['subtype'].value == 'vide':
            # Video sample entry
            yield UInt16(self, "version")
            yield UInt16(self, "revision_level")
            yield RawBytes(self, "vendor_id", 4)
            yield UInt32(self, "temporal_quality")
            yield UInt32(self, "spatial_quality")
            yield UInt16(self, "width", "Width (pixels)")
            yield UInt16(self, "height", "Height (pixels)")
            yield QTFloat32(self, "horizontal_resolution", "Horizontal resolution in DPI")
            yield QTFloat32(self, "vertical resolution", "Vertical resolution in DPI")
            yield UInt32(self, "data_size")
            yield UInt16(self, "frame_count")
            yield UInt8(self, "compressor_name_length")
            yield String(self, "compressor_name", 31, strip='\0')
            yield UInt16(self, "depth", "Bit depth of image")
            yield Int16(self, "unknown")
        elif handler['subtype'].value == 'hint':
            # Hint sample entry
            pass

        while not self.eof:
            yield Atom(self, "atom[]")

        size = self['size'].value - self.current_size // 8
        if size > 0:
            yield RawBytes(self, "extra_data", size)


class VPCodecConfigurationBox(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt8(self, "profile")
        yield UInt8(self, "level")
        yield Bits(self, "bit_depth", 4)
        yield Bits(self, "chroma_subsampling", 3)
        yield Bit(self, "video_full_range_flag")
        yield UInt8(self, "colour_primaries")
        yield UInt8(self, "transfer_characteristics")
        yield UInt8(self, "matrix_coefficients")
        yield UInt16(self, "codec_initialization_data_size")


class AVCCodecConfigurationBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "configurationVersion")
        yield UInt8(self, "AVCProfileindication")
        yield UInt8(self, "profile_compatibility")
        yield UInt8(self, "AVCLevelIndication")
        yield PaddingBits(self, "res[]", 6)
        yield Bits(self, "lengthSizeMinusOne", 2)
        yield PaddingBits(self, "res[]", 3)
        yield Bits(self, "numOfSequenceParameterSets", 5)
        for i in range(self["numOfSequenceParameterSets"].value):
            yield AVCSequenceParameterSet(self, "sequenceParamaterSet[]")
        yield UInt8(self, "numOfPictureParameterSets")
        for i in range(self["numOfPictureParameterSets"].value):
            yield AVCPictureParameterSet(self, "pictureParameterSet[]")


class AVCSequenceParameterSet(FieldSet):
    def createFields(self):
        yield UInt16(self, "sequenceParameterSetLength")
        yield RawBytes(self, "sequenceParameterSetNALUnit", self["sequenceParameterSetLength"].value)


class AVCPictureParameterSet(FieldSet):
    def createFields(self):
        yield UInt16(self, "pictureParameterSetLength")
        yield RawBytes(self, "pictureParameterSetNALUnit", self["pictureParameterSetLength"].value)


class HEVCCodecConfigurationBox(FieldSet):

    def createFields(self):
        yield UInt8(self, "configurationVersion")
        yield Bits(self, "profile_space", 2)
        yield Bit(self, "tier_flag")
        yield Bits(self, "profile_idc", 5)
        yield UInt32(self, "profile_compatibility_indications")
        yield Bits(self, "constraint_indicator_flags", 48)
        yield UInt8(self, "level_idc")
        yield PaddingBits(self, "res[]", 4, pattern=1)
        yield Bits(self, "min_spatial_segmentation_idc", 12)
        yield PaddingBits(self, "res[]", 6, pattern=1)
        yield Bits(self, "parallelismType", 2)
        yield PaddingBits(self, "res[]", 6, pattern=1)
        yield Bits(self, "chroma_format_idc", 2)
        yield PaddingBits(self, "res[]", 5, pattern=1)
        yield Bits(self, "bit_depth_luma_minus_8", 3)
        yield PaddingBits(self, "res[]", 5, pattern=1)
        yield Bits(self, "bit_depth_chroma_minus_8", 3)
        yield Bits(self, "avgFrameRate", 16)
        yield Bits(self, "constantFrameRate", 2)
        yield Bits(self, "numTemporalLayers", 3)
        yield Bit(self, "temporalIDNested")
        yield Bits(self, "lengthSizeMinusOne", 2)
        yield UInt8(self, "numOfArrays")
        for i in range(self["numOfArrays"].value):
            yield HEVCNALArray(self, "NAL_arrays[]")


class HEVCNALArray(FieldSet):

    def createFields(self):
        yield Bit(self, "array_completeness")
        yield Bit(self, "reserved")
        yield Bits(self, "NAL_unit_type", 6)
        yield UInt16(self, "numNalus")
        for i in range(self["numNalus"].value):
            yield HEVCNalUnit(self, "NAL_units[]")


class HEVCNalUnit(FieldSet):

    def createFields(self):
        yield UInt16(self, "nalUnitLength")
        yield Bits(self, "nalUnit", self["nalUnitLength"].value)


class SampleDescription(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Total entries in table")
        for i in range(self['count'].value):
            yield SampleEntry(self, "sample_entry[]")


class SyncSampleTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Number of sync samples")
        for i in range(self['count'].value):
            yield UInt32(self, "sample_number[]")


class SampleSizeTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "uniform_size", description="Uniform size of each sample (0 if non-uniform)")
        yield UInt32(self, "count", description="Number of samples")
        if self['uniform_size'].value == 0:
            for i in range(self['count'].value):
                yield UInt32(self, "sample_size[]")


class CompactSampleSizeTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield NullBits(self, "reserved[]", 24)
        yield UInt8(self, "field_size", "Size of each entry in this table, in bits")
        yield UInt32(self, "count", description="Number of samples")
        bitsize = self['field_size'].value
        for i in range(self['count'].value):
            yield Bits(self, "sample_size[]", bitsize)
        if self.current_size % 8 != 0:
            yield NullBits(self, "padding[]", 8 - (self.current_size % 8))


class SampleToChunkTable(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "count", description="Number of sample to chunk table entries")
        for i in range(self['count'].value):
            yield UInt32(self, "first_chunk[]")
            yield UInt32(self, "samples_per_chunk[]")
            yield UInt32(self, "sample_description_index[]")


class SubSampleInformation(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "entry_count")
        for i in range(self["entry_count"].value):
            if self["version"].value == 1:
                yield SubSampleEntryV1(self, "SubSampleEntry[]")
            else:
                yield SubSampleEntryV0(self, "SubSampleEntry[]")


class SubSampleEntryV1(FieldSet):

    def createFields(self):
        yield UInt32(self, "sample_delta")
        yield UInt16(self, "subsample_count")
        for j in range(self["subsample_count"].value):
            yield UInt32(self, "subsample_size[]")
            yield UInt8(self, "subsample_priority[]")
            yield UInt8(self, "discardable[]")
            yield UInt32(self, "codec_specific_parameters[]")


class SubSampleEntryV0(FieldSet):

    def createFields(self):
        yield UInt32(self, "sample_delta")
        yield UInt16(self, "subsample_count")
        for j in range(self["subsample_count"].value):
            yield UInt16(self, "subsample_size[]")
            yield UInt8(self, "subsample_priority[]")
            yield UInt8(self, "discardable[]")
            yield RawBytes(self, "codec_specific_parameters[]", 4)


class TrackFragmentHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield Bits(self, "default_base_is_moof", 7)
        yield Bit(self, "duration_is_empty")
        yield Bits(self, "default_sample_flags_present", 11)
        yield Bit(self, "default_sample_size_present")
        yield Bit(self, "default_sample_duration_present")
        yield Bits(self, "sample_description_index_present", 2)
        yield Bit(self, "base_data_offset_present")

        yield UInt32(self, "track_id")

        if (self["base_data_offset_present"].value):
            yield UInt64(self, "base_data_offset")
        if (self["sample_description_index_present"].value):
            yield UInt32(self, "sample_description_index")
        if (self["default_sample_duration_present"].value):
            yield UInt32(self, "default_sample_duration")
        if (self["default_sample_size_present"].value):
            yield UInt32(self, "default_sample_size")
        if (self["default_sample_flags_present"].value):
            yield Bits(self, "is_leading", 6)
            yield Bits(self, "sample_depends_on", 2)
            yield Bits(self, "sample_is_depended_on", 2)
            yield Bits(self, "sample_has_redundancy", 2)
            yield Bits(self, "sample_is_non_sync_sample", 4)
            yield UInt16(self, "sample_degradation_priority")


class TrackFragmentDecodeTime(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        if self["version"].value == 1:
            yield UInt64(self, "base_media_decode_time")
        else:
            yield UInt32(self, "base_media_decode_time")


class TrackFragmentRun(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        # flags
        yield Bits(self, "sample_composition_time_offsets_present", 13)
        yield Bit(self, "sample_flags_present")
        yield Bit(self, "sample_size_present")
        yield Bit(self, "sample_duration_present")
        yield Bits(self, "first_sample_flags_present", 6)
        yield Bits(self, "data_offset_present", 2)

        yield UInt32(self, "sample_count")

        if (self["data_offset_present"].value):
            yield Int32(self, "data_offset")
        if (self["first_sample_flags_present"].value):
            yield Bits(self, "is_leading", 6)
            yield Bits(self, "sample_depends_on", 2)
            yield Bits(self, "sample_is_depended_on", 2)
            yield Bits(self, "sample_has_redundancy", 2)
            yield Bits(self, "sample_is_non_sync_sample", 4)
            yield UInt16(self, "sample_degradation_priority")

        for i in range(self["sample_count"].value):
            yield TrackFragmentRunSample(self, "sample[]")


class TrackFragmentRunSample(FieldSet):

    def createFields(self):
        if (self.parent["sample_duration_present"].value):
            yield UInt32(self, "sample_duration[]")
        if (self.parent["sample_size_present"].value):
            yield UInt32(self, "sample_size[]")
        if (self.parent["sample_flags_present"].value):
            yield Bits(self, "is_leading", 6)
            yield Bits(self, "sample_depends_on", 2)
            yield Bits(self, "sample_is_depended_on", 2)
            yield Bits(self, "sample_has_redundancy", 2)
            yield Bits(self, "sample_is_non_sync_sample", 4)
            yield UInt16(self, "sample_degradation_priority")
        if (self.parent["sample_composition_time_offsets_present"].value):
            if (self.parent["version"].value == 1):
                yield UInt32(self, "sample_composition_time_offset[]")
            else:
                yield Int32(self, "sample_composition_time_offset[]")


class MovieExtendsHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        if self["version"].value == 1:
            yield UInt64(self, "fragment_duration")
        else:
            yield UInt32(self, "fragment_duration")


class TrackExtends(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "track_id")
        yield UInt32(self, "default_sample_description_index")
        yield UInt32(self, "default_sample_duration")
        yield UInt32(self, "default_sample_size")

        yield Bits(self, "is_leading", 6)
        yield Bits(self, "sample_depends_on", 2)
        yield Bits(self, "sample_is_depended_on", 2)
        yield Bits(self, "sample_has_redundancy", 2)
        yield Bits(self, "sample_is_non_sync_sample", 4)
        yield UInt16(self, "sample_degradation_priority")


class SegmentIndex(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)

        yield UInt32(self, "reference_ID")
        yield UInt32(self, "timescale")

        if (self["version"].value == 0):
            yield UInt32(self, "earliest_presentation_time")
            yield UInt32(self, "first_offset")
        else:
            yield UInt64(self, "earliest_presentation_time")
            yield UInt64(self, "first_offset")

        yield NullBits(self, "pad[]", 16)
        yield UInt16(self, "reference_count")

        for i in range(self["reference_count"].value):
            yield Bit(self, "reference_type[]")
            yield Bits(self, "referenced_size[]", 31)
            yield UInt32(self, "subsegment_duration[]")
            yield Bit(self, "starts_with_SAP[]")
            yield Bits(self, "SAP_type[]", 3)
            yield Bits(self, "SAP_delta_time[]", 28)


class ItemLocation(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)

        yield Bits(self, "offset_size", 4)
        yield Bits(self, "length_size", 4)
        yield Bits(self, "base_offset_size", 4)

        if self["version"].value == 1 or self["version"].value == 2:
            yield Bits(self, "index_size", 4)
        else:
            yield Bits(self, "reserved", 4)
        if self["version"].value < 2:
            yield UInt16(self, "item_count")
        elif self["version"].value == 2:
            yield UInt32(self, "item_count")
        for i in range(self["item_count"].value):
            yield ItemLocationItem(self, "item_location_item[]")


class ItemLocationItem(FieldSet):

    def createFields(self):
        if self.parent["version"].value < 2:
            yield UInt16(self, "item_ID")
        elif self.parent["version"].value == 2:
            yield UInt32(self, "item_ID")
        if self.parent["version"].value == 1 or self.parent["version"].value == 2:
            yield Bits(self, "reserved", 12)
            yield Bits(self, "construction_method", 4)
        yield UInt16(self, "data_reference_index")
        yield Bits(self, "base_offset", self.parent["base_offset_size"].value * 8)
        yield UInt16(self, "extent_count")
        for j in range(self["extent_count"].value):
            if (self.parent["version"].value == 1 or self.parent["version"].value == 2) and self.parent["index_size"].value > 0:
                yield Bits(self, "extend_index", self.parent["index_size"].value * 8)
            yield Bits(self, "extent_offset", self.parent["offset_size"].value * 8)
            yield Bits(self, "extent_length", self.parent["length_size"].value * 8)


class TrackFragmentExtendedHeader(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        if self["version"].value == 1:
            yield UInt64(self, "absolute_time")
            yield UInt64(self, "duration")
        else:
            yield UInt32(self, "absolute_time")
            yield UInt32(self, "duration")

        size = self.parent["size"].value - self.current_size // 8
        print(size)
        print(self.parent["size"].value)
        print(self.current_size)
        if size > 0:
            yield RawBytes(self, "extra_data", size)


class EventMessage(FieldSet):

    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)

        yield CString(self, "scheme_id_uri")
        yield CString(self, "value")

        yield UInt32(self, "timescale")
        yield UInt32(self, "presentation_time_delta")
        yield UInt32(self, "event_duration")
        yield UInt32(self, "id")

        size = self.size // 8 - self.current_size // 8
        if size > 0:
            yield RawBytes(self, "message_data", size)


class ProtectionSystemSpecificHeaderBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)

        yield RawBytes(self, "SystemID", 16)

        if self["version"].value > 0:
            yield UInt32(self, "KID_Count")
            for i in range(self["KID_Count"].value):
                yield RawBytes(self, "KID[]", 16)

        yield UInt32(self, "DataSize")
        yield RawBytes(self, "Data", self["DataSize"].value)


# ISO/IEC 14496-12:2012 8.12.1
class ProtectionSchemeInfoBox(FieldSet):
    def createFields(self):
        yield Atom(self, "original_format")
        if not self.eof:
            yield Atom(self, "scheme_type_box")
        if not self.eof:
            yield Atom(self, "info")


# ISO/IEC 14496-12:2012 8.12.2
class OriginalFormatBox(FieldSet):
    def createFields(self):
        yield RawBytes(self, "data_format", 4)


# ISO/IEC 14496-12:2012 8.12.5
class SchemeTypeBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "version")
        yield UInt24(self, "flags")
        yield RawBytes(self, "scheme_type", 4)
        yield UInt32(self, "scheme_version")
        if self["flags"].value & 0x1:
            yield CString(self, "scheme_uri")


# ISO/IEC 14496-12:2012 8.12.6
class SchemeInformationBox(FieldSet):
    def createFields(self):
        yield Atom(self, "scheme_specific_data")



# ISO/IEC 14496-12:2012 8.16.3
class SegmentIndexBoxReference(FieldSet):
    def createFields(self):
        yield Bit(self, "reference_type")
        yield Bits(self, "referenced_size", 31)
        yield UInt32(self, "subsegment_duration")
        yield Bit(self, "starts_with_SAP")
        yield Bits(self, "SAP_type", 3)
        yield Bits(self, "SAP_delta_time", 28)


class SegmentIndexBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield UInt32(self, "reference_ID")
        yield UInt32(self, "timescale")
        if self["version"].value == 0:
            yield UInt32(self, "earliest_presentation_time")
            yield UInt32(self, "first_offset")
        else:
            yield UInt64(self, "earliest_presentation_time")
            yield UInt64(self, "first_offset")
        yield NullBits(self, "reserved", 16)
        yield UInt16(self, "reference_count")
        for i in range(self["reference_count"].value):
            yield SegmentIndexBoxReference(self, "reference[]")


# ISO/IEC 23001-7:2016 7.2
class SampleEncryptionItem(FieldSet):
    def createFields(self):
        yield RawBytes(self, "IV", 8)  # TODO: Per_Sample_IV_Size
        if self["../flags"].value & 0x2:
            yield UInt16(self, "subsample_count")
            for i in range(self["subsample_count"].value):
                yield UInt16(self, "BytesOfClearData[]")
                yield UInt32(self, "ByteOfProtectedData[]")


class SampleEncryptionBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "version")
        yield UInt24(self, "flags")

        yield UInt32(self, "sample_count")
        for i in range(self["sample_count"].value):
            yield SampleEncryptionItem(self, "sample[]")


# ISO/IEC 23001-7:2016 8.1.1
class ProtectionSystemSpecificHeaderBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)

        yield RawBytes(self, "SystemID", 16)

        if self["version"].value > 0:
            yield UInt32(self, "KID_Count")
            for i in range(self["KID_Count"].value):
                yield RawBytes(self, "KID[]", 16)

        yield UInt32(self, "DataSize")
        yield RawBytes(self, "Data", self["DataSize"].value)

# ISO/IEC 23001-7:2016 8.2
class TrackEncryptionBox(FieldSet):
    def createFields(self):
        yield UInt8(self, "version")
        yield NullBits(self, "flags", 24)
        yield NullBits(self, "reserved", 8)
        if self["version"].value == 0:
            yield NullBits(self, "reserved2", 8)
        else:
            yield Bits(self, "default_crypt_byte_block", 4)
            yield Bits(self, "default_skip_byte_block", 4)
        yield UInt8(self, "default_isProtected")
        yield UInt8(self, "default_Per_sample_IV_Size")
        yield RawBytes(self, "default_KID", 16)
        if self["default_isProtected"].value == 1 and self["default_Per_sample_IV_Size"].value == 0:
            yield UInt8(self, "default_constant_IV_size")
            yield RawBytes(self, "default_constant_IV", self["default_constant_IV_size"].value)


class Atom(FieldSet):
    tag_info = {
        "ftyp": (FileType, "file_type", "File type and compatibility"),
        "styp": (SegmentType, "segment_type", "Segment type and compatibility"),
        # pdin: progressive download information
        # pnot: movie preview (old QT spec)
        "moov": (AtomList, "movie", "Container for all metadata"),
            "mvhd": (MovieHeader, "movie_hdr", "Movie header, overall declarations"),
            # clip: movie clipping (old QT spec)
                # crgn: movie clipping region (old QT spec)
            "trak": (AtomList, "track", "Container for an individual track or stream"),
                "tkhd": (TrackHeader, "track_hdr", "Track header, overall information about the track"),
                # matt: track matte (old QT spec)
                    # kmat: compressed matte (old QT spec)
                "tref": (AtomList, "tref", "Track reference container"),
                    "hint": (TrackReferenceType, "hint", "Original media track(s) for this hint track"),
                    "cdsc": (TrackReferenceType, "cdsc", "Reference to track described by this track"),
                "edts": (AtomList, "edts", "Edit list container"),
                    "elst": (EditList, "elst", "Edit list"),
                "load": (Load, "load", "Track loading settings (old QT spec)"),
                # imap: Track input map (old QT spec)
                "mdia": (AtomList, "media", "Container for the media information in a track"),
                    "mdhd": (MediaHeader, "media_hdr", "Media header, overall information about the media"),
                    "hdlr": (Handler, "hdlr", "Handler, declares the media or metadata (handler) type"),
                    "minf": (AtomList, "minf", "Media information container"),
                        "vmhd": (VideoMediaHeader, "vmhd", "Video media header, overall information (video track only)"),
                        "smhd": (SoundMediaHeader, "smhd", "Sound media header, overall information (sound track only)"),
                        "hmhd": (HintMediaHeader, "hmhd", "Hint media header, overall information (hint track only)"),
                        # nmhd: Null media header, overall information (some tracks only) (unparsed)
                        "dinf": (AtomList, "dinf", "Data information, container"),
                            "dref": (DataReference, "dref", "Data reference, declares source(s) of media data in track"),
                                "url ": (DataEntryUrl, "url", "URL data reference"),
                                "urn ": (DataEntryUrn, "urn", "URN data reference"),
                        "stbl": (AtomList, "stbl", "Sample table, container for the time/space map"),
                            "stsd": (SampleDescription, "stsd", "Sample descriptions (codec types, initialization etc.)"),
                            "stts": (SampleDecodeTimeTable, "stts", "decoding time-to-sample delta table"),
                            "ctts": (SampleCompositionTimeTable, "ctts", "composition time-to-sample offset table"),
                            "stsc": (SampleToChunkTable, "stsc", "sample-to-chunk, partial data-offset information"),
                            "stsz": (SampleSizeTable, "stsz", "Sample size table (framing)"),
                            "stz2": (CompactSampleSizeTable, "stz2", "Compact sample size table (framing)"),
                            "stco": (ChunkOffsetTable, "stco", "Chunk offset, partial data-offset information"),
                            "co64": (ChunkOffsetTable64, "co64", "64-bit chunk offset"),
                            "stss": (SyncSampleTable, "stss", "Sync sample table (random access points)"),
                            # stsh: shadow sync sample table
                            # padb: sample padding bits
                            # stdp: sample degradation priority
                            # sdtp: independent and disposable samples
                            # sbgp: sample-to-group
                            # sgpd: sample group description
                            "subs": (SubSampleInformation, "subs", "subsample information"),
            # ctab color table (old QT spec)
            # mvex: movie extends
                # mehd: movie extends header
                # trex: track extends defaults
            "mvex": (AtomList, "mvex", "movie extends box"),
                "mehd": (MovieExtendsHeader, "mehd", "movie extends header"),
                "trex": (TrackExtends, "trex", "track extends"),
            "pssh": (ProtectionSystemSpecificHeaderBox, "pssh", "Protection system information"),
            # ipmc: IPMP control
        "moof": (AtomList, "moof", "movie fragment"),
            "mfhd": (MovieFragmentHeader, "mfhd", "movie fragment header"),
            "traf": (AtomList, "traf", "track fragment"),
                # tfhd: track fragment header
                "tfhd": (TrackFragmentHeader, "tfhd", "track fragment header"),
                # trun: track fragment run
                "trun": (TrackFragmentRun, "trun", "track fragment run"),
                # sdtp: independent and disposable samples
                # sbgp: sample-to-group
                # subs: sub-sample information
                "tfdt": (TrackFragmentDecodeTime, "tfdt", "track fragment decode time"),
        "mfra": (AtomList, "mfra", "movie fragment random access"),
            "tfra": (TrackFragmentRandomAccess, "tfra", "track fragment random access"),
            "mfro": (MovieFragmentRandomAccessOffset, "mfro", "movie fragment random access offset"),
        # mdat: media data container
        "mdat": (AtomList, "mdat", "movie data"),
        # free: free space (unparsed)
        # skip: free space (unparsed)
        "udta": (AtomList, "udta", "User data"),
        "meta": (META, "meta", "File metadata"),
            "keys": (KeyList, "keys", "Metadata keys"),
            # hdlr
            # dinf
                # dref: data reference, declares source(s) of metadata items
            # ipmc: IPMP control
            # iloc: item location
            "iloc": (ItemLocation, "iloc", "item location"),
            # ipro: item protection
                # sinf: protection scheme information
                    # frma: original format
                    # imif: IPMP information
                    # schm: scheme type
                    # schi: scheme information
            # iinf: item information
            # xml : XML container
            # bxml: binary XML container
            # pitm: primary item reference
        # other tags
        "ilst": (ItemList, "ilst", "Item list"),
            "trkn": (AtomList, "trkn", "Metadata: Track number"),
            "disk": (AtomList, "disk", "Metadata: Disk number"),
            "tmpo": (AtomList, "tempo", "Metadata: Tempo"),
            "cpil": (AtomList, "cpil", "Metadata: Compilation"),
            "gnre": (AtomList, "gnre", "Metadata: Genre"),
            "\xa9cpy": (AtomList, "copyright", "Metadata: Copyright statement"),
            "\xa9day": (AtomList, "date", "Metadata: Date of content creation"),
            "\xa9dir": (AtomList, "director", "Metadata: Movie director"),
            "\xa9ed1": (AtomList, "edit1", "Metadata: Edit date and description (1)"),
            "\xa9ed2": (AtomList, "edit2", "Metadata: Edit date and description (2)"),
            "\xa9ed3": (AtomList, "edit3", "Metadata: Edit date and description (3)"),
            "\xa9ed4": (AtomList, "edit4", "Metadata: Edit date and description (4)"),
            "\xa9ed5": (AtomList, "edit5", "Metadata: Edit date and description (5)"),
            "\xa9ed6": (AtomList, "edit6", "Metadata: Edit date and description (6)"),
            "\xa9ed7": (AtomList, "edit7", "Metadata: Edit date and description (7)"),
            "\xa9ed8": (AtomList, "edit8", "Metadata: Edit date and description (8)"),
            "\xa9ed9": (AtomList, "edit9", "Metadata: Edit date and description (9)"),
            "\xa9fmt": (AtomList, "format", "Metadata: Movie format (CGI, digitized, etc.)"),
            "\xa9inf": (AtomList, "info", "Metadata: Information about the movie"),
            "\xa9prd": (AtomList, "producer", "Metadata: Movie producer"),
            "\xa9prf": (AtomList, "performers", "Metadata: Performer names"),
            "\xa9req": (AtomList, "requirements", "Metadata: Special hardware and software requirements"),
            "\xa9src": (AtomList, "source", "Metadata: Credits for those who provided movie source content"),
            "\xa9nam": (AtomList, "name", "Metadata: Name of song or video"),
            "\xa9des": (AtomList, "description", "Metadata: File description"),
            "\xa9cmt": (AtomList, "comment", "Metadata: General comment"),
            "\xa9alb": (AtomList, "album", "Metadata: Album name"),
            "\xa9gen": (AtomList, "genre", "Metadata: Custom genre"),
            "\xa9ART": (AtomList, "artist", "Metadata: Artist name"),
            "\xa9too": (AtomList, "encoder", "Metadata: Encoder"),
            "\xa9wrt": (AtomList, "writer", "Metadata: Writer"),
            "covr": (AtomList, "cover", "Metadata: Cover art"),
            "----": (AtomList, "misc", "Metadata: Miscellaneous"),
        "tags": (AtomList, "tags", "File tags"),
        "tseg": (AtomList, "tseg", "tseg"),
        "chpl": (NeroChapters, "chpl", "Nero chapter data"),
        "sidx": (SegmentIndex, "sidx", "Segment Index"),
        "6D1D9B05-42D5-44E6-80E2-141DAFF757B2": (TrackFragmentExtendedHeader, "tfxd", "track fragment extended header"),
        "emsg": (EventMessage, "emsg", "Event Message"),
        "vpcC": (VPCodecConfigurationBox, "vpcC", "VP codec configuration"),
        "hvcC": (HEVCCodecConfigurationBox, "hvcC", "HEVC codec configuration"),
        "avcC": (AVCCodecConfigurationBox, "avcC", "AVC codec configuration"),
        "sinf": (ProtectionSchemeInfoBox, "sinf", "Protection scheme information"),
        "frma": (OriginalFormatBox, "frma", "original format"),
        "schm": (SchemeTypeBox, "schm", "scheme type"),
        "schi": (SchemeInformationBox, "schi", "scheme information"),
        "tenc": (TrackEncryptionBox, "tenc", "track encryption"),
    }  # noqa
    tag_handler = [item[0] for item in tag_info]
    tag_desc = [item[1] for item in tag_info]

    def createFields(self):
        yield UInt32(self, "size")
        yield String(self, "tag", 4, charset="ASCII")
        size = self["size"].value
        if size == 1:
            # 64-bit size
            yield UInt64(self, "size64")
            size = self["size64"].value - 16
        elif size == 0:
            # Unbounded atom
            if self._size is None:
                size = (self.parent.size - self.parent.current_size) // 8 - 8
            else:
                size = (self.size - self.current_size) // 8
        else:
            size = size - 8
        if self['tag'].value == 'uuid':
            yield GUID(self, "usertag")
            tag = self["usertag"].value
            size -= 16
        else:
            tag = self["tag"].value
        if size > 0:
            if tag in self.tag_info:
                handler, name, desc = self.tag_info[tag]
                yield handler(self, name, desc, size=size * 8)
            else:
                yield RawBytes(self, "data", size)

    def createDescription(self):
        if self["tag"].value == "uuid":
            return "Atom: uuid: " + self["usertag"].value
        return "Atom: %s" % self["tag"].value


class MovFile(Parser):
    PARSER_TAGS = {
        "id": "mov",
        "category": "video",
        "file_ext": ("mov", "qt", "mp4", "m4v", "m4a", "m4p", "m4b"),
        "mime": ("video/quicktime", 'video/mp4'),
        "min_size": 8 * 8,
        "magic": ((b"moov", 4 * 8),),
        "description": "Apple QuickTime movie"
    }
    BRANDS = {
        # File type brand => MIME type
        'mp41': 'video/mp4',
        'mp42': 'video/mp4',
        'avc1': 'video/mp4',
        'isom': 'video/mp4',
        'iso2': 'video/mp4',
    }
    endian = BIG_ENDIAN

    def __init__(self, *args, **kw):
        Parser.__init__(self, *args, **kw)

    is_mpeg4 = property(lambda self: self.mime_type == 'video/mp4')

    def validate(self):
        # TODO: Write better code, erk!
        size = self.stream.readBits(0, 32, self.endian)
        if size < 8:
            return "Invalid first atom size"
        tag = self.stream.readBytes(4 * 8, 4)
        if tag not in (b"ftyp", b"moov", b"free", b"moof", b"styp"):
            return "Unknown MOV file type"
        return True

    def createFields(self):
        while not self.eof:
            yield Atom(self, "atom[]")

    def createMimeType(self):
        first = self[0]
        try:
            # Read brands in the file type
            if first['tag'].value != "ftyp":
                return None
            file_type = first["file_type"]
            brand = file_type["brand"].value
            if brand in self.BRANDS:
                return self.BRANDS[brand]
            for field in file_type.array("compat_brand"):
                brand = field.value
                if brand in self.BRANDS:
                    return self.BRANDS[brand]
        except MissingField:
            pass
        return 'video/quicktime'
