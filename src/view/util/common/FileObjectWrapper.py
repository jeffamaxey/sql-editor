
import wx, time
import re
import codecs
import locale

import logging.config
from src.view.constants import LOG_SETTINGS

from src.view.util.common.FileImpl import FileObjectBaseImpl
from src.view.util.common.FileChecker import FileTypeChecker
from io import StringIO
import sys
from src.view.util.common.fileutil import GetFileModTime, GetFileSize
import os
logging.config.dictConfig(LOG_SETTINGS)
logger = logging.getLogger('extensive')

#--------------------------------------------------------------------------#
# Globals

# The default fallback encoding
# DEFAULT_ENCODING = locale.getpreferredencoding()
# try:
#     codecs.lookup(DEFAULT_ENCODING)
# except (LookupError, TypeError):
DEFAULT_ENCODING = 'utf-8'

# File Helper Functions
# NOTE: keep in synch with CheckBom function
BOM = { 'utf-8'  : codecs.BOM_UTF8,
        'utf-16' : codecs.BOM,
        'utf-32' : codecs.BOM_UTF32 }

# Regex for extracting magic comments from source files
# i.e *-* coding: utf-8 *-*, encoding=utf-8, ect...
# The first group from this expression will be the encoding.
RE_MAGIC_COMMENT = re.compile("coding[:=]\s*\"*([-\w.]+)\"*")

# File Load States
FL_STATE_START = 0
FL_STATE_READING = 1
FL_STATE_PAUSED = 2
FL_STATE_END = 3
FL_STATE_ABORTED = 4

#--------------------------------------------------------------------------#


class ReadError(Exception):
    """Error happened while trying to read the file"""
    pass


class WriteError(Exception):
    """Error happened while trying to write the file"""
    pass


#--------------------------------------------------------------------------#
class FileObject(FileObjectBaseImpl):
    """Wrapper for representing a file object that stores data
    about the file encoding and path.

    """
    _Checker = FileTypeChecker()
    
    def __init__(self, path=u'', modtime=0):
        """Create the file wrapper object
        @keyword path: the absolute path to the file
        @keyword modtime: file modification time

        """
        super().__init__(path, modtime)

        # Attributes
        self._magic = dict(comment=None, bad=False)
        self.encoding = None
        self.bom = None
        self._mcallback = []
        self._buffer = None
        self._raw = False  # Raw bytes?
        self._fuzzy_enc = False
        self._job = None  # async file read job
        
    def _SanitizeBOM(self, bstring):
        """Remove byte order marks that get automatically added by some codecs"""
        bstring = bytes(bstring, 'utf-8')
        for enc in ('utf-8', 'utf-32', 'utf-16'):
            bmark = BOM.get(enc)
            if bstring.startswith(bmark):
                bstring = bstring.lstrip(bmark)
                break
        return bstring

    def _HandleRawBytes(self, bytes_value):
        """Handle prepping raw bytes for return to the buffer
        @param bytes_value: raw read bytes
        @return: string

        """
        logger.debug("[ed_txt][info] HandleRawBytes called")
        if self._magic['comment']:
            self._magic['bad'] = True
        # Return the raw bytes to put into the buffer
        self._raw = True
        return '\0'.join(bytes_value) + '\0'

    def _ResetBuffer(self):
        logger.debug("[ed_txt][info] Resetting buffer")
        if self._buffer is not None:
            self._buffer.flush()
            del self._buffer
        self._buffer = StringIO()
