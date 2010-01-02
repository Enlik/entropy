# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Framework SystemSettings module}.

    SystemSettings is a singleton, pluggable interface which contains
    all the runtime settings (mostly parsed from configuration files
    and inherited from entropy.const -- which contains almost all the
    default values).
    SystemSettings works as a I{dict} object. Due to limitations of
    multiple inherittance when using the Singleton class, SystemSettings
    ONLY mimics a I{dict} AND it's not a subclass of it.

"""
import os
import sys
from threading import RLock

from entropy.const import etpConst, etpUi, etpSys, const_setup_perms, \
    const_secure_config_file, const_set_nice_level, const_isunicode, \
    const_convert_to_unicode, const_convert_to_rawstring
from entropy.core import Singleton, EntropyPluginStore
from entropy.cache import EntropyCacher
from entropy.core.settings.plugins.skel import SystemSettingsPlugin

class SystemSettings(Singleton, EntropyPluginStore):

    """
    This is the place where all the Entropy settings are stored if
    they are not considered instance constants (etpConst).
    For example, here we store package masking cache information and
    settings, client-side, server-side and services settings.
    Also, this class mimics a dictionary (even if not inheriting it
    due to development choices).

    Sample code:

        >>> from entropy.core.settings.base import SystemSettings
        >>> system_settings = SystemSettings()
        >>> system_settings.clear()
        >>> system_settings.destroy()

    """

    import entropy.tools as entropyTools
    def init_singleton(self):

        """
        Replaces __init__ because SystemSettings is a Singleton.
        see Singleton API reference for more information.

        """
        EntropyPluginStore.__init__(self)

        from entropy.core.settings.plugins.factory import get_available_plugins
        self.__get_external_plugins = get_available_plugins

        from entropy.cache import EntropyCacher
        self.__cacher = EntropyCacher()
        self.__data = {}
        self.__is_destroyed = False
        self.__mutex = RLock() # reentrant lock on purpose

        self.__external_plugins = {}
        self.__setting_files_order = []
        self.__setting_files_pre_run = []
        self.__setting_files = {}
        self.__mtime_files = {}
        self.__persistent_settings = {
            'pkg_masking_reasons': etpConst['pkg_masking_reasons'].copy(),
            'pkg_masking_reference': etpConst['pkg_masking_reference'].copy(),
            'backed_up': {},
            # package masking, live
            'live_packagemasking': {
                'unmask_matches': set(),
                'mask_matches': set(),
            },
        }

        self.__setup_const()
        self.__scan()

    def destroy(self):
        """
        Overloaded method from Singleton.
        "Destroys" the instance.

        @return: None
        @rtype: None
        """
        with self.__mutex:
            self.__is_destroyed = True

    def add_plugin(self, system_settings_plugin_instance):
        """
        This method lets you add custom parsers to SystemSettings.
        Mind that you are responsible of handling your plugin instance
        and remove it before it is destroyed. You can remove the plugin
        instance at any time by issuing remove_plugin.
        Every add_plugin or remove_plugin method will also issue clear()
        for you. This could be bad and it might be removed in future.

        @param system_settings_plugin_instance: valid SystemSettingsPlugin
            instance
        @type system_settings_plugin_instance: SystemSettingsPlugin instance
        @return: None
        @rtype: None
        """
        inst = system_settings_plugin_instance
        if not isinstance(inst, SystemSettingsPlugin):
            raise AttributeError("SystemSettings: expected valid " + \
                    "SystemSettingsPlugin instance")
        with self.__mutex:
            EntropyPluginStore.add_plugin(self, inst.get_id(), inst)
            self.clear()

    def remove_plugin(self, plugin_id):
        """
        This method lets you remove previously added custom parsers from
        SystemSettings through its plugin identifier. If plugin_id is not
        available, KeyError exception will be raised.
        Every add_plugin or remove_plugin method will also issue clear()
        for you. This could be bad and it might be removed in future.

        @param plugin_id: plugin identifier
        @type plugin_id: basestring
        @return: None
        @rtype: None
        """
        with self.__mutex:
            EntropyPluginStore.remove_plugin(self, plugin_id)
            self.clear()

    def __setup_const(self):

        """
        Internal method. Does constants initialization.

        @return: None
        @rtype: None
        """

        del self.__setting_files_order[:]
        del self.__setting_files_pre_run[:]
        self.__setting_files.clear()
        self.__mtime_files.clear()

        self.__setting_files.update({
             # keywording configuration files
            'keywords': etpConst['confpackagesdir']+"/package.keywords",
             # unmasking configuration files
            'unmask': etpConst['confpackagesdir']+"/package.unmask",
             # masking configuration files
            'mask': etpConst['confpackagesdir']+"/package.mask",
            # satisfied packages configuration file
            'satisfied': etpConst['confpackagesdir']+"/package.satisfied",
             # masking configuration files
            'license_mask': etpConst['confpackagesdir']+"/license.mask",
            'license_accept': etpConst['confpackagesdir']+"/license.accept",
            'system_mask': etpConst['confpackagesdir']+"/system.mask",
            'system_dirs': etpConst['confdir']+"/fsdirs.conf",
            'system_dirs_mask': etpConst['confdir']+"/fsdirsmask.conf",
            'system_rev_symlinks': etpConst['confdir']+"/fssymlinks.conf",
            'broken_syms': etpConst['confdir']+"/brokensyms.conf",
            'broken_libs_mask': etpConst['confdir']+"/brokenlibsmask.conf",
            'hw_hash': etpConst['confdir']+"/.hw.hash",
            'socket_service': etpConst['socketconf'],
            'system': etpConst['entropyconf'],
            'repositories': etpConst['repositoriesconf'],
            'system_package_sets': {},
        })
        self.__setting_files_order.extend([
            'keywords', 'unmask', 'mask', 'satisfied', 'license_mask',
            'license_accept', 'system_mask', 'system_package_sets',
            'system_dirs', 'system_dirs_mask', 'socket_service', 'system',
            'system_rev_symlinks', 'hw_hash', 'broken_syms', 'broken_libs_mask'
        ])
        self.__setting_files_pre_run.extend(['repositories'])

        dmp_dir = etpConst['dumpstoragedir']
        self.__mtime_files.update({
            'keywords_mtime': os.path.join(dmp_dir, "keywords.mtime"),
            'unmask_mtime': os.path.join(dmp_dir, "unmask.mtime"),
            'mask_mtime': os.path.join(dmp_dir, "mask.mtime"),
            'satisfied_mtime': os.path.join(dmp_dir, "satisfied.mtime"),
            'license_mask_mtime': os.path.join(dmp_dir, "license_mask.mtime"),
            'license_accept_mtime': os.path.join(dmp_dir, "license_accept.mtime"),
            'system_mask_mtime': os.path.join(dmp_dir, "system_mask.mtime"),
        })


    def __scan(self):

        """
        Internal method. Scan settings and fill variables.

        @return: None
        @rtype: None
        """

        def enforce_persistent():
            # merge persistent settings back
            self.__data.update(self.__persistent_settings)
            # restore backed-up settings
            self.__data.update(self.__persistent_settings['backed_up'].copy())

        self.__parse()
        enforce_persistent()

        # plugins support
        local_plugins = self.get_plugins()
        for plugin_id in sorted(local_plugins):
            local_plugins[plugin_id].parse(self)

        # external plugins support
        external_plugins = self.__get_external_plugins()
        for external_plugin_id in sorted(external_plugins):
            external_plugin = external_plugins[external_plugin_id]()
            external_plugin.parse(self)
            self.__external_plugins[external_plugin_id] = external_plugin

        enforce_persistent()

        # run post-SystemSettings setup, plugins hook
        for plugin_id in sorted(local_plugins):
            local_plugins[plugin_id].post_setup(self)

        # run post-SystemSettings setup for external plugins too
        for external_plugin_id in sorted(self.__external_plugins):
            self.__external_plugins[external_plugin_id].post_setup(self)

    def __setitem__(self, mykey, myvalue):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            # backup here too
            if mykey in self.__persistent_settings:
                self.__persistent_settings[mykey] = myvalue
            self.__data[mykey] = myvalue

    def __getitem__(self, mykey):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data[mykey]

    def __delitem__(self, mykey):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            del self.__data[mykey]

    def __iter__(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return iter(self.__data)

    def __contains__(self, item):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return item in self.__data

    def __hash__(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return hash(self.__data)

    def __len__(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return len(self.__data)

    def get(self, mykey, alt_obj = None):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.get(mykey, alt_obj)

    def copy(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.copy()

    def fromkeys(self, seq, val = None):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.fromkeys(seq, val)

    def items(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.items()

    def iteritems(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.iteritems()

    def iterkeys(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.iterkeys()

    def keys(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.keys()

    def pop(self, mykey, default = None):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.pop(mykey, default)

    def popitem(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.popitem()

    def setdefault(self, mykey, default = None):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.setdefault(mykey, default)

    def update(self, kwargs):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.update(kwargs)

    def values(self):
        """
        dict method. See Python dict API reference.
        """
        with self.__mutex:
            return self.__data.values()

    def clear(self):
        """
        dict method. See Python dict API reference.
        Settings are also re-initialized here.

        @return None
        """
        with self.__mutex:
            self.__data.clear()
            self.__setup_const()
            self.__scan()

    def set_persistent_setting(self, persistent_dict):
        """
        Make metadata persistent, the input dict will be merged
        with the base one at every reset call (clear()).

        @param persistent_dict: dictionary to merge
        @type persistent_dict: dict

        @return: None
        @rtype: None
        """
        with self.__mutex:
            self.__persistent_settings.update(persistent_dict)

    def unset_persistent_setting(self, persistent_key):
        """
        Remove dict key from persistent dictionary

        @param persistent_key: key to remove
        @type persistent_dict: dict

        @return: None
        @rtype: None
        """
        with self.__mutex:
            del self.__persistent_settings[persistent_key]
            del self.__data[persistent_key]

    def __setup_package_sets_vars(self):

        """
        This function setups the *files* dictionary about package sets
        that will be read and parsed afterwards by the respective
        internal parser.

        @return: None
        @rtype: None
        """

        # user defined package sets
        sets_dir = etpConst['confsetsdir']
        pkg_set_data = {}
        if (os.path.isdir(sets_dir) and os.access(sets_dir, os.R_OK)):
            set_files = [x for x in os.listdir(sets_dir) if \
                (os.path.isfile(os.path.join(sets_dir, x)) and \
                os.access(os.path.join(sets_dir, x), os.R_OK))]
            for set_file in set_files:
                try:
                    set_file = const_convert_to_unicode(set_file, 'utf-8')
                except UnicodeDecodeError:
                    set_file = const_convert_to_unicode(set_file,
                        sys.getfilesystemencoding())

                path = os.path.join(sets_dir, set_file)
                if sys.hexversion < 0x3000000:
                    if const_isunicode(path):
                        path = const_convert_to_rawstring(path, 'utf-8')
                pkg_set_data[set_file] = path

        self.__setting_files['system_package_sets'].update(pkg_set_data)

    def __parse(self):
        """
        This is the main internal parsing method.
        *files* and *mtimes* dictionaries are prepared and
        parsed just a few lines later.

        @return: None
        @rtype: None
        """
        # some parsers must be run BEFORE everything:
        for item in self.__setting_files_pre_run:
            myattr = '_%s_parser' % (item,)
            if not hasattr(self, myattr):
                continue
            func = getattr(self, myattr)
            self.__data[item] = func()

        # parse main settings
        self.__setup_package_sets_vars()

        for item in self.__setting_files_order:
            myattr = '_%s_parser' % (item,)
            if not hasattr(self, myattr):
                continue
            func = getattr(self, myattr)
            self.__data[item] = func()

    def get_setting_files_data(self):
        """
        Return a copy of the internal *files* dictionary.
        This dict contains config file paths and their identifiers.

        @return: dict __setting_files
        @rtype: dict
        """
        with self.__mutex:
            return self.__setting_files.copy()

    def _keywords_parser(self):
        """
        Parser returning package keyword masking metadata
        read from package.keywords file.
        This file contains package mask or unmask directives
        based on package keywords.

        @return: parsed metadata
        @rtype: dict
        """
        # merge universal keywords
        data = {
                'universal': set(),
                'packages': {},
                'repositories': {},
        }

        self.validate_entropy_cache(self.__setting_files['keywords'],
            self.__mtime_files['keywords_mtime'])
        content = [x.split() for x in \
            self.__generic_parser(self.__setting_files['keywords']) \
            if len(x.split()) < 4]
        for keywordinfo in content:
            # skip wrong lines
            if len(keywordinfo) > 3:
                continue
            # inversal keywording, check if it's not repo=
            if len(keywordinfo) == 1:
                if keywordinfo[0].startswith("repo="):
                    continue
                # convert into entropy format
                if keywordinfo[0] == "**":
                    keywordinfo[0] = ""
                data['universal'].add(keywordinfo[0])
                continue
            # inversal keywording, check if it's not repo=
            if len(keywordinfo) in (2, 3,):
                # repo=?
                if keywordinfo[0].startswith("repo="):
                    continue
                # add to repo?
                items = keywordinfo[1:]
                # convert into entropy format
                if keywordinfo[0] == "**":
                    keywordinfo[0] = ""
                reponame = [x for x in items if x.startswith("repo=") \
                    and (len(x.split("=")) == 2)]
                if reponame:
                    reponame = reponame[0].split("=")[1]
                    if reponame not in data['repositories']:
                        data['repositories'][reponame] = {}
                    # repository unmask or package in repository unmask?
                    if keywordinfo[0] not in data['repositories'][reponame]:
                        data['repositories'][reponame][keywordinfo[0]] = set()
                    if len(items) == 1:
                        # repository unmask
                        data['repositories'][reponame][keywordinfo[0]].add('*')
                    elif "*" not in \
                        data['repositories'][reponame][keywordinfo[0]]:

                        item = [x for x in items if not x.startswith("repo=")]
                        data['repositories'][reponame][keywordinfo[0]].add(
                            item[0])
                elif len(items) == 2:
                    # it's going to be a faulty line!!??
                    # can't have two items and no repo=
                    continue
                else:
                    # add keyword to packages
                    if keywordinfo[0] not in data['packages']:
                        data['packages'][keywordinfo[0]] = set()
                    data['packages'][keywordinfo[0]].add(items[0])

        # merge universal keywords
        etpConst['keywords'].clear()
        etpConst['keywords'].update(etpSys['keywords'])
        for keyword in data['universal']:
            etpConst['keywords'].add(keyword)

        return data


    def _unmask_parser(self):
        """
        Parser returning package unmasking metadata read from
        package.unmask file.
        This file contains package unmask directives, allowing
        to enable experimental or *secret* packages.

        @return: parsed metadata
        @rtype: dict
        """
        self.validate_entropy_cache(self.__setting_files['unmask'],
            self.__mtime_files['unmask_mtime'])
        return self.__generic_parser(self.__setting_files['unmask'])

    def _mask_parser(self):
        """
        Parser returning package masking metadata read from
        package.mask file.
        This file contains package mask directives, allowing
        to disable experimental or *secret* packages.

        @return: parsed metadata
        @rtype: dict
        """
        self.validate_entropy_cache(self.__setting_files['mask'],
            self.__mtime_files['mask_mtime'])
        return self.__generic_parser(self.__setting_files['mask'])

    def _satisfied_parser(self):
        """
        Parser returning package forced satisfaction metadata
        read from package.satisfied file.
        This file contains packages which updates as dependency are
        filtered out.

        @return: parsed metadata
        @rtype: dict
        """
        self.validate_entropy_cache(self.__setting_files['satisfied'],
            self.__mtime_files['satisfied_mtime'])
        return self.__generic_parser(self.__setting_files['satisfied'])

    def _system_mask_parser(self):
        """
        Parser returning system packages mask metadata read from
        package.system_mask file.
        This file contains packages that should be always kept
        installed, extending the already defined (in repository database)
        set of atoms.

        @return: parsed metadata
        @rtype: dict
        """
        self.validate_entropy_cache(self.__setting_files['system_mask'],
            self.__mtime_files['system_mask_mtime'])
        return self.__generic_parser(self.__setting_files['system_mask'])

    def _license_mask_parser(self):
        """
        Parser returning packages masked by license metadata read from
        license.mask file.
        Packages shipped with licenses listed there will be masked.

        @return: parsed metadata
        @rtype: dict
        """
        self.validate_entropy_cache(self.__setting_files['license_mask'],
            self.__mtime_files['license_mask_mtime'])
        return self.__generic_parser(self.__setting_files['license_mask'])

    def _license_accept_parser(self):
        """
        Parser returning packages unmasked by license metadata read from
        license.mask file.
        Packages shipped with licenses listed there will be unmasked.

        @return: parsed metadata
        @rtype: dict
        """
        self.validate_entropy_cache(self.__setting_files['license_accept'],
            self.__mtime_files['license_accept_mtime'])
        return self.__generic_parser(self.__setting_files['license_accept'])

    def _system_package_sets_parser(self):
        """
        Parser returning system defined package sets read from
        /etc/entropy/packages/sets.

        @return: parsed metadata
        @rtype: dict
        """
        data = {}
        for set_name in self.__setting_files['system_package_sets']:
            set_filepath = self.__setting_files['system_package_sets'][set_name]
            set_elements = self.entropyTools.extract_packages_from_set_file(
                set_filepath)
            if set_elements:
                data[set_name] = set_elements.copy()
        return data

    def _system_dirs_parser(self):
        """
        Parser returning directories considered part of the base system.

        @return: parsed metadata
        @rtype: dict
        """
        return self.__generic_parser(self.__setting_files['system_dirs'])

    def _system_dirs_mask_parser(self):
        """
        Parser returning directories NOT considered part of the base system.
        Settings here overlay system_dirs_parser.

        @return: parsed metadata
        @rtype: dict
        """
        return self.__generic_parser(self.__setting_files['system_dirs_mask'])

    def _broken_syms_parser(self):
        """
        Parser returning a list of shared objects symbols that can be used by
        QA tools to scan the filesystem or a subset of it.

        @return: parsed metadata
        @rtype: dict
        """
        return self.__generic_parser(self.__setting_files['broken_syms'])

    def _broken_libs_mask_parser(self):
        """
        Parser returning a list of broken shared libraries which are
        always considered sane.

        @return: parsed metadata
        @rtype: dict
        """
        return self.__generic_parser(self.__setting_files['broken_libs_mask'])

    def _hw_hash_parser(self):
        """
        Hardware hash metadata parser and generator. It returns a theorically
        unique SHA256 hash bound to the computer running this Framework.

        @return: string containing SHA256 hexdigest
        @rtype: string
        """
        hw_hash_file = self.__setting_files['hw_hash']
        if os.access(hw_hash_file, os.R_OK) and os.path.isfile(hw_hash_file):
            hash_f = open(hw_hash_file, "r")
            hash_data = hash_f.readline().strip()
            hash_f.close()
            return hash_data

        hash_file_dir = os.path.dirname(hw_hash_file)
        hw_hash_exec = etpConst['etp_hw_hash_gen']
        if os.access(hash_file_dir, os.W_OK) and \
            os.access(hw_hash_exec, os.X_OK | os.R_OK) and \
            os.path.isfile(hw_hash_exec):

            pipe = os.popen('{ ' + hw_hash_exec + '; } 2>&1', 'r')
            hash_data = pipe.read().strip()
            sts = pipe.close()
            if sts is not None:
                return None
            hash_f = open(hw_hash_file, "w")
            hash_f.write(hash_data)
            hash_f.flush()
            hash_f.close()
            return hash_data

    def _system_rev_symlinks_parser(self):
        """
        Parser returning important system symlinks mapping. For example:
            {'/usr/lib': ['/usr/lib64']}
        Useful for reverse matching files belonging to packages.

        @return: dict containing the mapping
        @rtype: dict
        """
        setting_file = self.__setting_files['system_rev_symlinks']
        raw_data = self.__generic_parser(setting_file)
        data = {}
        for line in raw_data:
            line = line.split()
            if len(line) < 2:
                continue
            data[line[0]] = frozenset(line[1:])
        return data

    def _socket_service_parser(self):
        """
        Parses socket service configuration file.
        This file contains information about Entropy remote service ports
        and SSL.

        @return: parsed metadata
        @rtype: dict
        """

        data = etpConst['socket_service'].copy()

        sock_conf = self.__setting_files['socket_service']
        if not (os.path.isfile(sock_conf) and \
            os.access(sock_conf, os.R_OK)):
            return data

        socket_f = open(sock_conf, "r")
        socketconf = [x.strip() for x in socket_f.readlines()  if \
            x.strip() and not x.strip().startswith("#")]
        socket_f.close()

        for line in socketconf:

            split_line = line.split("|")
            split_line_len = len(split_line)

            if line.startswith("listen|") and (split_line_len > 1):

                item = split_line[1].strip()
                if item:
                    data['hostname'] = item

            elif line.startswith("listen-port|") and \
                (split_line_len > 1):

                item = split_line[1].strip()
                try:
                    item = int(item)
                    data['port'] = item
                except ValueError:
                    continue

            elif line.startswith("listen-timeout|") and \
                (split_line_len > 1):

                item = split_line[1].strip()
                try:
                    item = int(item)
                    data['timeout'] = item
                except ValueError:
                    continue

            elif line.startswith("listen-threads|") and \
                (split_line_len > 1):

                item = split_line[1].strip()
                try:
                    item = int(item)
                    data['threads'] = item
                except ValueError:
                    continue

            elif line.startswith("session-ttl|") and \
                (split_line_len > 1):

                item = split_line[1].strip()
                try:
                    item = int(item)
                    data['session_ttl'] = item
                except ValueError:
                    continue

            elif line.startswith("max-connections|") and \
                (split_line_len > 1):

                item = split_line[1].strip()
                try:
                    item = int(item)
                    data['max_connections'] = item
                except ValueError:
                    continue

            elif line.startswith("ssl-port|") and \
                (split_line_len > 1):

                item = split_line[1].strip()
                try:
                    item = int(item)
                    data['ssl_port'] = item
                except ValueError:
                    continue

            elif line.startswith("disabled-commands|") and \
                (split_line_len > 1):

                disabled_cmds = split_line[1].strip().split()
                for disabled_cmd in disabled_cmds:
                    data['disabled_cmds'].add(disabled_cmd)

            elif line.startswith("ip-blacklist|") and \
                (split_line_len > 1):

                ips_blacklist = split_line[1].strip().split()
                for ip_blacklist in ips_blacklist:
                    data['ip_blacklist'].add(ip_blacklist)

        return data

    def _system_parser(self):

        """
        Parses Entropy system configuration file.

        @return: parsed metadata
        @rtype: dict
        """

        data = {
            'proxy': etpConst['proxy'].copy(),
            'name': etpConst['systemname'],
            'log_level': etpConst['entropyloglevel'],
            'spm_backend': None,
        }

        etp_conf = self.__setting_files['system']
        if not (os.path.isfile(etp_conf) and \
            os.access(etp_conf, os.R_OK)):
            return data

        const_secure_config_file(etp_conf)
        entropy_f = open(etp_conf, "r")
        entropyconf = [x.strip() for x in entropy_f.readlines()  if \
            x.strip() and not x.strip().startswith("#")]
        entropy_f.close()

        for line in entropyconf:

            split_line = line.split("|")
            split_line_len = len(split_line)

            if line.startswith("loglevel|") and \
                (len(line.split("loglevel|")) == 2):

                loglevel = line.split("loglevel|")[1]
                try:
                    loglevel = int(loglevel)
                except ValueError:
                    pass
                if (loglevel > -1) and (loglevel < 3):
                    data['log_level'] = loglevel

            elif line.startswith("ftp-proxy|") and \
                (split_line_len == 2):

                ftpproxy = split_line[1].strip().split()
                if ftpproxy:
                    data['proxy']['ftp'] = ftpproxy[-1]

            elif line.startswith("http-proxy|") and \
                (split_line_len == 2):

                httpproxy = split_line[1].strip().split()
                if httpproxy:
                    data['proxy']['http'] = httpproxy[-1]

            elif line.startswith("proxy-username|") and \
                (split_line_len == 2):

                httpproxy = split_line[1].strip().split()
                if httpproxy:
                    data['proxy']['username'] = httpproxy[-1]

            elif line.startswith("proxy-password|") and \
                (split_line_len == 2):

                httpproxy = split_line[1].strip().split()
                if httpproxy:
                    data['proxy']['password'] = httpproxy[-1]

            elif line.startswith("system-name|") and \
                (split_line_len == 2):

                data['name'] = split_line[1].strip()

            elif line.startswith("spm-backend|") and \
                (split_line_len == 2):

                data['spm_backend'] = split_line[1].strip()

            elif line.startswith("nice-level|") and \
                (split_line_len == 2):

                mylevel = split_line[1].strip()
                try:
                    mylevel = int(mylevel)
                    if (mylevel >= -19) and (mylevel <= 19):
                        const_set_nice_level(mylevel)
                except (ValueError,):
                    continue

        return data

    def _analyze_client_repo_string(self, repostring, branch = None,
        product = None):
        """
        Extract repository information from the provided repository string,
        usually contained in the repository settings file, repositories.conf.

        @param repostring: valid repository identifier
        @type repostring: string
        @rtype: tuple (string, dict)
        @return: tuple composed by (repository identifier, extracted repository
            metadata)
        """

        if branch == None:
            branch = etpConst['branch']
        if product == None:
            product = etpConst['product']

        reponame = repostring.split("|")[1].strip()
        repodesc = repostring.split("|")[2].strip()
        repopackages = repostring.split("|")[3].strip()
        repodatabase = repostring.split("|")[4].strip()

        eapi3_uri = None
        eapi3_port = etpConst['socket_service']['port']
        eapi3_ssl_port = etpConst['socket_service']['ssl_port']
        eapi3_formatcolon = repodatabase.rfind("#")

        # Support for custom EAPI3 ports
        if eapi3_formatcolon != -1:
            try:
                ports = repodatabase[eapi3_formatcolon+1:].split(",")
                if ports:
                    eapi3_port = int(ports[0])
                if len(ports) > 1:
                    eapi3_ssl_port = int(ports[1])
            except (ValueError, IndexError,):
                eapi3_port = etpConst['socket_service']['port']
                eapi3_ssl_port = etpConst['socket_service']['ssl_port']
            repodatabase = repodatabase[:eapi3_formatcolon]

        # Support for custom database file compression
        dbformat = etpConst['etpdatabasefileformat']
        dbformatcolon = repodatabase.rfind("#")
        if dbformatcolon != -1:
            if dbformat in etpConst['etpdatabasesupportedcformats']:
                try:
                    dbformat = repodatabase[dbformatcolon+1:]
                except (IndexError, ValueError, TypeError,):
                    pass
            repodatabase = repodatabase[:dbformatcolon]

        # Support for custom EAPI3 service URI
        eapi3_uricolon = repodatabase.rfind(",")
        if eapi3_uricolon != -1:

            found_eapi3_uri = repodatabase[eapi3_uricolon+1:]
            if found_eapi3_uri:
                eapi3_uri = found_eapi3_uri
            repodatabase = repodatabase[:eapi3_uricolon]

        mydata = {}
        mydata['repoid'] = reponame
        mydata['service_port'] = eapi3_port
        mydata['ssl_service_port'] = eapi3_ssl_port

        if not repodatabase.endswith("file://") and (eapi3_uri is None):
            try:
                # try to cope with the fact that no specific EAPI3 URI has been
                # provided
                eapi3_uri = repodatabase.split("/")[2]
            except IndexError:
                eapi3_uri = None
        mydata['service_uri'] = eapi3_uri
        mydata['description'] = repodesc
        mydata['packages'] = []
        mydata['plain_packages'] = []

        mydata['dbpath'] = etpConst['etpdatabaseclientdir'] + os.path.sep + \
            reponame + os.path.sep + product + os.path.sep + \
            etpConst['currentarch'] + os.path.sep + branch

        mydata['dbcformat'] = dbformat
        if not dbformat in etpConst['etpdatabasesupportedcformats']:
            mydata['dbcformat'] = etpConst['etpdatabasesupportedcformats'][0]

        mydata['plain_database'] = repodatabase

        mydata['database'] = repodatabase + os.path.sep + product + \
            os.path.sep + reponame + "/database/" + etpConst['currentarch'] + \
            os.path.sep + branch

        mydata['notice_board'] = mydata['database'] + os.path.sep + \
            etpConst['rss-notice-board']

        mydata['local_notice_board'] = mydata['dbpath'] + os.path.sep + \
            etpConst['rss-notice-board']

        mydata['local_notice_board_userdata'] = mydata['dbpath'] + \
            os.path.sep + etpConst['rss-notice-board-userdata']

        mydata['dbrevision'] = "0"
        dbrevision_file = os.path.join(mydata['dbpath'],
            etpConst['etpdatabaserevisionfile'])
        if os.path.isfile(dbrevision_file) and \
            os.access(dbrevision_file, os.R_OK):
            with open(dbrevision_file, "r") as dbrev_f:
                mydata['dbrevision'] = dbrev_f.readline().strip()

        # setup GPG key path
        mydata['gpg_pubkey'] = mydata['dbpath'] + os.path.sep + \
            etpConst['etpdatabasegpgfile']

        # setup script paths
        mydata['post_branch_hop_script'] = mydata['dbpath'] + os.path.sep + \
            etpConst['etp_post_branch_hop_script']
        mydata['post_branch_upgrade_script'] = mydata['dbpath'] + \
            os.path.sep + etpConst['etp_post_branch_upgrade_script']
        mydata['post_repo_update_script'] = mydata['dbpath'] + os.path.sep + \
            etpConst['etp_post_repo_update_script']

        # initialize CONFIG_PROTECT
        # will be filled the first time the db will be opened
        mydata['configprotect'] = None
        mydata['configprotectmask'] = None
        repopackages = [x.strip() for x in repopackages.split() if x.strip()]
        repopackages = [x for x in repopackages if (x.startswith('http://') or \
            x.startswith('ftp://') or x.startswith('file://'))]

        for repo_package in repopackages:
            try:
                repo_package = str(repo_package)
            except (UnicodeDecodeError, UnicodeEncodeError,):
                continue
            mydata['plain_packages'].append(repo_package)
            mydata['packages'].append(
                repo_package + os.path.sep + product + os.path.sep + reponame)

        return reponame, mydata

    def _repositories_parser(self):

        """
        Setup Entropy Client repository settings reading them from
        the relative config file specified in etpConst['repositoriesconf']

        @return: parsed metadata
        @rtype: dict
        """

        data = {
            'available': {},
            'excluded': {},
            'order': [],
            'product': etpConst['product'],
            'branch': etpConst['branch'],
            'default_repository': etpConst['officialrepositoryid'],
            'transfer_limit': etpConst['downloadspeedlimit'],
            'timeout': etpConst['default_download_timeout'],
            'security_advisories_url': etpConst['securityurl'],
            'developer_repo': False,
        }

        repo_conf = etpConst['repositoriesconf']
        if not (os.path.isfile(repo_conf) and os.access(repo_conf, os.R_OK)):
            return data

        repo_f = open(repo_conf, "r")
        repositoriesconf = [x.strip() for x in repo_f.readlines() if x.strip()]
        repo_f.close()

        # setup product and branch first
        for line in repositoriesconf:

            split_line = line.split("|")
            split_line_len = len(split_line)

            if (line.find("product|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                data['product'] = split_line[1]

            elif (line.find("branch|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                branch = split_line[1].strip()
                data['branch'] = branch
                branch_dir = os.path.join(etpConst['packagesbindir'], branch)
                if not os.path.isdir(branch_dir):
                    try:
                        os.makedirs(branch_dir, 0o775)
                        const_setup_perms(branch_dir, etpConst['entropygid'])
                    except (OSError, IOError,):
                        continue

        repoids = set()
        for line in repositoriesconf:

            split_line = line.split("|")
            split_line_len = len(split_line)

            # populate data['available']
            if (line.find("repository|") != -1) and (split_line_len == 5):

                excluded = False
                my_repodata = data['available']
                if line.startswith("##"):
                    continue
                elif line.startswith("#"):
                    excluded = True
                    my_repodata = data['excluded']
                    line = line[1:]

                reponame, repodata = self._analyze_client_repo_string(line,
                    data['branch'], data['product'])
                repoids.add(reponame)
                if reponame in my_repodata:

                    my_repodata[reponame]['plain_packages'].extend(
                        repodata['plain_packages'])
                    my_repodata[reponame]['packages'].extend(
                        repodata['packages'])

                    if (not my_repodata[reponame]['plain_database']) and \
                        repodata['plain_database']:

                        my_repodata[reponame]['plain_database'] = \
                            repodata['plain_database']
                        my_repodata[reponame]['database'] = \
                            repodata['database']
                        my_repodata[reponame]['dbrevision'] = \
                            repodata['dbrevision']
                        my_repodata[reponame]['dbcformat'] = \
                            repodata['dbcformat']
                else:

                    my_repodata[reponame] = repodata.copy()
                    if not excluded:
                        data['order'].append(reponame)

            elif (line.find("officialrepositoryid|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                officialreponame = split_line[1]
                data['default_repository'] = officialreponame

            elif (line.find("developer-repo|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                dev_repo = split_line[1]
                if dev_repo in ("enable", "enabled", "true", "1", "yes",):
                    data['developer_repo'] = True

            elif (line.find("downloadspeedlimit|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                try:
                    myval = int(split_line[1])
                    if myval > 0:
                        data['transfer_limit'] = myval
                    else:
                        data['transfer_limit'] = None
                except (ValueError, IndexError,):
                    data['transfer_limit'] = None

            elif (line.find("downloadtimeout|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                try:
                    myval = int(split_line[1])
                    data['timeout'] = myval
                except (ValueError, IndexError,):
                    continue

            elif (line.find("securityurl|") != -1) and \
                (not line.startswith("#")) and (split_line_len == 2):

                try:
                    data['security_advisories_url'] = split_line[1]
                except (IndexError, ValueError, TypeError,):
                    continue

        try:
            tx_limit = int(os.getenv("ETP_DOWNLOAD_KB"))
        except (ValueError, TypeError,):
            tx_limit = None
        if tx_limit is not None:
            data['transfer_limit'] = tx_limit

        # validate using mtime
        dmp_path = etpConst['dumpstoragedir']
        for repoid in repoids:
            if repoid in data['available']:
                repo_data = data['available'][repoid]
            elif repoid in data['excluded']:
                repo_data = data['excluded'][repoid]
            else:
                continue

            repo_db_path = os.path.join(repo_data['dbpath'],
                etpConst['etpdatabasefile'])
            repo_mtime_fn = "%s_%s_%s.mtime" % (repoid, data['branch'],
                data['product'],)

            repo_db_path_mtime = os.path.join(dmp_path, repo_mtime_fn)
            if os.path.isfile(repo_db_path) and \
                os.access(repo_db_path, os.R_OK):
                self.validate_entropy_cache(repo_db_path, repo_db_path_mtime,
                    repoid = repoid)

        return data

    def _clear_repository_cache(self, repoid = None):
        """
        Internal method, go away!
        """
        self.__cacher.discard()
        for key, value in EntropyCacher.CACHE_IDS.items():
            if key == "db_match":
                continue
            EntropyCacher.clear_cache_item(value)

        if repoid is not None:
            EntropyCacher.clear_cache_item("%s/%s%s/" % (
                EntropyCacher.CACHE_IDS['db_match'],
                    etpConst['dbnamerepoprefix'], repoid,))

    def __generic_parser(self, filepath):
        """
        Internal method. This is the generic file parser here.

        @param filepath: valid path
        @type filepath: string
        @return: raw text extracted from file
        @rtype: list
        """
        return self.entropyTools.generic_file_content_parser(filepath)

    def __remove_repo_cache(self, repoid = None):
        """
        Internal method. Remove repository cache, because not valid anymore.

        @keyword repoid: repository identifier or None
        @type repoid: string or None
        @return: None
        @rtype: None
        """
        if os.path.isdir(etpConst['dumpstoragedir']):
            if repoid:
                self._clear_repository_cache(repoid = repoid)
                return
            for repoid in self['repositories']['order']:
                self._clear_repository_cache(repoid = repoid)
        else:
            try:
                os.makedirs(etpConst['dumpstoragedir'])
            except IOError as e:
                if e.errno == 30: # readonly filesystem
                    etpUi['pretend'] = True
                return
            except OSError:
                return

    def __save_file_mtime(self, toread, tosaveinto):
        """
        Internal method. Save mtime of a file to another file.

        @param toread: file path to read
        @type toread: string
        @param tosaveinto: path where to save retrieved mtime information
        @type tosaveinto: string
        @return: None
        @rtype: None
        """
        if not os.path.isfile(toread):
            currmtime = 0.0
        else:
            currmtime = os.path.getmtime(toread)

        if not os.path.isdir(etpConst['dumpstoragedir']):
            try:
                os.makedirs(etpConst['dumpstoragedir'], 0o775)
                const_setup_perms(etpConst['dumpstoragedir'],
                    etpConst['entropygid'])
            except IOError as e:
                if e.errno == 30: # readonly filesystem
                    etpUi['pretend'] = True
                return
            except (OSError,) as e:
                # unable to create the storage directory
                # useless to continue
                return

        try:
            mtime_f = open(tosaveinto, "w")
        except IOError as e: # unable to write?
            if e.errno == 30: # readonly filesystem
                etpUi['pretend'] = True
            return
        else:
            mtime_f.write(str(currmtime))
            mtime_f.flush()
            mtime_f.close()
            os.chmod(tosaveinto, 0o664)
            if etpConst['entropygid'] is not None:
                os.chown(tosaveinto, 0, etpConst['entropygid'])


    def validate_entropy_cache(self, settingfile, mtimefile, repoid = None):
        """
        Internal method. Validates Entropy Cache based on a setting file
        and its stored (cache bound) mtime.

        @param settingfile: path of the setting file
        @type settingfile: string
        @param mtimefile: path where to save retrieved mtime information
        @type mtimefile: string
        @keyword repoid: repository identifier or None
        @type repoid: string or None
        @return: None
        @rtype: None
        """

        def revalidate():
            try:
                self.__remove_repo_cache(repoid = repoid)
                self.__save_file_mtime(settingfile, mtimefile)
            except (OSError, IOError):
                return

        # handle on-disk cache validation
        # in this case, repositories cache
        # if file is changed, we must destroy cache
        if not os.path.isfile(mtimefile):
            # we can't know if it has been updated
            # remove repositories caches
            revalidate()
            return

        # check mtime
        try:
            with open(mtimefile, "r") as mtime_f:
                mtime = str(mtime_f.readline().strip())
        except (OSError, IOError,):
            mtime = "0.0"

        try:
            currmtime = str(os.path.getmtime(settingfile))
        except (OSError, IOError,):
            currmtime = "0.0"

        if mtime != currmtime:
            revalidate()
