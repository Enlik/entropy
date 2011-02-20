# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Source Package Manager "Portage" Plugin}.

"""
import os
import errno
import bz2
import hashlib
import shlex
import stat
import sys
import shutil
import stat
import tempfile
import subprocess
import tarfile
import time

from entropy.const import etpConst, etpUi, const_get_stringtype, \
    const_convert_to_unicode, const_convert_to_rawstring, const_setup_perms
from entropy.exceptions import FileNotFound, SPMError, InvalidDependString, \
    InvalidAtom, EntropyException
from entropy.output import darkred, darkgreen, brown, darkblue, purple, red, \
    bold, blue, getcolor, decolorize
from entropy.i18n import _
from entropy.core.settings.base import SystemSettings
from entropy.misc import LogFile
from entropy.spm.plugins.skel import SpmPlugin
import entropy.dep
import entropy.tools
from entropy.spm.plugins.interfaces.portage_plugin import xpak
from entropy.spm.plugins.interfaces.portage_plugin import xpaktools

class PortagePackageGroups(dict):
    """
    Entropy Package categories group representation
    """
    def __init__(self):
        dict.__init__(self)

        data = {
            'accessibility': {
                'name': _("Accessibility"),
                'description': \
                    _("Accessibility applications"),
                'categories': ['app-accessibility'],
            },
            'office': {
                'name': _("Office"),
                'description': _("Applications used in office environments"),
                'categories': ['app-office', 'app-pda', 'app-mobilephone',
                    'app-cdr', 'app-antivirus', 'app-laptop', 'mail-',
                ],
            },
            'development': {
                'name': _("Development"),
                'description': _("Applications or system libraries"),
                'categories': ['dev-', 'sys-devel'],
            },
            'system': {
                'name': _("System"),
                'description': _("System applications or libraries"),
                'categories': ['sys-'],
            },
            'games': {
                'name': _("Games"),
                'description': _("Games, enjoy your spare time"),
                'categories': ['games-'],
            },
            'gnome': {
                'name': _("GNOME Desktop"),
                'description': \
                    _("Applications and libraries for the GNOME Desktop"),
                'categories': ['gnome-'],
            },
            'kde': {
                'name': _("KDE Desktop"),
                'description': \
                    _("Applications and libraries for the KDE Desktop"),
                'categories': ['kde-'],
            },
            'xfce': {
                'name': _("XFCE Desktop"),
                'description': \
                    _("Applications and libraries for the XFCE Desktop"),
                'categories': ['xfce-'],
            },
            'lxde': {
                'name': _("LXDE Desktop"),
                'description': \
                    _("Applications and libraries for the LXDE Desktop"),
                'categories': ['lxde-'],
            },
            'multimedia': {
                'name': _("Multimedia"),
                'description': \
                    _("Applications and libraries for Multimedia"),
                'categories': ['media-'],
            },
            'networking': {
                'name': _("Networking"),
                'description': \
                    _("Applications and libraries for Networking"),
                'categories': ['net-', 'www-'],
            },
            'science': {
                'name': _("Science"),
                'description': \
                    _("Scientific applications and libraries"),
                'categories': ['sci-'],
            },
            'security': {
                'name': _("Security"),
                'description': \
                    _("Security orientend applications"),
                'categories': ['app-antivirus', 'net-analyzer', 'net-firewall'],
            },
            'x11': {
                'name': _("X11"),
                'description': \
                    _("Applications and libraries for X11"),
                'categories': ['x11-'],
            },
        }
        self.update(data)


class PortageMetaphor:

    """
    This class (will) contains Portage packages metaphor related functions.
    It is intended for internal (plugin) use only. So, go away from here ;)
    """

    # used to properly sort /usr/portage/profiles/updates files
    @staticmethod
    def sort_update_files(update_list):
        """
        docstring_title

        @param update_list: 
        @type update_list: 
        @return: 
        @rtype: 
        """
        sort_dict = {}
        # sort per year
        for item in update_list:
            # get year
            year = item.split("-")[1]
            if year in sort_dict:
                sort_dict[year].append(item)
            else:
                sort_dict[year] = []
                sort_dict[year].append(item)
        new_list = []
        keys = sorted(sort_dict.keys())
        for key in keys:
            sort_dict[key].sort()
            new_list += sort_dict[key]
        del sort_dict
        return new_list


class PortageEntropyDepTranslator(object):
    """
    Conditional dependency string translator from Portage to Entropy.

    Example usage:
    >>> translator = PortageEntropyDepTranslator(portage_string)
    >>> entropy_string = translator.translate()
    entropy_string

    """

    class ParseError(EntropyException):
        """
        Parse error.
        """

    def __init__(self, portage_dependency):
        """
        PortageEntropyDepTranslator constructor.

        @param portage_dependency: Portage dependency string
        @type portage_dependency: string
        """
        self.__dep = portage_dependency

    def __produce_entropy_dep(self, split_dep):
        """
        Digest Portage raw dependency data produced by __extract_scope()
        """
        dep_str_list = []
        operator, sub_split = split_dep[0], split_dep[1:]

        for dep in sub_split:
            if isinstance(dep, list):
                _str = self.__produce_entropy_dep(dep)
            else:
                _str = dep
            dep_str_list.append(_str)

        return "( " + (" " + operator + " ").join(dep_str_list) + " )"

    def __extract_scope(self, split_sub):
        """
        Prepare split Portage dependency string for complete digestion.
        """
        scope_list = []
        nest_level = 0
        skip_count = 0
        sub_count = 0

        for sub_idx in range(len(split_sub)):

            sub_count += 1
            if skip_count:
                skip_count -= 1
                continue

            sub = split_sub[sub_idx]
            if sub == "||": # or
                try:
                    next_sub = split_sub[sub_idx+1]
                except IndexError:
                    raise PortageEntropyDepTranslator.ParseError()
                if next_sub != "(":
                    raise PortageEntropyDepTranslator.ParseError()

                local_sub_count, sub_scope = self.__extract_scope(
                    split_sub[sub_idx+2:])
                skip_count += local_sub_count
                scope_list.append(
                    [entropy.dep.DependencyStringParser.LOGIC_OR] + sub_scope)

            elif sub == "(":
                local_sub_count, sub_scope = self.__extract_scope(
                    split_sub[sub_idx+1:])
                skip_count += local_sub_count
                scope_list.append(
                    [entropy.dep.DependencyStringParser.LOGIC_AND] + sub_scope)
                nest_level += 1

            elif sub == ")":
                if nest_level == 0:
                    break # end of scope
                nest_level -= 1

            else:
                scope_list.append(sub)

        return sub_count, scope_list

    def translate(self):
        """
        Effectively translate Portage dependency string returning Entropy one.

        @return: Entropy dependency string
        @rtype: string
        @raise PortageEntropyDepTranslator.ParseError: in case of malformed
            Portage dependency.
        """
        split_sub = [x.strip() for x in self.__dep.split() if x.strip()]
        count, split_dep = self.__extract_scope(split_sub)
        return self.__produce_entropy_dep(split_dep[0])


class PortagePlugin(SpmPlugin):

    xpak_entries = {
        'description': "DESCRIPTION",
        'homepage': "HOMEPAGE",
        'chost': "CHOST",
        'category': "CATEGORY",
        'cflags': "CFLAGS",
        'cxxflags': "CXXFLAGS",
        'license': "LICENSE",
        'src_uri': "SRC_URI",
        'use': "USE",
        'iuse': "IUSE",
        'slot': "SLOT",
        'provide': "PROVIDE",
        'depend': "DEPEND",
        'rdepend': "RDEPEND",
        'pdepend': "PDEPEND",
        'needed': "NEEDED",
        'inherited': "INHERITED",
        'keywords': "KEYWORDS",
        'contents': "CONTENTS",
        'counter': "COUNTER",
        'defined_phases': "DEFINED_PHASES",
        'repository': "repository",
        'pf': "PF",
        'eapi': "EAPI",
        'features': "FEATURES",
    }

    _xpak_const = {
        # xpak temp directory path
        'entropyxpakrelativepath': "xpak",
        # xpak metadata directory path
        'entropyxpakdatarelativepath': "data",
        # xpak metadata file name
        'entropyxpakfilename': "metadata.xpak",
    }

    _ebuild_entries = {
        'ebuild_pkg_tag_var': "ENTROPY_PROJECT_TAG",
    }

    _cmd_map = {
        'env_update_cmd': "/usr/sbin/env-update",
        'ask_cmd': "--ask",
        'info_cmd': "--info",
        'remove_cmd': "-C",
        'nodeps_cmd': "--nodeps",
        'fetchonly_cmd': "--fetchonly",
        'buildonly_cmd': "--buildonly",
        'oneshot_cmd': "--oneshot",
        'pretend_cmd': "--pretend",
        'verbose_cmd': "--verbose",
        'nocolor_cmd': "--color=n",
        'source_profile_cmd': "source /etc/profile",
        'exec_cmd': "/usr/bin/emerge",
    }

    _package_phases_map = {
        'setup': 'setup',
        'preinstall': 'preinst',
        'postinstall': 'postinst',
        'preremove': 'prerm',
        'postremove': 'postrm',
        'configure': 'config',
    }

    _config_files_map = {
        'global_make_conf': "/etc/make.conf",
        'global_package_keywords': "/etc/portage/package.keywords",
        'global_package_use': "/etc/portage/package.use",
        'global_package_mask': "/etc/portage/package.mask",
        'global_package_unmask': "/etc/portage/package.unmask",
        'global_make_profile': "/etc/make.profile",
    }

    PLUGIN_API_VERSION = 6

    SUPPORTED_MATCH_TYPES = [
        "bestmatch-visible", "cp-list", "list-visible", "match-all",
        "match-visible", "minimum-all", "minimum-visible"
    ]

    CACHE = {
        'vartree': {},
        'binarytree': {},
        'config': {},
        'portagetree': {},
    }

    IS_DEFAULT = True
    PLUGIN_NAME = 'portage'
    ENV_FILE_COMP = "environment.bz2"
    EBUILD_EXT = ".ebuild"
    KERNEL_CATEGORY = "sys-kernel"
    _PORTAGE_ENTROPY_PACKAGE_NAME = "sys-apps/portage"

    if "/usr/lib/gentoolkit/pym" not in sys.path:
        sys.path.append("/usr/lib/gentoolkit/pym")

    def init_singleton(self, output_interface):

        self.__output = output_interface
        self.__entropy_repository_treeupdate_digests = {}

        # setup color status
        if not getcolor():
            # Entropy color output is disable, disable Portage
            os.environ['NOCOLOR'] = "yes"
        elif "NOCOLOR" in os.environ:
            del os.environ['NOCOLOR']

        # importing portage stuff
        import portage.const
        # Portage 2.1.9x, enable package sets for overlay.
        portage.const._ENABLE_SET_CONFIG = True
        import portage
        import portage.util
        self._portage = portage

    def _reload_modules(self):

        """
        WARNING: this function reloads Portage modules in RAM
        it brutally kills the current instance by removing
        it from sys.modules and calling a new import.
        There may be resource leaks but since this can only be run
        once per "session", that's nothing to worry about.
        """
        mytxt = "%s..." % (
            brown(_("Reloading Portage modules")),
        )
        self.__output.output(
            mytxt,
            importance = 0,
            header = red("   ## ")
        )

        for obj in tuple(PortagePlugin.CACHE.values()):
            obj.clear()

        port_key = "portage"
        emerge_key = "_emerge"
        # we have a portage module instance in here too
        # need to kill it
        current_module_name = __name__ + "." + port_key
        if current_module_name in sys.modules:
            del sys.modules[current_module_name]

        for key in tuple(sys.modules.keys()):
            if key.startswith(port_key):
                del sys.modules[key]
            elif key.startswith(emerge_key):
                del sys.modules[key]
        # now reimport everything

        # Portage 2.1.9x, enable package sets for overlay.
        import portage.const
        portage.const._ENABLE_SET_CONFIG = True
        import portage
        import portage.util
        # reassign portage variable, pointing to a fresh object
        self._portage = portage

    @staticmethod
    def get_package_groups():
        """
        Return package groups available metadata (Spm categories are grouped
        into macro categories called "groups").
        """
        return PortagePackageGroups()

    def package_metadata_keys(self):
        """
        Reimplemented from SpmPlugin class.
        """
        # return what's inside vartree because it's more complete
        dbapi = self._get_portage_vartree().dbapi
        if hasattr(dbapi, '_aux_cache_keys'):
            return list(dbapi._aux_cache_keys)

        sys.stderr.write("PortagePlugin: missing vardb._aux_cache_keys !\n")
        return ["CHOST", "COUNTER", "DEPEND", "DESCRIPTION",
            "EAPI", "HOMEPAGE", "IUSE", "KEYWORDS",
            "LICENSE", "PDEPEND", "PROPERTIES", "PROVIDE", "RDEPEND",
            "repository", "RESTRICT", "SLOT", "USE"
        ]

    def get_cache_directory(self, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        if root is None:
            root = etpConst['systemroot'] + os.path.sep
        cache_path = self._portage.const.CACHE_PATH.lstrip(os.path.sep)
        return os.path.join(root, cache_path)

    def get_package_metadata(self, package, key):
        """
        Reimplemented from SpmPlugin class.
        """
        return self._portage.portdb.aux_get(package, [key])[0]

    def get_package_changelog(self, package):
        """
        Reimplemented from SpmPlugin class.
        """
        ebuild_path = self.get_package_build_script_path(package)
        if isinstance(ebuild_path, const_get_stringtype()):

            clog_path = os.path.join(os.path.dirname(ebuild_path), "ChangeLog")
            if os.access(clog_path, os.R_OK) and os.path.isfile(clog_path):
                with open(clog_path, "rb") as clog_f:
                    return clog_f.read()

    def get_package_build_script_path(self, package):
        """
        Reimplemented from SpmPlugin class.
        """
        return self._portage.portdb.findname(package)

    def get_installed_package_build_script_path(self, package, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        return os.path.join(self._get_vdb_path(root = root), package,
            package.split("/")[-1] + PortagePlugin.EBUILD_EXT)

    def get_installed_package_metadata(self, package, key, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        if root is None:
            root = etpConst['systemroot'] + os.path.sep
        vartree = self._get_portage_vartree(root = root)
        try:
            return vartree.dbapi.aux_get(package, [key])[0]
        except KeyError: # make clear that we raise KeyError
            raise
        except OSError as err:
            raise KeyError("Original OSError: %s" % (err,))

    def get_system_packages(self):
        """
        Reimplemented from SpmPlugin class.
        """
        system = []
        for package in self._portage.settings.packages:
            pkgs = self.match_installed_package(package, match_all = True)
            system.extend(pkgs)
        return system

    def get_package_categories(self):
        """
        Reimplemented from SpmPlugin class.
        """
        return self._get_portage_config(os.path.sep, os.path.sep).categories

    def get_package_category_description_metadata(self, category):
        """
        Reimplemented from SpmPlugin class.
        """
        from xml.dom import minidom
        data = {}
        portdir = self._portage.settings['PORTDIR']
        myfile = os.path.join(portdir, category, "metadata.xml")
        if os.access(myfile, os.R_OK) and os.path.isfile(myfile):
            doc = minidom.parse(myfile)
            longdescs = doc.getElementsByTagName("longdescription")
            for longdesc in longdescs:
                data[longdesc.getAttribute("lang").strip()] = \
                    ' '.join([x.strip() for x in \
                        longdesc.firstChild.data.strip().split("\n")])
        return data

    def _get_glsa(self):
        try:
            import glsa
            glsa_mod = glsa
        except ImportError:
            glsa_mod = None
        return glsa_mod

    def get_security_packages(self, security_property):
        """
        Reimplemented from SpmPlugin class.
        """
        _glsa = self._get_glsa()
        if _glsa is None:
            return []
        if security_property not in ['new', 'all', 'affected']:
            return []

        glsaconfig = _glsa.checkconfig(
            self._portage.config(clone=self._portage.settings))
        completelist = _glsa.get_glsa_list(
            glsaconfig["GLSA_DIR"], glsaconfig)

        glsalist = []
        if security_property == "new":

            checklist = []
            if os.access(glsaconfig["CHECKFILE"], os.R_OK) and \
                os.path.isfile(glsaconfig["CHECKFILE"]):
                with open(glsaconfig["CHECKFILE"], "rb") as check_f:
                    checklist.extend([x.strip() for x in check_f.readlines()])
            glsalist = [x for x in completelist if x not in checklist]

        elif security_property == "all":
            glsalist = completelist

        elif security_property == "affected":

            # maybe this should be todolist instead
            for glsa_item in completelist:
                try:
                    myglsa = _glsa.Glsa(glsa_item, glsaconfig)
                except (_glsa.GlsaTypeException, _glsa.GlsaFormatException,):
                    continue

                if not myglsa.isVulnerable():
                    continue

                glsalist.append(glsa_item)

        return glsalist

    def get_security_advisory_metadata(self, advisory_id):
        """
        Reimplemented from SpmPlugin class.
        """
        _glsa = self._get_glsa()
        if _glsa is None:
            return {}

        glsaconfig = _glsa.checkconfig(
            self._portage.config(clone=self._portage.settings))
        try:
            myglsa = _glsa.Glsa(advisory_id, glsaconfig)
        except (_glsa.GlsaTypeException, _glsa.GlsaFormatException):
            return {}

        mydict = {
            'glsa_id': advisory_id,
            'number': myglsa.nr,
            'access': myglsa.access,
            'title': myglsa.title,
            'synopsis': myglsa.synopsis,
            'announced': myglsa.announced,
            'revised': myglsa.revised,
            'bugs': myglsa.bugs,
            'description': myglsa.description,
            'resolution': myglsa.resolution,
            'impact': myglsa.impact_text,
            'impacttype': myglsa.impact_type,
            'affected': myglsa.affected,
            'background': myglsa.background,
            'glsatype': myglsa.glsatype,
            'packages': myglsa.packages,
            'services': myglsa.services,
            'product': myglsa.product,
            'references': myglsa.references,
            'workaround': myglsa.workaround,
        }

        status = "[U]"
        if myglsa.isApplied():
            status = "[A]"
        elif myglsa.isVulnerable():
            status = "[N]"
        mydict['status'] = status

        return mydict

    def get_setting(self, key):
        """
        Reimplemented from SpmPlugin class.
        """
        return self._portage.settings[key]

    def get_user_installed_packages_file(self, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        world_file = self._portage.const.WORLD_FILE
        if root is None:
            root = etpConst['systemroot'] + os.path.sep
        return os.path.join(root, world_file)

    def get_merge_protected_paths(self):
        """
        Reimplemented from SpmPlugin class.
        """
        config_protect = self._portage.settings['CONFIG_PROTECT']
        return [os.path.expandvars(x) for x in config_protect.split()]

    def get_merge_protected_paths_mask(self):
        """
        Reimplemented from SpmPlugin class.
        """
        config_protect = self._portage.settings['CONFIG_PROTECT_MASK']
        return [os.path.expandvars(x) for x in config_protect.split()]

    def get_download_mirrors(self, mirror_name):
        """
        Reimplemented from SpmPlugin class.
        """
        mirrors = []
        if mirror_name in self._portage.thirdpartymirrors:
            mirrors.extend(self._portage.thirdpartymirrors[mirror_name])
        return mirrors

    def _get_global_updates(self):
        try:
            from portage._global_updates import _global_updates
        except ImportError:
            _global_updates = self._portage._global_updates
        return _global_updates

    def packages_repositories_metadata_update(self):
        """
        Reimplemented from SpmPlugin class.
        """
        root = etpConst['systemroot'] + os.path.sep
        mydb = {}
        mydb[root] = {}
        mydb[root]['vartree'] = self._get_portage_vartree(root)
        mydb[root]['porttree'] = self._get_portage_portagetree(root)
        mydb[root]['bintree'] = self._get_portage_binarytree(root)
        mydb[root]['virtuals'] = self._portage.settings.getvirtuals()

        if etpUi['mute']:
            pid = os.fork()
            if pid > 0:
                os.waitpid(pid, 0)
            else:
                log = LogFile(
                    level = SystemSettings()['system']['log_level'],
                    filename = etpConst['entropylogfile'],
                    header = "[spm]"
                )
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = log
                sys.stderr = log

                self._get_global_updates()(mydb, {})

                sys.stdout = old_stdout
                sys.stderr = old_stderr
                log.flush()
                log.close()
                os._exit(0)
        else:
            self._get_global_updates()(mydb, {}) # always force

    def match_package(self, package, match_type = None):
        """
        Reimplemented from SpmPlugin class.
        """
        if match_type is None:
            match_type = "bestmatch-visible"
        elif match_type not in PortagePlugin.SUPPORTED_MATCH_TYPES:
            raise KeyError()
        try:
            return self._portage.portdb.xmatch(match_type, package)
        except self._portage.exception.PortageException:
            raise KeyError()

    def match_installed_package(self, package, match_all = False, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        if root is None:
            root = etpConst['systemroot'] + os.path.sep

        vartree = self._get_portage_vartree(root = root)
        try:
            matches = vartree.dep_match(package) or []
        except self._portage.exception.InvalidAtom as err:
            raise InvalidAtom(str(err))

        if match_all:
            return matches
        elif matches:
            return matches[-1]
        return ''

    def generate_package(self, package, file_save_path):
        """
        Reimplemented from SpmPlugin class.
        """
        pkgcat, pkgname = package.split("/", 1)
        if not os.path.isdir(file_save_path):
            os.makedirs(file_save_path)
        file_save_path += os.path.sep + pkgcat + ":" + \
            pkgname + etpConst['packagesext']
        dbdir = os.path.join(self._get_vdb_path(), pkgcat, pkgname)

        trees = self._portage.db["/"]
        vartree = trees["vartree"]
        dblnk = self._portage.dblink(pkgcat, pkgname, "/", vartree.settings,
            treetype="vartree", vartree=vartree)
        if etpConst['uid'] == 0:
            dblnk.lockdb()

        # store package file in temporary directory, then move
        # atomicity ftw
        tmp_fd, tmp_file = tempfile.mkstemp(dir = etpConst['entropyunpackdir'])
        # cannot use fdopen with tarfile
        tar = tarfile.open(tmp_file, mode = "w:bz2")

        contents = dblnk.getcontents()
        paths = sorted(contents)

        for path in paths:
            try:
                exist = os.lstat(path)
            except OSError:
                continue # skip file
            ftype = contents[path][0]
            lpath = path
            arcname = path[1:]
            if 'dir' == ftype and \
                not stat.S_ISDIR(exist.st_mode) and \
                os.path.isdir(lpath):
                lpath = os.path.realpath(lpath)
            tarinfo = tar.gettarinfo(lpath, arcname)

            if stat.S_ISREG(exist.st_mode):
                with open(path, "rb") as f:
                    tar.addfile(tarinfo, f)
            else:
                tar.addfile(tarinfo)

        tar.close()
        # appending xpak informations
        tbz2 = xpak.tbz2(tmp_file)
        tbz2.recompose(dbdir)
        dblnk.unlockdb()
        # now do atomic move
        try:
            os.rename(tmp_file, file_save_path)
        except OSError:
            # atomicity not possible
            shutil.move(tmp_file, file_save_path)

        if os.path.isfile(file_save_path) and \
            os.access(file_save_path, os.F_OK | os.R_OK):
            return file_save_path

        raise SPMError("SPMError: Spm:generate_package %s: %s %s" % (
                _("error"),
                file_save_path,
                _("not found"),
            )
        )

    def _add_kernel_dependency_to_pkg(self, pkg_data, pkg_dir_prefix):

        # NOTE: i hate hardcoded shit, but our SPM doesn't support
        # kernel dependencies.
        kmod_pfx = "/lib/modules"
        kmox_sfx = ".ko"
        modinfo_path = "/sbin/modinfo"
        content = [x for x in pkg_data['content'] if x.startswith(kmod_pfx)]
        content = [x for x in content if x.endswith(kmox_sfx)]

        # filter out hidden files
        if not content:
            return

        def read_kern_vermagic(ko_path):

            tmp_fd, tmp_file = tempfile.mkstemp()
            try:
                with os.fdopen(tmp_fd, "w") as tmp_fw:
                    rc = subprocess.call((modinfo_path, "-F", "vermagic",
                        ko_path), stdout = tmp_fw, stderr = tmp_fw)
                    tmp_fw.flush()

                tmp_r = open(tmp_file, "r")
                modinfo_output = tmp_r.read().strip()
                tmp_r.close()
            finally:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
                os.remove(tmp_file)

            if rc != 0:
                import warnings
                warnings.warn(
                    "Cannot properly guess kernel module vermagic, error" + \
                    modinfo_output)
                return

            return modinfo_output.split()[0]

        for item in content:

            # read vermagic
            item_pkg_path = os.path.join(pkg_dir_prefix, item[1:])
            kern_vermagic = read_kern_vermagic(item_pkg_path)
            if kern_vermagic is None:
                continue

            if not entropy.dep.is_valid_package_tag(kern_vermagic):
                # argh! wtf, this is invalid!
                continue

            # properly set package tag and slot
            pkg_data['versiontag'] = kern_vermagic
            # tweak slot, yeah
            pkg_data['slot'] = "%s,%s" % (pkg_data['slot'], kern_vermagic,)

            # now try to guess package providing that vermagic
            possible_kernel_owned_path = os.path.join(kmod_pfx, kern_vermagic)
            owners = self.search_paths_owners([possible_kernel_owned_path])
            owner_data = None
            k_atom = None
            for k_atom, k_slot in owners:
                k_cat, k_name, k_ver, k_rev = entropy.dep.catpkgsplit(k_atom)
                if k_cat == PortagePlugin.KERNEL_CATEGORY:
                    owner_data = (k_cat, k_name, k_ver, k_rev,)
                    break

            if owner_data is None:
                # heh, user has broken deps, who cares!
                return

            # yippie, kernel dep installed also for SPM.
            k_cat, k_name, k_ver, k_rev = owner_data
            if k_rev != "r0":
                k_ver += "-%s" % (k_rev,)
            if k_atom is not None:
                kern_dep_key = "=%s~-1" % (k_atom,)

            return kern_dep_key

    def _get_default_virtual_pkg(self, virtual_key):
        defaults = self._portage.settings.getvirtuals()[virtual_key]
        if defaults:
            return defaults[0]

    def __source_env_get_var(self, env_file, env_var):
        cmd = "/bin/bash -c \"source " + env_file + \
            " && echo ${" + env_var + "}\""
        tmp_fd, tmp_file = tempfile.mkstemp(prefix = "etp_portage")
        try:
            with os.fdopen(tmp_fd, "w") as std_f:
                proc = subprocess.Popen(shlex.split(cmd), stdout = std_f,
                    stderr = std_f)
                sts = proc.wait()
                std_f.flush()

            with open(tmp_file, "r") as std_f:
                output = std_f.read()
        finally:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
            os.remove(tmp_file)

        if sts != 0:
            raise IOError("cannot source %s and get %s => %s" % (env_file,
                env_var, repr(output)))
        return output.strip()

    def __pkg_sources_filtering(self, sources):
        sources.discard("->")
        sources = set((x for x in sources if "/" in x))
        return sources

    @staticmethod
    def dump_package_metadata(entropy_package_path, metadata_path):
        """
        Reimplemented from SpmPlugin class.
        """
        return xpaktools.suck_xpak(entropy_package_path, metadata_path)

    @staticmethod
    def aggregate_package_metadata(entropy_package_path, metadata_path):
        """
        Reimplemented from SpmPlugin class.
        """
        return xpaktools.aggregate_xpak(entropy_package_path, metadata_path)

    def extract_package_metadata(self, package_file, license_callback = None,
        restricted_callback = None):
        """
        Reimplemented from SpmPlugin class.
        """
        data = {}
        system_settings = SystemSettings()

        # fill package name and version
        data['digest'] = entropy.tools.md5sum(package_file)
        data['signatures'] = {
            'sha1': entropy.tools.sha1(package_file),
            'sha256': entropy.tools.sha256(package_file),
            'sha512': entropy.tools.sha512(package_file),
            'gpg': None, # GPG signature will be filled later on, if enabled
        }
        data['datecreation'] = str(os.path.getmtime(package_file))
        data['size'] = str(entropy.tools.get_file_size(package_file))

        tmp_dir = tempfile.mkdtemp()
        meta_dir = os.path.join(tmp_dir, "portage")
        pkg_dir = os.path.join(tmp_dir, "pkg")
        os.mkdir(meta_dir)
        os.mkdir(pkg_dir)

        # extract stuff
        xpaktools.extract_xpak(package_file, meta_dir)
        empty_content = False
        try:
            entropy.tools.uncompress_tarball(package_file,
                extract_path = pkg_dir, catch_empty = False)
        except tarfile.ReadError:
            empty_content = True

        # package injection status always false by default
        # developer can change metadatum after this function
        data['injected'] = False
        data['branch'] = system_settings['repositories']['branch']

        portage_entries = self._extract_pkg_metadata_generate_extraction_dict()
        for item in portage_entries:

            value = ''
            try:
                item_path = os.path.join(meta_dir,
                    portage_entries[item]['path'])
                with open(item_path, "rb") as item_f:
                    value = item_f.readline().strip()
                    value = const_convert_to_unicode(value)

            except IOError:
                if portage_entries[item]['critical']:
                    raise
            data[item] = value

        #if not data['chost']:
        #    # stupid portage devs and virtual pkgs!
        #    # try to cope
        #    # WARNING: this can be erroneously set to currently running
        #    # system CHOST that could not match the CHOST the package was
        #    # built with
        #    data['chost'] = self._portage.settings['CHOST']

        if not data['spm_repository']: # make sure it's set to None
            data['spm_repository'] = None

        if not data['sources']:
            env_bz2 = os.path.join(meta_dir, PortagePlugin.ENV_FILE_COMP)
            if os.path.isfile(env_bz2) and os.access(env_bz2, os.R_OK):
                # when extracting fake metadata, env_bz2 can be unavailable
                uncompressed_env_file = entropy.tools.unpack_bzip2(env_bz2)
                # unfortunately upstream dropped SRC_URI file support
                data['sources'] = self.__source_env_get_var(
                    uncompressed_env_file, "SRC_URI")

        # workout pf
        pf_atom = os.path.join(data['category'], data['pf'])
        pkgcat, pkgname, pkgver, pkgrev = entropy.dep.catpkgsplit(
            pf_atom)
        if pkgrev != "r0":
            pkgver += "-%s" % (pkgrev,)
        data['name'] = pkgname
        data['version'] = pkgver
        # bye bye pf
        del data['pf']

        # setup spm_phases properly
        spm_defined_phases_path = os.path.join(meta_dir,
            portage_entries['spm_phases']['path'])
        if not os.path.isfile(spm_defined_phases_path):
            # force to None, because metadatum can be '', which is valid
            data['spm_phases'] = None

        try:
            data['counter'] = int(data['counter'])
        except ValueError:
            # -2 values will be insterted as incremental
            # negative values into the database
            data['counter'] = -2

        data['keywords'] = [x.strip() for x in data['keywords'].split() \
            if x.strip()]
        if not data['keywords']:
            # support for packages with no keywords
            data['keywords'].insert(0, "**")

        data['keywords'] = set(data['keywords'])
        needed_file = os.path.join(meta_dir,
            PortagePlugin.xpak_entries['needed'])

        data['needed'] = self._extract_pkg_metadata_needed(needed_file)

        content_file = os.path.join(meta_dir,
            PortagePlugin.xpak_entries['contents'])
        # even if pkg_dir is tweaked after this, it's fine anyway for
        # packages emerge with -B, because for those, we also get the
        # full package_file (not a fake one).
        data['content'] = self._extract_pkg_metadata_content(content_file,
                package_file, pkg_dir)
        # There are packages providing no files, even if given package_file
        # is complete (meaning, it contains real file. Not a fake one, like
        # it can happen with "equo rescue spmsync", to make things quicker).
        # So, to differentiate between "complete package file with no content"
        # and "fake package file, with arbitrary content", we check
        # data['content']. If empty_content is True but data['content'] is
        # contains something, then we have a fake package_file.
        if data['content'] and empty_content:
            # fake package_file, need to tweak pkg_dir to systemroot
            pkg_dir = etpConst['systemroot'] + os.path.sep

        # at this point, pkg_dir must point to a valid "root" directory
        # because checksums have to be calculated against files being available
        # in the package. The case above (when using equo rescue spmsync) is
        # fine too.
        data['content_safety'] = self._extract_pkg_metadata_content_safety(
            data['content'], pkg_dir)
        data['disksize'] = entropy.tools.sum_file_sizes([
                os.path.join(pkg_dir, x) for x in data['content']])
        data['provided_libs'] = self._extract_pkg_metadata_provided_libs(
            pkg_dir, data['content'])

        # [][][] Kernel dependent packages hook [][][]
        data['versiontag'] = ''
        kern_dep_key = None

        if data['category'] != PortagePlugin.KERNEL_CATEGORY:
            kern_dep_key = self._add_kernel_dependency_to_pkg(data, pkg_dir)

        file_ext = PortagePlugin.EBUILD_EXT
        ebuilds_in_path = [x for x in os.listdir(meta_dir) if \
            x.endswith(file_ext)]

        if not data['versiontag'] and ebuilds_in_path:
            # has the user specified a custom package tag inside the ebuild
            ebuild_path = os.path.join(meta_dir, ebuilds_in_path[0])
            data['versiontag'] = self._extract_pkg_metadata_ebuild_entropy_tag(
                ebuild_path)

        data['trigger'] = const_convert_to_rawstring("")
        trigger_file = os.path.join(etpConst['triggersdir'], data['category'],
            data['name'], etpConst['triggername'])
        if os.access(trigger_file, os.R_OK) and os.path.isfile(trigger_file):
            with open(trigger_file, "rb") as trig_f:
                data['trigger'] = trig_f.read()

        # Get Spm ChangeLog
        pkgatom = "%s/%s-%s" % (data['category'], data['name'],
            data['version'],)
        try:
            changelog = self.get_package_changelog(pkgatom)
            if changelog is not None:
                data['changelog'] = const_convert_to_unicode(changelog)
            else:
                data['changelog'] = None
        except (UnicodeEncodeError, UnicodeDecodeError,) as e:
            sys.stderr.write("%s: %s, %s\n" % (
                "changelog string conversion error", e,
                package_file,)
            )
            data['changelog'] = None
        except:
            data['changelog'] = None

        if not data['eapi']:
            data['eapi'] = None
        portage_metadata = self._calculate_dependencies(
            data['iuse'], data['use'], data['license'], data['depend'],
            data['rdepend'], data['pdepend'], data['provide'], data['sources'],
            data['eapi']
        )

        data['provide'] = set(portage_metadata['PROVIDE'].split())
        data['license'] = portage_metadata['LICENSE']
        data['useflags'] = []
        for my_use in portage_metadata['USE']:
            if my_use in portage_metadata['USE_MASK']:
                continue
            if my_use in portage_metadata['USE_FORCE']:
                data['useflags'].append(my_use)
                continue
            if my_use in portage_metadata['ENABLED_USE']:
                data['useflags'].append(my_use)
            else:
                data['useflags'].append("-"+my_use)

        # useflags must be a set, as returned by entropy.db.getPackageData
        data['useflags'] = set(data['useflags'])
        # sources must be a set, as returned by entropy.db.getPackageData
        data['sources'] = set(portage_metadata['SRC_URI'].split())
        data['sources'] = self.__pkg_sources_filtering(data['sources'])
        data['dependencies'] = {}

        dep_keys = {
            "RDEPEND": etpConst['dependency_type_ids']['rdepend_id'],
            "PDEPEND": etpConst['dependency_type_ids']['pdepend_id'],
            "DEPEND": etpConst['dependency_type_ids']['bdepend_id'],
        }
        for dep_key, dep_val in dep_keys.items():
            for x in portage_metadata[dep_key].split():
                if x.startswith("!") or (x in ("(", "||", ")", "")):
                    continue
                data['dependencies'][x] = dep_val

        data['conflicts'] = [x.replace("!", "") for x in \
            portage_metadata['RDEPEND'].split() + \
            portage_metadata['PDEPEND'].split() if \
            x.startswith("!") and not x in ("(", "||", ")", "")]

        if kern_dep_key is not None:
            data['dependencies'][kern_dep_key] = \
                etpConst['dependency_type_ids']['rdepend_id']

        # Conflicting tagged packages support
        # Needs Entropy Client System Settings Plugin,
        # but since entropy.server loads entropy.client, it's completely
        # fine as of now.
        key = data['category'] + "/" + data['name']
        plug_data = etpConst['system_settings_plugins_ids']
        client_sysset_plg_id = plug_data['client_plugin']
        client_data = system_settings.get(client_sysset_plg_id, {})
        confl_data = None

        if client_data:
            repo_data = client_data['repositories']
            confl_data = repo_data['conflicting_tagged_packages'].get(key)

        if confl_data:
            for conflict in confl_data:
                data['conflicts'].append(conflict)

        # conflicts must be a set, which is what is returned
        # by entropy.db.getPackageData
        data['conflicts'] = set(data['conflicts'])

        # old-style virtual support, we need to check if this pkg provides
        # PROVIDE metadatum which points to itself, if so, this is the
        # default
        provide_extended = set()
        myself_provide_key = data['category'] + "/" + data['name']
        for provide_key in data['provide']:
            is_provide_default = 0
            try:
                profile_default_provide = self._get_default_virtual_pkg(
                    provide_key)
            except KeyError:
                profile_default_provide = 1 # cant be this

            if profile_default_provide == myself_provide_key:
                is_provide_default = 1

            provide_extended.add((provide_key, is_provide_default,))

        # this actually changes provide format
        data['provide_extended'] = provide_extended

        # Get License text if possible
        # NOTE: this is sucky, because Portage XPAK metadata doesn't contain
        # license text, and we need to rely on PORTDIR, which is very bad
        data['licensedata'] = self._extract_pkg_metadata_license_data(
            data['spm_repository'], data['license'])

        data['desktop_mime'], data['provided_mime'] = \
            self._extract_pkg_metadata_desktop_mime(
                pkg_dir, data['content'])

        data['mirrorlinks'] = self._extract_pkg_metadata_mirror_links(
            data['sources'])

        # write only if it's a systempackage
        data['systempackage'] = False
        system_packages = [entropy.dep.dep_getkey(x) for x in \
            self.get_system_packages()]
        if data['category'] + "/" + data['name'] in system_packages:
            data['systempackage'] = True

        # write only if it's a systempackage
        data['config_protect'] = ' '.join(self.get_merge_protected_paths())
        data['config_protect_mask'] = ' '.join(
            self.get_merge_protected_paths_mask())

        # kept for backward compatibility, remove in late 2011
        data['messages'] = []
        data['eclasses'] = []

        # etpapi must be int, as returned by entropy.db.getPackageData
        data['etpapi'] = int(etpConst['etpapi'])

        # prepare download URL string, check licenses
        nonfree = False
        restricted = False
        if license_callback is not None:
            nonfree = not license_callback(data)
        if restricted_callback is not None:
            restricted = restricted_callback(data)
        data['download'] = entropy.tools.create_package_dirpath(data['branch'],
            nonfree = nonfree, restricted = restricted)
        data['download'] = os.path.join(data['download'],
            entropy.dep.create_package_filename(
                data['category'], data['name'], data['version'],
                    data['versiontag']))

        # removing temporary directory
        shutil.rmtree(tmp_dir, True)

        # clear unused metadata
        del data['use'], data['iuse'], data['depend'], data['pdepend'], \
            data['rdepend'], data['eapi']

        return data

    def enable_package_compile_options(self, package, options):
        """
        Reimplemented from SpmPlugin class.
        """
        result = self._unset_package_useflags(package, options)
        if not result:
            return False
        return self._handle_new_useflags(package, options, "")

    def disable_package_compile_options(self, package, options):
        """
        Reimplemented from SpmPlugin class.
        """
        result = self._unset_package_useflags(package, options)
        if not result:
            return False
        return self._handle_new_useflags(package, options, "-")

    def get_package_compile_options(self, package):
        """
        Reimplemented from SpmPlugin class.
        """
        matched_atom = self.match_package(package)
        if not matched_atom:
            return {}
        global_useflags = self._get_useflags()
        use_force = self._get_useflags_force()
        use_mask = self._get_useflags_mask()
        package_use_useflags = self._get_package_use_useflags(package)

        data = {}
        data['use_force'] = use_force.copy()
        data['use_mask'] = use_mask.copy()
        data['global_use'] = global_useflags.split()

        iuse = self.get_package_metadata(package, "IUSE")
        if not isinstance(iuse, const_get_stringtype()):
            iuse = ''
        data['iuse'] = iuse.split()[:]
        iuse = set()
        for myiuse in data['iuse']:
            if myiuse.startswith("+"):
                myiuse = myiuse[1:]
            iuse.add(myiuse)

        use = [f for f in data['global_use'] + \
            list(package_use_useflags['enabled']) if (f in iuse) \
                and (f not in use_mask) and \
                    (f not in package_use_useflags['disabled'])]

        use_disabled = [f for f in iuse if (f not in data['global_use']) \
            and (f not in use_mask) and \
                (f not in package_use_useflags['enabled'])]

        data['use'] = use[:]
        data['use_disabled'] = use_disabled[:]

        matched_slot = self.get_package_metadata(matched_atom, "SLOT")
        try:
            inst_key = "%s%s%s" % (
                entropy.dep.dep_getkey(package),
                etpConst['entropyslotprefix'],
                matched_slot,
            )
            installed_atom = self.match_installed_package(inst_key)
        except self._portage.exception.PortageException:
            installed_atom = ''

        if installed_atom:

            # get its useflags
            previous_iuse = self.get_installed_package_metadata(installed_atom,
                "IUSE").split()
            previous_use = self.get_installed_package_metadata(installed_atom,
                "USE").split()

            new_previous_iuse = set()
            for myuse in previous_iuse:
                if myuse.startswith("+"):
                    myuse = myuse[1:]
                new_previous_iuse.add(myuse)
            previous_iuse = list(new_previous_iuse)

            inst_use = [f for f in previous_iuse if (f in previous_use) and \
                (f not in use_mask)]
            #inst_use_disabled = [f for f in previous_use if \
            #    (f not in previous_iuse) and (f not in use_mask)]

            # check removed use
            use_removed = []
            for myuse in inst_use:
                if myuse not in use:
                    use_removed.append(myuse)

            # use not available
            use_not_avail = []
            for myuse in previous_iuse:
                if (myuse not in iuse) and (myuse not in use_removed):
                    use_not_avail.append(myuse)

            # check new use
            t_use = []
            for myuse in use:
                if myuse not in inst_use:
                    myuse = "+%s*" % (myuse,)
                t_use.append(myuse)
            use = t_use

            # check disabled use
            t_use_disabled = []
            for myuse in use_disabled:
                if myuse in inst_use:
                    if myuse in use_removed+use_not_avail:
                        continue
                    myuse = "-%s*" % (myuse,)
                else:
                    myuse = "-%s" % (myuse,)
                t_use_disabled.append(myuse)
            use_disabled = t_use_disabled

            for myuse in use_removed:
                use_disabled.append("(-%s*)" % (myuse,))
            for myuse in use_not_avail:
                use_disabled.append("(-%s)" % (myuse,))
        else:
            use_disabled = ["-"+x for x in use_disabled]

        data['use_string'] = ' '.join(sorted(use)+sorted([x for x in \
            use_disabled]))
        data['use_string_colored'] = ' '.join(
                sorted([darkred(x) for x in use if not x.startswith("+")] + \
                        [darkgreen(x) for x in use if x.startswith("+")]) + \
                sorted([darkblue(x) for x in use_disabled if x.startswith("-")] + \
                    [brown(x) for x in use_disabled if x.startswith("(") and \
                        (x.find("*") == -1)] + \
                    [purple(x) for x in use_disabled if x.startswith("(") and \
                        (x.find("*") != -1)]
                )
        )

        return data

    def get_installed_package_compile_options(self, package, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        matched_atom = self.match_installed_package(package, root = root)
        if not matched_atom:
            return {}

        global_use = self.get_installed_package_metadata(matched_atom, "USE",
            root = root)
        use_mask = self._get_useflags_mask()

        data = {}
        data['use_mask'] = use_mask.copy()
        data['global_use'] = global_use.split()

        iuse = self.get_installed_package_metadata(matched_atom, "IUSE",
            root = root)
        if not isinstance(iuse, const_get_stringtype()):
            iuse = ''
        data['iuse'] = iuse.split()[:]
        iuse = set()
        for myiuse in data['iuse']:
            if myiuse.startswith("+"):
                myiuse = myiuse[1:]
            iuse.add(myiuse)

        use = [f for f in data['global_use'] if (f in iuse) and \
            (f not in use_mask)]
        use_disabled = [f for f in iuse if (f not in data['global_use']) and \
            (f not in use_mask)]
        data['use'] = use[:]
        data['use_disabled'] = use_disabled[:]

        data['use_string'] = ' '.join(sorted(use)+sorted([x for x in \
            use_disabled]))
        data['use_string_colored'] = ' '.join(
                sorted([darkred(x) for x in use if not x.startswith("+")] + \
                        [darkgreen(x) for x in use if x.startswith("+")]) + \
                sorted([darkblue(x) for x in use_disabled if x.startswith("-")] + \
                    [brown(x) for x in use_disabled if x.startswith("(") and \
                        (x.find("*") == -1)] + \
                    [purple(x) for x in use_disabled if x.startswith("(") and \
                        (x.find("*") != -1)]
                )
        )
        return data

    def get_installed_package_content(self, package, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        if root is None:
            root = etpConst['systemroot'] + os.path.sep

        cat, pkgv = package.split("/")
        return sorted(self._portage.dblink(cat, pkgv, root,
            self._portage.settings).getcontents())

    def get_packages(self, categories = None, filter_reinstalls = True):
        """
        Reimplemented from SpmPlugin class.
        """
        if categories is None:
            categories = []

        root = etpConst['systemroot'] + os.path.sep
        mysettings = self._get_portage_config(os.path.sep, root)
        portdb = self._get_portage_portagetree(root).dbapi

        cps = portdb.cp_all()
        visibles = set()
        for cp in cps:
            if categories:
                if cp.split("/")[0] not in categories:
                    continue

            # get slots
            slots = set()
            atoms = self.match_package(cp, match_type = "match-visible")
            if atoms:
                for atom in atoms:
                    slots.add(portdb.aux_get(atom, ["SLOT"])[0])
                for slot in slots:
                    visibles.add(cp+":"+slot)

        # now match visibles
        available = set()
        for visible in visibles:

            match = self.match_package(visible)
            if not match:
                continue

            if filter_reinstalls:
                installed = self.match_installed_package(visible)
                if installed != match:
                    available.add(match)
            else:
                available.add(match)

        return available

    def compile_packages(self, packages, stdin = None, stdout = None,
        stderr = None, environ = None, pid_write_func = None,
        pretend = False, verbose = False, fetch_only = False,
        build_only = False, no_dependencies = False,
        ask = False, coloured_output = False, oneshot = False):

        cmd = [PortagePlugin._cmd_map['exec_cmd']]
        if pretend:
            cmd.append(PortagePlugin._cmd_map['pretend_cmd'])
        if verbose:
            cmd.append(PortagePlugin._cmd_map['verbose_cmd'])
        if ask:
            cmd.append(PortagePlugin._cmd_map['ask_cmd'])
        if oneshot:
            cmd.append(PortagePlugin._cmd_map['oneshot_cmd'])
        if not coloured_output:
            cmd.append(PortagePlugin._cmd_map['nocolor_cmd'])
        if fetch_only:
            cmd.append(PortagePlugin._cmd_map['fetchonly_cmd'])
        if build_only:
            cmd.append(PortagePlugin._cmd_map['buildonly_cmd'])
        if no_dependencies:
            cmd.append(PortagePlugin._cmd_map['nodeps_cmd'])

        cmd.extend(packages)
        cmd_string = """\
        %s && %s && %s
        """ % (PortagePlugin._cmd_map['env_update_cmd'],
            PortagePlugin._cmd_map['source_profile_cmd'],
            ' '.join(cmd)
        )

        env = os.environ.copy()
        if environ is not None:
            env.update(environ)

        proc = subprocess.Popen(cmd_string, stdout = stdout, stderr = stderr,
            stdin = stdin, env = env, shell = True)
        if pid_write_func is not None:
            pid_write_func(proc.pid)
        return proc.wait()

    def remove_packages(self, packages, stdin = None, stdout = None,
        stderr = None, environ = None, pid_write_func = None,
        pretend = False, verbose = False, no_dependencies = False, ask = False,
        coloured_output = False):

        cmd = [PortagePlugin._cmd_map['exec_cmd'],
            PortagePlugin._cmd_map['remove_cmd']]
        if pretend:
            cmd.append(PortagePlugin._cmd_map['pretend_cmd'])
        if verbose:
            cmd.append(PortagePlugin._cmd_map['verbose_cmd'])
        if ask:
            cmd.append(PortagePlugin._cmd_map['ask_cmd'])
        if not coloured_output:
            cmd.append(PortagePlugin._cmd_map['nocolor_cmd'])
        if no_dependencies:
            cmd.append(PortagePlugin._cmd_map['nodeps_cmd'])

        cmd.extend(packages)
        cmd_string = """\
        %s && %s && %s
        """ % (PortagePlugin._cmd_map['env_update_cmd'],
            PortagePlugin._cmd_map['source_profile_cmd'],
            ' '.join(cmd)
        )

        env = os.environ.copy()
        if environ is not None:
            env.update(environ)

        proc = subprocess.Popen(cmd_string, stdout = stdout, stderr = stderr,
            stdin = stdin, env = env, shell = True)
        if pid_write_func is not None:
            pid_write_func(proc.pid)
        return proc.wait()

    def environment_update(self):
        args = (PortagePlugin._cmd_map['env_update_cmd'],)
        try:
            # inherit stdin, stderr, stdout from parent
            proc = subprocess.Popen(args, stdout = sys.stdout,
                stderr = sys.stderr, stdin = sys.stdin)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
            return
        proc.wait()

    def print_build_environment_info(self, stdin = None, stdout = None,
        stderr = None, environ = None, pid_write_func = None,
        coloured_output = False):

        cmd = [PortagePlugin._cmd_map['exec_cmd'],
            PortagePlugin._cmd_map['info_cmd']]
        if not coloured_output:
            cmd.append(PortagePlugin._cmd_map['nocolor_cmd'])

        cmd_string = """\
        %s && %s && %s
        """ % (PortagePlugin._cmd_map['env_update_cmd'],
            PortagePlugin._cmd_map['source_profile_cmd'],
            ' '.join(cmd)
        )

        env = os.environ.copy()
        if environ is not None:
            env.update(environ)

        proc = subprocess.Popen(cmd_string, stdout = stdout, stderr = stderr,
            stdin = stdin, env = env, shell = True)
        if pid_write_func is not None:
            pid_write_func(proc.pid)
        return proc.wait()

    def get_installed_packages(self, categories = None, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        vartree = self._get_portage_vartree(root = root)
        packages = vartree.dbapi.cpv_all()
        if not categories:
            return packages

        def catfilter(pkg):
            if pkg.split("/", 1)[0] in categories:
                return True
            return False

        return list(filter(catfilter, packages))

    def get_package_sets(self, builtin_sets):
        """
        Reimplemented from SpmPlugin class.
        """
        config = self._get_set_config()
        if config == None:
            return {}

        mysets = config.getSets()
        if not builtin_sets:
            sets_obj = self._get_portage_sets_object()
            # attention, this is sensible to Portage API changes
            static_file_class = sets_obj.files.StaticFileSet
            # filter out Portage-generated sets object, those not being
            # an instance of portage._sets.files.StaticFileSet
            for key, obj in tuple(mysets.items()):
                if not isinstance(obj, static_file_class):
                    mysets.pop(key)

        set_data = {}
        for k, obj in mysets.items():
            pset = obj.getAtoms()
            pset |= obj.getNonAtoms()
            set_data[k] = pset
        return set_data

    def convert_from_entropy_package_name(self, entropy_package_name):
        """
        Reimplemented from SpmPlugin class.
        """
        spm_name = entropy.dep.remove_tag(entropy_package_name)
        spm_name = entropy.dep.remove_entropy_revision(spm_name)
        return spm_name

    def assign_uid_to_installed_package(self, package, root = None):
        """
        Reimplemented from SpmPlugin class.
        """
        if root is None:
            root = etpConst['systemroot'] + os.path.sep

        vartree = self._get_portage_vartree(root)
        dbbuild = self.get_installed_package_build_script_path(package,
            root = root)

        counter_dir = os.path.dirname(dbbuild)
        counter_name = PortagePlugin.xpak_entries['counter']
        counter_path = os.path.join(counter_dir, counter_name)

        if not os.access(counter_dir, os.W_OK):
            raise SPMError("SPM package directory not found")

        with open(counter_path, "wb") as count_f:
            new_counter = vartree.dbapi.counter_tick(root, mycpv = package)
            count_f.write(const_convert_to_rawstring(new_counter))
            count_f.flush()

        return new_counter

    def resolve_package_uid(self, entropy_repository,
        entropy_repository_package_id):
        """
        Reimplemented from SpmPlugin class.
        """
        counter_path = PortagePlugin.xpak_entries['counter']
        entropy_atom = entropy_repository.retrieveAtom(
            entropy_repository_package_id)

        spm_name = self.convert_from_entropy_package_name(entropy_atom)
        build_path = self.get_installed_package_build_script_path(spm_name)
        atom_counter_path = os.path.join(os.path.dirname(build_path),
            counter_path)

        if not (os.access(atom_counter_path, os.R_OK) and \
            os.path.isfile(atom_counter_path)):
            return None # not found

        try:
            with open(atom_counter_path, "r") as f:
                counter = int(f.readline().strip())
        except ValueError:
            raise SPMError("invalid Unique Identifier found")
        except Exception as e:
            raise SPMError("General SPM Error: %s" % (e,))

        return counter

    def search_paths_owners(self, paths, exact_match = True):
        """
        Reimplemented from SpmPlugin class.
        """
        if not isinstance(paths, (list, set, frozenset, dict, tuple)):
            raise AttributeError("iterable needed")

        matches = {}
        root = etpConst['systemroot'] + os.path.sep

        # if qfile is avail, it's much faster than using Portage API
        qfile_exec = "/usr/bin/qfile"
        if os.access(qfile_exec, os.X_OK):

            qfile_args = (qfile_exec, "-q", "-C", "-R", root,)
            if exact_match:
                qfile_args += ("-e",)

            rc = 0
            for filename in paths:

                proc = subprocess.Popen(qfile_args + (filename,),
                    stdout = subprocess.PIPE)
                rc = proc.wait()
                if rc != 0:
                    # wtf?, fallback to old way
                    proc.stdout.close()
                    matches.clear()
                    break

                pkgs = set([x.strip() for x in proc.stdout.readlines()])
                for pkg in pkgs:
                    slot = self.get_installed_package_metadata(pkg, "SLOT")
                    obj = matches.setdefault((pkg, slot,), set())
                    obj.add(filename)

                proc.stdout.close()

            if rc == 0:
                return matches

        mytree = self._get_portage_vartree(root)
        packages = mytree.dbapi.cpv_all()

        for package in packages:
            cat, pkgv = package.split("/")
            content = self._portage.dblink(cat, pkgv, root,
                self._portage.settings).getcontents()

            if exact_match:
                for filename in paths:
                    if filename in content:
                        myslot = self.get_installed_package_metadata(package,
                            "SLOT")
                        obj = matches.setdefault((package, myslot,), set())
                        obj.add(filename)
            else:
                for filename in paths:
                    for myfile in content:
                        if myfile.find(filename) == -1:
                            continue
                        myslot = self.get_installed_package_metadata(package,
                            "SLOT")
                        obj = matches.setdefault((package, myslot,), set())
                        obj.add(filename)

        return matches

    def _reload_portage_if_required(self, phase, package_metadata):
        # filter out unwanted phases
        if phase not in ("postrm", "postinst"):
            return
        category, name = package_metadata['category'], package_metadata['name']
        key = category + "/" + name
        # reload portage modules only if we're dealing with sys-apps/portage
        if key == PortagePlugin._PORTAGE_ENTROPY_PACKAGE_NAME:
            self._reload_modules()

    class StdoutSplitter(object):

        def __init__(self, phase, logger, std):
            self._phase = phase
            self._logger = logger
            self._std = std

            if sys.hexversion >= 0x3000000:

                class Writer(object):

                    def __init__(self, parent, buf):
                        self._buf = buf
                        self._parent = parent

                    def write(self, b):
                        self._buf.write(b)
                        self._parent.write(const_convert_to_unicode(b))

                    def flush(self):
                        self._buf.flush()
                        self._parent.flush()

                self.buffer = Writer(self, self._std.buffer)

        def __iter__(self):
            return self._std

        def __hash__(self):
            return hash(self._std)

        @property
        def softspace(self):
            return self._std.softspace

        @property
        def name(self):
            return self._std.name

        @property
        def newlines(self):
            return self._std.newlines

        @property
        def mode(self):
            return self._std.mode

        @property
        def errors(self):
            return self._std.errors

        @property
        def encoding(self):
            return self._std.encoding

        @property
        def closed(self):
            return self._std.closed

        def fileno(self):
            return self._std.fileno()

        def flush(self):
            self._logger.flush()
            return self._std.flush()

        def close(self):
            self._logger.close()
            return self._std.close()

        def isatty(self):
            return self._std.isatty()

        if sys.hexversion < 0x3000000:
            def next(self):
                return self._std.next()
        else:
            def __next__(self):
                return next(self._std)

        def read(self, *args, **kwargs):
            return self._std.read(*args, **kwargs)

        def readline(self, *args, **kwargs):
            return self._std.readline(*args, **kwargs)

        def readlines(self, *args, **kwargs):
            return self._std.readlines(*args, **kwargs)

        def seek(self, *args, **kwargs):
            return self._std.seek(*args, **kwargs)

        def tell(self):
            return self._std.tell()

        def truncate(self, *args, **kwargs):
            return self._std.truncate(*args, **kwargs)

        def write(self, mystr):
            self._logger.log(
                "[Portage %s]" % (self._phase,),
                etpConst['logging']['normal_loglevel_id'], "\n" + \
                    decolorize(mystr))
            return self._std.write(mystr)

        def writelines(self, lst):
            self._logger.log(
                "[Portage %s]" % (self._phase,),
                etpConst['logging']['normal_loglevel_id'], "")
            self._logger.writelines([decolorize(x) for x in lst])
            return self._std.writelines(lst)

        if sys.hexversion >= 0x3000000:

            # line_buffering readable seekable writable
            def readable(self):
                return self._std.readable()

            def seekable(self):
                return self._std.seekable()

            def writable(self):
                return self._std.writable()

            @property
            def line_buffering(self):
                return self._std.line_buffering

        else:

            def xreadlines(self):
                return self._std.xreadlines()

    def _portage_doebuild(self, myebuild, mydo, tree, cpv,
        portage_tmpdir = None, licenses = None):

        # myebuild = path/to/ebuild.ebuild with a valid unpacked xpak metadata
        # tree = "bintree"
        # cpv = atom
        # mydbapi = portage.fakedbapi(settings=portage.settings)
        # vartree = portage.vartree(root=myroot)

        if licenses is None:
            licenses = []

        root = etpConst['systemroot'] + os.path.sep

        # old way to avoid loop of deaths for entropy portage hooks
        os.environ["SKIP_EQUO_SYNC"] = "1"

        # load metadata
        myebuilddir = os.path.dirname(myebuild)
        keys = sorted(self._portage.auxdbkeys) + ["repository"]
        metadata = {}

        for key in keys:
            mykeypath = os.path.join(myebuilddir, key)
            if os.path.isfile(mykeypath) and os.access(mykeypath, os.R_OK):
                if sys.hexversion >= 0x3000000:
                    f = open(mykeypath, "r", encoding = "raw_unicode_escape")
                else:
                    f = open(mykeypath, "rb")
                metadata[key] = f.readline().strip()
                f.close()

        ### END SETUP ENVIRONMENT

        # find config
        mysettings = self._get_portage_config(os.path.sep, root)
        mysettings['EBUILD_PHASE'] = mydo
        mysettings['EMERGE_FROM'] = "binary"

        # we already do this early
        mysettings["ACCEPT_LICENSE"] = str(' '.join(licenses))
        mysettings.backup_changes("ACCEPT_LICENSE")
        mysettings.regenerate()

        mysettings['EAPI'] = "0"
        if 'EAPI' in metadata:
            mysettings['EAPI'] = metadata['EAPI']

        # workaround for scripts asking for user intervention
        mysettings['ROOT'] = root
        mysettings['CD_ROOT'] = "/tmp"

        mysettings.backup_changes("EAPI")
        mysettings.backup_changes("EBUILD_PHASE")
        mysettings.backup_changes("EMERGE_FROM")
        mysettings.backup_changes("ROOT")
        mysettings.backup_changes("CD_ROOT")

        try: # this is a >portage-2.1.4_rc11 feature
            env_wl = set(mysettings._environ_whitelist)
            # put our vars into whitelist
            env_wl.add("SKIP_EQUO_SYNC")
            env_wl.add("ACCEPT_LICENSE")
            env_wl.add("CD_ROOT")
            env_wl.add("ROOT")
            mysettings._environ_whitelist = frozenset(env_wl)
        except (AttributeError,):
            self.log_message(entropy.tools.get_traceback())

        portage_tmpdir_created = False # for pkg_postrm, pkg_prerm

        if portage_tmpdir is None:
            portage_tmpdir = tempfile.mkdtemp()
            portage_tmpdir_created = True
        elif not os.path.isdir(portage_tmpdir):
            os.makedirs(portage_tmpdir, 0o744)
            const_setup_perms(portage_tmpdir, etpConst['entropygid'],
                recursion = False)

        if portage_tmpdir:
            mysettings['PORTAGE_TMPDIR'] = str(portage_tmpdir)
            mysettings.backup_changes("PORTAGE_TMPDIR")

        # create FAKE ${PORTDIR} directory and licenses subdir
        portdir = os.path.join(portage_tmpdir, "portdir")
        portdir_lic = os.path.join(portdir, "licenses")
        if not os.path.isdir(portdir):
            os.mkdir(portdir, 0o744)
            const_setup_perms(portdir, etpConst['entropygid'],
                recursion = False)
        # create licenses subdir
        if not os.path.isdir(portdir_lic):
            os.mkdir(portdir_lic)

        # set fake PORTDIR
        old_portdir = mysettings["PORTDIR"][:]
        mysettings["PORTDIR"] = portdir
        mysettings.backup_changes("PORTDIR")

        ### WORKAROUND for buggy check_license() in eutils.eclass
        ### that looks for file availability before considering
        ### ACCEPT_LICENSE
        for lic in licenses:
            lic_path = os.path.join(portdir_lic, lic)
            if os.access(portdir_lic, os.W_OK | os.R_OK) and \
                os.path.isdir(portdir_lic):
                lic_f = open(lic_path, "wb")
                lic_f.close()

        cpv = str(cpv)
        mydbapi = self._portage.fakedbapi(settings=mysettings)
        # XXX: temporary workaround for broken Portage API
        if not hasattr(mydbapi, "getFetchMap"):
            def _get_fetch_map(*b_args, **b_kwargs):
                return {}
            mydbapi.getFetchMap = _get_fetch_map

        mydbapi.cpv_inject(cpv, metadata = metadata)
        mysettings.setcpv(cpv, mydb = mydbapi)

        # cached vartree class
        vartree = self._get_portage_vartree(root = root)

        if etpUi['debug']:
            self.__output.output(
                "PortagePlugin<_portage_doebuild>, env: %s" % (
                    locals(),),
                importance = 0,
                header = ""
            )

        with LogFile(level = SystemSettings()['system']['log_level'],
            filename = etpConst['entropylogfile'], header = "[spm]") as logger:

            oldsysstdout = sys.stdout
            oldsysstderr = sys.stderr
            if etpUi['mute']:
                tmp_fd, tmp_file = tempfile.mkstemp()
                tmp_fw = os.fdopen(tmp_fd, "w")
                sys.stdout = tmp_fw
                sys.stderr = tmp_fw
            else:
                splitter_out = self.StdoutSplitter(mydo, logger, sys.stdout)
                splitter_err = self.StdoutSplitter(mydo, logger, sys.stderr)
                sys.stdout = splitter_out
                sys.stderr = splitter_err

            try:
                rc = self._portage.doebuild(
                    myebuild = str(myebuild),
                    mydo = str(mydo),
                    myroot = root,
                    tree = tree,
                    mysettings = mysettings,
                    mydbapi = mydbapi,
                    vartree = vartree,
                    use_cache = 0,
                    debug = etpUi['debug']
                )
            except:
                logger.write(entropy.tools.get_traceback())
                raise
            finally:
                sys.stdout = oldsysstdout
                sys.stderr = oldsysstderr
                if etpUi['mute']:
                    tmp_fw.flush()
                    tmp_fw.close()
                    try:
                        os.remove(tmp_file)
                    except OSError:
                        pass

                # remove self-created portdir directory in any case
                shutil.rmtree(portdir, True)
                if portage_tmpdir_created:
                    shutil.rmtree(portage_tmpdir, True)

                # reset PORTDIR back to its old path
                # for security !
                mysettings["PORTDIR"] = old_portdir
                mysettings.backup_changes("PORTDIR")

                del mydbapi
                del metadata
                del keys

        return rc

    @staticmethod
    def _pkg_compose_atom(package_metadata):
        return package_metadata['category'] + "/" + \
                package_metadata['name'] + "-" + package_metadata['version']

    @staticmethod
    def _pkg_compose_xpak_ebuild(package_metadata):
        package = PortagePlugin._pkg_compose_atom(package_metadata)
        return os.path.join(package_metadata['xpakdir'],
            os.path.basename(package) + PortagePlugin.EBUILD_EXT)

    def _pkg_remove_overlayed_ebuild(self, moved_ebuild):

        mydir = os.path.dirname(moved_ebuild)
        shutil.rmtree(mydir, True)
        mydir = os.path.dirname(mydir)
        content = os.listdir(mydir)
        while not content:
            try:
                os.rmdir(mydir)
            except OSError:
                # cannot remove further
                break
            mydir = os.path.dirname(mydir)
            content = os.listdir(mydir)

    def _pkg_remove_ebuild_env_setup_hook(self, ebuild):

        ebuild_path = os.path.dirname(ebuild)

        myroot = os.path.sep
        if etpConst['systemroot']:
            myroot = etpConst['systemroot'] + os.path.sep

        # we need to fix ROOT= if it's set inside environment
        bz2envfile = os.path.join(ebuild_path, PortagePlugin.ENV_FILE_COMP)
        if os.path.isfile(bz2envfile) and os.path.isdir(myroot):
            envfile = entropy.tools.unpack_bzip2(bz2envfile)
            bzf = bz2.BZ2File(bz2envfile, "w")
            f = open(envfile, "rb")
            line = f.readline()
            root_tag = const_convert_to_rawstring("ROOT=")
            while line:
                if line.startswith(root_tag):
                    line = const_convert_to_rawstring("ROOT=%s\n" % (myroot,))
                bzf.write(line)
                line = f.readline()

            f.close()
            bzf.close()
            os.remove(envfile)

    def _pkg_remove_setup_ebuild_env(self, myebuild, portage_atom):

        ebuild_dir = os.path.dirname(myebuild)
        ebuild_file = os.path.basename(myebuild)
        moved_ebuild = None

        # copy the whole directory in a safe place
        dest_dir = os.path.join(etpConst['entropyunpackdir'],
            "vardb/" + portage_atom)
        if os.path.exists(dest_dir):
            if os.path.isdir(dest_dir):
                shutil.rmtree(dest_dir, True)
            elif os.path.isfile(dest_dir) or os.path.islink(dest_dir):
                os.remove(dest_dir)

        os.makedirs(dest_dir)
        items = os.listdir(ebuild_dir)
        for item in items:
            myfrom = os.path.join(ebuild_dir, item)
            myto = os.path.join(dest_dir, item)
            if os.path.isfile(myfrom) and os.access(myfrom, os.R_OK):
                # make sure it is readable before copying
                shutil.copy2(myfrom, myto)

        newmyebuild = os.path.join(dest_dir, ebuild_file)
        if os.path.isfile(newmyebuild):
            myebuild = newmyebuild
            moved_ebuild = myebuild
            self._pkg_remove_ebuild_env_setup_hook(myebuild)

        return myebuild, moved_ebuild

    def _pkg_setup(self, package_metadata, skip_if_found = False):

        package = PortagePlugin._pkg_compose_atom(package_metadata)
        env_file = os.path.join(package_metadata['unpackdir'], "portage",
            package, "temp/environment")

        if os.path.isfile(env_file) and skip_if_found:
            return 0

        ebuild = PortagePlugin._pkg_compose_xpak_ebuild(package_metadata)
        rc = self._portage_doebuild(ebuild, "setup",
            "bintree", package, portage_tmpdir = package_metadata['unpackdir'],
            licenses = package_metadata.get('accept_license'))

        if rc != 0:
            self.log_message(
                "[POST] ATTENTION Cannot properly run Source Package Manager"
                " setup phase for %s Something bad happened." % (package,)
            )

        return rc

    def _pkg_fooinst(self, package_metadata, phase):

        package = PortagePlugin._pkg_compose_atom(package_metadata)
        ebuild = PortagePlugin._pkg_compose_xpak_ebuild(package_metadata)
        rc = 0

        # is ebuild available
        if not (os.path.isfile(ebuild) and os.access(ebuild, os.R_OK)):
            return rc

        try:

            self._pkg_setup(package_metadata, skip_if_found = True)

            rc = self._portage_doebuild(ebuild, phase, "bintree",
                package, portage_tmpdir = package_metadata['unpackdir'],
                licenses = package_metadata.get('accept_license'))

            if rc != 0:
                self.log_message(
                    "[PRE] ATTENTION Cannot properly run SPM %s"
                    " phase for %s. Something bad happened." % (
                        phase, package,)
                )
            self._reload_portage_if_required(phase, package_metadata)

        except Exception as e:

            entropy.tools.print_traceback()

            self.log_message(
                "[PRE] ATTENTION Cannot properly run SPM %s"
                " phase for %s. Something bad happened."
                " Exception %s" % (phase, package, repr(e),))

            mytxt = "%s: %s %s." % (
                bold(_("QA")),
                brown(_("Cannot run Source Package Manager trigger for")),
                bold(str(package)),
            )
            self.__output.output(
                mytxt,
                importance = 0,
                header = red("   ## ")
            )
            mytxt = "%s. %s: %s [%s]" % (
                brown(_("Please report it")),
                bold(_("Attach this")),
                darkred(etpConst['entropylogfile']),
                brown(phase),
            )
            self.__output.output(
                mytxt,
                importance = 0,
                header = red("   ## ")
            )

        return rc

    def _pkg_foorm(self, package_metadata, phase):

        rc = 0
        moved_ebuild = None
        package = PortagePlugin._pkg_compose_atom(package_metadata)
        ebuild = self.get_installed_package_build_script_path(package)

        if not os.path.isfile(ebuild):
            return 0

        try:
            ebuild, moved_ebuild = self._pkg_remove_setup_ebuild_env(
                ebuild, package)

        except EOFError as e:
            # stuff on system is broken, ignore it
            self.__output.output(
                darkred("!!! Ebuild: pkg_" + phase + "() failed, EOFError: ") + \
                    str(e) + darkred(" - ignoring"),
                importance = 1,
                level = "warning",
                header = red("   ## ")
            )
            return 0

        except ImportError as e:
            # stuff on system is broken, ignore it
            self.__output.output(
                darkred("!!! Ebuild: pkg_" + phase + "() failed, ImportError: ") + \
                    str(e) + darkred(" - ignoring"),
                importance = 1,
                level = "warning",
                header = red("   ## ")
            )
            return 0

        work_dir = os.path.join(etpConst['entropyunpackdir'],
            package.replace("/", "_"))

        try:
            self._reload_portage_if_required(phase, package_metadata)
            rc = self._portage_doebuild(ebuild, phase, "bintree",
                package, portage_tmpdir = work_dir,
                licenses = package_metadata.get('accept_license'))
        except Exception as e:

            entropy.tools.print_traceback()

            self.log_message(
                "[PRE] ATTENTION Cannot properly run SPM %s"
                " phase for %s. Something bad happened."
                " Exception %s" % (phase, package, repr(e),)
            )

            mytxt = "%s: %s %s." % (
                bold(_("QA")),
                brown(_("Cannot run Source Package Manager trigger for")),
                bold(str(package)),
            )
            self.__output.output(
                mytxt,
                importance = 0,
                header = red("   ## ")
            )
            mytxt = "%s. %s: %s [%s]" % (
                brown(_("Please report it")),
                bold(_("Attach this")),
                darkred(etpConst['entropylogfile']),
                brown(phase),
            )
            self.__output.output(
                mytxt,
                importance = 0,
                header = red("   ## ")
            )
        finally:
            if os.path.isdir(work_dir):
                shutil.rmtree(work_dir, True)

        if rc != 0:
            self.log_message(
                "[PRE] ATTENTION Cannot properly run SPM %s trigger "
                "for %s. Something bad happened." % (phase, package,)
            )

        if moved_ebuild is not None:
            if os.path.isfile(moved_ebuild):
                self._pkg_remove_overlayed_ebuild(moved_ebuild)

        return rc

    def _pkg_preinst(self, package_metadata):
        return self._pkg_fooinst(package_metadata, "preinst")

    def _pkg_postinst(self, package_metadata):
        return self._pkg_fooinst(package_metadata, "postinst")

    def _pkg_prerm(self, package_metadata):
        return self._pkg_foorm(package_metadata, "prerm")

    def _pkg_postrm(self, package_metadata):
        return self._pkg_foorm(package_metadata, "postrm")

    def _pkg_config(self, package_metadata):

        package = PortagePlugin._pkg_compose_atom(package_metadata)
        ebuild = self.get_installed_package_build_script_path(package)
        if not os.path.isfile(ebuild):
            return 2

        try:

            rc = self._portage_doebuild(ebuild, "config", "bintree",
                package, licenses = package_metadata.get('accept_license'))

            if rc != 0:
                return 3

        except Exception as err:

            entropy.tools.print_traceback()
            mytxt = "%s: %s %s." % (
                bold(_("QA")),
                brown(_("Cannot run SPM configure phase for")),
                bold(str(package)),
            )
            mytxt2 = "%s: %s, %s" % (
                bold(_("Error")),
                type(Exception),
                err,
            )
            for txt in (mytxt, mytxt2,):
                self.__output.output(
                    txt,
                    importance = 0,
                    header = red("   ## ")
                )
            return 1

        return 0

    def append_metadata_to_package(self, entropy_package_name, package_path):
        """
        Reimplemented from SpmPlugin class.
        """
        spm_name = self.convert_from_entropy_package_name(entropy_package_name)
        dbbuild = self.get_installed_package_build_script_path(spm_name)
        dbdir = os.path.dirname(dbbuild)

        if os.path.isdir(dbdir):
            tbz2 = xpak.tbz2(package_path)
            tbz2.recompose(dbdir)
            return True
        return False

    def __run_pkg_sync_quickpkg(self, entropy_server, atoms, repo_db, repo):
        """
        Executes packages regeneration for given atoms.
        """
        package_paths = set()
        runatoms = set()
        for myatom in atoms:
            mymatch = repo_db.atomMatch(myatom)
            if mymatch[0] == -1:
                continue
            myatom = repo_db.retrieveAtom(mymatch[0])
            myatom = entropy.dep.remove_tag(myatom)
            runatoms.add(myatom)

        for myatom in runatoms:

            # check if atom is available
            if not self.match_installed_package(myatom):
                self.__output.output(
                    red("%s: " % (_("package not available on system"),) ) + \
                        blue(myatom),
                    importance = 1,
                    level = "warning",
                    header = purple("  # ")
                )
                continue
            else:
                self.__output.output(
                    red("%s: " % (_("repackaging"),) )+blue(myatom),
                    importance = 1,
                    level = "warning",
                    header = blue("  # ")
                )

            mydest = entropy_server._get_local_store_directory(repo)
            try:
                mypath = self.generate_package(myatom, mydest)
            except Exception:
                entropy.tools.print_traceback()
                # remove broken bin before raising
                mypath = os.path.join(mydest,
                    os.path.basename(myatom) + etpConst['packagesext'])
                if os.path.isfile(mypath):
                    os.remove(mypath)
                mytxt = "%s: %s: %s, %s." % (
                    bold(_("WARNING")),
                    red(_("Cannot complete quickpkg for atom")),
                    blue(myatom),
                    _("do it manually"),
                )
                self.__output.output(
                    mytxt,
                    importance = 1,
                    level = "warning",
                    header = darkred(" * ")
                )
                continue
            package_paths.add(mypath)
        packages_data = [(x, False,) for x in package_paths]
        idpackages = entropy_server.add_packages_to_repository(repo,
            packages_data)

        if not idpackages:

            mytxt = "%s: %s. %s." % (
                bold(_("ATTENTION")),
                red(_("package files rebuild did not run properly")),
                red(_("Please update packages manually")),
            )
            self.__output.output(
                mytxt,
                importance = 1,
                level = "warning",
                header = darkred(" * ")
            )

    def __portage_updates_md5(self, repo_updates_file):

        root = etpConst['systemroot'] + os.path.sep

        portdb = self._get_portage_portagetree(root).dbapi
        mdigest = hashlib.md5()
        # this way, if no matches are found, the same value is returned
        if sys.hexversion >= 0x3000000:
            mdigest.update(const_convert_to_rawstring("begin"))
        else:
            mdigest.update("begin")

        for repo_name in portdb.getRepositories():
            repo_path = portdb.getRepositoryPath(repo_name)
            updates_dir = os.path.join(repo_path, "profiles", "updates")
            if not os.path.isdir(updates_dir):
                continue

            # get checksum
            # update
            ndigest = entropy.tools.md5obj_directory(updates_dir)
            mdigest.update(ndigest.digest())

        # also checksum etpConst['etpdatabaseupdatefile']
        if os.path.isfile(repo_updates_file):
            with open(repo_updates_file, "rb") as f:
                block = f.read(1024)
                while block:
                    mdigest.update(block)
                    block = f.read(1024)
                f.flush()

        return mdigest

    def __get_portage_update_actions(self, repo_updates_file):

        root = etpConst['systemroot'] + os.path.sep

        updates_map = {}
        portdb = self._get_portage_portagetree(root).dbapi

        for repo_name in portdb.getRepositories():
            repo_path = portdb.getRepositoryPath(repo_name)
            updates_dir = os.path.join(repo_path, "profiles", "updates")
            if not os.path.isdir(updates_dir):
                continue

            update_files_repo = [x for x in os.listdir(updates_dir) if x \
                not in ("CVS", ".svn")]
            for update_id in update_files_repo:
                obj = updates_map.setdefault(update_id, [])
                obj.append(os.path.join(updates_dir, update_id))

        update_actions = []
        sorted_ids = PortageMetaphor.sort_update_files(list(updates_map.keys()))
        for update_id in sorted_ids:
            update_files = updates_map[update_id]

            # now load actions from files
            for update_file in update_files:
                f = open(update_file, "r")
                mycontent = f.readlines()
                f.close()
                lines = [x.strip() for x in mycontent if x.strip()]
                update_actions.extend(lines)

        # add entropy packages.db.repo_updates content
        if os.path.isfile(repo_updates_file):
            f = open(repo_updates_file, "r")
            mycontent = f.readlines()
            f.close()
            lines = [x.strip() for x in mycontent if x.strip() and \
                not x.strip().startswith("#")]
            update_actions.extend(lines)

        return update_actions

    def package_names_update(self, entropy_repository, entropy_repository_id,
        entropy_server, entropy_branch):

        repo_updates_file = \
            entropy_server._get_local_repository_treeupdates_file(
                entropy_repository_id)
        do_rescan = False

        stored_digest = entropy_repository.retrieveRepositoryUpdatesDigest(
            entropy_repository_id)
        if stored_digest == -1:
            do_rescan = True

        # check portage files for changes if do_rescan is still false
        portage_dirs_digest = "0"
        if not do_rescan:

            if entropy_repository_id in \
                self.__entropy_repository_treeupdate_digests:

                portage_dirs_digest = \
                    self.__entropy_repository_treeupdate_digests.get(
                        entropy_repository_id)
            else:
                mdigest = self.__portage_updates_md5(repo_updates_file)
                portage_dirs_digest = mdigest.hexdigest()
                self.__entropy_repository_treeupdate_digests[entropy_repository_id] = \
                    portage_dirs_digest

        if do_rescan or (str(stored_digest) != str(portage_dirs_digest)):

            # force parameters, only ServerEntropyRepository exposes
            # the setReadonly method
            entropy_repository.setReadonly(False)
            # disable upload trigger
            from entropy.server.interfaces.main import \
                ServerEntropyRepositoryPlugin
            entropy_repository.set_plugin_metadata(
                ServerEntropyRepositoryPlugin.PLUGIN_ID, "no_upload", True)

            # reset database tables
            entropy_repository.clearTreeupdatesEntries(entropy_repository_id)
            update_actions = self.__get_portage_update_actions(
                repo_updates_file)

            # now filter the required actions
            update_actions = entropy_repository.filterTreeUpdatesActions(
                update_actions)
            if update_actions:

                mytxt = "%s: %s. %s %s" % (
                    bold(_("ATTENTION")),
                    red(_("forcing package updates")),
                    red(_("Syncing with")),
                    blue("Portage"),
                )
                self.__output.output(
                    mytxt,
                    importance = 1,
                    level = "info",
                    header = brown(" * ")
                )
                # lock database
                if entropy_repository.get_plugins_metadata().get("lock_remote"):
                    no_upload = entropy_repository.get_plugins_metadata().get(
                        "no_upload")
                    entropy_server._server_repository_sync_lock(
                        entropy_repository_id, no_upload)
                # now run queue
                try:
                    quickpkg_list = entropy_repository.runTreeUpdatesActions(
                        update_actions)
                except:
                    # destroy digest
                    entropy_repository.setRepositoryUpdatesDigest(
                        entropy_repository_id, "-1")
                    raise

                if quickpkg_list:
                    # quickpkg package and packages owning it as a dependency
                    try:
                        self.__run_pkg_sync_quickpkg(
                            entropy_server,
                            quickpkg_list, entropy_repository,
                            entropy_repository_id)
                    except:
                        entropy.tools.print_traceback()
                        mytxt = "%s: %s: %s, %s." % (
                            bold(_("WARNING")),
                            red(_("Cannot complete quickpkg for atoms")),
                            blue(str(sorted(quickpkg_list))),
                            _("do it manually"),
                        )
                        self.__output.output(
                            mytxt,
                            importance = 1,
                            level = "warning",
                            header = darkred(" * ")
                        )
                    entropy_repository.commit()

                # store new actions
                entropy_repository.addRepositoryUpdatesActions(
                    entropy_repository_id, update_actions, entropy_branch)

            # store new digest into database
            entropy_repository.setRepositoryUpdatesDigest(
                entropy_repository_id, portage_dirs_digest)
            entropy_repository.commit()

    @staticmethod
    def package_phases_map():
        """
        Reimplemented from SpmPlugin class.
        """
        return PortagePlugin._package_phases_map.copy()

    @staticmethod
    def config_files_map():
        """
        Reimplemented from SpmPlugin class.
        """
        return PortagePlugin._config_files_map.copy()

    def execute_package_phase(self, package_metadata, phase_name):
        """
        Reimplemented from SpmPlugin class.
        """
        portage_phase = PortagePlugin._package_phases_map[phase_name]
        phase_calls = {
            'setup': self._pkg_setup,
            'preinst': self._pkg_preinst,
            'postinst': self._pkg_postinst,
            'prerm': self._pkg_prerm,
            'postrm': self._pkg_postrm,
            'config': self._pkg_config,
        }
        return phase_calls[portage_phase](package_metadata)

    def _bump_vartree_mtime(self, portage_cpv):
        root = etpConst['systemroot'] + os.path.sep
        vartree = self._get_portage_vartree(root = root)
        if hasattr(vartree.dbapi, '_bump_mtime'):
            vartree.dbapi._bump_mtime(portage_cpv)

    def __splitdebug_update_features_file(self, features_path):

        with open(features_path, "r") as feat_f:
            feat_content = feat_f.read().split(" ")

        if "splitdebug" in feat_content:

            feat_content.remove("splitdebug")

            with open(features_path+".tmp", "w") as feat_f:
                feat_f.write(" ".join(feat_content) + "\n")
                feat_f.flush()

            os.rename(features_path+".tmp", features_path)

    def __splitdebug_update_contents_file(self, contents_path, splitdebug_dirs):

        if not (os.path.isfile(contents_path) and \
            os.access(contents_path, os.R_OK)):
            return

        with open(contents_path, "r") as cont_f:
            with open(contents_path+".tmp", "w") as cont_new_f:
                line = cont_f.readline()
                while line:
                    do_skip = False
                    split_line = line.split()
                    if len(split_line) > 1:
                        for splitdebug_dir in splitdebug_dirs:
                            if split_line[1].startswith(splitdebug_dir):
                                do_skip = True
                                break
                    if do_skip:
                        line = cont_f.readline()
                        continue
                    cont_new_f.write(line)
                    line = cont_f.readline()

                cont_new_f.flush()

        os.rename(contents_path+".tmp", contents_path)

    def _create_contents_file_if_not_available(self, pkg_dir,
        entropy_package_metadata):

        c_file = PortagePlugin.xpak_entries['contents']
        cont_path = os.path.join(pkg_dir, c_file)
        contents_file_exists = os.path.exists(cont_path)
        if contents_file_exists:
            return # all fine already
        entropy_content = entropy_package_metadata['content'] # this is a set

        from portage.dbapi.vartree import write_contents

        obj_t = const_convert_to_rawstring("obj")
        sym_t = const_convert_to_rawstring("sym")
        dir_t = const_convert_to_rawstring("dir")
        fif_t = const_convert_to_rawstring("fif")
        dev_t = const_convert_to_rawstring("dev")
        sys_root = const_convert_to_rawstring(etpConst['systemroot'])

        content_meta = {}
        for path_orig in sorted(entropy_content):

            path_orig = const_convert_to_rawstring(path_orig)
            path = sys_root + path_orig

            if not os.path.lexists(path):
                mytxt = "%s: %s: %s" % (red(_("QA")),
                    brown(_("Cannot stat path")),
                    purple(repr(path)),)
                self.__output.output(
                    mytxt,
                    importance = 1,
                    level = "warning",
                    header = darkred("   ## ")
                )
                continue

            is_sym = os.path.islink(path)
            if os.path.isfile(path) and not is_sym:
                md5sum = entropy.tools.md5sum(path)
                mtime = int(os.path.getmtime(path))
                content_meta[path] = (obj_t, mtime, md5sum,)
            elif os.path.isdir(path) and not is_sym:
                content_meta[path] = (dir_t,)
            elif is_sym:
                try:
                    mtime = int(os.path.getmtime(path))
                except OSError:
                    # broken symlink!
                    mtime = int(time.time())
                content_meta[path] = (sym_t, mtime, os.readlink(path),)
            else:
                try:
                    lstat = os.lstat(path)
                except (OSError, AttributeError):
                    lstat = None
                if lstat is not None:
                    if stat.S_ISFIFO(lstat[stat.ST_MODE]):
                        content_meta[path] = (fif_t,)
                    elif not stat.S_ISREG(lstat[stat.ST_MODE]):
                        # device?
                        content_meta[path] = (dev_t,)

        portage_cpv = PortagePlugin._pkg_compose_atom(entropy_package_metadata)
        self._bump_vartree_mtime(portage_cpv)

        with open(cont_path, "w") as cont_f:
            utf_sys_root = etpConst['systemroot'] + os.path.sep
            # NOTE: content_meta contains paths with ROOT prefix, it's ok
            write_contents(content_meta, utf_sys_root, cont_f)
            cont_f.flush()

        self._bump_vartree_mtime(portage_cpv)

    def _get_portage_sets_object(self):
        try:
            import portage._sets as sets
        except ImportError:
            try:
                # older portage, <= 2.2_rc67
                import portage.sets as sets
            except ImportError:
                sets = None
        return sets

    def _get_world_set_object(self):
        try:
            from portage._sets.files import WorldSelectedSet
        except ImportError:
            try:
                # older portage, <= 2.2_rc67
                from portage.sets.files import WorldSelectedSet
            except ImportError:
                WorldSelectedSet = None
        return WorldSelectedSet

    class _PortageVdbLocker(object):

        def __init__(self, parent):
            self.__vdb_path = parent._get_vdb_path()
            self.__vdb_lock = None
            self.__parent = parent
            self.__locked = 0

        def __enter__(self):
            if self.__locked == 0:
                self.__vdb_lock = self.__parent._portage.locks.lockdir(
                    self.__vdb_path)
            self.__locked += 1

        def __exit__(self, exc_type, exc_value, traceback):
            if self.__locked > 0:
                self.__locked -= 1
            if (self.__locked == 0) and (self.__vdb_lock is not None):
                self.__parent._portage.locks.unlockdir(
                    self.__vdb_lock)
                self.__vdb_lock = None

    class _PortageWorldSetLocker(object):

        def __init__(self, parent):
            self.__world_set = None
            world_set = parent._get_world_set_object()
            if world_set is not None:
                self.__root = etpConst['systemroot'] + os.path.sep
                self.__world_set = world_set(self.__root)
            self.__locked = 0

        def __enter__(self):
            if self.__world_set is not None:
                if self.__locked == 0:
                    self.__world_set.lock()
                self.__locked += 1

        def __exit__(self, exc_type, exc_value, traceback):
            if self.__world_set is not None:
                if self.__locked > 0:
                    self.__locked -= 1
                if self.__locked == 0:
                    self.__world_set.unlock()

    def add_installed_package(self, package_metadata):
        """
        Reimplemented from SpmPlugin class.
        """
        atomsfound = set()
        spm_package = PortagePlugin._pkg_compose_atom(package_metadata)
        key = entropy.dep.dep_getkey(spm_package)
        category = key.split("/")[0]

        build = self.get_installed_package_build_script_path(spm_package)
        pkg_dir = package_metadata.get('unittest_root', '') + \
            os.path.dirname(build)
        cat_dir = os.path.dirname(pkg_dir)

        if os.path.isdir(cat_dir):
            my_findings = [os.path.join(category, x) for x in \
                os.listdir(cat_dir)]
            # filter by key
            real_findings = [x for x in my_findings if \
                key == entropy.dep.dep_getkey(x)]
            atomsfound.update(real_findings)

        myslot = package_metadata['slot']
        for xatom in atomsfound:

            try:
                if self.get_installed_package_metadata(xatom, "SLOT") != myslot:
                    continue
            except KeyError: # package not found??
                continue

            mybuild = self.get_installed_package_build_script_path(xatom)
            remove_path = os.path.dirname(mybuild)
            shutil.rmtree(remove_path, True)

        # we now install it
        xpak_rel_path = PortagePlugin._xpak_const['entropyxpakdatarelativepath']
        proposed_xpak_dir = os.path.join(package_metadata['xpakpath'],
            xpak_rel_path)

        counter = -1
        if (package_metadata['xpakstatus'] != None) and \
            os.path.isdir(proposed_xpak_dir) or package_metadata['merge_from']:

            copypath = proposed_xpak_dir
            if package_metadata['merge_from']:
                copypath = package_metadata['xpakdir']
                if not os.path.isdir(copypath):
                    return 0

            if not os.path.isdir(cat_dir):
                os.makedirs(cat_dir, 0o755)

            splitdebug = package_metadata.get("splitdebug", False)
            splitdebug_dirs = package_metadata.get("splitdebug_dirs", tuple())
            if splitdebug:
                features_path = os.path.join(copypath,
                    PortagePlugin.xpak_entries['features'])
                self.__splitdebug_update_features_file(features_path)
            elif not splitdebug and splitdebug_dirs:
                contents_path = os.path.join(copypath,
                    PortagePlugin.xpak_entries['contents'])
                self.__splitdebug_update_contents_file(contents_path,
                    splitdebug_dirs)

            # lock vdb before making changes
            with self._PortageVdbLocker(self):

                if os.path.isdir(pkg_dir):
                    shutil.rmtree(pkg_dir)

                try:
                    shutil.copytree(copypath, pkg_dir)
                except (IOError,) as e:
                    mytxt = "%s: %s: %s: %s" % (red(_("QA")),
                        brown(_("Cannot update Portage database to destination")),
                        purple(pkg_dir), e,)
                    self.__output.output(
                        mytxt,
                        importance = 1,
                        level = "warning",
                        header = darkred("   ## ")
                    )

                # this is a Unit Testing setting, so it's always not available
                # unless in unit testing code
                if not package_metadata.get('unittest_root'):

                    # Packages emerged with -B don't contain CONTENTS file
                    # in their metadata, so we have to create one
                    self._create_contents_file_if_not_available(pkg_dir,
                        package_metadata['triggers']['install'])

                    try:
                        counter = self.assign_uid_to_installed_package(
                            spm_package)
                    except SPMError as err:
                        mytxt = "%s: %s [%s]" % (
                            brown(_("SPM uid update error")), pkg_dir, err,
                        )
                        self.__output.output(
                            red("QA: ") + mytxt,
                            importance = 1,
                            level = "warning",
                            header = darkred("   ## ")
                        )
                        counter = -1

                # from this point, every vardb change has to be committed
                self._bump_vartree_mtime(spm_package)

        user_inst_source = etpConst['install_sources']['user']
        if package_metadata['install_source'] != user_inst_source:
            # only user selected packages in Portage world file
            return counter

        myslot = package_metadata['slot'][:]
        # old slot protocol for kernel packages
        # XXX: remove before 2011-12-31
        if (package_metadata['versiontag'] == package_metadata['slot']) \
            and package_metadata['versiontag']:
            # usually kernel packages
            myslot = "0"
        elif package_metadata['versiontag'] and \
            ("," in package_metadata['slot']):
            # new slot format for kernel tagged packages
            myslot = entropy.dep.remove_tag_from_slot(myslot)

        keyslot = const_convert_to_rawstring(key+":"+myslot)
        key = const_convert_to_rawstring(key)
        world_file = self.get_user_installed_packages_file()
        world_dir = os.path.dirname(world_file)
        world_atoms = set()


        try:

            with self._PortageWorldSetLocker(self):

                if os.access(world_file, os.R_OK) and \
                    os.path.isfile(world_file):

                    with open(world_file, "rb") as world_f:
                        world_atoms |= set((x.strip() for x in \
                            world_f.readlines() if x.strip()))

                if keyslot not in world_atoms and \
                    os.access(world_dir, os.W_OK) and \
                    entropy.tools.istextfile(world_file):

                    world_atoms.discard(key)
                    world_atoms.add(keyslot)
                    world_file_tmp = world_file+".entropy_inst"

                    newline = const_convert_to_rawstring("\n")
                    with open(world_file_tmp, "wb") as world_f:
                        for item in sorted(world_atoms):
                            world_f.write(
                                const_convert_to_rawstring(item + newline))
                        world_f.flush()

                    os.rename(world_file_tmp, world_file)

        except (UnicodeDecodeError, UnicodeEncodeError,) as e:

            mytxt = "%s: %s" % (
                brown(_("Cannot update SPM installed pkgs file")), world_file,
            )
            self.__output.output(
                red("QA: ") + mytxt + ": " + repr(e),
                importance = 1,
                level = "warning",
                header = darkred("   ## ")
            )

        return counter

    def remove_installed_package(self, package_metadata):
        """
        Reimplemented from SpmPlugin class.
        """
        atom = entropy.dep.remove_tag(package_metadata['removeatom'])
        remove_build = self.get_installed_package_build_script_path(atom)
        remove_path = os.path.dirname(remove_build)
        key = entropy.dep.dep_getkey(atom)

        with self._PortageVdbLocker(self):

            others_installed = self.match_installed_package(key,
                match_all = True)

            # Support for tagged packages
            slot = package_metadata['slot']
            tag = package_metadata['versiontag']
            if (tag == slot) and tag:
                # old kernel tagged pkgs protocol
                slot = "0"
            elif tag and ("," in slot):
                # new kernel tagged pkgs protocol
                slot = entropy.dep.remove_tag_from_slot(slot)

            def do_rm_path_atomic(xpath):
                for my_el in os.listdir(xpath):
                    my_el = os.path.join(xpath, my_el)
                    try:
                        os.remove(my_el)
                    except OSError:
                        pass
                try:
                    os.rmdir(xpath)
                except OSError:
                    pass

            if os.path.isdir(remove_path):
                do_rm_path_atomic(remove_path)

            # also remove parent directory if empty
            category_path = os.path.dirname(remove_path)
            if os.path.isdir(category_path):
                if not os.listdir(category_path):
                    try:
                        os.rmdir(category_path)
                    except OSError:
                        pass

            if isinstance(others_installed, (list, set, tuple)):

                for myatom in others_installed:

                    if myatom == atom:
                        # do not remove self
                        continue

                    try:
                        myslot = self.get_installed_package_metadata(myatom,
                            "SLOT")
                    except KeyError:
                        # package got removed or not available or broken
                        continue

                    if myslot != slot:
                        continue
                    mybuild = self.get_installed_package_build_script_path(
                        myatom)
                    mydir = os.path.dirname(mybuild)
                    if not os.path.isdir(mydir):
                        continue
                    do_rm_path_atomic(mydir)

        with self._PortageWorldSetLocker(self):

            # otherwise update Portage world file
            world_file = self.get_user_installed_packages_file()
            world_file_tmp = world_file + ".entropy.tmp"
            if os.access(world_file, os.W_OK) and os.path.isfile(world_file):

                new = open(world_file_tmp, "wb")
                old = open(world_file, "rb")
                line = old.readline()
                key_raw = const_convert_to_rawstring(key)
                keyslot = const_convert_to_rawstring(key+":"+slot)

                while line:

                    if line.find(key_raw) != -1:
                        line = old.readline()
                        continue
                    if line.find(keyslot) != -1:
                        line = old.readline()
                        continue
                    new.write(line)
                    line = old.readline()

                new.flush()
                new.close()
                old.close()
                os.rename(world_file_tmp, world_file)

        return 0

    @staticmethod
    def execute_qa_tests(package_path):
        """
        Reimplemented from SpmPlugin class.
        """
        tests = [PortagePlugin._test_environment_bz2]
        msg = None
        exec_rc = 0
        for test in tests:
            exec_rc, msg = test(package_path)
            if exec_rc != 0:
                break
        return exec_rc, msg

    @staticmethod
    def _test_environment_bz2(package_path):

        tmp_path = tempfile.mkdtemp()
        xpaktools.extract_xpak(package_path, tmpdir = tmp_path)
        if not os.listdir(tmp_path):
            shutil.rmtree(tmp_path)
            return 1, "unable to extract xpak metadata"

        # make sure we have the environment.bz2 file to check
        env_file = os.path.join(tmp_path, PortagePlugin.ENV_FILE_COMP)
        if not (os.path.isfile(env_file) and os.access(env_file, os.R_OK)):
            shutil.rmtree(tmp_path)
            return 2, "unable to locate %s file" % (
                PortagePlugin.ENV_FILE_COMP,)

        # check if we have an alternate setting for LC*
        sys_settings = SystemSettings()
        srv_plug_id = etpConst['system_settings_plugins_ids']['server_plugin']
        try:
            qa_langs = sys_settings[srv_plug_id]['server']['qa_langs']
        except KeyError:
            qa_langs = ["en_US", "C"]

        qa_rlangs = [const_convert_to_rawstring("LC_ALL="+x) for x in qa_langs]

        valid_lc_all = False
        lc_found = False
        msg = None
        lc_all_str = const_convert_to_rawstring("LC_ALL")
        found_lang = None
        bz_f = None
        try:

            # read env file
            bz_f = bz2.BZ2File(env_file, "r")

            for line in bz_f.readlines():
                if not line.startswith(lc_all_str):
                    continue
                lc_found = True
                found_lang = line.strip()
                for lang in qa_rlangs:
                    if line.startswith(lang):
                        valid_lc_all = True
                        break
        finally:
            if bz_f is not None:
                bz_f.close()

        env_rc = 0
        if lc_found and (not valid_lc_all):
            msg = "LC_ALL not set to => %s (but: %s)" % (qa_langs, found_lang,)
            env_rc = 1
        shutil.rmtree(tmp_path)

        return env_rc, msg

    @staticmethod
    def _config_updates_make_conf(entropy_client, repo):

        ## WARNING: it doesn't handle multi-line variables, yet. remember this.
        system_make_conf = PortagePlugin._config_files_map['global_make_conf']

        sys_settings = SystemSettings()
        avail_data = sys_settings['repositories']['available']
        repo_dbpath = avail_data[repo]['dbpath']
        repo_make_conf = os.path.join(repo_dbpath,
            os.path.basename(system_make_conf))

        if not (os.path.isfile(repo_make_conf) and \
            os.access(repo_make_conf, os.R_OK)):
            return

        make_conf_variables_check = ["CHOST"]

        if not os.path.isfile(system_make_conf):
            entropy_client.output(
                "%s %s. %s." % (
                    red(system_make_conf),
                    blue(_("does not exist")), blue(_("Overwriting")),
                ),
                importance = 1,
                level = "info",
                header = blue(" @@ ")
            )
            if os.path.lexists(system_make_conf):
                shutil.move(
                    system_make_conf,
                    "%s.backup_%s" % (system_make_conf,
                        entropy.tools.get_random_number(),)
                )
            shutil.copy2(repo_make_conf, system_make_conf)

        elif os.access(system_make_conf, os.W_OK):

            repo_f = open(repo_make_conf, "r")
            sys_f = open(system_make_conf, "r")
            repo_make_c = [x.strip() for x in repo_f.readlines()]
            sys_make_c = [x.strip() for x in sys_f.readlines()]
            repo_f.close()
            sys_f.close()

            # read repository settings
            repo_data = {}
            for setting in make_conf_variables_check:
                for line in repo_make_c:
                    if line.startswith(setting+"="):
                        # there can't be bash vars with a space
                        # after its name on declaration
                        repo_data[setting] = line
                        # I don't break, because there might be
                        # other overlapping settings

            differences = {}
            # update make.conf data in memory
            for setting in repo_data:
                for idx in range(len(sys_make_c)):
                    line = sys_make_c[idx]

                    if line.startswith(setting+"=") and \
                        (line != repo_data[setting]):

                        # there can't be bash vars with a
                        # space after its name on declaration
                        entropy_client.output(
                            "%s: %s %s. %s." % (
                                red(system_make_conf), bold(repr(setting)),
                                blue(_("variable differs")), red(_("Updating")),
                            ),
                            importance = 1,
                            level = "info",
                            header = blue(" @@ ")
                        )
                        differences[setting] = repo_data[setting]
                        line = repo_data[setting]
                    sys_make_c[idx] = line

            if differences:

                entropy_client.output(
                    "%s: %s." % (
                        red(system_make_conf),
                        blue(_("updating critical variables")),
                    ),
                    importance = 1,
                    level = "info",
                    header = blue(" @@ ")
                )
                # backup user make.conf
                shutil.copy2(system_make_conf,
                    "%s.entropy_backup" % (system_make_conf,))

                entropy_client.output(
                    "%s: %s." % (
                        red(system_make_conf),
                        darkgreen("writing changes to disk"),
                    ),
                    importance = 1,
                    level = "info",
                    header = blue(" @@ ")
                )
                # write to disk, safely
                tmp_make_conf = "%s.entropy_write" % (system_make_conf,)
                f = open(tmp_make_conf, "w")
                for line in sys_make_c:
                    f.write(line+"\n")
                f.flush()
                f.close()
                shutil.move(tmp_make_conf, system_make_conf)

            # update environment
            for var in differences:
                try:
                    myval = '='.join(differences[var].strip().split("=")[1:])
                    if myval:
                        if myval[0] in ("'", '"',):
                            myval = myval[1:]
                        if myval[-1] in ("'", '"',):
                            myval = myval[:-1]
                except IndexError:
                    myval = ''
                os.environ[var] = myval

    @staticmethod
    def _config_updates_make_profile(entropy_client, repo):

        sys_settings = SystemSettings()
        avail_data = sys_settings['repositories']['available']
        repo_dbpath = avail_data[repo]['dbpath']
        profile_link = PortagePlugin._config_files_map['global_make_profile']
        profile_link_name = os.path.basename(profile_link)

        repo_make_profile = os.path.join(repo_dbpath, profile_link_name)

        if not (os.path.isfile(repo_make_profile) and \
            os.access(repo_make_profile, os.R_OK)):
            return

        system_make_profile = \
            PortagePlugin._config_files_map['global_make_profile']

        f = open(repo_make_profile, "r")
        repo_profile_link_data = f.readline().strip()
        f.close()
        current_profile_link = ''
        if os.path.islink(system_make_profile) and \
            os.access(system_make_profile, os.R_OK):

            current_profile_link = os.readlink(system_make_profile)

        if (repo_profile_link_data != current_profile_link) and \
            repo_profile_link_data:

            entropy_client.output(
                "%s: %s %s. %s." % (
                    red(system_make_profile), blue("link"),
                    blue(_("differs")), red(_("Updating")),
                ),
                importance = 1,
                level = "info",
                header = blue(" @@ ")
            )
            merge_sfx = ".entropy_merge"
            os.symlink(repo_profile_link_data, system_make_profile+merge_sfx)
            if entropy.tools.is_valid_path(system_make_profile+merge_sfx):
                os.rename(system_make_profile+merge_sfx, system_make_profile)
            else:
                # revert change, link does not exist yet
                entropy_client.output(
                    "%s: %s %s. %s." % (
                        red(system_make_profile), blue("new link"),
                        blue(_("does not exist")), red(_("Reverting")),
                    ),
                    importance = 1,
                    level = "info",
                    header = blue(" @@ ")
                )
                os.remove(system_make_profile+merge_sfx)

    @staticmethod
    def entropy_client_post_repository_update_hook(entropy_client,
        entropy_repository_id):

        # are we root?
        if etpConst['uid'] != 0:
            entropy_client.output(
                brown(_("Skipping configuration files update, you are not root.")),
                importance = 1,
                level = "info",
                header = blue(" @@ ")
            )
            return 0

        sys_settings = SystemSettings()
        default_repo = sys_settings['repositories']['default_repository']

        if default_repo == entropy_repository_id:
            PortagePlugin._config_updates_make_conf(entropy_client,
                entropy_repository_id)
            PortagePlugin._config_updates_make_profile(entropy_client,
                entropy_repository_id)

        return 0

    @staticmethod
    def entropy_install_setup_hook(entropy_client, package_metadata):
        """
        Reimplemented from SpmPlugin class.
        """
        package_metadata['xpakpath'] = os.path.join(
            package_metadata['unpackdir'],
            PortagePlugin._xpak_const['entropyxpakrelativepath'])

        if not package_metadata['merge_from']:

            package_metadata['xpakstatus'] = None
            package_metadata['xpakdir'] = os.path.join(
                package_metadata['xpakpath'],
                PortagePlugin._xpak_const['entropyxpakdatarelativepath'])

        else:

            package_metadata['xpakstatus'] = True

            try:
                import portage.const as pc
                portdbdir = pc.VDB_PATH
            except ImportError:
                portdbdir = 'var/db/pkg'

            portdbdir = os.path.join(package_metadata['merge_from'], portdbdir)
            portdbdir = os.path.join(portdbdir,
                PortagePlugin._pkg_compose_atom(package_metadata))

            package_metadata['xpakdir'] = portdbdir

        package_metadata['triggers']['install']['xpakdir'] = \
            package_metadata['xpakdir']

        return 0

    @staticmethod
    def entropy_install_unpack_hook(entropy_client, package_metadata):
        """
        Reimplemented from SpmPlugin class.
        """
        # unpack xpak ?
        if os.path.isdir(package_metadata['xpakpath']):
            shutil.rmtree(package_metadata['xpakpath'], True)

        # create data dir where we'll unpack the xpak
        xpak_dir = os.path.join(package_metadata['xpakpath'],
            PortagePlugin._xpak_const['entropyxpakdatarelativepath'])

        os.makedirs(xpak_dir, 0o755)

        xpak_path = os.path.join(package_metadata['xpakpath'],
            PortagePlugin._xpak_const['entropyxpakfilename'])

        if not package_metadata['merge_from']:

            if package_metadata['smartpackage']:

                # we need to get the .xpak from database
                xdbconn = entropy_client.open_repository(
                    package_metadata['repository'])
                xpakdata = xdbconn.retrieveSpmMetadata(
                    package_metadata['idpackage'])
                if xpakdata:
                    # save into a file
                    with open(xpak_path, "wb") as xpak_f:
                        xpak_f.write(xpakdata)
                        xpak_f.flush()
                    package_metadata['xpakstatus'] = \
                        xpaktools.unpack_xpak(
                            xpak_path,
                            xpak_dir
                        )
                else:
                    package_metadata['xpakstatus'] = None
                del xpakdata

            else:
                package_metadata['xpakstatus'] = xpaktools.extract_xpak(
                    package_metadata['pkgpath'],
                    xpak_dir
                )

        else: # merge_from

            tolink_dir = xpak_dir
            if os.path.isdir(tolink_dir):
                shutil.rmtree(tolink_dir, True)
            # now link
            os.symlink(package_metadata['xpakdir'], tolink_dir)

        # create fake portage ${D} linking it to imagedir
        portage_cpv = PortagePlugin._pkg_compose_atom(package_metadata)

        portage_db_fakedir = os.path.join(
            package_metadata['unpackdir'],
            "portage/" + portage_cpv
        )

        try:
            os.makedirs(portage_db_fakedir, 0o755)
        except OSError as err:
            if err.errno != errno.EEXIST:
                raise
            shutil.rmtree(portage_db_fakedir, True)
            os.makedirs(portage_db_fakedir, 0o755)
        # now link it to package_metadata['imagedir']
        os.symlink(package_metadata['imagedir'],
            os.path.join(portage_db_fakedir, "image"))

        return 0

    def _get_portage_vartree(self, root = None):

        if root is None:
            root = etpConst['systemroot'] + os.path.sep

        cached = PortagePlugin.CACHE['vartree'].get(root)
        if cached is not None:
            return cached

        try:
            mytree = self._portage.vartree(root=root)
        except Exception as e:
            raise SPMError("SPMError: %s" % (e,))
        PortagePlugin.CACHE['vartree'][root] = mytree
        return mytree

    def _get_portage_portagetree(self, root):

        cached = PortagePlugin.CACHE['portagetree'].get(root)
        if cached is not None:
            return cached

        try:
            # settings=self._portage.settings
            mytree = self._portage.portagetree(root=None,
                settings=self._portage.settings)
        except Exception as e:
            raise SPMError("SPMError: %s" % (e,))
        PortagePlugin.CACHE['portagetree'][root] = mytree
        return mytree

    def _get_portage_binarytree(self, root):

        cached = PortagePlugin.CACHE['binarytree'].get(root)
        if cached is not None:
            return cached

        pkgdir = root+self._portage.settings['PKGDIR']
        try:
            mytree = self._portage.binarytree(root, pkgdir)
        except Exception as e:
            raise SPMError("SPMError: %s" % (e,))
        PortagePlugin.CACHE['binarytree'][root] = mytree
        return mytree

    def _get_portage_config(self, config_root, root, use_cache = True):

        if use_cache:
            cached = PortagePlugin.CACHE['config'].get((config_root, root))
            if cached is not None:
                return cached

        try:
            mysettings = self._portage.config(config_root = config_root,
                target_root = root,
                config_incrementals = self._portage.const.INCREMENTALS)
        except Exception as e:
            raise SPMError("SPMError: %s" % (e,))
        if use_cache:
            PortagePlugin.CACHE['config'][(config_root, root)] = mysettings

        return mysettings

    def _get_package_use_file(self):
        return os.path.join(self._portage.const.USER_CONFIG_PATH, 'package.use')

    def _handle_new_useflags(self, atom, useflags, mark):
        matched_atom = self.match_package(atom)
        if not matched_atom:
            return False
        use_file = self._get_package_use_file()

        if not (os.path.isfile(use_file) and os.access(use_file, os.W_OK)):
            return False
        f = open(use_file, "rb")
        content = [x.strip() for x in f.readlines()]
        f.close()

        def handle_line(line, useflags):

            data = line.split()
            if len(data) < 2:
                return False, line

            myatom = data[0]
            if matched_atom != self.match_package(myatom):
                return False, line

            plus = const_convert_to_rawstring("+")
            minus = const_convert_to_rawstring("-")
            myatom = const_convert_to_rawstring(myatom)

            flags = data[1:]
            base_flags = []
            added_flags = []
            for flag in flags:
                myflag = flag
                if myflag.startswith(plus):
                    myflag = myflag[1:]
                elif myflag.startswith(minus):
                    myflag = myflag[1:]
                if not myflag:
                    continue
                base_flags.append(myflag)

            for useflag in useflags:
                if mark+useflag in base_flags:
                    continue
                added_flags.append(mark+useflag)

            if sys.hexversion >= 0x3000000:
                new_line = myatom + b" " + b" ".join(flags+added_flags)
            else:
                new_line = myatom + " " + " ".join(flags+added_flags)

            return True, new_line


        atom_found = False
        new_content = []
        for line in content:

            changed, elaborated_line = handle_line(line, useflags)
            if changed:
                atom_found = True
            new_content.append(elaborated_line)

        if not atom_found:
            if sys.hexversion >= 0x3000000:
                myline = atom + b" " + b' '.join([mark+x for x in useflags])
            else:
                myline = "%s %s" % (atom, ' '.join([mark+x for x in useflags]))
            new_content.append(myline)


        f = open(use_file+".tmp", "wb")
        newline = const_convert_to_rawstring("\n")
        for line in new_content:
            f.write(line + newline)
        f.flush()
        f.close()
        os.rename(use_file + ".tmp", use_file)
        return True

    def _unset_package_useflags(self, atom, useflags):
        matched_atom = self.match_package(atom)
        if not matched_atom:
            return False

        use_file = self._get_package_use_file()
        if not (os.path.isfile(use_file) and os.access(use_file, os.W_OK)):
            return False

        with open(use_file, "rb") as f:
            content = [x.strip() for x in f.readlines()]

        new_content = []
        for line in content:

            data = line.split()
            if len(data) < 2:
                new_content.append(line)
                continue

            myatom = data[0]
            if matched_atom != self.match_package(myatom):
                new_content.append(line)
                continue

            plus = const_convert_to_rawstring("+")
            minus = const_convert_to_rawstring("-")
            myatom = const_convert_to_rawstring(myatom)

            flags = data[1:]
            new_flags = []
            for flag in flags:
                myflag = flag

                if myflag.startswith(plus):
                    myflag = myflag[1:]
                elif myflag.startswith(minus):
                    myflag = myflag[1:]

                if myflag in useflags:
                    continue
                elif not flag:
                    continue

                new_flags.append(flag)

            if new_flags:
                if sys.hexversion >= 0x3000000:
                    new_line = myatom + b" " + b" ".join(new_flags)
                else:
                    new_line = myatom + " " + " ".join(new_flags)
                new_content.append(new_line)

        newline = const_convert_to_rawstring("\n")
        with open(use_file+".tmp", "wb") as f:
            for line in new_content:
                f.write(line + newline)
            f.flush()

        os.rename(use_file + ".tmp", use_file)
        return True

    def _get_package_use_useflags(self, atom):

        data = {
            'enabled': set(),
            'disabled': set(),
        }

        matched_atom = self.match_package(atom)
        if not matched_atom:
            return data

        use_file = self._get_package_use_file()
        if not (os.path.isfile(use_file) and os.access(use_file, os.W_OK)):
            return data

        plus = const_convert_to_rawstring("+")
        minus = const_convert_to_rawstring("-")
        use_data = self._portage.util.grabdict(use_file)
        for myatom in use_data:
            mymatch = self.match_package(myatom)
            if mymatch != matched_atom:
                continue
            for flag in use_data[myatom]:
                if flag.startswith(minus):
                    myflag = flag[1:]
                    data['enabled'].discard(myflag)
                    data['disabled'].add(myflag)
                else:
                    myflag = flag
                    if myflag.startswith(plus):
                        myflag = myflag[1:]
                    data['disabled'].discard(myflag)
                    data['enabled'].add(myflag)

        return data

    def _get_useflags(self):
        return self._portage.settings['USE']

    def _get_useflags_force(self):
        return self._portage.settings.useforce

    def _get_useflags_mask(self):
        return self._portage.settings.usemask

    def _resolve_enabled_useflags(self, iuse_list, use_list):
        use = set()
        use_mask = self._get_useflags_mask()
        use_force = self._get_useflags_force()
        plus = const_convert_to_rawstring("+")
        minus = const_convert_to_rawstring("-")
        for myiuse in iuse_list:
            if myiuse[0] in (plus, minus,):
                myiuse = myiuse[1:]
            if ((myiuse in use_list) or (myiuse in use_force)) and \
                (myiuse not in use_mask):
                use.add(myiuse)
        return use

    def _calculate_dependencies(self, my_iuse, my_use, my_license, my_depend,
        my_rdepend, my_pdepend, my_provide, my_src_uri, my_eapi):

        metadata = {
            'LICENSE': my_license,
            'DEPEND': my_depend,
            'PDEPEND': my_pdepend,
            'RDEPEND': my_rdepend,
            'PROVIDE': my_provide,
            'SRC_URI': my_src_uri,
            'USE_MASK': sorted(self._get_useflags_mask()),
            'USE_FORCE': sorted(self._get_useflags_force()),
        }

        # generate USE flags metadata
        raw_use = my_use.split()
        enabled_use = sorted(self._resolve_enabled_useflags(
            my_iuse.split(), raw_use))

        metadata['ENABLED_USE'] = enabled_use
        use = raw_use + [x for x in metadata['USE_FORCE'] if x not in raw_use]
        metadata['USE'] = sorted([const_convert_to_unicode(x) for x in use if \
            x not in metadata['USE_MASK']])

        for k in "LICENSE", "RDEPEND", "DEPEND", "PDEPEND", "PROVIDE", "SRC_URI":
            try:
                deps = self._portage.dep.use_reduce(metadata[k],
                    uselist = enabled_use, masklist = metadata['USE_MASK'],
                    is_src_uri = (k == "SRC_URI"), eapi = my_eapi)
                if k == "LICENSE":
                    deps = self._paren_license_choose(deps)
                else:
                    deps = self._paren_choose(deps)
                if k.endswith("DEPEND"):
                    deps = self._usedeps_reduce(deps, enabled_use)
                deps = ' '.join(deps)
            except Exception as e:
                entropy.tools.print_traceback()
                self.__output.output(
                    darkred("%s: %s :: %s") % (
                        _("Error calculating dependencies"),
                        k,
                        e,
                    ),
                    importance = 1,
                    level = "error",
                    header = red(" !!! ")
                )
                deps = ''
                continue
            metadata[k] = deps
        return metadata

    def _usedeps_reduce(self, dependencies, enabled_useflags):
        newlist = []

        def strip_use(xuse):
            myuse = xuse[:]
            if myuse[0] == "!":
                myuse = myuse[1:]
            if myuse[-1] in ("=", "?",):
                myuse = myuse[:-1]
            return myuse

        def filter_use_deps(dependency):
            new_use_deps = []
            for use in use_deps:
                """
                explicitly support only specific types
                """
                if (use[0] == "!") and (use[-1] not in ("=", "?",)):
                    # this does not exist atm
                    continue
                elif use[-1] == "=":
                    if use[0] == "!":
                        # foo[!bar=] means bar? ( foo[-bar] ) !bar? ( foo[bar] )
                        s_use = strip_use(use)
                        if s_use in enabled_useflags:
                            new_use_deps.append("-%s" % (s_use,))
                        else:
                            new_use_deps.append(s_use)
                        continue
                    else:
                        # foo[bar=] means bar? ( foo[bar] ) !bar? ( foo[-bar] )
                        s_use = strip_use(use)
                        if s_use in enabled_useflags:
                            new_use_deps.append(s_use)
                        else:
                            new_use_deps.append("-%s" % (s_use,))
                        continue
                elif use[-1] == "?":
                    if use[0] == "!":
                        # foo[!bar?] means bar? ( foo ) !bar? ( foo[-bar] )
                        s_use = strip_use(use)
                        if s_use not in enabled_useflags:
                            new_use_deps.append("-%s" % (s_use,))
                        continue
                    else:
                        # foo[bar?] means bar? ( foo[bar] ) !bar? ( foo )
                        s_use = strip_use(use)
                        if s_use in enabled_useflags:
                            new_use_deps.append(s_use)
                        continue
                new_use_deps.append(use)
            return new_use_deps


        for raw_dependency in dependencies:

            split_deps = entropy.dep.dep_split_or_deps(raw_dependency)
            filtered_deps = []
            for depstring in split_deps:

                use_deps = entropy.dep.dep_getusedeps(depstring)
                if use_deps:

                    new_use_deps = filter_use_deps(depstring)

                    if new_use_deps:
                        depstring = "%s[%s]" % (
                            entropy.dep.remove_usedeps(depstring),
                            ','.join(new_use_deps),
                        )
                    else:
                        depstring = entropy.dep.remove_usedeps(depstring)

                filtered_deps.append(depstring)

            if len(filtered_deps) > 1:
                or_dep = etpConst['entropyordepsep']
                raw_dependency = or_dep.join(filtered_deps) + \
                    etpConst['entropyordepquestion']
            else:
                raw_dependency = filtered_deps[0]
            newlist.append(raw_dependency)

        return newlist

    def _strip_empty(self, myarr):
        """

        # deps.py -- Portage dependency resolution functions
        # Copyright 2003-2004 Gentoo Foundation
        # Distributed under the terms of the GNU General Public License v2
        # $Id: portage_dep.py 9174 2008-01-11 05:49:02Z zmedico $

        Strip all empty elements from an array

        @param myarr: The list of elements
        @type myarr: List
        @rtype: Array
        @return: The array with empty elements removed
        """
        for x in range(len(myarr)-1, -1, -1):
            if not myarr[x]:
                del myarr[x]
        return myarr

    def _paren_choose(self, dep_list):
        newlist = []
        do_skip = False
        for idx in range(len(dep_list)):

            if do_skip:
                do_skip = False
                continue

            item = dep_list[idx]
            if item == "||": # or
                next_item = dep_list[idx+1]
                # || ( asd? ( atom ) dsa? ( atom ) )
                # => [] if use asd and dsa are disabled
                if not next_item:
                    do_skip = True
                    continue
                # must be a list
                item = self._dep_or_select(next_item, top_level = True)
                if not item:
                    # no matches, transform to string and append,
                    # so reagent will fail
                    newlist.append(str(next_item))
                else:
                    newlist += item
                do_skip = True
            elif isinstance(item, list): # and
                item = self._dep_and_select(item)
                newlist += item
            else:
                newlist.append(item)

        return newlist

    def _dep_and_select(self, and_list):
        do_skip = False
        newlist = []
        for idx in range(len(and_list)):

            if do_skip:
                do_skip = False
                continue

            x = and_list[idx]
            if x == "||":
                x = self._dep_or_select(and_list[idx+1])
                do_skip = True
                if not x:
                    x = str(and_list[idx+1])
                else:
                    newlist += x
            elif isinstance(x, list):
                x = self._dep_and_select(x)
                newlist += x
            else:
                newlist.append(x)

        return newlist

    def _dep_or_select(self, or_list, top_level = False):

        if top_level:
            simple_or_list = [x for x in or_list if \
                isinstance(x, const_get_stringtype())] == or_list
            if simple_or_list:
                return [etpConst['entropyordepsep'].join(or_list) + \
                    etpConst['entropyordepquestion']]

        def select_or_dep(dep_list):
            for item in dep_list:
                if isinstance(item, const_get_stringtype()):
                    # match in currently running system
                    if self.match_installed_package(item):
                        return [item]
                else:
                    # and deps, all have to match
                    all_matched = True
                    for dep in item:
                        if not self.match_installed_package(dep):
                            all_matched = False
                            break
                    if all_matched:
                        return item

            # no match found, bailing out
            return [','.join(entropy.tools.flatten(dep_list))]

        deps = []
        skip_next = False

        for idx, item in enumerate(or_list):
            if skip_next:
                skip_next = False
                continue
            if item == "||":
                # get next item
                deps += self._dep_or_select(or_list[idx+1])
                skip_next = True
            elif not isinstance(item, const_get_stringtype()):
                # AND list, all have to match
                # must append one item that is a list
                dep = self._dep_and_select(item)
                if not dep:
                    # holy! add the whole dep as string (so it will fail)
                    dep = ['&'.join(item)]
                deps.append(dep)
            else:
                deps.append(item)

        return select_or_dep(deps)

    def _paren_license_choose(self, dep_list):

        newlist = set()
        for item in dep_list:
            if not isinstance(item, const_get_stringtype()):
                # match the first
                newlist.update(self._paren_license_choose(item))
            elif item != "||":
                newlist.add(item)

        return sorted(newlist)

    def _get_vdb_path(self, root = None):
        if root is None:
            root = etpConst['systemroot'] + os.path.sep
        return os.path.join(root, self._portage.const.VDB_PATH)

    def _load_sets_config(self, settings, trees):

        sets = self._get_portage_sets_object()
        if sets is None:
            return None
        return sets.load_default_config(settings, trees)

    def _get_set_config(self):
        myroot = etpConst['systemroot'] + os.path.sep
        return self._load_sets_config(
            self._portage.settings,
            self._portage.db[myroot]
        )

    def _extract_pkg_metadata_generate_extraction_dict(self):
        data = {
            'eapi': {
                'path': PortagePlugin.xpak_entries['eapi'],
                'critical': False,
            },
            'pf': {
                'path': PortagePlugin.xpak_entries['pf'],
                'critical': True,
            },
            'chost': {
                'path': PortagePlugin.xpak_entries['chost'],
                'critical': False, # we deal with it afterwards
            },
            'description': {
                'path': PortagePlugin.xpak_entries['description'],
                'critical': False,
            },
            'homepage': {
                'path': PortagePlugin.xpak_entries['homepage'],
                'critical': False,
            },
            'slot': {
                'path': PortagePlugin.xpak_entries['slot'],
                'critical': False,
            },
            'cflags': {
                'path': PortagePlugin.xpak_entries['cflags'],
                'critical': False,
            },
            'cxxflags': {
                'path': PortagePlugin.xpak_entries['cxxflags'],
                'critical': False,
            },
            'category': {
                'path': PortagePlugin.xpak_entries['category'],
                'critical': True,
            },
            'rdepend': {
                'path': PortagePlugin.xpak_entries['rdepend'],
                'critical': False,
            },
            'pdepend': {
                'path': PortagePlugin.xpak_entries['pdepend'],
                'critical': False,
            },
            'depend': {
                'path': PortagePlugin.xpak_entries['depend'],
                'critical': False,
            },
            'use': {
                'path': PortagePlugin.xpak_entries['use'],
                'critical': False,
            },
            'iuse': {
                'path': PortagePlugin.xpak_entries['iuse'],
                'critical': False,
            },
            'license': {
                'path': PortagePlugin.xpak_entries['license'],
                'critical': False,
            },
            'provide': {
                'path': PortagePlugin.xpak_entries['provide'],
                'critical': False,
            },
            'sources': {
                'path': PortagePlugin.xpak_entries['src_uri'],
                'critical': False, # we deal with it afterwards
            },
            'counter': {
                'path': PortagePlugin.xpak_entries['counter'],
                'critical': False,
            },
            'keywords': {
                'path': PortagePlugin.xpak_entries['keywords'],
                'critical': False,
            },
            'spm_phases': {
                'path': PortagePlugin.xpak_entries['defined_phases'],
                'critical': False,
            },
            'spm_repository': {
                'path': PortagePlugin.xpak_entries['repository'],
                'critical': False,
            },
        }
        return data

    def _extract_pkg_metadata_content_safety(self, content_data, pkg_dir):

        def is_reg(file_path):
            try:
                st = os.lstat(file_path)
            except OSError:
                return False
            return stat.S_ISREG(st.st_mode)

        def gen_meta(real_path, repo_path):
            return {
                'sha256': entropy.tools.sha256(real_path),
                'mtime': os.path.getmtime(real_path),
            }

        pkg_files = [(os.path.join(pkg_dir, k.lstrip("/")), k) for k, v in \
            content_data.items() if v == "obj"]
        pkg_files = [(real_path, repo_path) for real_path, repo_path in \
            pkg_files if is_reg(real_path)]
        return dict((repo_path, gen_meta(real_path, repo_path)) \
            for real_path, repo_path in pkg_files)

    def _extract_pkg_metadata_content(self, content_file, package_path, pkg_dir):

        pkg_content = {}
        obj_t = const_convert_to_unicode("obj")
        sym_t = const_convert_to_unicode("sym")
        fif_t = const_convert_to_unicode("fif")
        dev_t = const_convert_to_unicode("dev")
        dir_t = const_convert_to_unicode("dir")

        if os.path.isfile(content_file):

            with open(content_file, "rb") as f:
                content = [const_convert_to_unicode(x) for x in f.readlines()]

            outcontent = set()
            for line in content:
                line = line.strip().split()
                try:
                    datatype = line[0]
                    datafile = line[1:]
                    if datatype == obj_t:
                        datafile = datafile[:-2]
                        datafile = ' '.join(datafile)
                    elif datatype in (dir_t, fif_t, dev_t):
                        datafile = ' '.join(datafile)
                    elif datatype == sym_t:
                        datafile = datafile[:-3]
                        datafile = ' '.join(datafile)
                    else:
                        myexc = "%s %s. %s." % (
                            datafile,
                            _("not supported"),
                            _("Probably Portage API has changed"),
                        )
                        raise AttributeError(myexc)
                    outcontent.add((datafile, datatype))
                except:
                    pass

            outcontent = sorted(outcontent)
            for datafile, datatype in outcontent:
                pkg_content[datafile] = datatype

        else:

            # CONTENTS is not generated when a package is emerged with
            # portage and the option -B
            # we have to use the unpacked package file and generate content dict
            tmpdir_len = len(pkg_dir)
            for currentdir, subdirs, files in os.walk(pkg_dir):
                cur_dir = currentdir[tmpdir_len:]
                if cur_dir: # ignore "" entries
                    pkg_content[cur_dir] = dir_t
                for item in files:
                    item = currentdir + os.path.sep + item
                    if os.path.islink(item):
                        pkg_content[item[tmpdir_len:]] = sym_t
                    else:
                        pkg_content[item[tmpdir_len:]] = obj_t

        return pkg_content

    def _extract_pkg_metadata_needed(self, needed_file):

        pkg_needed = set()
        lines = []

        try:
            f = open(needed_file, "rb")
            lines = [x.strip() for x in f.readlines() if x.strip()]
            lines = [const_convert_to_unicode(x) for x in lines]
            f.close()
        except IOError:
            return lines

        for line in lines:
            needed = line.split()
            if len(needed) == 2:
                ownlib = needed[0]
                ownelf = -1
                if os.access(ownlib, os.R_OK):
                    ownelf = entropy.tools.read_elf_class(ownlib)
                for lib in needed[1].split(","):
                    #if lib.find(".so") != -1:
                    pkg_needed.add((lib, ownelf))

        return tuple(sorted(pkg_needed))

    def _extract_pkg_metadata_provided_libs(self, pkg_dir, content):

        # NOTE: this does not take into account changes to environment
        # caused by the installation of the package, if this metadata
        # is read off a non-installed one.
        provided_libs = set()
        ldpaths = entropy.tools.collect_linker_paths()
        for obj, ftype in content.items():

            if ftype == "dir":
                continue
            obj_dir, obj_name = os.path.split(obj)

            if obj_dir not in ldpaths:
                continue

            unpack_obj = os.path.join(pkg_dir, obj[1:])
            try:
                os.stat(unpack_obj)
            except OSError:
                continue

            # do not trust ftype
            if os.path.isdir(unpack_obj):
                continue
            try:
                if not entropy.tools.is_elf_file(unpack_obj):
                    continue
                elf_class = entropy.tools.read_elf_class(unpack_obj)
            except IOError as err:
                self.__output.output("%s: %s => %s" % (
                    _("IOError while reading"), unpack_obj, repr(err),),
                    level = "warning")
                continue

            provided_libs.add((obj_name, obj, elf_class,))

        return provided_libs

    def _extract_pkg_metadata_desktop_mime(self, pkg_dir, content):

        valid_paths = [x for x in content if x.endswith(".desktop")]
        if not valid_paths:
            return [], set()

        data_dirs = [os.path.join(x, "applications") for x in \
            os.getenv("XDG_DATA_DIRS", "/usr/share").split(":")]

        def filter_valid_paths(path):
            for data_dir in data_dirs:
                if path.startswith(data_dir):
                    return True
            return False

        valid_paths = list(filter(filter_valid_paths, valid_paths))
        valid_paths = [os.path.join(pkg_dir, x[1:]) for x in valid_paths]

        desktop_mime = []
        provided_mime = set()

        for desktop_path in sorted(valid_paths):
            if not (os.path.isfile(desktop_path) and \
                os.access(desktop_path, os.R_OK)):
                continue
            with open(desktop_path, "r") as desk_f:
                desk_data = [x.strip().split("=", 1) for x in \
                    desk_f.readlines() if len(x.strip().split("=", 1)) == 2]
                raw_desk_meta = dict(desk_data)

                if "MimeType" not in raw_desk_meta:
                    continue
                elif "Name" not in raw_desk_meta:
                    continue
                provided_mime.update(raw_desk_meta['MimeType'].split(";"))
                desk_meta = {
                    "name": raw_desk_meta['Name'],
                    "mimetype": raw_desk_meta['MimeType'],
                    "executable": raw_desk_meta.get('Exec'),
                    "icon": raw_desk_meta.get("Icon"),
                }
                desktop_mime.append(desk_meta)

        provided_mime.discard("")
        return desktop_mime, provided_mime

    def _extract_pkg_metadata_license_data(self, spm_repository, license_string):

        root = etpConst['systemroot'] + os.path.sep
        portdb = self._get_portage_portagetree(root).dbapi
        license_dirs = [os.path.join(self.get_setting('PORTDIR'), "licenses")]
        if spm_repository is not None:
            repo_path = portdb.getRepositoryPath(spm_repository)
            if repo_path is not None:
                license_dirs.append(os.path.join(repo_path, "licenses"))

        pkg_licensedata = {}
        licdata = [x.strip() for x in license_string.split() if x.strip() \
            and entropy.tools.is_valid_string(x.strip())]

        for mylicense in licdata:
            found_lic = False
            for license_dir in license_dirs:
                licfile = os.path.join(license_dir, mylicense)

                if not (os.access(licfile, os.R_OK | os.F_OK) and \
                    os.path.isfile(licfile)):
                    continue

                if not entropy.tools.istextfile(licfile):
                    continue

                with open(licfile, "rb") as f:
                    content = const_convert_to_rawstring('')
                    line = f.readline()
                    while line:
                        content += line
                        line = f.readline()
                    try:

                        try:
                            pkg_licensedata[mylicense] = \
                                const_convert_to_unicode(content)
                        except UnicodeDecodeError:
                            pkg_licensedata[mylicense] = \
                                const_convert_to_unicode(content, 'utf-8')

                    except (UnicodeDecodeError, UnicodeEncodeError,):
                        continue # sorry!
                found_lic = True
                break

            if not found_lic:
                # make sure we always collect license and show something to
                # user. Also set a default sorry text, in case we are not
                # able to print it.
                pkg_licensedata[mylicense] = """We're sorry, %s license couldn't