#         self.__setattr__('__buffer',io.StringIO)

    def AddModifiedCallback(self, callback):
        """Set modified callback method
        @param callback: callable

        """
        self._mcallback.append(callback)

    def CleanUp(self):
        """Cleanup callback"""
        pass

    def Clone(self):
        """Clone the file object
        @return: FileObject

        """
        fileobj = FileObject(self.Path, self.ModTime)
        fileobj.SetLastError(self.last_err)
        fileobj.SetEncoding(self.encoding)
        fileobj.bom = self.bom
        fileobj._magic = dict(self._magic)
        fileobj._fuzzy_enc = self._fuzzy_enc
        for cback in self._mcallback:
            fileobj.AddModifiedCallback(cback)
        return fileobj

    def DecodeText(self):
        """Decode the text in the buffer and return a unicode string.
        @return: unicode or str

        """
        assert self._buffer is not None, "No buffer!"
        assert self.encoding is not None, "Encoding Not Set!"

        bytes_value = self._buffer.getvalue()
        ustr = u""
        try:
            if not self._fuzzy_enc or not FileObject._Checker.IsBinaryBytes(bytes_value):
                if self.bom is not None:
                    logger.debug(f"[ed_txt][info] Stripping {self.encoding} BOM from text")
                    bytes_value = bytes_value.replace(self.bom, '', 1)

                logger.debug(f"[ed_txt][info] Attempting to decode with: {self.encoding}")
                ustr = bytes_value.decode(self.encoding)
                # TODO: temporary...maybe
                # Check for utf-16 encodings which use double bytes
                # can result in NULLs in the string if decoded with
                # other encodings.
                if '\0' in ustr:
                    logger.debug("[ed_txt][info] NULL terminators found in decoded str")
                    logger.debug("[ed_txt][info] Attempting UTF-16/32 detection...")
                    for utf_encoding in ('utf_16', 'utf_32'):
                        try:
                            tmpstr = bytes_value.decode(utf_encoding)
                        except UnicodeDecodeError:
                            pass
                        else:
                            self.encoding = utf_encoding
                            ustr = tmpstr
                            logger.debug(f"[ed_txt][info] {utf_encoding} detected")
                            break
                    else:
                        logger.debug("[ed_txt][info] No valid UTF-16/32 bytes detected")
            else:
                # Binary data was read
                logger.debug("[ed_txt][info] Binary bytes where read")
                ustr = self._HandleRawBytes(bytes_value)
        except (UnicodeDecodeError, LookupError) as msg:
            logger.debug(f"[ed_txt][err] Error while reading with {self.encoding}")
            logger.debug(f"[ed_txt][err] {msg}")
            self.SetLastError(msg)
            self.Close()
            # Decoding failed so convert to raw bytes for display
            ustr = self._HandleRawBytes(bytes_value)
        else:
            # logger.debug success
            if not self._raw:
                logger.debug(f"[ed_txt][info] Decoded {self.GetPath()} with {self.encoding}")

        # Scintilla bug, SetText will quit at first null found in the
        # string. So join the raw bytes and stuff them in the buffer instead.
        # TODO: are there other control characters that need to be checked
        #       for besides NUL?
        if not self._raw and '\0' in ustr:
            # Return the raw bytes to put into the buffer
            logger.debug("[ed_txt][info] DecodeText - joining nul terminators")
            ustr = '\0'.join(bytes_value) + '\0'
            self._raw = True

        if self._raw:
            # TODO: wx/Scintilla Bug?
            # Replace \x05 with a space as it causes the buffer
            # to crash when its inserted.
            logger.debug("[ed_txt][info] DecodeText - raw - set encoding to binary")
            ustr = ustr.replace('\x05', ' ')
            self.SetEncoding('binary')
            self._raw = True

        return ustr

    def DetectEncoding(self):
        """Try to determine the files encoding
        @precondition: File handle has been opened and is valid
        @postcondition: encoding and bom attributes will be set

        """
        if self.encoding != None:
            msg = ("[ed_txt][info] DetectEncoding, skipping do to user set "
                   "encoding: %s") % self.encoding
            logger.debug(msg)
            return

        assert self.Handle is not None, "File handle not initialized"
        lines = [self.Handle.readline() for _ in range(2)]
        self.Handle.seek(0)
        enc = None
        if len(lines):
            # First check for a Byte Order Mark
            enc = CheckBom(lines[0])

            # If no byte-order mark check for an encoding comment
            if enc is None:
                logger.debug("[ed_txt][info] DetectEncoding - Check magic comment")
                self.bom = None
                if not self._magic['bad']:
                    enc = CheckMagicComment(lines)
                    if enc:
                        self._magic['comment'] = enc
            else:
                logger.debug(f"[ed_txt][info] File Has {enc} BOM")
                self.bom = BOM.get(enc, None)

        if enc is None:
            logger.debug("[ed_txt][info] Doing brute force encoding check")
            enc = GuessEncoding(self.GetPath(), 4096)

        if enc is None:
            self._fuzzy_enc = True
