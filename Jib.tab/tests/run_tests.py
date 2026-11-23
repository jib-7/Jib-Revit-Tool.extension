# -*- coding: utf-8 -*-
"""Offline tests for ACC Quick Access (run with desktop Python 3, NOT inside Revit):

    python tests/run_tests.py

They exercise the data layer, validation, project detection logic (with fake model data
and fake Revit document objects), URL opening (launcher mocked), backup/restore and
static checks of the UI definitions. They cannot test real WPF windows, the ribbon or
real ACC/Revit behaviour - see docs/TEST_CHECKLIST.md for those.
"""
import ast
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.dom.minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

TMP = tempfile.mkdtemp(prefix="accqa_test_")
os.environ["ACCQA_DATA_DIR"] = TMP

from accqa import (acc_url_manager, backup_manager, config_manager as cfg, folder_manager,  # noqa: E402
                   project_detector, recent_manager, revit_compat, ui_xaml, validation)
from accqa.validation import ValidationError  # noqa: E402

URL1 = "https://acc.autodesk.com/docs/files/projects/11111111-2222-3333-4444-555555555555?folderUrn=urn%3Aadsk.wipprod%3Afs.folder%3Aco.AAA&viewModel=detail&moduleId=folders"
URL2 = "https://acc.autodesk.com/docs/files/projects/11111111-2222-3333-4444-555555555555?folderUrn=urn%3Aadsk.wipprod%3Afs.folder%3Aco.BBB"
URL3 = "https://acc.autodesk.com/docs/files/projects/99999999-2222-3333-4444-555555555555?folderUrn=urn%3Aadsk.wipprod%3Afs.folder%3Aco.CCC"


def fresh():
    """Start every test with an empty data folder."""
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP)
    cfg.take_notice()


