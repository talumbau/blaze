from __future__ import absolute_import, division, print_function

import unittest
import tempfile
import os
import csv
import sys

import datashape

from blaze.compatibility import skipIf
from blaze.data.core import DataDescriptor
from blaze.data import CSV
from blaze.data.csv import has_header, discover_dialect
from blaze.utils import filetext
from blaze.data.utils import tuplify
from dynd import nd


def sanitize(lines):
    return '\n'.join(line.strip() for line in lines.split('\n'))


class Test_Indexing(unittest.TestCase):

    buf = sanitize(
    u"""Name Amount
        Alice 100
        Bob 200
        Alice 50
    """)

    schema = "{ name: string, amount: int }"

    def setUp(self):
        self.csv_file = tempfile.mktemp(".csv")
        with open(self.csv_file, "w") as f:
            f.write(self.buf)
        self.dd = CSV(self.csv_file, dialect='excel', schema=self.schema,
                            delimiter=' ', mode='r+')
        assert self.dd.header

    def tearDown(self):
        os.remove(self.csv_file)

    def test_row(self):
        self.assertEqual(tuplify(self.dd.py[0]), ('Alice', 100))
        self.assertEqual(tuplify(self.dd.py[1]), ('Bob', 200))

    def test_dynd(self):
        assert isinstance(self.dd.dynd[0], nd.array)

    def test_rows(self):
        self.assertEqual(tuplify(self.dd.py[[0, 1]]), (('Alice', 100), ('Bob', 200)))


    def test_point(self):
        self.assertEqual(self.dd.py[0, 0], 'Alice')
        self.assertEqual(self.dd.py[1, 1], 200)

    def test_nested(self):
        self.assertEqual(tuplify(self.dd.py[[0, 1], 0]), ('Alice', 'Bob'))
        self.assertEqual(tuplify(self.dd.py[[0, 1], 1]), (100, 200))
        self.assertEqual(tuplify(self.dd.py[0, [0, 1]]), ('Alice', 100))
        self.assertEqual(tuplify(self.dd.py[[1, 0], [0, 1]]),
                        (('Bob', 200), ('Alice', 100)))

    def test_slices(self):
        self.assertEqual(list(self.dd.py[:, 1]), [100, 200, 50])
        self.assertEqual(list(self.dd.py[1:, 1]), [200, 50])
        self.assertEqual(list(self.dd.py[0, :]), ['Alice', 100])

    def test_names(self):
        self.assertEqual(list(self.dd.py[:, 'name']), ['Alice', 'Bob', 'Alice'])
        self.assertEqual(tuplify(self.dd.py[:, ['amount', 'name']]),
                    ((100, 'Alice'), (200, 'Bob'), (50, 'Alice')))

    def test_dynd_complex(self):
        self.assertEqual(self.dd.py[:, ['amount', 'name']],
                nd.as_py(self.dd.dynd[:, ['amount', 'name']], tuple=True))


class Test_Dialect(unittest.TestCase):

    buf = sanitize(
    u"""Name Amount
        Alice 100
        Bob 200
        Alice 50
    """)

    schema = "{ f0: string, f1: int }"

    def setUp(self):
        self.csv_file = tempfile.mktemp(".csv")
        with open(self.csv_file, "w") as f:
            f.write(self.buf)
        self.dd = CSV(self.csv_file, dialect='excel', schema=self.schema,
                            delimiter=' ', mode='r+')

    def tearDown(self):
        os.remove(self.csv_file)

    @skipIf(sys.version_info[:2] < (2, 7), 'CSV module unable to parse')
    def test_has_header(self):
        assert has_header(self.buf)

    def test_overwrite_delimiter(self):
        self.assertEquals(self.dd.dialect['delimiter'], ' ')

    def test_content(self):
        s = str(list(self.dd))
        assert 'Alice' in s and 'Bob' in s

    def test_append(self):
        self.dd.extend([('Alice', 100)])
        with open(self.csv_file) as f:
            self.assertEqual(f.readlines()[-1].strip(), 'Alice 100')

    def test_append_dict(self):
        self.dd.extend([{'f0': 'Alice', 'f1': 100}])
        with open(self.csv_file) as f:
            self.assertEqual(f.readlines()[-1].strip(), 'Alice 100')

    def test_extend_structured(self):
        with filetext('1,1.0\n2,2.0\n') as fn:
            csv = CSV(fn, 'r+', schema='{x: int32, y: float32}',
                            delimiter=',')
            csv.extend([(3, 3)])
            assert tuplify(tuple(csv)) == ((1, 1.0), (2, 2.0), (3, 3.0))

    def test_discover_dialect(self):
        s = '1,1\r\n2,2'
        self.assertEqual(discover_dialect(s),
                {'escapechar': None,
                 'skipinitialspace': False,
                 'quoting': 0,
                 'delimiter': ',',
                 'lineterminator': '\r\n',
                 'quotechar': '"',
                 'doublequote': False})


