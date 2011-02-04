# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Services System Management Executors Interface}.

"""
import os
import sys
import subprocess
from entropy.core.settings.base import SystemSettings
from entropy.const import etpConst
from entropy.output import blue, red
from entropy.exceptions import InvalidAtom
from entropy.i18n import _
from entropy.transceivers import EntropyTransceiver
from entropy.server.interfaces.rss import ServerRssMetadata

import entropy.dep
import entropy.tools

def seek_till_newline(f):
    count = 0
    f.seek(count, os.SEEK_END)
    size = f.tell()
    while count > (size*-1):
        count -= 1
        f.seek(count, os.SEEK_END)
        myc = f.read(1)
        if myc == "\n":
            break
    f.seek(count+1, os.SEEK_END)
    pos = f.tell()
    f.truncate(pos)

class Base:

    def __init__(self, SystemManagerExecutorInstance, *args, **kwargs):

        try:
            import pickle as pickle
        except ImportError:
            import pickle
        self.pickle = pickle

        self.SystemManagerExecutor = SystemManagerExecutorInstance
        self.args = args
        self.kwargs = kwargs
        self.available_commands = {
            'sync_spm': {
                'func': self.sync_portage,
                'args': 1,
            },
            'compile_atoms': {
                'func': self.compile_atoms,
                'args': 2,
            },
            'spm_remove_atoms': {
                'func': self.spm_remove_atoms,
                'args': 2,
            },
            'get_spm_categories_updates': {
                'func': self.get_spm_categories_updates,
                'args': 2,
            },
            'get_spm_categories_installed': {
                'func': self.get_spm_categories_installed,
                'args': 2,
            },
            'enable_uses_for_atoms': {
                'func': self.enable_uses_for_atoms,
                'args': 3,
            },
            'disable_uses_for_atoms': {
                'func': self.disable_uses_for_atoms,
                'args': 3,
            },
            'get_spm_atoms_info': {
                'func': self.get_spm_atoms_info,
                'args': 2,
            },
            'run_spm_info': {
                'func': self.run_spm_info,
                'args': 1,
            },
            'run_custom_shell_command': {
                'func': self.run_custom_shell_command,
                'args': 1,
            },
            'get_spm_glsa_data': {
                'func': self.get_spm_glsa_data,
                'args': 1,
            },
            'move_entropy_packages_to_repository': {
                'func': self.move_entropy_packages_to_repository,
                'args': 5,
            },
            'scan_entropy_packages_database_changes': {
                'func': self.scan_entropy_packages_database_changes,
                'args': 1,
            },
            'run_entropy_database_updates': {
                'func': self.run_entropy_database_updates,
                'args': 4,
            },
            'run_entropy_dependency_test': {
                'func': self.run_entropy_dependency_test,
                'args': 1,
            },
            'run_entropy_library_test': {
                'func': self.run_entropy_library_test,
                'args': 1,
            },
            'run_entropy_treeupdates': {
                'func': self.run_entropy_treeupdates,
                'args': 2,
            },
            'scan_entropy_mirror_updates': {
                'func': self.scan_entropy_mirror_updates,
                'args': 2,
            },
            'run_entropy_mirror_updates': {
                'func': self.run_entropy_mirror_updates,
                'args': 2,
            },
            'run_entropy_checksum_test': {
                'func': self.run_entropy_checksum_test,
                'args': 3,
            },
            'get_notice_board': {
                'func': self.get_notice_board,
                'args': 2,
            },
            'remove_notice_board_entries': {
                'func': self.remove_notice_board_entries,
                'args': 3,
            },
            'add_notice_board_entry': {
                'func': self.add_notice_board_entry,
                'args': 5,
            },
        }

    def _set_processing_pid(self, queue_id, process_pid):
        with self.SystemManagerExecutor.SystemInterface.QueueLock:
            self.SystemManagerExecutor.SystemInterface.load_queue()
            live_item, key = self.SystemManagerExecutor.SystemInterface._get_item_by_queue_id(queue_id)
            if isinstance(live_item, dict):
                live_item['processing_pid'] = process_pid
                # _get_item_by_queue_id
                self.SystemManagerExecutor.SystemInterface.store_queue()

    def sync_portage(self, queue_id):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        cmd = ["emerge", "--sync"]
        try:
            p = subprocess.Popen(cmd, stdout = stdout_err, stderr = stdout_err, stdin = self._get_stdin(queue_id))
            self._set_processing_pid(queue_id, p.pid)
            rc = p.wait()
        finally:
            stdout_err.write("\n### Done ###\n")
            stdout_err.flush()
            stdout_err.close()
        return True, rc

    def compile_atoms(
            self,
            queue_id, atoms,
            pretend = False, oneshot = False,
            verbose = True, nocolor = True,
            fetchonly = False, buildonly = False,
            nodeps = False, custom_use = '', ldflags = '', cflags = ''):

        sys_intf = self.SystemManagerExecutor.SystemInterface
        queue_data, key = sys_intf.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        def set_proc_pid(pid):
            self._set_processing_pid(queue_id, pid)

        stdout_err = open(queue_data['stdout'], "a+")
        stdout_err.write("Preparing to spawn compilation of: '%s'"
            ". Good luck mate!\n" % (' '.join(atoms),))
        stdout_err.flush()

        env = {}
        if ldflags:
            env['LDFLAGS'] = ldflags
        if cflags:
            env['CFLAGS'] = cflags

        try:

            spm = sys_intf.Entropy.Spm()
            status = spm.compile_packages(atoms,
                stdin = self._get_stdin(queue_id),
                stdout = stdout_err, stderr = stdout_err, environ = env,
                pid_write_func = set_proc_pid, pretend = pretend,
                verbose = verbose, fetch_only = fetchonly,
                build_only = buildonly, no_dependencies = nodeps,
                coloured_output = not nocolor, oneshot = oneshot)

        finally:

            stdout_err.write("\n### Done ###\n")
            stdout_err.flush()
            stdout_err.close()

        return True, status

    def spm_remove_atoms(self, queue_id, atoms, pretend = True, verbose = True, nocolor = True):

        sys_intf = self.SystemManagerExecutor.SystemInterface
        queue_data, key = sys_intf.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        def set_proc_pid(pid):
            self._set_processing_pid(queue_id, pid)

        stdout_err = open(queue_data['stdout'], "a+")
        stdout_err.write("Preparing to spawn removal of: '%s'"
            ". Good luck mate!\n" % (' '.join(atoms),))
        stdout_err.flush()

        try:

            spm = sys_intf.Entropy.Spm()
            status = spm.remove_packages(atoms,
                stdin = self._get_stdin(queue_id),
                stdout = stdout_err, stderr = stdout_err,
                pid_write_func = set_proc_pid, pretend = pretend,
                verbose = verbose, coloured_output = not nocolor)

        finally:

            stdout_err.write("\n### Done ###\n")
            stdout_err.flush()
            stdout_err.close()

        return True, status

    def enable_uses_for_atoms(self, queue_id, atoms, useflags):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        use_data = {}
        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        for atom in atoms:
            try:
                status = spm.enable_package_compile_options(atom, useflags)
            except:
                continue
            if status:
                use_data[atom] = {}
                matched_atom = spm.match_package(atom)
                use_data[atom] = spm.get_package_compile_options(matched_atom)

        return True, use_data

    def disable_uses_for_atoms(self, queue_id, atoms, useflags):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        use_data = {}
        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        for atom in atoms:
            try:
                status = spm.disable_package_compile_options(atom, useflags)
            except:
                continue
            if status:
                use_data[atom] = {}
                matched_atom = spm.match_package(atom)
                use_data[atom] = spm.get_package_compile_options(matched_atom)

        return True, use_data

    def get_spm_atoms_info(self, queue_id, atoms):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        atoms_data = {}
        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        for atom in atoms:

            try:
                key = entropy.dep.dep_getkey(atom)
                category = key.split("/")[0]
            except:
                continue
            try:
                matched_atom = spm.match_package(atom)
            except InvalidAtom:
                continue
            if not matched_atom:
                continue

            if category not in atoms_data:
                atoms_data[category] = {}

            atoms_data[category][matched_atom] = self._get_spm_pkginfo(matched_atom)

        return True, atoms_data

    def get_spm_categories_updates(self, queue_id, categories):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        packages = spm.get_packages(categories)
        package_data = {}
        for package in packages:
            try:
                key = entropy.dep.dep_getkey(package)
                category = key.split("/")[0]
            except:
                continue
            if category not in package_data:
                package_data[category] = {}
            package_data[category][package] = self._get_spm_pkginfo(package)

        return True, package_data

    def get_spm_categories_installed(self, queue_id, categories):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        packages = spm.get_installed_packages(categories = categories)
        package_data = {}
        for package in packages:
            try:
                key = entropy.dep.dep_getkey(package)
                category = key.split("/")[0]
            except:
                continue
            if category not in package_data:
                package_data[category] = {}
            package_data[category][package] = self._get_spm_pkginfo(package, from_installed = True)

        return True, package_data

    def run_spm_info(self, queue_id):

        sys_intf = self.SystemManagerExecutor.SystemInterface
        queue_data, key = sys_intf.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        def set_proc_pid(pid):
            self._set_processing_pid(queue_id, pid)

        stdout_err = open(queue_data['stdout'], "a+")
        stdout_err.write("Preparing to spawn SPM info. Good luck mate!\n")
        stdout_err.flush()

        try:

            spm = sys_intf.Entropy.Spm()
            status = spm.print_build_environment_info(
                stdin = self._get_stdin(queue_id),
                stdout = stdout_err, stderr = stdout_err,
                pid_write_func = set_proc_pid, coloured_output = False)

        finally:

            stdout_err.write("\n### Done ###\n")
            stdout_err.flush()
            stdout_err.close()

        return True, status

    def run_custom_shell_command(self, queue_id, command):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        cmd = command.split()
        cmd = ' '.join(cmd)
        stdout_err.write("Preparing to spawn parameter: '%s'. Good luck mate!\n" % (cmd,))
        stdout_err.flush()

        try:
            p = subprocess.Popen(cmd, stdout = stdout_err, stderr = stdout_err,
                stdin = self._get_stdin(queue_id), shell = True)
            self._set_processing_pid(queue_id, p.pid)
            rc = p.wait()
        finally:
            stdout_err.write("\n### Done ###\n")
            stdout_err.flush()
            stdout_err.close()
        return True, rc

    def move_entropy_packages_to_repository(self, queue_id, from_repo, to_repo, idpackages, do_copy):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        # run
        matches = []
        for idpackage in idpackages:
            matches.append((idpackage, from_repo,))

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin: sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                switched = self.SystemManagerExecutor.SystemInterface.Entropy.move_packages(
                    matches, to_repo,
                    from_repo = from_repo,
                    ask = False,
                    do_copy = do_copy
                )
                return switched
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        switched = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()

        rc = 1
        if len(switched) == len(idpackages):
            rc = 0
        return True, rc

    def scan_entropy_packages_database_changes(self, queue_id):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")
        Entropy = self.SystemManagerExecutor.SystemInterface.Entropy

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin: sys.stdin = os.fdopen(mystdin, 'rb')
            try:

                for repoid in Entropy.available_repositories():
                    self.run_entropy_treeupdates(queue_id, repoid)

                stdout_err.write("\n"+_("Calculating updates...").encode('utf-8')+"\n")
                stdout_err.flush()

                to_add, to_remove, to_inject = Entropy.scan_package_changes()
                mydict = { 'add': to_add, 'remove': to_remove, 'inject': to_inject }

                # setup add data
                mydict['add_data'] = {}
                for portage_atom, portage_counter in to_add:
                    mydict['add_data'][(portage_atom, portage_counter,)] = self._get_spm_pkginfo(portage_atom, from_installed = True)

                mydict['remove_data'] = {}
                for idpackage, repoid in to_remove:
                    dbconn = Entropy.open_server_repository(repo = repoid, just_reading = True, warnings = False, do_cache = False)
                    mydict['remove_data'][(idpackage, repoid,)] = self._get_entropy_pkginfo(dbconn, idpackage, repoid)
                    dbconn.close()

                mydict['inject_data'] = {}
                for idpackage, repoid in to_inject:
                    dbconn = Entropy.open_server_repository(repo = repoid, just_reading = True, warnings = False, do_cache = False)
                    mydict['inject_data'][(idpackage, repoid,)] = self._get_entropy_pkginfo(dbconn, idpackage, repoid)
                    dbconn.close()

                return True, mydict

            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        data = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return data

    def run_entropy_database_updates(self, queue_id, to_add, to_remove, to_inject):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")
        Entropy = self.SystemManagerExecutor.SystemInterface.Entropy
        sys_settings = SystemSettings()

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:

                atoms_removed = []
                matches_injected = set()

                if to_inject:
                    Entropy.output(_("Running package injection"))

                # run inject
                for idpackage, repoid in to_inject:
                    matches_injected.add((idpackage, repoid,))
                    Entropy._transform_package_into_injected(idpackage,
                        repo = repoid)

                if to_remove:
                    Entropy.output(_("Running package removal"))

                # run remove
                remdata = {}
                for idpackage, repoid in to_remove:
                    dbconn = Entropy.open_server_repository(repo = repoid, just_reading = True, warnings = False, do_cache = False)
                    atoms_removed.append(dbconn.retrieveAtom(idpackage))
                    dbconn.close()
                    if repoid not in remdata:
                        remdata[repoid] = set()
                    remdata[repoid].add(idpackage)
                for repoid in remdata:
                    Entropy.remove_packages(remdata[repoid], repo = repoid)

                mydict = {
                    'added_data': {},
                    'remove_data': atoms_removed,
                    'inject_data': {}
                }

                if to_add:
                    problems = Entropy.check_config_file_updates()
                    if problems:
                        return False, mydict
                    Entropy.output(_("Running package quickpkg"))

                # run quickpkg
                for repoid in to_add:
                    store_dir = Entropy._get_local_store_directory(repoid)
                    for atom in to_add[repoid]:
                        Entropy.Spm().generate_package(atom, store_dir)

                # inject new into db
                avail_repos = Entropy.available_repositories()
                if etpConst['clientserverrepoid'] in avail_repos:
                    avail_repos.pop(etpConst['clientserverrepoid'])
                matches_added = set()
                for repoid in avail_repos:
                    store_dir = Entropy._get_local_store_directory(repoid)
                    package_files = os.listdir(store_dir)
                    if not package_files:
                        continue
                    package_files = [(os.path.join(store_dir, x), False) for x in package_files]

                    Entropy.output( "[%s|%s] %s" % (
                            repoid,
                            sys_settings['repositories']['branch'],
                            _("Adding packages"),
                        )
                    )
                    for package_file, inject in package_files:
                        Entropy.output("    %s" % (package_file,))

                    idpackages = Entropy.add_packages_to_repository(package_files, ask = False, repo = repoid)
                    matches_added |= set([(x, repoid,) for x in idpackages])


                Entropy.dependencies_test()

                for idpackage, repoid in matches_added:
                    dbconn = Entropy.open_server_repository(repo = repoid, just_reading = True, warnings = False, do_cache = False)
                    mydict['added_data'][(idpackage, repoid,)] = self._get_entropy_pkginfo(dbconn, idpackage, repoid)
                    dbconn.close()
                for idpackage, repoid in matches_injected:
                    dbconn = Entropy.open_server_repository(repo = repoid, just_reading = True, warnings = False, do_cache = False)
                    mydict['inject_data'][(idpackage, repoid,)] = self._get_entropy_pkginfo(dbconn, idpackage, repoid)
                    dbconn.close()
                return True, mydict

            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        data = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return data

    def run_entropy_dependency_test(self, queue_id):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                deps_not_matched = self.SystemManagerExecutor.SystemInterface.Entropy.dependencies_test()
                return True, deps_not_matched
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        data = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return data

    def run_entropy_library_test(self, queue_id):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                return self.SystemManagerExecutor.SystemInterface.Entropy.test_shared_objects()
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        status, result = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()

        mystatus = False
        if status == 0:
            mystatus = True
        if not result:
            result = set()
        return mystatus, result

    def run_entropy_checksum_test(self, queue_id, repoid, mode):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                if mode == "local":
                    data = self.SystemManagerExecutor.SystemInterface.Entropy.verify_local_packages([], ask = False, repo = repoid)
                else:
                    data = self.SystemManagerExecutor.SystemInterface.Entropy.verify_remote_packages([], ask = False, repo = repoid)
                return True, data
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        mydata = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return mydata

    def run_entropy_treeupdates(self, queue_id, repoid):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                sys.stdout.write(_("Opening database to let it run treeupdates. If you won't see anything below, it's just fine.").encode('utf-8')+"\n")
                dbconn = self.SystemManagerExecutor.SystemInterface.Entropy.open_server_repository(
                    repo = repoid, do_cache = False,
                    read_only = True
                )
                dbconn.close()
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return True, 0

    def scan_entropy_mirror_updates(self, queue_id, repositories):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")
        import socket
        Entropy = self.SystemManagerExecutor.SystemInterface.Entropy
        sys_settings = SystemSettings()

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:

                sys.stdout.write(_("Scanning").encode('utf-8')+"\n")
                repo_data = {}
                for repoid in repositories:

                    repo_data[repoid] = {}

                    for uri in Entropy.remote_packages_mirrors(repoid):

                        crippled_uri = EntropyTransceiver.get_uri_name(uri)

                        repo_data[repoid][crippled_uri] = {}
                        repo_data[repoid][crippled_uri]['packages'] = {}

                        try:
                            upload_queue, download_queue, removal_queue, \
                                fine_queue, remote_packages_data = Entropy.Mirrors._calculate_packages_to_sync(
                                    repoid, uri)
                        except socket.error:
                            entropy.tools.print_traceback(f = stdout_err)
                            stdout_err.write("\n"+_("Socket error, continuing...").encode('utf-8')+"\n")
                            continue

                        if (upload_queue or download_queue or removal_queue):
                            upload, download, removal, copy, metainfo = Entropy.Mirrors.expand_queues(
                                upload_queue,
                                download_queue,
                                removal_queue,
                                remote_packages_data,
                                sys_settings['repositories']['branch'],
                                repoid
                            )
                            if len(upload)+len(download)+len(removal)+len(copy):
                                repo_data[repoid][crippled_uri]['packages'] = {
                                    'upload': upload,
                                    'download': download,
                                    'removal': removal,
                                    'copy': copy,
                                }

                        repo_data[repoid][crippled_uri]['database'] = {
                            'current_revision': 0,
                            'remote_revision': 0,
                            'download_latest': (),
                            'upload_queue': []
                        }

                    for uri in Entropy.remote_repository_mirrors(repoid):

                        crippled_uri = EntropyTransceiver.get_uri_name(uri)
                        if crippled_uri not in repo_data[repoid]:
                            repo_data[repoid][crippled_uri] = {}
                            repo_data[repoid][crippled_uri]['packages'] = {}

                        # now the db
                        current_revision = Entropy.local_repository_revision(
                            repoid)
                        remote_revision = Entropy.remote_repository_revision(
                            repoid)
                        download_latest, upload_queue = Entropy.Mirrors.calculate_database_sync_queues(repoid)

                        repo_data[repoid][crippled_uri]['database'] = {
                            'current_revision': current_revision,
                            'remote_revision': remote_revision,
                            'download_latest': download_latest,
                            'upload_queue': [(EntropyTransceiver.get_uri_name(x[0]), x[1],) for x in upload_queue]
                        }

                return True, repo_data

            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        data = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return data

    def run_entropy_mirror_updates(self, queue_id, repository_data):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")
        Entropy = self.SystemManagerExecutor.SystemInterface.Entropy
        sys_settings = SystemSettings()

        def sync_remote_databases(repoid, pretend):

            rdb_status = Entropy.Mirrors.remote_repository_status(repoid)
            Entropy.output(
                "%s:" % (_("Remote Entropy Database Repository Status"),),
                header = " * "
            )
            for myuri, myrev in rdb_status.items():
                Entropy.output("\t %s:\t %s" % (_("Host"), EntropyTransceiver.get_uri_name(myuri),))
                Entropy.output("\t  * %s: %s" % (_("Database revision"), myrev,))
            local_revision = Entropy.local_repository_revision(repoid)
            Entropy.output("\t  * %s: %s" % (_("Database local revision currently at"), local_revision,))
            if pretend:
                return 0, set(), set()

            errors = Entropy.Mirrors.sync_repository(repoid)
            remote_status = Entropy.Mirrors.remote_repository_status(repoid)
            Entropy.output(" * %s: " % (_("Remote Entropy Database Repository Status"),))
            for myuri, myrev in remote_status.items():
                Entropy.output("\t %s:\t%s" % (_("Host"), EntropyTransceiver.get_uri_name(myuri),))
                Entropy.output("\t  * %s: %s" % (_("Database revision"), myrev,) )

            return errors


        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:

                repo_data = {}
                sys_settings_srv_plugin_id = \
                    etpConst['system_settings_plugins_ids']['server_plugin']
                for repoid in repository_data:

                    # avoid __default__
                    if repoid == etpConst['clientserverrepoid']:
                        continue

                    successfull_mirrors = set()
                    mirrors_errors = False
                    mirrors_tainted = False
                    broken_mirrors = set()
                    check_data = []

                    repo_data[repoid] = {
                        'mirrors_tainted': mirrors_tainted,
                        'mirrors_errors': mirrors_errors,
                        'successfull_mirrors': successfull_mirrors.copy(),
                        'broken_mirrors': broken_mirrors.copy(),
                        'check_data': check_data,
                        'db_errors': 0,
                    }

                    if repository_data[repoid]['pkg']:

                        mirrors_tainted, mirrors_errors, \
                        successfull_mirrors, broken_mirrors, \
                        check_data = Entropy.Mirrors.sync_packages(
                            repo, ask = False,
                            pretend = repository_data[repoid]['pretend'],
                            packages_check = repository_data[repoid]['pkg_check'])

                        repo_data[repoid]['mirrors_tainted'] = mirrors_tainted
                        repo_data[repoid]['mirrors_errors'] = mirrors_errors
                        repo_data[repoid]['successfull_mirrors'] = successfull_mirrors
                        repo_data[repoid]['broken_mirrors'] = broken_mirrors
                        repo_data[repoid]['check_data'] = check_data

                        if (not successfull_mirrors) and (not repository_data[repoid]['pretend']):
                            continue

                    if (not mirrors_errors) and repository_data[repoid]['db']:

                        if mirrors_tainted and sys_settings[sys_settings_srv_plugin_id]['server']['rss']['enabled']:
                            commit_msg = repository_data[repoid]['commit_msg']
                            if not commit_msg:
                                commit_msg = "Autodriven update"
                            ServerRssMetadata()['commitmessage'] = commit_msg

                        errors = sync_remote_databases(repoid, repository_data[repoid]['pretend'])
                        repo_data[repoid]['db_errors'] = errors
                        if errors:
                            continue
                        Entropy.Mirrors.lock_mirrors(repoid, False)
                        Entropy.Mirrors.tidy_mirrors(
                            repoid, ask = False,
                            pretend = repository_data[repoid]['pretend'])

                return True, repo_data

            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        data = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return data

    def get_spm_glsa_data(self, queue_id, list_type):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        glsa_ids = spm.get_security_packages(list_type)
        if not glsa_ids:
            return True, [] # return empty list then

        data = {}
        for myid in glsa_ids:
            data[myid] = spm.get_security_advisory_metadata(myid)
        return True, data

    def get_notice_board(self, queue_id, repoid):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                data = self.SystemManagerExecutor.SystemInterface.Entropy.Mirrors.read_notice_board(repoid)
                if data is None:
                    return False, None
                return True, data
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        mydata = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return mydata

    def remove_notice_board_entries(self, queue_id, repoid, entry_ids):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                for entry_id in entry_ids:
                    self.SystemManagerExecutor.SystemInterface.Entropy.Mirrors.remove_from_notice_board(repoid, entry_id)
                self.SystemManagerExecutor.SystemInterface.Entropy.Mirrors.upload_notice_board(repoid)
                return True, data
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        mydata = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return mydata

    def add_notice_board_entry(self, queue_id, repoid, title, notice_text, link):

        queue_data, key = self.SystemManagerExecutor.SystemInterface.get_item_by_queue_id(queue_id, copy = True)
        if queue_data is None:
            return False, 'no item in queue'

        stdout_err = open(queue_data['stdout'], "a+")

        def myfunc():
            sys.stdout = stdout_err
            sys.stderr = stdout_err
            mystdin = self._get_stdin(queue_id)
            if mystdin:
                sys.stdin = os.fdopen(mystdin, 'rb')
            try:
                data = self.SystemManagerExecutor.SystemInterface.Entropy.Mirrors.update_notice_board(
                    repoid, title, notice_text, link = link)
                return True, data
            except Exception as e:
                entropy.tools.print_traceback()
                return False, str(e)
            finally:
                sys.stdout.write("\n### Done ###\n")
                sys.stdout.flush()
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                sys.stdin = sys.__stdin__

        def write_pid(pid):
            self._set_processing_pid(queue_id, pid)

        mydata = entropy.tools.spawn_function(myfunc, write_pid_func = write_pid)
        stdout_err.flush()
        stdout_err.close()
        return mydata

    def _get_stdin(self, queue_id):
        mystdin = None
        std_data = self.SystemManagerExecutor.SystemInterface.ManagerQueueStdInOut.get(queue_id)
        if std_data is not None:
            mystdin = std_data[0]
        return mystdin

    def _file_output(self, f, *myargs, **mykwargs):

        f.flush()
        back = mykwargs.get("back")
        count = mykwargs.get("count")
        header = mykwargs.get("header")
        percent = mykwargs.get("percent")
        text = myargs[0].encode('utf-8')
        if not header:
            header = ''

        count_str = ""
        if count:
            if len(count) > 1:
                if percent:
                    count_str = " ("+str(round((float(count[0])/count[1])*100, 1))+"%) "
                else:
                    count_str = " (%s/%s) " % (red(str(count[0])), blue(str(count[1])),)

        def is_last_newline(f):
            try:
                f.seek(-1, os.SEEK_END)
                last = f.read(1)
                if last == "\n":
                    return True
            except IOError:
                pass
            return False

        if back:
            seek_till_newline(f)
            txt = header+count_str+text
        else:
            if not is_last_newline(f):
                f.write("\n")
            txt = header+count_str+text+"\n"
        f.write(txt)

        f.flush()

    # !!! duplicate
    def _get_entropy_pkginfo(self, dbconn, idpackage, repoid):
        data = {}
        try:
            data['atom'], data['name'], data['version'], data['versiontag'], \
            data['description'], data['category'], data['chost'], \
            data['cflags'], data['cxxflags'], data['homepage'], \
            data['license'], data['branch'], data['download'], \
            data['digest'], data['slot'], data['etpapi'], \
            data['datecreation'], data['size'], data['revision']  = dbconn.getBaseData(idpackage)
        except TypeError:
            return data
        data['injected'] = dbconn.isInjected(idpackage)
        data['repoid'] = repoid
        data['idpackage'] = idpackage
        return data

    def _get_spm_pkginfo(self, matched_atom, from_installed = False):
        data = {}
        data['atom'] = matched_atom
        data['key'] = entropy.dep.dep_getkey(matched_atom)
        spm = self.SystemManagerExecutor.SystemInterface.Entropy.Spm()
        try:
            if from_installed:
                data['slot'] = spm.get_installed_package_metadata(matched_atom, "SLOT")
                portage_matched_atom = spm.match_package("%s:%s" % (data['key'], data['slot'],))
                # get installed package description
                data['available_atom'] = portage_matched_atom
                if portage_matched_atom:
                    data['use'] = spm.get_package_compile_options(portage_matched_atom)
                else:
                    # get use flags of the installed package
                    data['use'] = spm.get_installed_package_useflags(matched_atom)
                data['description'] = spm.get_installed_package_metadata(matched_atom, "DESCRIPTION")
            else:
                data['slot'] = spm.get_package_metadata(matched_atom, "SLOT")
                data['use'] = spm.get_package_compile_options(matched_atom)
                data['installed_atom'] = spm.match_installed_package("%s:%s" % (data['key'], data['slot'].split(",")[0],))
                data['description'] = spm.get_package_metadata(matched_atom, "DESCRIPTION")
        except KeyError:
            pass

        return data
