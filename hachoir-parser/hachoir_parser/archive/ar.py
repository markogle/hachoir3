"""
GNU ar archive : archive file (.a) and Debian (.deb) archive.
"""

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet, ParserError,
    String, RawBytes, UnixLine)
from hachoir_core.endian import BIG_ENDIAN

class ArchiveFileEntry(FieldSet):
    def createFields(self):
        yield UnixLine(self, "header", "Header")
        info = self["header"].value.split()
        if len(info) != 7:
            raise ParserError("Invalid file entry header")
        size = int(info[5])
        if 0 < size:
            yield RawBytes(self, "content", size, "File data")

    def createDescription(self):
        return "File entry (%s)" % self["header"].value.split()[0]

class ArchiveFile(Parser):
    endian = BIG_ENDIAN
    MAGIC = '!<arch>\n'
    tags = {
        "file_ext": ("a", "deb"),
        "mime":
            ("application/x-debian-package",
             "application/x-archive",
             "application/x-dpkg"),
        "min_size": (8 + 13)*8, # file signature + smallest file as possible
        "magic": ((MAGIC, 0),),
        "description": "Unix archive"
    }

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalild magic string"
        return True

    def createFields(self):
        yield String(self, "id", 8, "Unix archive identifier (\"<!arch>\")", charset="ASCII")
        while not self.eof:
            data = self.stream.readBytes(self.current_size, 1)
            if data == "\n":
                yield UnixLine(self, "empty_line[]", "Empty line")
            else:
                yield ArchiveFileEntry(self, "file[]", "File")