#             enc = Profile_Get('ENCODING', default=DEFAULT_ENCODING)

        logger.debug(f"[ed_txt][info] DetectEncoding - Set Encoding to {enc}")
        self.encoding = enc 

    def EncodeText(self):
        """Do a trial run of encoding all the text to ensure that we can
        determine an encoding that will correctly be able to write the data
        to disk.
        @return: bool

        """
        bOk = True
        txt = self._buffer.read(8)
        self._buffer.seek(0)
#         if not IsUnicode(txt):
#             # Already a string so nothing to do
#             return bOk

        encs = GetEncodings()
#         if self.encoding is None:
#             self.encoding = Profile_Get('ENCODING', default=DEFAULT_ENCODING)
        encs.insert(0, self.encoding)
        cenc = self.encoding

        readsize = min(self._buffer.len, 4096)
        for enc in encs:
            self._buffer.seek(0)
            try:
                tmpchars = self._buffer.read(readsize)
                while len(tmpchars):
                    tmpchars.encode(enc)
                    tmpchars = self._buffer.read(readsize)
                self.encoding = enc
                self._buffer.seek(0)
                self.ClearLastError()
            except LookupError as msg:
                logger.debug(f"[ed_txt][err] Invalid encoding: {enc}")
                logger.debug(f"[ed_txt][err] {msg}")
                self.SetLastError(msg)
            except UnicodeEncodeError as msg:
                logger.debug(f"[ed_txt][err] Failed to encode text with {enc}")
                logger.debug(f"[ed_txt][err] {msg}")
                self.SetLastError(msg)
            else:
                break
        else:
            bOk = False
            raise WriteError("Failed to encode text to byte string")

        # logger.debug if the encoding changed due to encoding errors
        if self.encoding != cenc:
            logger.debug(
                f"[ed_txt][warn] Used encoding {self.encoding} differs from original {cenc}"
            )

        self._buffer.seek(0)
        return bOk

    def FireModified(self):
        """Fire the modified callback(s)"""
        remove = []
        for idx, mcallback in enumerate(self._mcallback):
            try:
                mcallback()
            except:
                remove.append(idx)

        # Cleanup any bad callbacks
        if len(remove):
            remove.reverse()
            for idx in remove:
                self._mcallback.pop(idx)

    def GetEncoding(self):
        """Get the encoding used by the file it may not be the
        same as the encoding requested at construction time
        @return: string encoding name

        """
        if self.encoding is None:
            self.encoding = DEFAULT_ENCODING
            # Guard against early entry
#             return Profile_Get('ENCODING', default=DEFAULT_ENCODING)
        return self.encoding

    def GetMagic(self):
        """Get the magic comment if one was present
        @return: string or None

        """
        return self._magic['comment']

    def HasBom(self):
        """Return whether the file has a bom byte or not
        @return: bool

        """
        return self.bom is not None

    def IsRawBytes(self):
        """Were only raw bytes read during the last read operation?
        @return: bool

        """
        return self._raw

    def IsReadOnly(self):
        """Return as read only when file is read only or if raw bytes"""
        return super().IsReadOnly() or self.IsRawBytes()

    def Read(self, chunk=512):
        """Get the contents of the file as a string, automatically handling
        any decoding that may be needed.
        @keyword chunk: read size
        @return: unicode str
        @throws: ReadError Failed to open file for reading

        """
        if self.DoOpen('rb'):
            self.DetectEncoding()

            if self.encoding is None:
                # fall back to user setting