class ValidationTests(unittest.TestCase):
    def test_url_rules(self):
        self.assertEqual(validation.validate_url("  " + URL1 + "\n"), URL1)  # only whitespace trimmed
        for bad in ("", "   ", "ftp://x.com/a", "file:///c:/windows/notepad.exe", "javascript:alert(1)",
                    "acc.autodesk.com/docs", "https://", "https://a b.com", "http://x.com/a b"):
            with self.assertRaises(ValidationError, msg=bad):
                validation.validate_url(bad)

    def test_autodesk_hint(self):
        self.assertTrue(validation.is_autodesk_url(URL1))
        self.assertFalse(validation.is_autodesk_url("https://example.com/x"))
        self.assertFalse(validation.is_autodesk_url("https://notautodesk.com/x"))

    def test_category_and_names(self):
        self.assertEqual(validation.validate_category("wip"), "WIP")
        with self.assertRaises(ValidationError):
            validation.validate_category("")
        self.assertEqual(validation.normalize_name("  EMAAR \u2013  Dubai   Hills "), "emaar - dubai hills")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        fresh()

    def test_first_load_creates_directory_and_file(self):
        shutil.rmtree(TMP)
        data = cfg.load()
        self.assertTrue(os.path.exists(cfg.config_path()))
        self.assertEqual(data["version"], "1.0")
        self.assertEqual(data["projects"], [])
        self.assertTrue(data["settings"]["auto_detect_project"])

    def test_save_load_roundtrip_utf8_and_backup(self):
        folder_manager.add_link(u"\u0645\u0634\u0631\u0648\u0639 Dubai Hills", "3929", "Shared", "Shared", URL1)
        folder_manager.add_link(u"\u0645\u0634\u0631\u0648\u0639 Dubai Hills", "3929", "WIP", "WIP", URL2)
        self.assertTrue(os.path.exists(cfg.config_path() + ".bak"))
        data = cfg.load()
        self.assertEqual(data["projects"][0]["project_name"], u"\u0645\u0634\u0631\u0648\u0639 Dubai Hills")
        raw = open(cfg.config_path(), "rb").read()
        raw.decode("utf-8")  # must be valid UTF-8

    def test_corrupted_file_is_kept_and_backup_restored(self):
        folder_manager.add_link("P1", "1001", "Shared", "Shared", URL1)
        folder_manager.add_link("P1", "1001", "WIP", "WIP", URL2)   # creates .bak holding the 1-folder version
        with open(cfg.config_path(), "wb") as handle:
            handle.write(b"{ this is not json")
        data = cfg.load()
        self.assertEqual(len(data["projects"]), 1)
        self.assertTrue(cfg.take_notice())
        self.assertTrue(glob.glob(os.path.join(TMP, "config.corrupt-*.json")))
        cfg.read_json_file(cfg.config_path())  # repaired file is valid again

    def test_corrupted_without_backup_gives_empty_config(self):
        os.makedirs(TMP, exist_ok=True)
        with open(cfg.config_path(), "wb") as handle:
            handle.write(b"\x00\x01garbage")
        data = cfg.load()
        self.assertEqual(data["projects"], [])
        self.assertTrue(cfg.take_notice())

    def test_spec_example_schema_is_accepted_and_migrated(self):
        example = {"version": "1.0", "projects": [{
            "project_id": "3929", "project_name": "EMAAR Dubai Hills Estate", "cloud_project_guid": "",
            "models": [], "folders": [
                {"folder_id": "shared_01", "folder_name": "Shared", "category": "Shared", "url": "https://example.autodesk.com/", "description": ""}]}],
            "recent_projects": [], "settings": {"auto_detect_project": True, "open_in_default_browser": True}}
        os.makedirs(TMP, exist_ok=True)
        with open(cfg.config_path(), "w") as handle:
            json.dump(example, handle)
        data = cfg.load()
        project = data["projects"][0]
        self.assertEqual(project["project_number"], "3929")
        self.assertEqual(data["settings"]["max_recent_projects"], 10)  # missing keys filled in
        self.assertEqual(project["folders"][0]["folder_id"], "shared_01")  # existing ids preserved

    def test_unknown_keys_preserved(self):
        folder_manager.add_link("P1", "", "Shared", "Shared", URL1)
        raw = cfg.read_json_file(cfg.config_path())
        raw["future_feature"] = {"a": 1}
        raw["projects"][0]["extra"] = "keep me"
        cfg.write_json_atomic(cfg.config_path(), raw)
        folder_manager.add_link("P1", "", "WIP", "WIP", URL2)
        after = cfg.read_json_file(cfg.config_path())
        self.assertEqual(after["future_feature"], {"a": 1})
        self.assertEqual(after["projects"][0]["extra"], "keep me")

    def test_reset_settings_keeps_projects_and_reset_all_backs_up(self):
        folder_manager.add_link("P1", "1001", "Shared", "Shared", URL1)
        cfg.update_settings({"confirm_delete": False, "max_recent_projects": 3})
        self.assertFalse(cfg.get_settings(cfg.load())["confirm_delete"])
        cfg.reset_settings()
        data = cfg.load()
        self.assertTrue(data["settings"]["confirm_delete"])
        self.assertEqual(len(data["projects"]), 1)
        backup = cfg.reset_all_data()
        self.assertTrue(backup and os.path.exists(backup))
        self.assertEqual(cfg.load()["projects"], [])

    def test_no_credentials_in_file(self):
        folder_manager.add_link("P1", "1", "Shared", "Shared", URL1)
        text = open(cfg.config_path()).read().lower()
        for word in ("password", "token", "secret", "credential"):
            self.assertNotIn(word, text)


