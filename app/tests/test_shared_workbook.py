"""The shared copy must never overwrite an editor's newer saved changes."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shared_workbook as shared


class SharedWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.place = Path(self.temp.name)
        self.local = self.place / 'verified.xlsx'
        self.local.write_bytes(b'first validated workbook')
        (self.place / 'validation.json').write_text('{"passed":true}', encoding='utf8')
        self.database = self.place / 'state.sqlite'
        with self.db() as c:
            shared.initialize(c)
        self.month = '2026-10'
        self.target = self.place / shared.filename(self.month)
        self.folder_patch = patch.object(shared, 'folder', return_value=self.place)
        self.book_patch = patch.object(shared, 'local_book', return_value=self.local)
        self.folder_patch.start(); self.book_patch.start()
        self.addCleanup(self.folder_patch.stop); self.addCleanup(self.book_patch.stop)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.database)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def test_imported_edit_is_published_and_a_later_edit_is_never_overwritten(self):
        self.assertEqual(shared.publish(self.place, self.db, self.month), str(self.target))
        self.assertEqual(self.target.read_bytes(), b'first validated workbook')
        self.target.write_bytes(b'edited by teammate')

        def import_edit(*args):
            self.assertEqual(args[-1], b'edited by teammate')
            self.local.write_bytes(b'validated workbook with teammate edit')
            return {'message': 'Saved correction'}

        with patch.object(shared.manual_edits, 'save', side_effect=import_edit):
            shared.pull(self.place, self.place, self.db, None, self.month)
        self.assertEqual(shared.expected(self.db, self.month), shared.digest(b'edited by teammate'))
        self.target.write_bytes(b'new edit while refresh was running')
        with self.assertRaisesRegex(ValueError, 'changed during refresh'):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'new edit while refresh was running')
        self.target.write_bytes(b'edited by teammate')
        shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'validated workbook with teammate edit')

    def test_missing_shared_file_stops_publish(self):
        shared.publish(self.place, self.db, self.month)
        self.target.unlink()
        with self.assertRaisesRegex(ValueError, 'missing from the shared folder'):
            shared.publish(self.place, self.db, self.month)

    def test_existing_unknown_file_is_never_replaced(self):
        self.target.write_bytes(b'someone else owns this workbook')
        with self.assertRaisesRegex(ValueError, 'not published by this app'):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'someone else owns this workbook')

    def test_open_excel_owner_file_blocks_publication(self):
        shared.publish(self.place, self.db, self.month)
        owner = self.target.with_name('~$' + self.target.name[2:])
        owner.write_bytes(b'open in Excel')
        self.local.write_bytes(b'new verified workbook')
        with self.assertRaisesRegex(ValueError, 'open in Excel'):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'first validated workbook')


if __name__ == '__main__':
    unittest.main()