#                 self.encoding = Profile_Get('ENCODING', default=DEFAULT_ENCODING)
                logger.debug(("[ed_txt][warn] Failed to detect encoding "
                    "falling back to default: %s") % self.encoding)

            self._ResetBuffer()
            self._raw = False

            logger.debug("[ed_txt][info] Read - Start reading")
            tmp = self.Handle.read(chunk)
            while len(tmp):
                self._buffer.write(tmp)
                tmp = self.Handle.read(chunk)
            logger.debug("[ed_txt][info] Read - End reading")

            self.Close()
            txt = self.DecodeText()
            self.SetModTime(GetFileModTime(self.GetPath()))
            self._ResetBuffer()
            return txt
        else:
            logger.debug(f"[ed_txt][err] Read Error: {self.GetLastError()}")
            raise (ReadError, self.GetLastError())

    def ReadAsync(self, control):
        """Read the file asynchronously on a separate thread
        @param control: text control to send text to

        """
        logger.debug("[ed_txt][info] FileObject.ReadAsync()")
        pid = control.GetTopLevelParent().Id
        filesize = GetFileSize(self.GetPath())
#         ed_msg.PostMessage(ed_msg.EDMSG_PROGRESS_STATE, (pid, 1, filesize))
        # Fork off async job to threadpool
        self._job = FileReadJob(control, self.ReadGenerator, 4096)
#         ed_thread.EdThreadPool().QueueJob(self._job.run)

    def ReadGenerator(self, chunk=512):
        """Get the contents of the file as a string, automatically handling
        any decoding that may be needed.

        @keyword chunk: read size
        @return: unicode (generator)
        @throws: ReadError Failed to open file for reading.

        """
        if not self.DoOpen('rb'):
            raise (ReadError, self.GetLastError())
        # Throttle yielded text to reduce event over head
        filesize = GetFileSize(self.Path)
        throttle = max(chunk, filesize / 100)

        self.DetectEncoding()
        try:
            # Must use codec reader to ensure correct number of
            # bytes are read in to be decoded.
            reader = codecs.getreader(self.Encoding)(self.Handle)
            buffered_data = StringIO()
            while True:
                tmp = reader.read(chunk)
                if not len(tmp):
                    if buffered_data.len:
                        yield buffered_data.getvalue()
                        buffered_data.close()
                    break

                buffered_data.write(tmp)
                if buffered_data.len >= throttle:
                    yield buffered_data.getvalue()
                    buffered_data.close()
                    buffered_data = StringIO()
        except Exception as msg:
            logger.debug(f"[ed_txt][err] Error while reading with {self.Encoding}")
            logger.debug(f"[ed_txt][err] {msg}")
            self.SetLastError(msg)
            self.Close()
            if self._magic['comment']:
                self._magic['bad'] = True

        logger.debug(f"[ed_txt][info] Decoded {self.Path} with {self.Encoding}")
        self.SetModTime(GetFileModTime(self.Path))

    def RemoveModifiedCallback(self, callback):
        """Remove a registered callback
        @param callback: callable to remove

        """
        if callback in self._mcallback:
            self._mcallback.remove(callback)

    def ResetAll(self):
        """Reset all attributes of this file"""
        super(FileObject, self).ResetAll()
        self._ResetBuffer()
        self._magic = dict(comment=None, bad=False)
