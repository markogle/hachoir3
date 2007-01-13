from hachoir_core.field import (Field, FieldError,
    createRawField, createNullField, createPaddingField, FakeArray)
from hachoir_core.event_handler import EventHandler
from hachoir_core.dict import Dict, UniqKeyError
from hachoir_core.endian import BIG_ENDIAN, LITTLE_ENDIAN
from hachoir_core.stream import InputStream, InputStreamError
from hachoir_core.error import error, warning, info, HACHOIR_ERRORS
from hachoir_core.tools import lowerBound
import hachoir_core.config as config

class ParserError(FieldError):
    """
    Error raised by a L{GenericFieldSet} (or L{FieldSet}/L{Parser}).

    @see: L{FieldError}
    """
    pass

class MatchError(FieldError):
    """
    Error raised by a L{FieldSet} or a L{Parser} when the stream content
    doesn't match to file format.

    @see: L{FieldError}
    """
    pass

class GenericFieldSet(Field):
    """
    Ordered list of fields. Use operator [] to access fields using their
    name (field names are unique in a field set, but not in the whole
    document).

    Class attributes:
    - endian: Bytes order (L{BIG_ENDIAN} or L{LITTLE_ENDIAN}). Optional if the
      field set has a parent ;
    - static_size: (optional) Size of FieldSet in bits. This attribute should
      be used in parser of constant size.

    Instance attributes/methods:
    - _fields: Ordered dictionnary of all fields, may be incomplete
      because feeded when a field is requested ;
    - stream: Input stream used to feed fields' value
    - root: The root of all field sets ;
    - __len__(): Number of fields, may need to create field set ;
    - __getitem(): Get an field by it's name or it's path.

    And attributes inherited from Field class:
    - parent: Parent field (may be None if it's the root) ;
    - name: Field name (unique in parent field set) ;
    - value: The field set ;
    - address: Field address (in bits) relative to parent ;
    - description: A string describing the content (can be None) ;
    - size: Size of field set in bits, may need to create field set.

    Event handling:
    - "connectEvent": Connect an handler to an event ;
    - "raiseEvent": Raise an event.

    To implement a new field set, you need to:
    - create a class which inherite from FieldSet ;
    - write createFields() method using lines like:
         yield Class(self, "name", ...) ;
    - and maybe set endian and static_size class attributes.
    """

    is_field_set = True
    endian = None
    _event_handler = None
    _current_size = 0

    def __init__(self, parent, name, stream, description=None, size=None):
        """
        Constructor
        @param parent: Parent field set, None for root parser
        @param name: Name of the field, have to be unique in parent. If it ends
            with "[]", end will be replaced with "[new_id]" (eg. "raw[]"
            becomes "raw[0]", next will be "raw[1]", and then "raw[2]", etc.)
        @type name: str
        @param stream: Input stream from which data are read
        @type stream: L{InputStream}
        @param description: Optional string description
        @type description: str|None
        @param size: Size in bits. If it's None, size will be computed. You
            can also set size with class attribute static_size
        """

        # Set field set size
        if self.static_size is not None:
            assert isinstance(self.static_size, (int, long))
            size = self.static_size

        # Make some tests on arguments
        assert not parent or issubclass(parent.__class__, GenericFieldSet)
        assert issubclass(stream.__class__, InputStream)
        assert (size is None) or (0 < size)

        # Call parent class constructor
        self._parent = parent
        self._name = name
        self._size = size
        self._description = description

        # Set endian
        if self.endian is None:
            assert parent is not None and parent.endian is not None
            self.endian = parent.endian
        assert self.endian in (BIG_ENDIAN, LITTLE_ENDIAN)

        self._fields = Dict()
        self._field_generator = self.createFields()
        self._field_array_count = {}
        self._array_cache = {}
        if parent:
            # This field set is one of the root leafs
            self._address = parent._current_size
            self.root = parent.root
            self.stream = parent.stream
        else:
            # This field set is the root
            self._address = 0
            self.root = self
            assert issubclass(stream.__class__, InputStream)
            self.stream = stream
            self._global_event_handler = None

    def array(self, key):
        try:
            return self._array_cache[key]
        except KeyError:
            array = FakeArray(self, key)
            self._array_cache[key] = array
            return self._array_cache[key]

    def connectEvent(self, event_name, handler, local=True):
        assert event_name in (
            # Callback prototype: def f(field)
            # Called when new value is already set
            "field-value-changed",

            # Callback prototype: def f(field)
            # Called when field size is already set
            "field-resized",

            # A new field has been insered in the field set
            # Callback prototype: def f(index, new_field)
            "field-insered",

            # Callback prototype: def f(old_field, new_field)
            # Called when new field is already in field set
            "field-replaced",

            # Callback prototype: def f(field, new_value)
            # Called to ask to set new value
            "set-field-value"
        )
        if local:
            if self._event_handler is None:
                self._event_handler = EventHandler()
            self._event_handler.connect(event_name, handler)
        else:
            if self.root._global_event_handler is None:
                self.root._global_event_handler = EventHandler()
            self.root._global_event_handler.connect(event_name, handler)

    def reset(self):
        """
        Reset a field set:
         * clear fields ;
         * restart field generator ;
         * set current size to zero ;
         * clear field array count.

        But keep: name, value, description and size.
        """
        self._fields = Dict()
        self._field_generator = self.createFields()
        self._field_array_count = {}
        self._current_size = 0
        self._array_cache = {}

    def __str__(self):
        return '<%s path=%s, current_size=%s, current length=%s>' % \
            (self.__class__.__name__, self.path, self._current_size, len(self._fields))

    def raiseEvent(self, event_name, *args):
        # Transfer event to local listeners
        if self._event_handler is not None:
            self._event_handler.raiseEvent(event_name, *args)

        # Transfer event to global listeners
        if self.root._global_event_handler is not None:
            self.root._global_event_handler.raiseEvent(event_name, *args)

    def __len__(self):
        """
        Returns number of fields, may need to create all fields
        if it's not done yet.
        """
        if self._field_generator is not None:
            self._feedAll()
        return len(self._fields)

    def _getCurrentLength(self):
        return len(self._fields)
    current_length = property(_getCurrentLength)

    def _getSize(self):
        if self._size is None:
            self._feedAll()
        return self._size
    size = property(_getSize, doc="Size in bits, may create all fields to get size")

    def _getCurrentSize(self):
        assert not(self.done)
        return self._current_size
    current_size = property(_getCurrentSize)

    eof = property(lambda self: self._checkSize(self._current_size + 1, True) < 0)

    def _checkSize(self, size, strict):
        field = self
        while field._size is None:
            if not field._parent:
                assert self.stream.size is None
                if not strict:
                    return None
                if self.stream.sizeGe(size):
                    return 0
                break
            size += field._address
            field = field._parent
        return field._size - size

    def setUniqueFieldName(self, field):
        key = field._name[:-2]
        try:
            self._field_array_count[key] += 1
        except KeyError:
            self._field_array_count[key] = 0
        field._name = key + "[%u]" % self._field_array_count[key]

    def _addField(self, field):
        """
        Add a field to the field set:
        * add it into _fields
        * update _current_size

        May raise a StopIteration() on error
        """
        if config.debug:
            info("[+] DBG: %s._addField(%s)" % (self.path, field.name))
        assert issubclass(field.__class__, Field)
        assert isinstance(field._name, str)
        if field._name.endswith("[]"):
            self.setUniqueFieldName(field)
        if field._address != self._current_size:
            error("assertion failed at GenericFieldSet._addField; fixing field._address...")
            field._address = self._current_size

        # Compute field size and check that there is enough place for it
        ask_stop = False
        try:
            field_size = field.size
        except HACHOIR_ERRORS, err:
            if field.is_field_set and field.current_length and field.eof:
                field._stopFeeding()
                ask_stop = True
            else:
                warning("Error when getting size of %s: delete it" % field.path)
                raise
        dsize = self._checkSize(field._address + field.size, False)

        # No more place?
        if None < dsize < 0 or (field.is_field_set and field.size <= 0):
            if config.autofix:
                self._fixFieldSize(field, field.size + dsize)
            else:
                raise ParserError("Field %s is too large!" % field.path)

        self._current_size += field.size
        try:
            self._fields.append(field._name, field)
        except UniqKeyError, err:
            warning("Duplicate field name %s in %s" % (unicode(err), self.path))
            field._name += "[]"
            self.setUniqueFieldName(field)
            self._fields.append(field._name, field)
        if ask_stop:
            raise StopIteration()

    def _fixFieldSize(self, field, new_size):
        warning("[Autofix] Delete %s (too large)" % field.path)
        if new_size > 0:
            if field.is_field_set and 0 < field.size:
                field._truncate(new_size)
                return

            # Don't add the field <=> delete item
            if self._size is None:
                self._size = self._current_size + new_size
        raise StopIteration()

    def _getField(self, name, const):
        field = Field._getField(self, name, const)
        if field is None:
            if name in self._fields:
                field = self._fields[name]
            elif self._field_generator is not None and not const:
                field = self._feedUntil(name)
        return field

    def getField(self, key, const=True):
        if isinstance(key, (int, long)):
            if key < 0:
                raise KeyError("Key must be positive!")
            if not const:
                self.readFirstFields(key+1)
            return self._fields.values[key]
        return Field.getField(self, key, const)

    def _truncate(self, size):
        assert size > 0
        if size < self._current_size:
            error("Truncating %s recursively" % self.path)
            self._size = size
            while True:
                field = self._fields.values[-1]
                if field._address < size:
                    break
                del self._fields[-1]
            self._current_size = field._address
            size -= field._address
            if size < field._size:
                if field.is_field_set:
                    field._truncate(size)
                else:
                    del self._fields[-1]
                    field = createRawField(self, size, "raw[]")
                    self._fields.append(field._name, field)
            self._current_size = self._size
        else:
            assert size < self._size or self._size is None
            self._size = size
        if self._size == self._current_size:
            self._field_generator = None

    def _deleteField(self, index):
        field = self._fields.values[index]
        size = field.size
        self._current_size -= size
        del self._fields[index]
        return field

    def _fixLastField(self):
        """
        Try to fix last field when we know current field set size.
        Returns new added field if any, or None.
        """
        assert self._size is not None

        # Stop parser
        message = ["stop parser"]
        self._field_generator = None

        # If last field is too big, delete it
        while self._size < self._current_size:
            field = self._deleteField(len(self._fields)-1)
            message.append("delete field %s" % field.path)
        assert self._current_size <= self._size

        # If field size current is smaller: add a raw field
        size = self._size - self._current_size
        if size:
            field = createRawField(self, size, "raw[]")
            message.append("add padding")
            self._current_size += field.size
            self._fields.append(field._name, field)
        else:
            field = None
        message = ", ".join(message)
        warning("[Autofix] Fix parser error in %s: %s" % (self.path, message))
        assert self._current_size == self._size
        return field

    def _stopFeeding(self):
        new_field = None
        if self._size is None:
            if self._parent:
                self._size = self._current_size
        elif self._size != self._current_size:
            if config.autofix:
                new_field = self._fixLastField()
            else:
                raise ParserError("Invalid parser \"%s\" size!" % self.path)
        self._field_generator = None
        return new_field

    def _fixFeedError(self, exception):
        """
        Try to fix a feeding error. Returns False if error can't be fixed,
        otherwise returns new field if any, or None.
        """
        if self._size is None or not config.autofix:
            return False
        warning(unicode(exception))
        return self._fixLastField()

    def _feedUntil(self, field_name):
        """
        Return the field if it was found, None else
        """
        try:
            while True:
                field = self._field_generator.next()
                self._addField(field)
                if field.name == field_name:
                    return field
        except HACHOIR_ERRORS, err:
            if self._fixFeedError(err) is False:
                raise
        except StopIteration:
            self._stopFeeding()
        return None

    def readFirstFields(self, number):
        """
        Read first number fields if they are not read yet.

        Returns number of new added fields.
        """
        if self._field_generator is None:
            return
        number = number - len(self._fields)
        if 0 < number:
            return self.readMoreFields(number)
        else:
            return 0

    def readMoreFields(self, number):
        """
        Read more number fields, or do nothing if parsing is done.

        Returns number of new added fields.
        """
        if self._field_generator is None:
            return 0
        added = 0
        try:
            for index in xrange(number):
                self._addField( self._field_generator.next() )
                added += 1
        except HACHOIR_ERRORS, err:
            if self._fixFeedError(err) is False:
                raise
            added += 1
        except StopIteration:
            if self._stopFeeding():
                added += 1
        return added

    def _feedAll(self):
        if self._field_generator is None:
            return
        try:
            while True:
                self._addField( self._field_generator.next() )
        except HACHOIR_ERRORS, err:
            if self._fixFeedError(err) is False:
                raise
        except StopIteration:
            self._stopFeeding()

    def __iter__(self):
        """
        Create a generator to iterate on each field, may create new
        fields when needed
        """
        try:
            done = 0
            while True:
                if done == len(self._fields):
                    if self._field_generator is None:
                        break
                    self._addField( self._field_generator.next() )
                for field in self._fields.values[done:]:
                    yield field
                    done += 1
        except HACHOIR_ERRORS, err:
            field = self._fixFeedError(err)
            if field:
                yield field
            elif field is False:
                raise
        except StopIteration:
            field = self._stopFeeding()
            if field:
                yield field

    def createFields(self):
        """
        DON'T CALL THIS FUNCTION DIRECTLY!
        Use: __iter__() or __getitem__() to access fields.

        This function have to be implemented in concrete field set.
        """
        raise NotImplementedError()

    def _isDone(self):
        return (self._field_generator is None)
    done = property(_isDone, doc="Boolean to know if parsing is done or not")


    #
    # FieldSet_SeekUtility
    #
    def seekBit(self, address, name="padding[]",
    description=None, relative=True, null=False):
        """
        Create a field to seek to specified address,
        or None if it's not needed.

        May raise an (ParserError) exception if address is invalid.
        """
        if relative:
            nbits = address - self._current_size
        else:
            nbits = address - (self.absolute_address + self._current_size)
        if nbits < 0:
            raise ParserError("Seek error, unable to go back!")
        if 0 < nbits:
            if null:
                return createNullField(self, nbits, name, description)
            else:
                return createPaddingField(self, nbits, name, description)
        else:
            return None

    def seekByte(self, address, name="padding[]", description=None, relative=True, null=False):
        """
        Same as seekBit(), but with address in byte.
        """
        return self.seekBit(address * 8, name, description, relative, null=null)

    #
    # RandomAccessFieldSet
    #
    def replaceField(self, name, new_fields):
        # TODO: Check in self and not self.field
        # Problem is that "generator is already executing"
        if name not in self._fields:
            raise ParserError("Unable to replace %s: field doesn't exist!" % name)
        assert 1 <= len(new_fields)
        old_field = self[name]
        total_size = sum( (field.size for field in new_fields) )
        if old_field.size != total_size:
            raise ParserError("Unable to replace %s: "
                "new field(s) hasn't same size (%u bits instead of %u bits)!"
                % (name, total_size, old_field.size))
        field = new_fields[0]
        if field._name.endswith("[]"):
            self.setUniqueFieldName(field)
        field._address = old_field.address
        if field.name != name and field.name in self._fields:
            raise ParserError(
                "Unable to replace %s: name \"%s\" is already used!"
                % (name, field.name))
        self._fields.replace(name, field.name, field)
        self.raiseEvent("field-replaced", old_field, field)
        if 1 < len(new_fields):
            index = self._fields.index(new_fields[0].name)+1
            address = field.address + field.size
            for field in new_fields[1:]:
                if field._name.endswith("[]"):
                    self.setUniqueFieldName(field)
                field._address = address
                if field.name in self._fields:
                    raise ParserError(
                        "Unable to replace %s: name \"%s\" is already used!"
                        % (name, field.name))
                self._fields.insert(index, field.name, field)
                self.raiseEvent("field-insered", index, field)
                index += 1
                address += field.size

    def getFieldByAddress(self, address, feed=True):
        """
        Only search in existing fields
        """
        if feed and self._field_generator is not None:
            self._feedAll()
        if address < self._current_size:
            i = lowerBound(self._fields.values, lambda x: x.address + x.size <= address)
            if i is not None:
                return self._fields.values[i]
        return None

    def writeFieldsIn(self, old_field, address, new_fields):
        """
        Can only write in existing fields (address < self._current_size)
        """

        # Check size
        total_size = sum( field.size for field in new_fields )
        if old_field.size < total_size:
            raise ParserError( \
                "Unable to write fields at address %s " \
                "(too big)!" % (address))

        # Need padding before?
        replace = []
        size = address - old_field.address
        assert 0 <= size
        if 0 < size:
            padding = createPaddingField(self, size)
            padding._address = old_field.address
            replace.append(padding)

        # Set fields address
        for field in new_fields:
            field._address = address
            address += field.size
            replace.append(field)

        # Need padding after?
        size = (old_field.address + old_field.size) - address
        assert 0 <= size
        if 0 < size:
            padding = createPaddingField(self, size)
            padding._address = address
            replace.append(padding)

        self.replaceField(old_field.name, replace)