class TestCSV_New_File(unittest.TestCase):

    data = (('Alice', 100),
            ('Bob', 200),
            ('Alice', 50))

    schema = "{ f0: string, f1: int32 }"

    def setUp(self):
        self.filename = tempfile.mktemp(".csv")

    def tearDown(self):
        if os.path.exists(self.filename):
            os.remove(self.filename)

    def test_errs_without_dshape(self):
        self.assertRaises(ValueError, lambda: CSV(self.filename, 'w'))

    def test_creation(self):
        dd = CSV(self.filename, 'w', schema=self.schema, delimiter=' ')

    def test_creation_rw(self):
        dd = CSV(self.filename, 'w+', schema=self.schema, delimiter=' ')

    def test_append(self):
        dd = CSV(self.filename, 'w', schema=self.schema, delimiter=' ')
        dd.extend([self.data[0]])
        with open(self.filename) as f:
            self.assertEqual(f.readlines()[0].strip(), 'Alice 100')

    def test_extend(self):
        dd = CSV(self.filename, 'w', schema=self.schema, delimiter=' ')
        dd.extend(self.data)
        with open(self.filename) as f:
            lines = f.readlines()
            self.assertEqual(lines[0].strip(), 'Alice 100')
            self.assertEqual(lines[1].strip(), 'Bob 200')
            self.assertEqual(lines[2].strip(), 'Alice 50')

        expected_dshape = datashape.DataShape(datashape.Var(), self.schema)
        # TODO: datashape comparison is broken
        self.assertEqual(str(dd.dshape).replace(' ', ''),
                         str(expected_dshape).replace(' ', ''))

class TestTransfer(unittest.TestCase):

    def test_re_dialect(self):
        dialect1 = {'delimiter': ',', 'lineterminator': '\n'}
        dialect2 = {'delimiter': ';', 'lineterminator': '--'}

        text = '1,1\n2,2\n'

        schema = '2 * int32'

        with filetext(text) as source_fn:
            with filetext('') as dest_fn:
                src = CSV(source_fn, schema=schema, **dialect1)
                dst = CSV(dest_fn, mode='w', schema=schema, **dialect2)

                # Perform copy
                dst.extend(src)

                with open(dest_fn) as f:
                    self.assertEquals(f.read(), '1;1--2;2--')


    def test_iter(self):
        with filetext('1,1\n2,2\n') as fn:
            dd = CSV(fn, schema='2 * int32')
            self.assertEquals(tuplify(list(dd)), ((1, 1), (2, 2)))


    def test_chunks(self):
        with filetext('1,1\n2,2\n3,3\n4,4\n') as fn:
            dd = CSV(fn, schema='2 * int32')
            assert all(isinstance(chunk, nd.array) for chunk in dd.chunks())
            self.assertEquals(len(list(dd.chunks(blen=2))), 2)
            self.assertEquals(len(list(dd.chunks(blen=3))), 2)


    def test_iter_structured(self):
        with filetext('1,2\n3,4\n') as fn:
            dd = CSV(fn, schema='{x: int, y: int}')
            self.assertEquals(tuplify(list(dd)), ((1, 2), (3, 4)))


class TestCSV(unittest.TestCase):

    # A CSV toy example
    buf = sanitize(
    u"""k1,v1,1,False
        k2,v2,2,True
        k3,v3,3,False
    """)

    data = (('k1', 'v1', 1, False),
            ('k2', 'v2', 2, True),
            ('k3', 'v3', 3, False))

    schema = "{ f0: string, f1: string, f2: int16, f3: bool }"

    def setUp(self):
        self.csv_file = tempfile.mktemp(".csv")
        with open(self.csv_file, "w") as f:
            f.write(self.buf)

    def tearDown(self):
        os.remove(self.csv_file)

    def test_has_header(self):
        assert not has_header(self.buf)

    def test_basic_object_type(self):
        dd = CSV(self.csv_file, schema=self.schema)
        self.assertTrue(isinstance(dd, DataDescriptor))
        self.assertTrue(isinstance(dd.dshape.shape[0], datashape.Var))

    def test_iter(self):
        dd = CSV(self.csv_file, schema=self.schema)

        self.assertEqual(tuplify(tuple(dd)), self.data)

    def test_as_py(self):
        dd = CSV(self.csv_file, schema=self.schema)

        self.assertEqual(tuplify(dd.as_py()), self.data)

    def test_getitem_start(self):
        dd = CSV(self.csv_file, schema=self.schema)
        self.assertEqual(tuplify(dd.py[0]), self.data[0])

    def test_getitem_stop(self):
        dd = CSV(self.csv_file, schema=self.schema)
        self.assertEqual(tuplify(dd.py[:1]), self.data[:1])

    def test_getitem_step(self):
        dd = CSV(self.csv_file, schema=self.schema)
        self.assertEqual(tuplify(dd.py[::2]), self.data[::2])

    def test_getitem_start_step(self):
        dd = CSV(self.csv_file, schema=self.schema)
        self.assertEqual(tuplify(dd.py[1::2]), self.data[1::2])


if __name__ == '__main__':
    unittest.main()