#         self.encoding = Profile_Get('ENCODING', default=DEFAULT_ENCODING)
        self.bom = None

    def SetEncoding(self, enc):
        """Explicitly set/change the encoding of the file
        @param enc: encoding to change to

        """
        if enc is None:
            enc = DEFAULT_ENCODING
        self.encoding = enc

    def ReadLines(self):
        """Get the contents of the file as a list of lines
        @return: list of strings

        """
        raise NotImplementedError

    def Write(self, value):
        """Write the given value to the file
        @param value: (Unicode) String of text to write to disk
        @note: exceptions are allowed to be raised for the writing
        @throws: WriteError Failed to open file for writing
        @throws: UnicodeEncodeError Failed to encode text using set encoding

        """
        ctime = time.time()
        logger.debug("[ed_txt][info] Write - Called: %s - Time: %d" % (self.Path, ctime))

        # Check if a magic comment was added or changed
        self._ResetBuffer()
        self._buffer.write(value)
        self._buffer.seek(0)
        enc = CheckMagicComment([self._buffer.readline() for _ in range(2)])
        self._buffer.seek(0)

        if self.DoOpen('wb'):
                
            if self.HasBom():
                logger.debug("Adding BOM back to text")
                self.Handle.write(self.bom)

            # Write the file to disk
            self._buffer.seek(0, os.SEEK_END)
            chunk = min(self._buffer.tell(), 4096)
            self._buffer.seek(0)
            buffer_read = self._buffer.read
            filewrite = self.Handle.write
            fileflush = self.Handle.flush
            sanitize = self._SanitizeBOM
            tmp = buffer_read(chunk)
            while len(tmp):
                tmp_bytes = sanitize(tmp)
                filewrite(tmp_bytes)
                fileflush()
                tmp = buffer_read(chunk)

            self._ResetBuffer()  # Free buffer
            self.Close()
            logger.debug(f"[ed_txt][info] {self.Path} was written successfully")
        else:
            self._ResetBuffer()
            raise (WriteError, self.GetLastError())

        logger.debug("[ed_txt][info] Write - Complete: %s - Time: %d" % 
            (self.Path, time.time() - ctime))
#-----------------------------------------------------------------------------#


class FileReadJob(object):
    """Job for running an async file read in a background thread"""

    def __init__(self, receiver, task, *args, **kwargs):
        """Create the thread
        @param receiver: Window to receive events
        @param task: generator method to call
        @param *args: positional arguments to pass to task
        @param **kwargs: keyword arguments to pass to task

        """
        super(FileReadJob, self).__init__()

        # Attributes
        self.cancel = False
        self._task = task
        self.receiver = receiver
        self._args = args
        self._kwargs = kwargs
        self.pid = receiver.TopLevelParent.Id

    def run(self):
        """Read the text"""
        evt = FileLoadEvent(edEVT_FILE_LOAD, wx.ID_ANY, None, FL_STATE_START)
        wx.PostEvent(self.receiver, evt)
        time.sleep(.75)  # give ui a chance to get ready

        count = 1
        for txt in self._task(*self._args, **self._kwargs):
            if self.cancel:
                break

            evt = FileLoadEvent(edEVT_FILE_LOAD, wx.ID_ANY, txt)
            evt.SetProgress(count * self._args[0])
            wx.PostEvent(self.receiver, evt)
            count += 1

        evt = FileLoadEvent(edEVT_FILE_LOAD, wx.ID_ANY, None, FL_STATE_END)
        wx.PostEvent(self.receiver, evt)

    def Cancel(self):
        """Cancel the running task"""
        self.cancel = True

#-----------------------------------------------------------------------------#


edEVT_FILE_LOAD = wx.NewEventType()
EVT_FILE_LOAD = wx.PyEventBinder(edEVT_FILE_LOAD, 1)


class FileLoadEvent(wx.PyEvent):
    """Event to signal that a chunk of text haes been read"""

    def __init__(self, etype, eid, value=None, state=FL_STATE_READING):
        """Creates the event object"""
        super(FileLoadEvent, self).__init__(eid, etype)

        # Attributes
        self._state = state
        self._value = value
        self._prog = 0
    
    def HasText(self):
        """Returns true if the event has text
        @return: bool whether the event contains text

        """
        return self._value is not None

    def GetProgress(self):
        """Get the current progress of the load"""
        return self._prog

    def GetState(self):
        """Get the state of the file load action
        @return: int (FL_STATE_FOO)

        """
        return self._state

    def GetValue(self):
        """Returns the value from the event.
        @return: the value of this event

        """
        return self._value

    def SetProgress(self, progress):
        """Set the number of bytes that have been read
        @param progress: int

        """
        self._prog = progress


#-----------------------------------------------------------------------------#
# Utility Function
def CheckBom(line):
    """Try to look for a bom byte at the beginning of the given line
    @param line: line (first line) of a file
    @return: encoding or None

    """
    logger.debug("[ed_txt][info] CheckBom called")
    has_bom = None
    # NOTE: MUST check UTF-32 BEFORE utf-16
    for enc in ('utf-8', 'utf-32', 'utf-16'):
        bom = BOM[enc]
        if line.startswith(bom):
            has_bom = enc
            break
    return has_bom


