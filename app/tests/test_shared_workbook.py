"""The shared copy must never overwrite an editor's newer saved changes."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import os
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

    def test_archived_month_stays_archived_after_sync_and_preserves_edit_checks(self):
        shared.publish(self.place, self.db, self.month)
        archive = self.place / 'Archive'
        archive.mkdir()
        archived = archive / self.target.name
        self.target.rename(archived)
        self.assertIsNone(shared.pull(self.place, self.place, self.db, None, self.month))
        self.local.write_bytes(b'new verified month')
        self.assertEqual(shared.publish(self.place, self.db, self.month), str(archived))
        self.assertFalse(self.target.exists())
        self.assertEqual(archived.read_bytes(), b'new verified month')
        archived.write_bytes(b'new teammate correction')
        with self.assertRaisesRegex(ValueError, 'changed during refresh'):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(archived.read_bytes(), b'new teammate correction')

    def test_two_shared_copies_require_review_instead_of_choosing_one(self):
        shared.publish(self.place, self.db, self.month)
        archive = self.place / 'Archive'
        archive.mkdir()
        archived = archive / self.target.name
        archived.write_bytes(b'another report copy')
        with self.assertRaisesRegex(ValueError, 'both the shared folder and Archive'):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(archived.read_bytes(), b'another report copy')
        self.assertEqual(self.target.read_bytes(), b'first validated workbook')

    def test_stop_before_replace_retains_shared_workbook_and_removes_staging_file(self):
        from operation_control import Cancelled
        shared.publish(self.place, self.db, self.month)
        self.local.write_bytes(b'new verified workbook')
        previous = shared.expected(self.db, self.month)
        with patch('operation_control.check_cancelled', side_effect=Cancelled()):
            with self.assertRaises(Cancelled):
                shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'first validated workbook')
        self.assertEqual(shared.expected(self.db, self.month), previous)
        self.assertEqual(list(self.place.glob('*.tmp')), [])

    def test_existing_unknown_file_is_never_replaced(self):
        self.target.write_bytes(b'someone else owns this workbook')
        with self.assertRaisesRegex(ValueError, 'not published by this app'):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'someone else owns this workbook')

    def test_open_excel_owner_file_blocks_publication(self):
        shared.publish(self.place, self.db, self.month)
        self.local.write_bytes(b'new verified workbook')
        for name in (self.target.name, self.target.name[2:]):
            with self.subTest(owner=name):
                owner = self.target.with_name('~$' + name)
                owner.write_bytes(b'open in Excel')
                try:
                    with self.assertRaisesRegex(ValueError, 'open in Excel'):
                        shared.publish(self.place, self.db, self.month)
                    with self.assertRaisesRegex(ValueError, 'open in Excel'):
                        shared.pull(self.place, self.place, self.db, None, self.month)
                    self.assertEqual(self.target.read_bytes(), b'first validated workbook')
                finally: owner.unlink()

    def denied_rename(self):
        error = PermissionError('SMB permits writing but denies replacement')
        error.winerror = 5
        return error

    @unittest.skipUnless(os.name == 'nt', 'Windows exclusive-file API')
    def test_denied_replace_saves_exclusively_with_verified_backup(self):
        shared.publish(self.place, self.db, self.month)
        original = self.target.read_bytes()
        self.local.write_bytes(b'new verified data with different length')
        with patch.object(Path, 'replace', side_effect=self.denied_rename()):
            shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), self.local.read_bytes())
        self.assertEqual(shared.expected(self.db, self.month), shared.digest(self.local.read_bytes()))
        self.assertTrue(any(p.read_bytes() == original for p in (self.place/'Backups').glob('*.xlsx')))
        self.assertEqual(list(self.place.glob('*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows exclusive-file API')
    def test_failed_exclusive_write_restores_previous_bytes_and_baseline(self):
        shared.publish(self.place, self.db, self.month)
        original = self.target.read_bytes(); previous = shared.expected(self.db, self.month)
        self.local.write_bytes(b'new verified workbook')
        write = shared.write_locked
        def fail_once(stream, content):
            if content != original:
                stream.seek(0); stream.write(b'partial'); stream.flush()
                raise OSError('Connection interrupted during save')
            write(stream, content)
        with patch.object(Path, 'replace', side_effect=self.denied_rename()), patch.object(shared, 'write_locked', side_effect=fail_once):
            with self.assertRaisesRegex(ValueError, 'previous workbook was restored'):
                shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(shared.expected(self.db, self.month), previous)

    @unittest.skipUnless(os.name == 'nt', 'Windows exclusive-file API')
    def test_other_open_handle_blocks_fallback_without_overwriting(self):
        shared.publish(self.place, self.db, self.month)
        original = self.target.read_bytes()
        with shared.exclusive_file(self.target):
            with self.assertRaisesRegex(ValueError, 'Shared update pending'):
                shared.save_exclusively(self.target, b'new bytes', shared.digest(original))
        self.assertEqual(self.target.read_bytes(), original)

    @unittest.skipUnless(os.name == 'nt', 'Windows exclusive-file API')
    def test_edit_saved_between_replace_failure_and_fallback_is_retained(self):
        shared.publish(self.place, self.db, self.month)
        previous = shared.expected(self.db, self.month)
        self.local.write_bytes(b'new verified workbook')
        def late_edit(*args):
            self.target.write_bytes(b'a teammates latest correction')
            raise self.denied_rename()
        with patch.object(Path, 'replace', side_effect=late_edit):
            with self.assertRaisesRegex(ValueError, 'changed during publishing'):
                shared.publish(self.place, self.db, self.month)
        self.assertEqual(self.target.read_bytes(), b'a teammates latest correction')
        self.assertEqual(shared.expected(self.db, self.month), previous)

    def test_unchanged_sync_does_not_replace_workbook(self):
        shared.publish(self.place, self.db, self.month)
        with patch.object(Path, 'replace', side_effect=AssertionError('Unnecessary replacement')):
            shared.publish(self.place, self.db, self.month)


if __name__ == '__main__':
    unittest.main()