class FolderManagerTests(unittest.TestCase):
    def setUp(self):
        fresh()

    def test_multiple_projects_and_folders(self):
        folder_manager.add_link("EMAAR Dubai Hills Estate", "3929", "Shared", "Shared", URL1)
        folder_manager.add_link("EMAAR Dubai Hills Estate", "3929", "WIP", "WIP", URL2)
        folder_manager.add_link("EMAAR Dubai Hills Estate", "3929", "Subcontractor A", "Custom", "https://acc.autodesk.com/a")
        folder_manager.add_link("EMAAR Dubai Hills Estate", "3929", "Subcontractor B", "Custom", "https://acc.autodesk.com/b")
        folder_manager.add_link("RAK Nikki Beach", "3862", "Shared", "Shared", URL3)
        data = cfg.load()
        self.assertEqual(len(data["projects"]), 2)
        emaar = [p for p in data["projects"] if p["project_number"] == "3929"][0]
        self.assertEqual(len(emaar["folders"]), 4)
        self.assertEqual([p["project_number"] for p in folder_manager.sort_projects(data["projects"])], ["3929", "3862"])

    def test_url_saved_exactly_with_all_parameters(self):
        folder_manager.add_link("P", "1", "F", "Shared", "  " + URL1 + "  ")
        self.assertEqual(cfg.load()["projects"][0]["folders"][0]["url"], URL1)

    def test_required_fields(self):
        for args in (("", "1", "F", "Shared", URL1), ("P", "1", "", "Shared", URL1), ("P", "1", "F", "Shared", "")):
            with self.assertRaises(ValidationError):
                folder_manager.add_link(*args)
        with self.assertRaises(ValidationError):
            folder_manager.add_link("P", "1", "F", "Shared", "ftp://nope")
        self.assertEqual(cfg.load()["projects"], [])

    def test_duplicate_rules(self):
        folder_manager.add_link("P", "10", "Shared", "Shared", URL1)
        with self.assertRaises(ValidationError):
            folder_manager.add_link("p", "10", "SHARED", "Shared", URL2)        # same folder name
        with self.assertRaises(ValidationError):
            folder_manager.add_link("P", "10", "Other", "WIP", URL1)            # same URL
        with self.assertRaises(ValidationError):
            folder_manager.add_link("Different name", "10", "X", "WIP", URL2)   # number belongs to P
        with self.assertRaises(ValidationError):
            folder_manager.add_link("P", "99", "X", "WIP", URL2)                # P already has number 10
        folder_manager.add_link("P", "", "WIP", "WIP", URL2)                    # blank number -> same project
        self.assertEqual(len(cfg.load()["projects"]), 1)
        self.assertEqual(folder_manager.find_url_elsewhere(URL1, "other"), ("P", "Shared"))

    def test_edit_rename_recategorise_delete(self):
        pid, fid = folder_manager.add_link("P", "10", "Shared", "Shared", URL1)
        folder_manager.update_folder(pid, fid, "Renamed", "Published", URL2, "desc")
        folder = cfg.load()["projects"][0]["folders"][0]
        self.assertEqual((folder["folder_name"], folder["category"], folder["url"], folder["description"]),
                         ("Renamed", "Published", URL2, "desc"))
        folder_manager.update_project(pid, "P renamed", "11", "ABC-GUID", None)
        project = cfg.load()["projects"][0]
        self.assertEqual((project["project_name"], project["project_number"], project["cloud_project_guid"]),
                         ("P renamed", "11", "abc-guid"))
        self.assertTrue(folder_manager.delete_folder(pid, fid))
        self.assertTrue(folder_manager.delete_project(pid))
        self.assertEqual(cfg.load()["projects"], [])

    def test_search(self):
        folder_manager.add_link("EMAAR Dubai Hills", "3929", "Shared", "Shared", URL1)
        folder_manager.add_link("EMAAR Dubai Hills", "3929", "Structural Models", "Custom", "https://acc.autodesk.com/s")
        folder_manager.add_link("RAK Nikki Beach", "3862", "Shared", "Shared", URL3)
        projects = cfg.load()["projects"]
        self.assertEqual(len(folder_manager.search_projects(projects, "")), 2)
        self.assertEqual(len(folder_manager.search_projects(projects, "nikki")), 1)
        self.assertEqual(len(folder_manager.search_projects(projects, "3929")), 1)
        hits = folder_manager.search_projects(projects, "structural")
        self.assertEqual([len(h[1]) for h in hits], [1])
        self.assertEqual(len(folder_manager.search_projects(projects, "shared")), 2)
        self.assertEqual(folder_manager.search_projects(projects, "zzz"), [])


