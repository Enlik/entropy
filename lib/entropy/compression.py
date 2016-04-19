# -*- coding: utf-8 -*-
"""

    @author: Slawomir Nizio <slawomir.nizio@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Slawomir Nizio
    @license: GPL-2

    B{Entropy compression utils module}.

    This module contains implementation of compression formats.

"""

import gzip
import bz2
import subprocess

_LBZIP2_EXEC = "/usr/bin/lbzip2"

class AbstractEntropyCompressionFile(object):
    """
    Abstract base class for implementations providing standard interface for
    handling compressed files.
    """
    def __init__(self, filename, mode, compresslevel):
        raise NotImplementedError()

    def read(self, size=None):
        raise NotImplementedError()

    def write(self, data):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

class EntropyStandardBZ2File(AbstractEntropyCompressionFile):
    """
    Class providing standard implementation for handling bzip2 files.
    """
    def __init__(self, filename, mode, compresslevel=9):
        self._opener = bz2.BZ2File(filename, mode, compresslevel=compresslevel)

    def read(self, size=None):
        if size is None:
            return self._opener.read()
        else:
            return self._opener.read(size)

    def write(self, data):
        return self._opener.write(data)

    def close(self):
        return self._opener.close()

class EntropyParallelBZ2File(object):
    """
    Parallel bzip2 compression and decompression, using external command lbzip2.
    Note: lbzip2 produces one bzip2 stream when compression, so it can be
    opened using standard bz2 from Python 2, which does not support multiple
    streams.
    """
    _MODE_READ = 0
    _MODE_WRITE = 1

    def __init__(self, filename, mode, compresslevel=9):
        self.outf = None
        self.mode = None
        self._setup_proc(filename, mode, compresslevel)

    def _check_handle_cmd_error(self):
        rc = self.proc.returncode
        if rc is None or rc == 0:
            return
        if rc < 0:
            msg = "terminated by signal %s" % (-rc,)
        else:
            msg = "exited with status %s" % (rc,)
        raise OSError("Command failed: %s" % (msg,))

    def _setup_proc(self, filename, mode, compresslevel):
        if mode in ("rb",):
            self.mode = EntropyParallelBZ2File._MODE_READ
        elif mode in ("wb", "w"):
            self.mode = EntropyParallelBZ2File._MODE_WRITE
        else:
            raise ValueError("Unsupported mode %s." % (mode,))
        cmd = [_LBZIP2_EXEC]
        if self.mode == EntropyParallelBZ2File._MODE_READ:
            cmd += ["--decompress", "--stdout", filename]
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        else:
            if compresslevel in range(10):
                cmd += ["-" + str(compresslevel)]
            else:
                msg = "compresslevel should be numeric 0..9 not %s"
                raise ValueError(msg % (compresslevel,))
            cmd += ["--compress"]
            self.outf = open(filename, mode)
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=self.outf)
        self.mode = mode

    def read(self, *args, **kwargs):
        return self.proc.stdout.read(*args, **kwargs)

    def write(self, *args, **kwargs):
        self.proc.stdin.write(*args, **kwargs)

    def close(self):
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        if self.proc.stdout is not None:
            self.proc.stdout.close()
        if self.outf is not None:
            self.outf.close()
        self.proc.wait()
        self._check_handle_cmd_error()

EntropyBZ2File = EntropyParallelBZ2File
#EntropyBZ2File = EntropyStandardBZ2File

class EntropyGzipFile(AbstractEntropyCompressionFile):
    """
    Class providing standard implementation for handling gzip files.
    """
    def __init__(self, filename, mode, compresslevel=9):
        self._opener = gzip.GzipFile(filename, mode, compresslevel=compresslevel)

    def read(self, size=None):
        if size is None:
            return self._opener.read()
        else:
            return self._opener.read(size)

    def write(self, data):
        return self._opener.write(data)

    def close(self):
        return self._opener.close()