be retrieved correcly, so this is a placeholder. I know it's a suboptimal
advice, but please make sure to read it, just google '%s license' and you'll
find it. By accepting this, you agree that your distribution won't be
responsible in any way.""" % (mylicense, mylicense,)

        return pkg_licensedata

    def _extract_pkg_metadata_mirror_links(self, sources_list):

        # =mirror://openoffice|link1|link2|link3
        pkg_links = []
        for i in sources_list:
            if i.startswith("mirror://"):
                # parse what mirror I need
                mirrorURI = i.split("/")[2]
                mirrorlist = set(self.get_download_mirrors(mirrorURI))
                pkg_links.append([mirrorURI, mirrorlist])
                # mirrorURI = openoffice and mirrorlist = [link1, link2, link3]

        return pkg_links

    def _extract_pkg_metadata_ebuild_entropy_tag(self, ebuild):
        search_tag = PortagePlugin._ebuild_entries['ebuild_pkg_tag_var']
        # search inside build environment
        ebuild_tag = os.getenv(search_tag, "")
        if ebuild_tag:
            return ebuild_tag

        # open in unicode fmt
        f = open(ebuild, "r")
        tags = [const_convert_to_unicode(x.strip()) for x in f.readlines() \
            if x.strip() and x.strip().startswith(search_tag)]
        f.close()
        if not tags:
            return ebuild_tag
        tag = tags[-1]
        tag = tag.split("=")[-1].strip('"').strip("'").strip()

        if not entropy.dep.is_valid_package_tag(tag):
            # invalid
            mytxt = "%s: %s: %s" % (
                bold(_("QA")),
                brown(_("illegal Entropy package tag in ebuild")),
                tag,
            )
            self.__output.output(
                mytxt,
                importance = 0,
                header = red("   ## ")
            )
            return ebuild_tag
        return tag
