# -*- coding: utf-8 -*-
import sys
import os
import bz2
import gzip
sys.path.insert(0, '.')
sys.path.insert(0, '../')
import unittest
# todo rm unused
from entropy.const import const_convert_to_rawstring, \
    const_mkstemp, const_is_python3
import entropy.tools as et
from entropy.compression import EntropyBZ2File, EntropyGzipFile

class CompressionTest(unittest.TestCase):
    """
    Tests for compression interface and capabilities that classes in
    compression.py (openers) must fullfill.
    """

    def _do_test_compression_write_method(self, std_unpack_func, opener, extension):

        s = const_convert_to_rawstring(
                "something not very interesting " * 10)

        for mode in ("wb", "w"):
            for compresslevel in (None, 1):
                fd, tmp_path = const_mkstemp(suffix = extension)

                if compresslevel is None:
                    bz2_f = opener(tmp_path, mode)
                else:
                    bz2_f = opener(
                            tmp_path, mode, compresslevel = compresslevel)

                bz2_f.write(s)
                bz2_f.close()

                compressed = os.read(fd, 512)
                self.assertTrue(len(compressed) < len(s))
                self.assertEqual(s, std_unpack_func(compressed))

                os.close(fd)
                os.remove(tmp_path)

    def test_bzip2_compression_write_method(self):
        self._do_test_compression_write_method(bz2.decompress, EntropyBZ2File, ".bz2")

    def test_gzip_compression_write_method(self):
        # gzip module from Python has no compress/decompress
        def _std_unpack_gz(data):
            fd, tmp_path = const_mkstemp()
            os.write(fd, data)
            with gzip.open(tmp_path, "rb") as f:
                ret = f.read()
            os.close(fd)
            os.remove(tmp_path)
            return ret

        self._do_test_compression_write_method(_std_unpack_gz, EntropyGzipFile, ".gz")

    def _do_test_unpack_read_method(self, std_compress_func, opener, extension):

        s = const_convert_to_rawstring("xyz " * 10)
        fd, tmp_path = const_mkstemp(suffix = extension)
        os.write(fd, std_compress_func(s))

        bz2_f = opener(tmp_path, "rb")
        decompressed = bz2_f.read()
        bz2_f.close()

        size = 15
        bz2_f = opener(tmp_path, "rb")
        decompressed_chunk = bz2_f.read(size)
        bz2_f.close()

        self.assertEqual(s, decompressed)
        self.assertEqual(s[:size], decompressed_chunk)

        os.close(fd)
        os.remove(tmp_path)

    def test_bzip2_unpack_read_method(self):
        self._do_test_unpack_read_method(bz2.compress, EntropyBZ2File, ".bz2")

    def test_gzip_unpack_read_method(self):
        def _std_compress_gz(data):
            fd, tmp_path = const_mkstemp(suffix = ".gz")
            with gzip.open(tmp_path, "wb") as gz_f:
                gz_f.write(data)
            ret = os.read(fd, 512)
            os.close(fd)
            os.remove(tmp_path)
            return ret

        self._do_test_unpack_read_method(_std_compress_gz, EntropyGzipFile, ".gz")

if __name__ == '__main__':
    unittest.main()
    raise SystemExit(0)