class RecentTests(unittest.TestCase):
    def setUp(self):
        fresh()

    def test_order_limit_clear_and_deleted_projects(self):
        ids = []
        for n in range(12):
            pid, fid = folder_manager.add_link("Project %d" % n, str(1000 + n), "Shared", "Shared", "https://acc.autodesk.com/%d" % n)
            ids.append((pid, fid))
        for index, (pid, fid) in enumerate(ids):
            recent_manager.record_access(pid, fid, "Shared")
            # make timestamps distinct without sleeping
            data = cfg.load()
            data["recent_projects"][0]["last_accessed"] = "2026-01-01T00:%02d:00" % index
            cfg.save(data)
        recent = recent_manager.get_recent()
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0]["project"]["project_name"], "Project 11")   # most recent first
        recent_manager.record_access(*ids[0][:1], folder_id=ids[0][1], folder_name="Shared")
        self.assertEqual(recent_manager.get_recent()[0]["project"]["project_name"], "Project 0")
        folder_manager.delete_project(ids[0][0])
        self.assertNotIn("Project 0", [r["project"]["project_name"] for r in recent_manager.get_recent()])
        recent_manager.clear()
        self.assertEqual(recent_manager.get_recent(), [])

    def test_tracking_off_and_custom_limit(self):
        pid, fid = folder_manager.add_link("P", "1", "Shared", "Shared", URL1)
        cfg.update_settings({"recent_tracking": False})
        self.assertFalse(recent_manager.record_access(pid, fid, "Shared"))
        self.assertEqual(recent_manager.get_recent(), [])
        cfg.update_settings({"recent_tracking": True, "max_recent_projects": 99})
        self.assertEqual(cfg.get_settings(cfg.load())["max_recent_projects"], 10)  # clamped

    def test_open_folder_records_only_after_successful_launch(self):
        pid, fid = folder_manager.add_link("P", "1", "Shared", "Shared", URL1)
        project = cfg.load()["projects"][0]
        folder = project["folders"][0]
        launched = []
        original = acc_url_manager._launch
        try:
            acc_url_manager._launch = lambda url: launched.append(url)
            result = acc_url_manager.open_folder(project, folder)
            self.assertEqual(result.status, "opened")
            self.assertEqual(launched, [URL1])                      # URL passed on completely unchanged
            self.assertEqual(len(recent_manager.get_recent()), 1)
            recent_manager.clear()

            def boom(url):
                raise RuntimeError("no browser")
            acc_url_manager._launch = boom
            result = acc_url_manager.open_folder(project, folder)
            self.assertEqual(result.status, "error")
            self.assertEqual(recent_manager.get_recent(), [])      # failure is not recorded as access
        finally:
            acc_url_manager._launch = original

    def test_tampered_url_is_refused_when_opening(self):
        data = cfg.load()
        data["projects"].append({"project_id": "p1", "project_name": "P", "project_number": "1", "folders": [
            {"folder_id": "f1", "folder_name": "Bad", "category": "Shared", "url": "file:///c:/windows/system32/calc.exe"}]})
        cfg.save(data)
        project = cfg.load()["projects"][0]
        original = acc_url_manager._launch
        try:
            acc_url_manager._launch = lambda url: self.fail("must not launch")
            self.assertEqual(acc_url_manager.open_folder(project, project["folders"][0]).status, "error")
        finally:
            acc_url_manager._launch = original

    def test_browser_setting_off_copies_instead(self):
        cfg.update_settings({"open_in_default_browser": False})
        copied = []
        original_copy, original_launch = acc_url_manager.copy_to_clipboard, acc_url_manager._launch
        try:
            acc_url_manager.copy_to_clipboard = lambda text: copied.append(text) or True
            acc_url_manager._launch = lambda url: self.fail("must not launch")
            self.assertEqual(acc_url_manager.open_url(URL1).status, "copied")
            self.assertEqual(copied, [URL1])
        finally:
            acc_url_manager.copy_to_clipboard, acc_url_manager._launch = original_copy, original_launch


