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

class EntropyBZ2File(AbstractEntropyCompressionFile):
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
