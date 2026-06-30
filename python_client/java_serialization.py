import struct
import io
import generated_packets

# Java Serialization constants
STREAM_MAGIC = 0xACED
STREAM_VERSION = 5

TC_NULL = 0x70
TC_REFERENCE = 0x71
TC_CLASSDESC = 0x72
TC_OBJECT = 0x73
TC_STRING = 0x74
TC_ARRAY = 0x75
TC_CLASS = 0x76
TC_BLOCKDATA = 0x77
TC_ENDBLOCKDATA = 0x78
TC_LONGSTRING = 0x7C

BASE_WIRE_HANDLE = 0x7E0000

class JavaObjectInputStream:
    def __init__(self, stream):
        if hasattr(stream, 'read'):
            self.stream = stream
        else:
            self.stream = io.BytesIO(stream)
        self.handles = []
        self._read_header()

    def _read_header(self):
        magic, version = struct.unpack('>HH', self.stream.read(4))
        if magic != STREAM_MAGIC or version != STREAM_VERSION:
            raise ValueError(f"Invalid stream header: {hex(magic)}, {version}")

    def read_object(self):
        tc = self.stream.read(1)
        if not tc:
            return None
        tc = tc[0]

        if tc == TC_NULL:
            return None

        elif tc == TC_REFERENCE:
            handle = struct.unpack('>I', self.stream.read(4))[0]
            idx = handle - BASE_WIRE_HANDLE
            return self.handles[idx]

        elif tc == TC_STRING:
            length = struct.unpack('>H', self.stream.read(2))[0]
            val = self.stream.read(length).decode('utf-8')
            self.handles.append(val)
            return val

        elif tc == TC_LONGSTRING:
            length = struct.unpack('>Q', self.stream.read(8))[0]
            val = self.stream.read(length).decode('utf-8')
            self.handles.append(val)
            return val

        elif tc == TC_OBJECT:
            # Read Class Descriptor
            class_desc_tc = self.stream.read(1)[0]
            if class_desc_tc != TC_CLASSDESC:
                raise ValueError("Expected TC_CLASSDESC")

            class_name = self._read_utf()
            uid = struct.unpack('>q', self.stream.read(8))[0]
            flags = self.stream.read(1)[0]
            field_count = struct.unpack('>H', self.stream.read(2))[0]

            fields = []
            for _ in range(field_count):
                f_type = self.stream.read(1).decode('ascii')
                f_name = self._read_utf()
                if f_type in ('[', 'L'):
                    # Object/Array descriptors have an extra string in classdesc
                    f_desc_tc = self.stream.read(1)[0]
                    # This should be TC_STRING (0x74)
                    if f_desc_tc == TC_STRING:
                        f_desc = self._read_utf()
                    elif f_desc_tc == TC_REFERENCE:
                        handle = struct.unpack('>I', self.stream.read(4))[0]
                        f_desc = self.handles[handle - BASE_WIRE_HANDLE]
                else:
                    f_desc = f_type
                fields.append((f_name, f_desc))

            # Skip classDescInfo (endBlockData + superclass desc)
            end_tc = self.stream.read(1)[0]
            if end_tc == TC_ENDBLOCKDATA:
                super_tc = self.stream.read(1)[0]
                if super_tc != TC_NULL:
                    # If it has a superclass, we'd need to parse it recursively.
                    # For simplicity, we assume we skip or it's TC_NULL.
                    pass

            # Map to python class
            py_class_name = class_name.split('.')[-1]
            if len(py_class_name) <= 2 or py_class_name.islower():
                py_class_name = "Packet_" + py_class_name

            py_class = getattr(generated_packets, py_class_name, None)
            obj = py_class() if py_class else None
            
            # Register object in handles immediately before reading fields (crucial for circular refs)
            self.handles.append(obj)

            # Read field values
            if obj:
                for f_name, f_desc in fields:
                    val = self._read_field_value(f_desc)
                    setattr(obj, f_name, val)
            else:
                # If we don't have the class, skip its values
                for _, f_desc in fields:
                    self._read_field_value(f_desc)

            return obj

        else:
            raise NotImplementedError(f"Unsupported type code: {hex(tc)}")

    def _read_utf(self):
        length = struct.unpack('>H', self.stream.read(2))[0]
        return self.stream.read(length).decode('utf-8')

    def _read_field_value(self, desc):
        if desc == 'Z':
            return self.stream.read(1)[0] != 0
        elif desc == 'B':
            return struct.unpack('>b', self.stream.read(1))[0]
        elif desc == 'C':
            return struct.unpack('>H', self.stream.read(2))[0]
        elif desc == 'S':
            return struct.unpack('>h', self.stream.read(2))[0]
        elif desc == 'I':
            return struct.unpack('>i', self.stream.read(4))[0]
        elif desc == 'J':
            return struct.unpack('>q', self.stream.read(8))[0]
        elif desc == 'F':
            return struct.unpack('>f', self.stream.read(4))[0]
        elif desc == 'D':
            return struct.unpack('>d', self.stream.read(8))[0]
        else:
            # Object or Array type
            return self.read_object()


