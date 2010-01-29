# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
sys.path.insert(0, '../')
import unittest
import os
from entropy.client.interfaces import Client
from entropy.const import etpConst, etpUi, const_convert_to_unicode, \
    const_convert_to_rawstring
from entropy.core.settings.base import SystemSettings
from entropy.db import EntropyRepository
import tests._misc as _misc

import entropy.tools

class EntropyRepositoryTest(unittest.TestCase):

    def setUp(self):
        sys.stdout.write("%s called\n" % (self,))
        sys.stdout.flush()
        self.Client = Client(noclientdb = 2, indexing = False, xcache = False,
            repo_validation = False)
        self.Spm = self.Client.Spm()
        self.test_db_name = "%s_test_suite" % (etpConst['dbnamerepoprefix'],)
        self.client_sysset_plugin_id = \
            etpConst['system_settings_plugins_ids']['client_plugin']
        self.test_db = self.__open_test_db()
        self.test_db2 = self.__open_test_db()
        self.SystemSettings = SystemSettings()

    def tearDown(self):
        """
        tearDown is run after each test
        """
        sys.stdout.write("%s ran\n" % (self,))
        sys.stdout.flush()
        self.test_db.closeDB()
        self.test_db2.closeDB()
        self.Client.destroy()

    def __open_test_db(self):
        return self.Client.open_memory_database(dbname = self.test_db_name)

    def test_db_clearcache(self):
        self.test_db.clearCache()

    def test_treeupdates_actions(self):
        self.assertEqual(self.test_db.listAllTreeUpdatesActions(), [])

        updates = [
            ('move media-libs/x264-svn media-libs/x264', '2020', '1210199116.46'),
            ('slotmove x11-libs/lesstif 2.1 0', '2020', '1210753863.16')
        ]
        actions = sorted(['move media-libs/x264-svn media-libs/x264',
            'slotmove x11-libs/lesstif 2.1 0'])

        self.test_db.insertTreeUpdatesActions(updates, self.test_db_name)
        db_actions = self.test_db.retrieveTreeUpdatesActions(self.test_db_name,
            forbranch = '2020')
        self.assertEqual(actions, db_actions)

        self.test_db.removeTreeUpdatesActions(self.test_db_name)
        db_actions = self.test_db.retrieveTreeUpdatesActions(self.test_db_name,
            forbranch = '2020')
        self.assertEqual([], db_actions)

    def test_db_creation(self):
        self.assert_(isinstance(self.test_db, EntropyRepository))
        self.assertEqual(self.test_db_name, self.test_db.dbname)
        self.assert_(self.test_db._doesTableExist('baseinfo'))
        self.assert_(self.test_db._doesTableExist('extrainfo'))

    def test_db_metadata_handling(self):

        test_entry = {
            const_convert_to_unicode("/path/to/foo", "utf-8"): \
                const_convert_to_unicode("dir", "utf-8"),
            const_convert_to_unicode("/path/to/foo/foo", "utf-8"): \
                const_convert_to_unicode("obj", "utf-8"),
        }

        test_pkg = _misc.get_test_package()
        data = self.Spm.extract_package_metadata(test_pkg)
        data['content'].update(test_entry.copy())
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)

        test_pkg2 = _misc.get_test_package2()
        data2 = self.Spm.extract_package_metadata(test_pkg2)
        data2['content'].update(test_entry.copy())
        idpackage2, rev2, new_data2 = self.test_db2.handlePackage(data2)
        db_data2 = self.test_db2.getPackageData(idpackage2)

        cont_diff = self.test_db.contentDiff(idpackage, self.test_db2,
            idpackage2)

        for key in test_entry:
            try:
                self.assert_(key not in cont_diff)
            except AssertionError:
                print(key)
                raise

        py_diff = sorted([x for x in db_data['content'] if x not in \
            db_data2['content']])

        self.assertEqual(sorted(cont_diff), py_diff)

        orig_diff = ['/lib64', '/lib64/libz.so', '/lib64/libz.so.1',
            '/lib64/libz.so.1.2.3', '/usr/include', '/usr/include/zconf.h',
            '/usr/include/zlib.h', '/usr/lib64/libz.a',
            '/usr/lib64/libz.so', '/usr/share/doc/zlib-1.2.3-r1',
            '/usr/share/doc/zlib-1.2.3-r1/ChangeLog.bz2',
            '/usr/share/doc/zlib-1.2.3-r1/FAQ.bz2',
            '/usr/share/doc/zlib-1.2.3-r1/README.bz2',
            '/usr/share/doc/zlib-1.2.3-r1/algorithm.txt.bz2',
            '/usr/share/man', '/usr/share/man/man3',
            '/usr/share/man/man3/zlib.3.bz2'
        ]
        orig_diff = [const_convert_to_unicode(x, 'utf-8') for x in orig_diff]
        self.assertEqual(orig_diff, py_diff)

        # test package content match
        self.assertEqual(self.test_db.getIDPackagesFromFile(orig_diff[3]),
            [1])
        category = self.test_db.retrieveCategory(idpackage)
        idcategory = self.test_db.getIDCategory(category)
        self.assertEqual(self.test_db.getCategory(idcategory),
            new_data['category'])

        versioning_data = self.test_db.getVersioningData(idpackage)
        dbverdata = (self.test_db.retrieveVersion(idpackage),
            self.test_db.retrieveVersionTag(idpackage),
            self.test_db.retrieveRevision(idpackage),)
        self.assertEqual(versioning_data, dbverdata)

        strict_scope = self.test_db.getStrictScopeData(idpackage)
        dbverdata = (self.test_db.retrieveAtom(idpackage),
            self.test_db.retrieveSlot(idpackage),
            self.test_db.retrieveRevision(idpackage),)
        self.assertEqual(strict_scope, dbverdata)

        scope_data = self.test_db.getScopeData(idpackage)
        dbverdata = (
            self.test_db.retrieveAtom(idpackage),
            self.test_db.retrieveCategory(idpackage),
            self.test_db.retrieveName(idpackage),
            self.test_db.retrieveVersion(idpackage),
            self.test_db.retrieveSlot(idpackage),
            self.test_db.retrieveVersionTag(idpackage),
            self.test_db.retrieveRevision(idpackage),
            self.test_db.retrieveBranch(idpackage),
            self.test_db.retrieveApi(idpackage),
        )
        self.assertEqual(scope_data, dbverdata)

        trigger_info = self.test_db.getTriggerInfo(idpackage)
        trigger_keys = ['version', 'eclasses', 'etpapi', 'cxxflags', 'cflags',
            'chost', 'atom', 'category', 'name', 'versiontag', 'content',
            'trigger', 'branch', 'spm_phases', 'revision']
        self.assertEqual(sorted(trigger_keys), sorted(trigger_info.keys()))

        system_pkgs = self.test_db.retrieveSystemPackages()
        self.assertEqual(system_pkgs, set([idpackage]))

    def test_db_insert_compare_match_provide(self):
        test_pkg = _misc.get_test_entropy_package_provide()
        data = self.Spm.extract_package_metadata(test_pkg)
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)
        self.assertEqual(new_data, db_data)

    def test_db_cache(self):
        test_pkg = _misc.get_test_entropy_package_provide()
        data = self.Spm.extract_package_metadata(test_pkg)
        idpackage, rev, new_data = self.test_db.handlePackage(data)

        # enable cache
        self.test_db.xcache = True
        key = new_data['category'] + "/" + new_data['name']

        from entropy.cache import EntropyCacher
        cacher = EntropyCacher()
        cacher.start()

        cached = self.test_db._EntropyRepository__atomMatchFetchCache(
            key, True, False, False, None, None, False, False, True)
        self.assert_(cached is None)

        # now store
        self.test_db._EntropyRepository__atomMatchStoreCache(
            key, True, False, False, None, None, False, False, True,
            result = (123, 0)
        )
        cacher.sync()

        cached = self.test_db._EntropyRepository__atomMatchFetchCache(
            key, True, False, False, None, None, False, False, True)
        self.assertEqual(cached, (123, 0))

    def test_db_insert_compare_match(self):

        # insert/compare
        test_pkg = _misc.get_test_package()
        data = self.Spm.extract_package_metadata(test_pkg)
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)
        self.assertEqual(new_data, db_data)

        # match
        nf_match = (-1, 1)
        f_match = (1, 0)
        pkg_atom = _misc.get_test_package_atom()
        pkg_name = _misc.get_test_package_name()
        self.assertEqual(nf_match, self.test_db.atomMatch("slib"))
        self.assertEqual(f_match,
            self.test_db.atomMatch(pkg_name))
        self.assertEqual(f_match,
            self.test_db.atomMatch(pkg_atom))

        # test package masking
        plug_id = self.client_sysset_plugin_id
        masking_validation = \
            self.SystemSettings[plug_id]['masking_validation']['cache']
        f_match_mask = (1, 
            self.test_db_name[len(etpConst['dbnamerepoprefix']):],)

        self.SystemSettings['live_packagemasking']['mask_matches'].add(
            f_match_mask)
        masking_validation.clear()
        self.assertEqual((-1, 1), self.test_db.atomMatch(pkg_atom))

        self.SystemSettings['live_packagemasking']['mask_matches'].discard(
            f_match_mask)
        masking_validation.clear()
        self.assertNotEqual((-1, 1), self.test_db.atomMatch(pkg_atom))

        # now test multimatch
        idpackage, rev, new_data = self.test_db.addPackage(db_data)
        results, rc = self.test_db.atomMatch(pkg_name, multiMatch = True)
        self.assertEqual(2, len(results))
        self.assert_(isinstance(results, set))
        self.assert_(rc == 0)

        results, rc = self.test_db.atomMatch(pkg_name+"foo", multiMatch = True)
        self.assertEqual(0, len(results))
        self.assert_(isinstance(results, set))
        self.assert_(rc == 1)

    def test_db_insert_compare_match_utf(self):

        # insert/compare
        test_pkg = _misc.get_test_package2()
        data = self.Spm.extract_package_metadata(test_pkg)
        # Portage stores them this way
        data['changelog'] = const_convert_to_unicode(
            "#248083).\n\n  06 Feb 2009; Ra\xc3\xbal Porcel")
        data['license'] = const_convert_to_unicode('GPL-2')
        data['licensedata'] = {
            const_convert_to_unicode('GPL-2'): \
                const_convert_to_unicode(
                    "#248083).\n\n  06 Feb 2009; Ra\xc3\xbal Porcel"),
        }
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)
        self.assertEqual(new_data, db_data)

        # match
        nf_match = (-1, 1)
        f_match = (1, 0)
        pkg_atom = _misc.get_test_package_atom2()
        pkg_name = _misc.get_test_package_name2()
        self.assertEqual(nf_match, self.test_db.atomMatch("slib"))
        self.assertEqual(f_match,
            self.test_db.atomMatch(pkg_name))
        self.assertEqual(f_match,
            self.test_db.atomMatch(pkg_atom))

        # test package masking
        plug_id = self.client_sysset_plugin_id
        masking_validation = \
            self.SystemSettings[plug_id]['masking_validation']['cache']
        f_match_mask = (1, 
            self.test_db_name[len(etpConst['dbnamerepoprefix']):],)

        self.SystemSettings['live_packagemasking']['mask_matches'].add(
            f_match_mask)
        masking_validation.clear()
        self.assertEqual((-1, 1), self.test_db.atomMatch(pkg_atom))

        self.SystemSettings['live_packagemasking']['mask_matches'].discard(
            f_match_mask)
        masking_validation.clear()
        self.assertNotEqual((-1, 1), self.test_db.atomMatch(pkg_atom))

    def test_db_insert_compare_match_utf2(self):

        # insert/compare
        test_pkg = _misc.get_test_package3()
        data = self.Spm.extract_package_metadata(test_pkg)
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)
        self.assertEqual(new_data, db_data)

        # match
        nf_match = (-1, 1)
        f_match = (1, 0)
        pkg_atom = _misc.get_test_package_atom3()
        pkg_name = _misc.get_test_package_name3()
        self.assertEqual(nf_match, self.test_db.atomMatch("slib"))
        self.assertEqual(f_match,
            self.test_db.atomMatch(pkg_name))
        self.assertEqual(f_match,
            self.test_db.atomMatch(pkg_atom))

        # test package masking
        plug_id = self.client_sysset_plugin_id
        masking_validation = \
            self.SystemSettings[plug_id]['masking_validation']['cache']
        f_match_mask = (1, 
            self.test_db_name[len(etpConst['dbnamerepoprefix']):],)

        self.SystemSettings['live_packagemasking']['mask_matches'].add(
            f_match_mask)
        masking_validation.clear()
        self.assertEqual((-1, 1), self.test_db.atomMatch(pkg_atom))

        self.SystemSettings['live_packagemasking']['mask_matches'].discard(
            f_match_mask)
        masking_validation.clear()
        self.assertNotEqual((-1, 1), self.test_db.atomMatch(pkg_atom))

    def test_db_insert_compare_match_tag(self):

        # insert/compare
        test_pkg = _misc.get_test_entropy_package_tag()
        data = self.Spm.extract_package_metadata(test_pkg)
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)
        self.assertEqual(new_data, db_data)

        # match
        f_match = (1, 0)

        for atom, pkg_id, branch in self.test_db.listAllPackages():
            pkg_key = entropy.tools.dep_getkey(atom)
            self.assertEqual(f_match, self.test_db.atomMatch(pkg_key))
            self.assertEqual(f_match, self.test_db.atomMatch(atom))
            self.assertEqual(f_match, self.test_db.atomMatch("~"+atom))

    def test_db_import_export(self):

        test_pkg = _misc.get_test_package2()
        data = self.Spm.extract_package_metadata(test_pkg)
        # Portage stores them this way
        data['changelog'] = const_convert_to_unicode(
            "#248083).\n\n  06 Feb 2009; Ra\xc3\xbal Porcel")
        data['license'] = const_convert_to_unicode('GPL-2')
        data['licensedata'] = {
            const_convert_to_unicode('GPL-2'): \
                const_convert_to_unicode(
                    "#248083).\n\n  06 Feb 2009; Ra\xc3\xbal Porcel"),
        }
        idpackage, rev, new_data = self.test_db.handlePackage(data)
        db_data = self.test_db.getPackageData(idpackage)
        self.assertEqual(new_data, db_data)

        etpUi['mute'] = True

        # export
        buf_file = "dbtst.txt"
        buf = open(buf_file, "wb")
        self.test_db.doDatabaseExport(buf)
        buf.flush()
        buf.close()

        new_db_path = "test_db_import_export.db"
        self.test_db.doDatabaseImport(buf_file, new_db_path)
        new_db = self.Client.open_generic_database(new_db_path)
        new_db_data = new_db.getPackageData(idpackage)
        new_db.closeDB()
        etpUi['mute'] = False
        self.assertEqual(new_db_data, db_data)
        os.remove(buf_file)
        os.remove(new_db_path)


    def test_db_package_sets(self):

        set_name = 'my_test_set'
        set_deps = ["app-foo/foo", "app-pling/plong", "media-foo/ajez"]
        set_name2 = 'my_test_set2'
        set_deps2 = ["app-foo/foo2", "app-pling/plong2", "media-foo/ajez2"]
        pkgsets = {
            set_name: set(set_deps),
            set_name2: set(set_deps2),
        }
        self.test_db.insertPackageSets(pkgsets)
        self.assertEqual(self.test_db.retrievePackageSets(), pkgsets)
        set_search = self.test_db.searchSets(set_name2)
        self.assertEqual(set([set_name2]), set_search)

    def test_db_license_data_str_insert(self):
        lic_txt = const_convert_to_rawstring('[3]\xab foo\n\n', 'utf-8')
        lic_name = const_convert_to_unicode('CCPL-Attribution-2.0')
        lic_data = {lic_name: lic_txt}
        self.test_db.insertLicenses(lic_data)
        db_lic_txt = self.test_db.retrieveLicenseText(lic_name)
        self.assertEqual(db_lic_txt, lic_txt)

if __name__ == '__main__':
    if "--debug" in sys.argv:
        sys.argv.remove("--debug")
        from entropy.const import etpUi
        etpUi['debug'] = True
    unittest.main()