class DetectorTests(unittest.TestCase):
    def setUp(self):
        fresh()
        folder_manager.add_link("EMAAR Dubai Hills Estate", "3929", "Shared", "Shared", URL1)   # contains GUID 1111...
        folder_manager.add_link("RAK Nikki Beach", "3862", "Shared", "Shared", URL3)            # GUID 9999...
        folder_manager.add_link("Canal Living", "3835", "Shared", "Shared", "https://acc.autodesk.com/canal")
        self.data = cfg.load()

    def info(self, **kw):
        base = {"has_document": True, "is_family": False, "title": "Some model", "path": "", "is_cloud": True,
                "project_guid": None, "model_guid": None, "region": None, "user_visible_path": None,
                "acc_project_name": None, "notes": [], "engine": "test", "revit_version": "2026"}
        base.update(kw)
        return base

    def name_of(self, result):
        return result.project["project_name"] if result.project else None

    def test_guid_in_saved_url(self):
        result = project_detector.match_project(self.data, self.info(project_guid="11111111-2222-3333-4444-555555555555"))
        self.assertEqual((self.name_of(result), result.method, result.confidence), ("EMAAR Dubai Hills Estate", "url_project_guid", "high"))

    def test_saved_project_guid_and_model_guid(self):
        project = self.data["projects"][0]
        folder_manager.update_project(project["project_id"], project["project_name"], project["project_number"], "AAAAAAAA-0000-0000-0000-000000000000")
        data = cfg.load()
        result = project_detector.match_project(data, self.info(project_guid="aaaaaaaa-0000-0000-0000-000000000000"))
        self.assertEqual(result.method, "cloud_project_guid")
        folder_manager.link_model(project["project_id"], "ModelX", "bbbbbbbb-0000-0000-0000-000000000000")
        result = project_detector.match_project(cfg.load(), self.info(model_guid="bbbbbbbb-0000-0000-0000-000000000000"))
        self.assertEqual(result.method, "saved_model_guid")

    def test_acc_project_name_exact_only(self):
        result = project_detector.match_project(self.data, self.info(acc_project_name="rak  nikki beach"))
        self.assertEqual((self.name_of(result), result.method), ("RAK Nikki Beach", "acc_project_name"))
        result = project_detector.match_project(self.data, self.info(acc_project_name="3835 \u2013 Canal Living"))
        self.assertEqual(self.name_of(result), "Canal Living")
        # similar but not equal names must NOT match
        result = project_detector.match_project(self.data, self.info(acc_project_name="RAK Nikki Beach Phase 2"))
        self.assertIsNone(result.project)
        result = project_detector.match_project(self.data, self.info(acc_project_name="Canal Living Tower"))
        self.assertIsNone(result.project)

    def test_title_similarity_never_matches(self):
        for title in ("RAK Nikki Beach", "Canal Living Model", "EMAAR Dubai Hills"):
            result = project_detector.match_project(self.data, self.info(title=title, is_cloud=False))
            self.assertIsNone(result.project, title)

    def test_title_project_number_token_low_confidence(self):
        result = project_detector.match_project(self.data, self.info(title="3862-RAK-ARC-Model", is_cloud=False))
        self.assertEqual((self.name_of(result), result.method, result.confidence), ("RAK Nikki Beach", "title_project_number", "low"))
        self.assertIsNone(project_detector.match_project(self.data, self.info(title="38620-Model")).project)  # token must be whole
        self.assertIsNone(project_detector.match_project(self.data, self.info(title="Model 386")).project)

    def test_remembered_title(self):
        folder_manager.link_model(self.data["projects"][1]["project_id"], "ZZ_Structure_Model.rvt")
        result = project_detector.match_project(cfg.load(), self.info(title="zz_structure_model"))
        self.assertEqual(result.method, "saved_model_title")

    def test_ambiguous_is_not_auto_selected(self):
        for project in self.data["projects"][:2]:
            folder_manager.link_model(project["project_id"], "Shared Name Model")
        result = project_detector.match_project(cfg.load(), self.info(title="Shared Name Model"))
        self.assertIsNone(result.project)
        self.assertTrue(result.ambiguous)
        self.assertEqual(len(result.candidates), 2)

    def test_no_document_family_and_setting_off(self):
        self.assertIsNone(project_detector.match_project(self.data, self.info(has_document=False)).project)
        self.assertIsNone(project_detector.match_project(self.data, self.info(is_family=True, title="3862 family")).project)
        cfg.update_settings({"auto_detect_project": False})
        result = project_detector.detect_current_project(cfg.load(), doc=FakeDoc("3862-RAK-Model"))
        self.assertIsNone(result.project)

    def test_link_model_fills_guid_and_is_idempotent(self):
        pid = self.data["projects"][0]["project_id"]
        folder_manager.link_model(pid, "M1", "cccccccc-0000-0000-0000-000000000000", "dddddddd-0000-0000-0000-000000000000")
        folder_manager.link_model(pid, "M1", "cccccccc-0000-0000-0000-000000000000", "dddddddd-0000-0000-0000-000000000000")
        project = cfg.load()["projects"][0]
        self.assertEqual(len(project["models"]), 1)
        self.assertEqual(project["cloud_project_guid"], "dddddddd-0000-0000-0000-000000000000")