class JavaObjectOutputStream:
    def __init__(self, write_header=True):
        self.stream = io.BytesIO()
        self.handles = {}
        if write_header:
            self._write_header()

    def _write_header(self):
        self.stream.write(struct.pack('>HH', STREAM_MAGIC, STREAM_VERSION))

    def get_bytes(self):
        return self.stream.getvalue()

    def write_object(self, obj):
        if obj is None:
            self.stream.write(bytes([TC_NULL]))
            return

        obj_id = obj if isinstance(obj, str) else id(obj)
        if obj_id in self.handles:
            self.stream.write(bytes([TC_REFERENCE]))
            self.stream.write(struct.pack('>I', self.handles[obj_id]))
            return

        if isinstance(obj, str):
            utf_bytes = obj.encode('utf-8')
            if len(utf_bytes) <= 65535:
                self.stream.write(bytes([TC_STRING]))
                self.stream.write(struct.pack('>H', len(utf_bytes)))
            else:
                self.stream.write(bytes([TC_LONGSTRING]))
                self.stream.write(struct.pack('>Q', len(utf_bytes)))
            self.stream.write(utf_bytes)
            self.handles[obj_id] = BASE_WIRE_HANDLE + len(self.handles)
            return

        # It's a custom packet object
        self.stream.write(bytes([TC_OBJECT]))
        
        # Write Class Descriptor
        self.stream.write(bytes([TC_CLASSDESC]))
        
        # Reconstruct Java class name
        class_name = obj.__class__.__name__
        if class_name.startswith("Packet_"):
            class_name = class_name[7:]
        full_java_name = f"com.jayavon.game.a.{class_name}"
        
        self._write_utf(full_java_name)
        self.stream.write(struct.pack('>q', obj.serialVersionUID))
        self.stream.write(bytes([2])) # Flags: SC_SERIALIZABLE = 0x02
        
        fields = getattr(obj, '_fields', [])
        self.stream.write(struct.pack('>H', len(fields)))
        
        for f_name, f_desc in fields:
            self.stream.write(f_desc[0].encode('ascii'))
            self._write_utf(f_name)
            if f_desc[0] in ('[', 'L'):
                self.stream.write(bytes([TC_STRING]))
                self._write_utf(f_desc)

        self.stream.write(bytes([TC_ENDBLOCKDATA, TC_NULL])) # classdesc end

        # Register handle BEFORE writing field values
        self.handles[obj_id] = BASE_WIRE_HANDLE + len(self.handles)

        # Write field values
        for f_name, f_desc in fields:
            val = getattr(obj, f_name)
            self._write_field_value(val, f_desc)

    def _write_utf(self, val):
        utf_bytes = val.encode('utf-8')
        self.stream.write(struct.pack('>H', len(utf_bytes)))
        self.stream.write(utf_bytes)

    def _write_field_value(self, val, desc):
        if desc == 'Z':
            self.stream.write(bytes([1 if val else 0]))
        elif desc == 'B':
            self.stream.write(struct.pack('>b', val))
        elif desc == 'C':
            self.stream.write(struct.pack('>H', val))
        elif desc == 'S':
            self.stream.write(struct.pack('>h', val))
        elif desc == 'I':
            self.stream.write(struct.pack('>i', val))
        elif desc == 'J':
            self.stream.write(struct.pack('>q', val))
        elif desc == 'F':
            self.stream.write(struct.pack('>f', val))
        elif desc == 'D':
            self.stream.write(struct.pack('>d', val))
        else:
            self.write_object(val)
