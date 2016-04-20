# -*- coding: utf-8 -*-
"""

    @author: Slawomir Nizio <slawomir.nizio@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Slawomir Nizio
    @license: GPL-2

    B{Entropy compression utils module}.

    This module contains implementation of compression formats.

"""

import errno
import gzip
import bz2
import os
import subprocess

_LBZIP2_EXEC = "/usr/bin/lbzip2"

def _get_bz2threads_config():
    """
    Internal function to return configuration for parallel bzip2 operations.
    Returns False, None if disabled and True, t if enabled, where t is number
    of thread set in configuration or None if no default has been specified.
    """
    from entropy.client.interfaces import Client
    client_settings = Client().ClientSettings()
    config = client_settings['misc']['bz2threads']
    if config == -1:
        return False, None
    elif config == 0:
        return True, None
    else:
        return True, config

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

class EntropyParallelBZ2File(AbstractEntropyCompressionFile):
    """
    Parallel bzip2 compression and decompression, using external command lbzip2.
    Note: lbzip2 produces one bzip2 stream when compression, so it can be
    opened using standard bz2 from Python 2, which does not support multiple
    streams.
    """
    _MODE_READ = 0
    _MODE_WRITE = 1

    def __init__(self, filename, mode, compresslevel=9, threads=None):
        self.outf = None
        self.mode = None
        self._setup_proc(filename, mode, compresslevel, threads)

    def _check_handle_cmd_error(self):
        rc = self.proc.returncode
        if rc is None or rc == 0:
            return
        if rc < 0:
            msg = "terminated by signal %s" % (-rc,)
        else:
            msg = "exited with status %s" % (rc,)
        raise OSError("Command failed: %s" % (msg,))

    def _setup_proc(self, filename, mode, compresslevel, threads):
        if mode in ("rb",):
            self.mode = EntropyParallelBZ2File._MODE_READ
        elif mode in ("wb", "w"):
            self.mode = EntropyParallelBZ2File._MODE_WRITE
        else:
            raise ValueError("Unsupported mode %s." % (mode,))
        cmd = [_LBZIP2_EXEC]

        if threads is not None:
            cmd += ["-n", str(threads)]
        # otherwise lbzip2 performs autodection

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

class _StandardBz2Adapter(EntropyStandardBZ2File):
    """
    Adapter for the EntropyStandardBZ2File class.
    """
    def __init__(self, threads, *args):
        super(_StandardBz2Adapter, self).__init__(*args)

class _ParallelBz2Adapter(EntropyParallelBZ2File):
    """
    Adapter for the EntropyParallelBZ2File class.
    """
    def __init__(self, threads, *args):
        super(_ParallelBz2Adapter, self).__init__(*args, threads=threads)

class EntropyBZ2File(AbstractEntropyCompressionFile):
    """
    Class that proxies class implementing bzip2 compression according to
    settings and the environment (availability of the external program).

    It is preferred that consumers use this class instead of the proxied ones.
    """
    _BZIP2_IMPL_CACHE = None
    _BZIP2_THREADS = None

    @classmethod
    def __set_bzip2_impl(cls, impl_class):
        cls._BZIP2_IMPL_CACHE = impl_class
        return impl_class

    @classmethod
    def __get_bzip2_impl(cls):
        if cls._BZIP2_IMPL_CACHE is not None:
            return cls._BZIP2_IMPL_CACHE

        enabled, threads = _get_bz2threads_config()
        if not enabled:
            return cls.__set_bzip2_impl(_StandardBz2Adapter)

        if os.path.isfile(_LBZIP2_EXEC):
            cls._BZIP2_THREADS = threads
            return cls.__set_bzip2_impl(_ParallelBz2Adapter)
        else:
            return cls.__set_bzip2_impl(_StandardBz2Adapter)

    def __init__(self, filename, mode, compresslevel=9):
        impl_class = self.__get_bzip2_impl()
        fallback = False

        try:
            self._obj = impl_class(self._BZIP2_THREADS,
                                   filename,
                                   mode,
                                   compresslevel)
        except OSError as err:
            if err.errno in (errno.ENOENT, errno.EACCES):
                # compression program could have been removed from system
                fallback = True
            else:
                raise

        if fallback:
            impl_class = self.__set_bzip2_impl(_StandardBz2Adapter)
            self._obj = impl_class(None, filename, mode, compresslevel)

    def read(self, size=None):
        return self._obj.read(size)

    def write(self, data):
        return self._obj.write(data)

    def close(self):
        return self._obj.close()

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