class FakeGuid(object):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class FakeCloudPath(object):
    CloudPath = True
    Region = "EMEA"

    def GetProjectGUID(self):
        return FakeGuid("11111111-2222-3333-4444-555555555555")

    def GetModelGUID(self):
        return FakeGuid("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")


class FakeApp(object):
    Username = "jdoe"


class FakeDoc(object):
    IsFamilyDocument = False
    IsWorkshared = False
    IsModelInCloud = False
    PathName = ""
    Application = FakeApp()

    def __init__(self, title):
        self.Title = title

    def GetCloudModelPath(self):
        raise RuntimeError("not a cloud model")


class CloudDoc(FakeDoc):
    IsModelInCloud = True
    PathName = "Autodesk Docs://EMAAR Dubai Hills Estate/Model.rvt"

    def GetCloudModelPath(self):
        return FakeCloudPath()


class OldApiDoc(object):
    """A document missing IsModelInCloud / GetCloudModelPath (older/odd API surface)."""
    Title = "X"
    IsFamilyDocument = False


class CompatTests(unittest.TestCase):
    def setUp(self):
        fresh()
        self._orig = revit_compat._user_visible_path
        revit_compat._user_visible_path = lambda mp: "Autodesk Docs://EMAAR Dubai Hills Estate/Model.rvt"

    def tearDown(self):
        revit_compat._user_visible_path = self._orig

    def test_cloud_info_with_fake_document(self):
        info = revit_compat.get_cloud_info(CloudDoc("Model"))
        self.assertTrue(info["is_cloud"])
        self.assertEqual(info["project_guid"], "11111111-2222-3333-4444-555555555555")
        self.assertEqual(info["model_guid"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(info["acc_project_name"], "EMAAR Dubai Hills Estate")
        self.assertEqual(info["file_name"], "Model.rvt")

    def test_non_cloud_and_missing_api_do_not_crash(self):
        self.assertFalse(revit_compat.get_cloud_info(FakeDoc("Local"))["is_cloud"])
        info = revit_compat.get_cloud_info(OldApiDoc())
        self.assertIsNone(info["project_guid"])
        self.assertTrue(info["notes"])
        self.assertIsNone(revit_compat.get_cloud_info(None)["project_guid"])

    def test_end_to_end_detection_with_fake_cloud_document(self):
        folder_manager.add_link("EMAAR Dubai Hills Estate", "3929", "Shared", "Shared", URL1)
        result = project_detector.detect_current_project(cfg.load(), doc=CloudDoc("Model"))
        self.assertEqual(result.project["project_number"], "3929")
        self.assertEqual(result.method, "url_project_guid")
        self.assertIn("Cloud project GUID", result.diagnostics_text())

    def test_helpers(self):
        self.assertEqual(revit_compat.parse_visible_path("BIM 360://Proj A/Sub/Model.rvt"), ("BIM 360", "Proj A", "Model.rvt"))
        self.assertEqual(revit_compat.project_name_from_local_path(r"C:\Users\x\DC\ACCDocs\Proj A\Project Files\M.rvt"), "Proj A")
        self.assertIsNone(revit_compat.project_name_from_local_path(r"C:\Projects\M.rvt"))
        doc = FakeDoc("Model_jdoe")
        doc.IsWorkshared = True
        self.assertEqual(revit_compat.get_model_title(doc), "Model")


class BackupTests(unittest.TestCase):
    def setUp(self):
        fresh()
        folder_manager.add_link("P One", "1", "Shared", "Shared", URL1)
        folder_manager.add_link("P One", "1", "WIP", "WIP", URL2)
        folder_manager.add_link("P Two", "2", "Shared", "Shared", URL3)
        self.file = os.path.join(TMP, "export.json")

    def test_export_and_replace_import_restores_everything(self):
        self.assertEqual(backup_manager.export_backup(self.file), (2, 3))
        for p in cfg.load()["projects"]:
            folder_manager.delete_project(p["project_id"])
        incoming, issues = backup_manager.read_backup(self.file)
        self.assertEqual(issues, [])
        lines = backup_manager.build_preview(cfg.load(), incoming, "replace", issues)
        self.assertTrue(any("REPLACE" in l for l in lines))
        backup_manager.apply_import(incoming, "replace")
        self.assertEqual(len(cfg.load()["projects"]), 2)

    def test_merge_has_no_duplicates_and_adds_new(self):
        backup_manager.export_backup(self.file)
        raw = cfg.read_json_file(self.file)
        raw["projects"][0]["folders"].append({"folder_id": "x", "folder_name": "New folder", "category": "Custom", "url": "https://acc.autodesk.com/new"})
        raw["projects"].append({"project_id": "zz", "project_name": "P Three", "project_number": "3", "folders": [
            {"folder_id": "q", "folder_name": "Shared", "category": "Shared", "url": "https://acc.autodesk.com/three"}]})
        cfg.write_json_atomic(self.file, raw)
        incoming, _ = backup_manager.read_backup(self.file)
        before = cfg.load()
        lines = backup_manager.build_preview(before, incoming, "merge")
        self.assertEqual(len(cfg.load()["projects"]), 2)                 # preview changed nothing
        backup_manager.apply_import(incoming, "merge")
        data = cfg.load()
        self.assertEqual(len(data["projects"]), 3)
        total = sum(len(p["folders"]) for p in data["projects"])
        self.assertEqual(total, 5)                                       # 3 old + New folder + P Three/Shared
        backup_manager.apply_import(incoming, "merge")                   # importing again must not duplicate
        self.assertEqual(sum(len(p["folders"]) for p in cfg.load()["projects"]), 5)
        self.assertTrue(glob.glob(os.path.join(TMP, "backups", "config_before-import_*.json")))

    def test_invalid_files_and_invalid_urls(self):
        bad = os.path.join(TMP, "bad.json")
        for content in (b"not json", b"[1,2,3]", b'{"hello": 1}'):
            open(bad, "wb").write(content)
            with self.assertRaises(ValidationError):
                backup_manager.read_backup(bad)
        open(bad, "w").write(json.dumps({"projects": [{"project_name": "Evil", "folders": [
            {"folder_name": "calc", "url": "file:///c:/windows/system32/calc.exe"},
            {"folder_name": "ok", "url": "https://acc.autodesk.com/ok"}]}]}))
        incoming, issues = backup_manager.read_backup(bad)
        self.assertEqual(len(issues), 1)
        self.assertEqual(len(incoming["projects"][0]["folders"]), 1)

    def test_import_settings_only_when_requested(self):
        backup_manager.export_backup(self.file)
        raw = cfg.read_json_file(self.file)
        raw["settings"]["confirm_delete"] = False
        cfg.write_json_atomic(self.file, raw)
        incoming, _ = backup_manager.read_backup(self.file)
        backup_manager.apply_import(incoming, "merge", import_settings=False)
        self.assertTrue(cfg.load()["settings"]["confirm_delete"])
        backup_manager.apply_import(incoming, "merge", import_settings=True)
        self.assertFalse(cfg.load()["settings"]["confirm_delete"])


class StaticChecks(unittest.TestCase):
    """Source-level checks that need no Revit."""

    def py_files(self):
        return glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True)

    def test_every_file_compiles_and_is_ascii(self):
        for path in self.py_files():
            source = open(path, "rb").read()
            source.decode("ascii")  # non-ASCII would break on IronPython 2.7 without care
            compile(source, path, "exec")

    def test_python27_compatible_syntax(self):
        """AST scan for syntax IronPython 2.7 cannot parse."""
        banned = (ast.JoinedStr, ast.AsyncFunctionDef, ast.Await, ast.Nonlocal, ast.YieldFrom, ast.NamedExpr,
                  ast.AnnAssign, ast.MatMult)
        for path in self.py_files():
            if os.sep + "tests" + os.sep in path:
                continue  # the test runner itself only runs on desktop Python 3
            tree = ast.parse(open(path, "rb").read())
            for node in ast.walk(tree):
                self.assertNotIsInstance(node, banned, "%s:%s" % (path, getattr(node, "lineno", "?")))
                if isinstance(node, ast.FunctionDef):
                    self.assertFalse(node.args.kwonlyargs, "keyword-only args in %s" % path)
                    self.assertIsNone(node.returns, "return annotation in %s" % path)
                    for arg in node.args.args:
                        self.assertIsNone(arg.annotation, "annotation in %s" % path)
                if isinstance(node, ast.Raise):
                    self.assertIsNone(node.cause, "'raise from' in %s" % path)
                if isinstance(node, ast.ExceptHandler) and node.name is None and False:
                    pass

    def test_xaml_well_formed_and_controls_exist(self):
        xamls = {}
        for name in dir(ui_xaml):
            value = getattr(ui_xaml, name)
            if name.isupper() and isinstance(value, str) and value.startswith("<Window"):
                xml.dom.minidom.parseString(value)
                found = ui_xaml.names(value)
                self.assertEqual(len(found), len(set(found)), name)
                xamls[name] = set(found)
        pairs = {"ui_link_dialog.py": ("LINK_DIALOG", "PROJECT_DIALOG"), "ui_projects_window.py": ("PROJECTS_WINDOW",),
                 "ui_manage_window.py": ("MANAGE_WINDOW",), "ui_current_window.py": ("CURRENT_WINDOW",),
                 "ui_recent_window.py": ("RECENT_WINDOW",), "ui_settings_window.py": ("SETTINGS_WINDOW",),
                 "ui_backup_window.py": ("BACKUP_WINDOW", "IMPORT_PREVIEW"), "ui_picker.py": ("PICKER_WINDOW",)}
        for filename, window_names in pairs.items():
            source = open(os.path.join(ROOT, "lib", "accqa", filename)).read()
            used = set(re.findall(r"\bc\.([A-Za-z_][A-Za-z0-9_]*)", source))
            known = set()
            for window in window_names:
                known |= xamls[window]
            native = {"Items", "Text", "IsChecked"}  # not expected after c. but harmless
            missing = used - known - native
            self.assertFalse(missing, "%s uses controls missing from XAML: %s" % (filename, sorted(missing)))

    def test_every_button_has_script_and_icon(self):
        buttons = glob.glob(os.path.join(ROOT, "ACC Quick Access.tab", "*.panel", "*.pushbutton"))
        self.assertEqual(len(buttons), 11)
        for folder in buttons:
            script = open(os.path.join(folder, "script.py")).read()
            self.assertIn("ui_manager.run_safe", script)
            self.assertTrue(os.path.getsize(os.path.join(folder, "icon.png")) > 200, folder)
        for entry in ("current_project", "all_projects", "recent_projects", "add_link", "manage_links", "settings", "backup"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "icons", entry + ".png")))

    def test_ui_manager_entry_points_exist(self):
        source = open(os.path.join(ROOT, "lib", "accqa", "ui_manager.py")).read()
        for script in glob.glob(os.path.join(ROOT, "ACC Quick Access.tab", "*.panel", "*.pushbutton", "script.py")):
            for name in re.findall(r"ui_manager\.(\w+)", open(script).read()):
                if name != "run_safe":
                    self.assertIn("def %s(" % name, source, script)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