def CheckMagicComment(lines):
    """Try to decode the given text on the basis of a magic
    comment if one is present.
    @param lines: list of lines to check for a magic comment
    @return: encoding or None

    """
    logger.debug(f"[ed_txt][info] CheckMagicComment: {str(lines)}")
    enc = None
    for line in lines:
        if isinstance(line, str):
            if match := RE_MAGIC_COMMENT.search(line):
                enc = match.group(1)
                try:
                    codecs.lookup(enc)
                except LookupError:
                    enc = None
                break

    logger.debug(f"[ed_txt][info] MagicComment is {enc}")
    return enc


def DecodeString(string, encoding=None):
    """Decode the given string to Unicode using the provided
    encoding or the DEFAULT_ENCODING if None is provided.
    @param string: string to decode
    @keyword encoding: encoding to decode string with

    """
    if encoding is None:
        encoding = DEFAULT_ENCODING

    try:
        rtxt = string.decode(encoding)
    except Exception as msg:
        logger.debug(f"[ed_txt][err] DecodeString with {encoding} failed")
        logger.debug(f"[ed_txt][err] {msg}")
        rtxt = string
    return rtxt


def EncodeString(string, encoding=None):
    """Try and encode a given unicode object to a string
    with the provided encoding returning that string. The
    default encoding will be used if None is given for the
    encoding.
    @param string: unicode object to encode into a string
    @keyword encoding: encoding to use for conversion

    """
    if not encoding:
        encoding = DEFAULT_ENCODING

    try:
        rtxt = string.encode(encoding)
    except LookupError:
        rtxt = string
    return rtxt


def FallbackReader(fname):
    """Guess the encoding of a file by brute force by trying one
    encoding after the next until something succeeds.
    @param fname: file path to read from
    @todo: deprecate this method

    """
    txt = None
    with open(fname, 'rb') as handle:
        byte_str = handle.read()
        for enc in GetEncodings():
            try:
                txt = byte_str.decode(enc)
            except Exception as msg:
                continue
            else:
                return (enc, txt)

    return (None, None)


def GuessEncoding(fname, sample):
    """Attempt to guess an encoding
    @param fname: filename
    @param sample: pre-read amount
    @return: encoding or None

    """
    for enc in GetEncodings():
        try:
            with open(fname, 'rb') as handle:
                with codecs.getreader(enc)(handle) as reader:
                    value = reader.read(sample)
                    if '\0' in value:
                        continue
                    else:
                        return enc
        except Exception as msg:
            continue
    return None


def GetEncodings():
    """Get a list of possible encodings to try from the locale information
    @return: list of strings

    """
    encodings = []
#     encodings.append(Profile_Get('ENCODING', None))

    try:
        encodings.append(locale.getpreferredencoding())
    except:
        pass

    encodings.append('utf-8')

#     try:
#         if hasattr(locale, 'nl_langinfo'):
#             encodings.append(locale.nl_langinfo(locale.CODESET))
#     except:
#         pass
    try:
        encodings.append(locale.getlocale()[1])
    except:
        pass
    try:
        encodings.append(locale.getdefaultlocale()[1])
    except:
        pass
    encodings.extend(
        (sys.getfilesystemencoding(), 'utf-16', 'utf-16-le', 'latin-1')
    )
    # Normalize all names
#     normlist = [ encodings.normalize_encoding(enc) for enc in encodings if enc]

    # Clean the list for duplicates and None values
    rlist = []
    codec_list = []
    for enc in encodings:
        if enc is not None and len(enc):
            enc = enc.lower()
            if enc not in rlist:
                # Ascii is useless so ignore it (ascii, us_ascii, ...)
                if 'ascii' in enc:
                    continue

                try:
                    ctmp = codecs.lookup(enc)
                    if ctmp.name not in codec_list:
                        codec_list.append(ctmp.name)
                        rlist.append(enc)
                except LookupError:
                    pass
    return rlist
