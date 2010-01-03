# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Framework constants module}.

    This module contains all the Entropy constants used all around
    the "entropy" package.

    Some of the constants in this module are used as "default" for
    the SystemSettings interface. So, make sure to read the documentation
    of SystemSettings in the "entropy.core" module.

    Even if possible, etpConst, etpUi, and etpSys objects
    *SHOULD* be I{never ever modified manually}. This freedom could change
    in future, so, if you want to produce a stable code, DON'T do that at all!

    Basic Entropy constants handling functions are available in this module
    and are all prefixed with "I{const_*}" or "I{initconfig_*}".
    If you are writing a third party application, you should always try
    to avoid to deal directly with functions here unless specified otherwise.
    In fact, usually these here are wrapper in upper-level modules
    (entropy.client, entropy.server, entropy.services).


"""
import sys
import os
import stat
import errno
import fcntl
import signal
import gzip
import bz2
from entropy.i18n import _


# ETP_ARCH_CONST setup
# add more arches here
ETP_ARCH_MAP = {
    ("i386", "i486", "i586", "i686",): "x86",
    ("x86_64",): "amd64",
    ("sun4u",): None,
    ("ppc",): None,
}
_uname_m = os.uname()[4]
ETP_ARCH_CONST = 'UNKNOWN'
for arches, arch in list(ETP_ARCH_MAP.items()):
    if _uname_m in arches:
        ETP_ARCH_CONST = arch

etpSys = {
    'archs': ['alpha', 'amd64', 'amd64-fbsd', 'arm', 'hppa', 'ia64', 'm68k',
        'mips', 'ppc', 'ppc64', 's390', 'sh', 'sparc', 'sparc-fbsd', 'x86',
        'x86-fbsd'],
    'keywords': set([ETP_ARCH_CONST, "~"+ETP_ARCH_CONST]),
    'api': '3',
    'arch': ETP_ARCH_CONST,
    'rootdir': "",
    'serverside': False,
    'unittest': False,
}

etpUi = {
    'debug': False,
    'quiet': False,
    'verbose': False,
    'ask': False,
    'pretend': False,
    'mute': False,
    'nolog': False,
    'clean': False,
    'warn': True,
}
if ("--debug" in sys.argv) or os.getenv("ETP_DEBUG"):
    etpUi['debug'] = True
if os.getenv('ETP_MUTE'):
    etpUi['mute'] = True

etpConst = {}

def initconfig_entropy_constants(rootdir):

    """
    Main constants configurators, this is the only function that you should
    call from the outside, anytime you want. it will reset all the variables
    excluding those backed up previously.

    @param rootdir: current root directory, if any, or ""
    @type rootdir: string
    @rtype: None
    @return: None
    @raise AttributeError: when specified rootdir is not a directory
    """

    if rootdir and not os.path.isdir(rootdir):
        raise AttributeError("not a valid chroot.")

    # set env ROOT
    # this way it doesn't need to be set around the code
    os.environ['ROOT'] = rootdir + os.path.sep

    # save backed up settings
    if 'backed_up' in etpConst:
        backed_up_settings = etpConst.pop('backed_up')
    else:
        backed_up_settings = {}

    const_default_settings(rootdir)
    const_read_entropy_release()
    const_create_working_dirs()
    const_setup_entropy_pid()
    const_configure_lock_paths()

    # reflow back settings
    etpConst.update(backed_up_settings)
    etpConst['backed_up'] = backed_up_settings.copy()

    # try to set proper permissions for /etc/entropy (at least group)
    # /etc/entropy should be always writeable by "entropy" group !
    # DO NOT FRIGGIN REMOVE
    const_setup_perms(etpConst['confdir'], etpConst['entropygid'],
        recursion = False)

    if sys.excepthook is sys.__excepthook__:
        sys.excepthook = __const_handle_exception

def const_default_settings(rootdir):

    """
    Initialization of all the Entropy base settings.

    @param rootdir: current root directory, if any, or ""
    @type rootdir: string
    @rtype: None
    @return: None
    """

    default_etp_dir = os.getenv('DEV_ETP_VAR_DIR', rootdir+"/var/lib/entropy")
    default_etp_tmpdir = "/tmp"
    default_etp_repodir = "/packages/"+ETP_ARCH_CONST
    default_etp_portdir = rootdir+"/usr/portage"
    default_etp_distfilesdir = "/distfiles"
    default_etp_dbdir = "/database/"+ETP_ARCH_CONST
    default_etp_dbfile = "packages.db"
    default_etp_dbclientfile = "equo.db"
    default_etp_client_repodir = "/client"
    default_etp_triggersdir = "/triggers/"+ETP_ARCH_CONST
    default_etp_smartappsdir = "/smartapps/"+ETP_ARCH_CONST
    default_etp_smartpackagesdir = "/smartpackages/"+ETP_ARCH_CONST
    default_etp_cachesdir = "/caches/"
    default_etp_securitydir = "/glsa/"
    default_etp_setsdirname = "sets"
    default_etp_setsdir = "/%s/" % (default_etp_setsdirname,)
    default_etp_logdir = default_etp_dir+"/"+"logs"
    default_etp_confdir = os.getenv('DEV_ETP_ETC_DIR', rootdir+"/etc/entropy")
    default_etp_packagesdir = default_etp_confdir+"/packages"
    default_etp_ugc_confdir = default_etp_confdir+"/ugc"
    default_etp_syslogdir = os.getenv('DEV_ETP_LOG_DIR',
        rootdir+"/var/log/entropy/")
    default_etp_vardir = os.getenv('DEV_ETP_TMP_DIR',
        rootdir+"/var/tmp/entropy")

    cmdline = []
    cmdline_file = "/proc/cmdline"
    if os.access(cmdline_file, os.R_OK) and os.path.isfile(cmdline_file):
        with open(cmdline_file, "r") as cmdline_f:
            cmdline = cmdline_f.readline().strip().split()

    etpConst.clear()
    my_const = {
        'logging': {
            'normal_loglevel_id': 1,
            'verbose_loglevel_id': 2,
        },
        'server_repositories': {},
        'community': {
            'mode': False,
        },
        'cmdline': cmdline,
        'backed_up': {},
        # entropy default installation directory
        'installdir': '/usr/lib/entropy',
        # etpConst['packagestmpdir'] --> temp directory
        'packagestmpdir': default_etp_dir+default_etp_tmpdir,
        # etpConst['packagesbindir'] --> repository
        # where the packages will be stored
        # by clients: to query if a package has been already downloaded
        # by servers or rsync mirrors: to store already
        #   uploaded packages to the main rsync server
        'packagesbindir': default_etp_dir+default_etp_repodir,
        # etpConst['smartappsdir'] location where smart apps files are places
        'smartappsdir': default_etp_dir+default_etp_smartappsdir,
        # etpConst['smartpackagesdir'] location where
        # smart packages files are places
        'smartpackagesdir': default_etp_dir+default_etp_smartpackagesdir,
        # etpConst['triggersdir'] location where external triggers are placed
        'triggersdir': default_etp_dir+default_etp_triggersdir,
        # directory where is stored our local portage tree
        'portagetreedir': default_etp_portdir,
        # directory where our sources are downloaded
        'distfilesdir': default_etp_portdir+default_etp_distfilesdir,
        # directory where entropy stores its configuration
        'confdir': default_etp_confdir,
        # same as above + /packages
        'confpackagesdir': default_etp_packagesdir,
        # system package sets dir
        'confsetsdir': default_etp_packagesdir+default_etp_setsdir,
        # just the dirname
        'confsetsdirname': default_etp_setsdirname,
        # entropy.conf file
        'entropyconf': default_etp_confdir+"/entropy.conf",
        # repositories.conf file
        'repositoriesconf': default_etp_confdir+"/repositories.conf",
        # server.conf file (generic server side settings)
        'serverconf': default_etp_confdir+"/server.conf",
        # client.conf file (generic entropy client side settings)
        'clientconf': default_etp_confdir+"/client.conf",
        # socket.conf file
        'socketconf': default_etp_confdir+"/socket.conf",
        # user by client interfaces
        'packagesrelativepath': "packages/"+ETP_ARCH_CONST+"/",

        'entropyworkdir': default_etp_dir, # Entropy workdir
        # Entropy unpack directory
        'entropyunpackdir': default_etp_vardir,
        # Entropy packages image directory
        'entropyimagerelativepath': "image",
        # Gentoo xpak temp directory path
        'entropyxpakrelativepath': "xpak",
        # Gentoo xpak metadata directory path
        'entropyxpakdatarelativepath': "data",
        # Gentoo xpak metadata file name
        'entropyxpakfilename': "metadata.xpak",

        # entropy repository database upload timestamp
        'etpdatabasetimestampfile': default_etp_dbfile+".timestamp",
        # entropy repository database owned (in repo) package files
        'etpdatabasepkglist': default_etp_dbfile+".pkglist",
        'etpdatabaseconflictingtaggedfile': default_etp_dbfile + \
            ".conflicting_tagged",
        # file containing a list of packages that are strictly
        # required by the repository, thus forced
        'etpdatabasesytemmaskfile': default_etp_dbfile+".system_mask",
        'etpdatabasemaskfile': default_etp_dbfile+".mask",
        'etpdatabasekeywordsfile': default_etp_dbfile+".keywords",
        'etpdatabaseupdatefile': default_etp_dbfile+".repo_updates",
        'etpdatabaselicwhitelistfile': default_etp_dbfile+".lic_whitelist",
        'etpdatabasecriticalfile': default_etp_dbfile+".critical",
        # the local/remote database revision file
        'etpdatabaserevisionfile': default_etp_dbfile+".revision",
        # missing dependencies black list file
        'etpdatabasemissingdepsblfile': default_etp_dbfile + \
            ".missing_deps_blacklist",
        # compressed file that contains all the "meta"
        # files in a repository dir
        'etpdatabasemetafilesfile': default_etp_dbfile+".meta",
        # file that contains a list of the "meta"
        # files not available in the repository
        'etpdatabasemetafilesnotfound': default_etp_dbfile+".meta_notfound",
        # database file checksum
        'etpdatabasehashfile': default_etp_dbfile+".md5",

        # the remote database lock file
        'etpdatabaselockfile': default_etp_dbfile+".lock",
        # the remote database lock file
        'etpdatabaseeapi3lockfile': default_etp_dbfile+".eapi3_lock",
        # the remote database download lock file
        'etpdatabasedownloadlockfile': default_etp_dbfile+".download.lock",
        'etpdatabasecacertfile': "ca.cert",
        'etpdatabaseservercertfile': "server.cert",
        # repository GPG public key file
        'etpdatabasegpgfile': "signature.asc",
        'etpgpgextension': ".asc",
        # Entropy Client GPG repositories keyring path
        'etpclientgpgdir': default_etp_confdir+"/client-gpg-keys",
        # when this file exists, the database is not synced
        # anymore with the online one
        'etpdatabasetaintfile': default_etp_dbfile+".tainted",

        # Entropy sqlite database file default_etp_dir + \
        #    default_etp_dbdir+"/packages.db"
        'etpdatabasefile': default_etp_dbfile,
        # Entropy sqlite database file (gzipped)
        'etpdatabasefilegzip': default_etp_dbfile+".gz",
        'etpdatabasefilegziphash': default_etp_dbfile+".gz.md5",
        # Entropy sqlite database file (bzipped2)
        'etpdatabasefilebzip2': default_etp_dbfile+".bz2",
        'etpdatabasefilebzip2hash': default_etp_dbfile+".bz2.md5",

        # Entropy sqlite database file (gzipped)
        'etpdatabasefilegziplight': default_etp_dbfile+".light.gz",
        'etpdatabasefilehashgziplight': default_etp_dbfile+".light.gz.md5",
        # Entropy sqlite database file (bzipped2)
        'etpdatabasefilebzip2light': default_etp_dbfile+".light.bz2",
        'etpdatabasefilehashbzip2light': default_etp_dbfile+".light.bz2.md5",

        # Entropy sqlite database dump file (bzipped2)
        'etpdatabasedumpbzip2': default_etp_dbfile+".dump.bz2",
        'etpdatabasedumphashfilebz2': default_etp_dbfile+".dump.bz2.md5",
        # Entropy sqlite database dump file (gzipped)
        'etpdatabasedumpgzip': default_etp_dbfile+".dump.gz",
        'etpdatabasedumphashfilegzip': default_etp_dbfile+".dump.gz.md5",

        # Entropy sqlite database dump file
        'etpdatabasedump': default_etp_dbfile+".dump",

        # Entropy sqlite database dump file (bzipped2) light ver
        'etpdatabasedumplightbzip2': default_etp_dbfile+".dumplight.bz2",
        # Entropy sqlite database dump file (gzipped) light ver
        'etpdatabasedumplightgzip': default_etp_dbfile+".dumplight.gz",
        # Entropy sqlite database dump file, light ver (no content)
        'etpdatabasedumplighthashfilebz2': default_etp_dbfile+".dumplight.bz2.md5",
        'etpdatabasedumplighthashfilegzip': default_etp_dbfile+".dumplight.gz.md5",
        'etpdatabasedumplight': default_etp_dbfile+".dumplight",
        # expiration based server-side packages removal

        'etpdatabaseexpbasedpkgsrm': default_etp_dbfile+".fatscope",

        # Entropy default compressed database format
        'etpdatabasefileformat': "bz2",
        # Entropy compressed databases format support
        'etpdatabasesupportedcformats': ["bz2", "gz"],
        'etpdatabasecompressclasses': {
            "bz2": (bz2.BZ2File, "unpack_bzip2", "etpdatabasefilebzip2",
                "etpdatabasedumpbzip2", "etpdatabasedumphashfilebz2",
                "etpdatabasedumplightbzip2", "etpdatabasedumplighthashfilebz2",
                "etpdatabasefilebzip2light", "etpdatabasefilehashbzip2light",
                "etpdatabasefilebzip2hash",),
            "gz": (gzip.GzipFile, "unpack_gzip", "etpdatabasefilegzip",
                "etpdatabasedumpgzip", "etpdatabasedumphashfilegzip",
                "etpdatabasedumplightgzip", "etpdatabasedumplighthashfilegzip",
                "etpdatabasefilegziplight", "etpdatabasefilehashgziplight",
                "etpdatabasefilegziphash",)
        },
        # Distribution website URL
        'distro_website_url': "http://www.sabayon.org",
        # enable/disable packages RSS feed feature
        'rss-feed': True,
        # default name of the RSS feed
        'rss-name': "packages.rss",
        'rss-light-name': "updates.rss", # light version
        # default URL to the entropy web interface
        # (overridden in reagent.conf)
        'rss-base-url': "http://pkg.sabayon.org/",
        # default URL to the Operating System website
        # (overridden in reagent.conf)
        'rss-website-url': "http://www.sabayon.org/",
        # xml file where will be dumped ServerInterface.rssMessages dictionary
        'rss-dump-name': "rss_database_actions",
        'rss-max-entries': 10000, # maximum rss entries
        'rss-light-max-entries': 300, # max entries for the light version
        'rss-managing-editor': "lxnay@sabayon.org", # updates submitter
        # repository RSS-based notice board content
        'rss-notice-board': "notice.rss",
        # File containing user data related to repository notice board
        'rss-notice-board-userdata': "notice.rss.userdata",

        'packagesetprefix': "@",
        'userpackagesetsid': "__user__",
        'setsconffilename': "sets.conf",
        'cachedumpext': ".dmp",
        'packagesext': ".tbz2",
        'smartappsext': ".esa",
        # Extension of the file that contains the checksum
        # of its releated package file
        'packagesmd5fileext': ".md5",
        'packagessha512fileext': ".sha512",
        'packagessha256fileext': ".sha256",
        'packagessha1fileext': ".sha1",
        # Supported Entropy Client package hashes encodings
        'packagehashes': ("sha1", "sha256", "sha512", "gpg"),
        # Extension of the file that "contains" expiration mtime
        'packagesexpirationfileext': ".expired",
        # number of days after a package will be removed from mirrors
        'packagesexpirationdays': 15,
        # name of the trigger file that would be executed
        # by equo inside triggerTools
        'triggername': "trigger",
        'trigger_sh_interpreter': rootdir+"/usr/sbin/entropy.sh",
        # entropy hardware hash generator executable
        'etp_hw_hash_gen': rootdir+"/usr/bin/entropy_hwgen.sh",
        # entropy client post valid branch migration (equo hop) script name
        'etp_post_branch_hop_script': default_etp_dbfile+".post_branch.sh",
        # entropy client post branch upgrade script
        'etp_post_branch_upgrade_script': default_etp_dbfile+".post_upgrade.sh",
        # previous branch file container
        'etp_previous_branch_file': default_etp_confdir+"/.previous_branch",
        'etp_in_branch_upgrade_file': default_etp_confdir+"/.in_branch_upgrade",
        # entropy client post repository update script (this is executed
        # every time)
        'etp_post_repo_update_script': default_etp_dbfile+".post_update.sh",

        # proxy configuration constants, used system wide
        'proxy': {
            'ftp': os.getenv("FTP_PROXY"),
            'http': os.getenv("HTTP_PROXY"),
            'username': None,
            'password': None
        },
        # Entropy log level (default: 1 - see entropy.conf for more info)
        'entropyloglevel': 1,
        # Entropy Socket Interface log level
        'socketloglevel': 2,
        'spmloglevel': 1,
        # Log dir where ebuilds store their stuff
        'logdir': default_etp_logdir,

        'syslogdir': default_etp_syslogdir, # Entropy system tools log directory
        'entropylogfile': default_etp_syslogdir+"entropy.log",
        'securitylogfile': default_etp_syslogdir+"security.log",
        'equologfile': default_etp_syslogdir+"equo.log",
        'spmlogfile': default_etp_syslogdir+"spm.log",
        'socketlogfile': default_etp_syslogdir+"socket.log",

        'etpdatabaseclientdir': default_etp_dir + default_etp_client_repodir + \
            default_etp_dbdir,
        # path to equo.db - client side database file
        'etpdatabaseclientfilepath': default_etp_dir + \
            default_etp_client_repodir + default_etp_dbdir + os.path.sep + \
            default_etp_dbclientfile,
        # prefix of the name of self.dbname in
        # entropy.db.LocalRepository class for the repositories
        'dbnamerepoprefix': "repo_",
        # prefix of database backups
        'dbbackupprefix': 'etp_backup_',

        # Entropy database API revision
        'etpapi': etpSys['api'],
        # contains the current running architecture
        'currentarch': etpSys['arch'],
        # Entropy supported Archs
        'supportedarchs': etpSys['archs'],

        # default choosen branch (overridden by setting in repositories.conf)
        'branch': "4",
         # default allowed package keywords
        'keywords': etpSys['keywords'].copy(),
        # allow multiple packages in single scope server-side?
        # this makes possible to have multiple versions of packages
        # and handle the removal through expiration (using creation date)
        'expiration_based_scope': False,
        # our official repository name
        'defaultserverrepositoryid': None,
        'officialrepositoryid': "sabayonlinux.org",
        # tag to append to .tbz2 file before entropy database (must be 32bytes)
        'databasestarttag': "|ENTROPY:PROJECT:DB:MAGIC:START|",
        # Entropy resources lock file path
        'pidfile': default_etp_dir+"/entropy.lock",
        'applicationlock': False,
        # option to keep a backup of config files after
        # being overwritten by equo conf update
        'filesbackup': True,
        # option to enable forced installation of critical updates
        'forcedupdates': True,
        # collision protection option, see client.conf for more info
        'collisionprotect': 1,
        # list of user specified CONFIG_PROTECT directories
        # (see Gentoo manual to understand the meaining of this parameter)
        'configprotect': [],
        # list of user specified CONFIG_PROTECT_MASK directories
        'configprotectmask': [],
        # list of user specified configuration files that
        # should be ignored and kept as they are
        'configprotectskip': [],
        # installed database CONFIG_PROTECT directories
        'dbconfigprotect': [],
        # installed database CONFIG_PROTECT_MASK directories
        'dbconfigprotectmask': [],
        # this will be used to show the number of updated
        # files at the end of the processes
        'configprotectcounter': 0,
        # default Entropy release version
        'entropyversion': "1.0",
        # default system name (overidden by entropy.conf settings)
        'systemname': "Sabayon Linux",
        # Product identificator (standard, professional...)
        'product': "standard",
        'errorstatus': default_etp_confdir+"/code",
        'systemroot': rootdir, # default system root
        'uid': os.getuid(), # current running UID
        'entropygid': None,
        'sysgroup': "entropy",
        'defaultumask': 0o22,
        'storeumask': 0o02,
        'gentle_nice': 15,
        'current_nice': 0,
        'default_nice': 0,
        # Default download socket timeout for Entropy Client transceivers
        'default_download_timeout': 20,
        # Entropy package dependencies type identifiers
        'dependency_type_ids': {
            'rdepend_id': 0, # runtime dependencies
            'pdepend_id': 1, # post dependencies
            'mdepend_id': 2, # actually, this is entropy-only
            'bdepend_id': 3, # build dependencies
        },
        'dependency_type_ids_desc': {
            'rdepend_id': _("Runtime dependency"),
            'pdepend_id': _("Post dependency"),
            'mdepend_id': _('Manually added (by staff) dependency'),
            'bdepend_id': _('Build dependency'),
        },

        # entropy client packages download speed limit (in kb/sec)
        'downloadspeedlimit': None,

        # data storage directory, useful to speed up
        # entropy client across multiple issued commands
        'dumpstoragedir': default_etp_dir+default_etp_cachesdir,
        # where GLSAs are stored
        'securitydir': default_etp_dir+default_etp_securitydir,
        'securityurl': "http://community.sabayon.org/security"
            "/security-advisories.tar.bz2",

        'safemodeerrors': {
            'clientdb': 1,
        },
        'safemodereasons': {
            0: _("All fine"),
            1: _("Corrupted Client Repository. Please restore a backup."),
        },

        'misc_counters': {
            'forced_atoms_update_ids': {
                '__idtype__': 1,
                'kde': 1,
            },
        },

        'system_settings_plugins_ids': {
            'client_plugin': "client_plugin",
            'server_plugin': "server_plugin",
            'server_plugin_fatscope': "server_plugin_fatscope",
        },

        'clientserverrepoid': "__system__",
        'clientdbid': "client",
        'serverdbid': "etpdb:",
        'genericdbid': "generic",
        'systemreleasefile': "/etc/sabayon-release",

        # these are constants, for real settings
        # look ad SystemSettings class
        'socket_service': { # here are the constants
            'hostname': "localhost",
            'port': 1026,
            'ssl_port': 1027, # above + 1
            'timeout': 200,
            'forked_requests_timeout': 300,
            'max_command_length': 768000, # bytes
            'threads': 5,
            'session_ttl': 15,
            'default_uid': 0,
            'max_connections': 5,
            'max_connections_per_host': 15,
            'max_connections_per_host_barrier': 8,
            'disabled_cmds': set(),
            'ip_blacklist': set(),
            'ssl_key': default_etp_confdir+"/socket_server.key",
            'ssl_cert': default_etp_confdir+"/socket_server.crt",
            'ssl_ca_cert': default_etp_confdir+"/socket_server.CA.crt",
            'ssl_ca_pkey': default_etp_confdir+"/socket_server.CA.key",
            'answers': {
                # command run
                'ok': const_convert_to_rawstring(chr(0)+"OK"+chr(0)),
                # execution error
                'er': const_convert_to_rawstring(chr(0)+"ER"+chr(1)),
                # not allowed
                'no': const_convert_to_rawstring(chr(0)+"NO"+chr(2)),
                # close connection
                'cl': const_convert_to_rawstring(chr(0)+"CL"+chr(3)),
                # max connections reached
                'mcr': const_convert_to_rawstring(chr(0)+"MCR"+chr(4)),
                # end of size
                'eos': const_convert_to_rawstring(chr(0)),
                # no operation
                'noop': const_convert_to_rawstring(chr(0)+"NOOP"+chr(0)),
            },
        },

        'install_sources': {
            'unknown': 0,
            'user': 1,
            'automatic_dependency': 2,
        },

        'pkg_masking_reasons': {
            0: _('reason not available'),
            1: _('user package.mask'),
            2: _('system keywords'),
            3: _('user package.unmask'),
            4: _('user repo package.keywords (all packages)'),
            5: _('user repo package.keywords'),
            6: _('user package.keywords'),
            7: _('completely masked (by keyword?)'),
            8: _('repository general packages.db.mask'),
            9: _('repository general packages.db.keywords'),
            10: _('user license.mask'),
            11: _('user live unmask'),
            12: _('user live mask'),
        },
        'pkg_masking_reference': {
            'reason_not_avail': 0,
            'user_package_mask': 1,
            'system_keyword': 2,
            'user_package_unmask': 3,
            'user_repo_package_keywords_all': 4,
            'user_repo_package_keywords': 5,
            'user_package_keywords': 6,
            'completely_masked': 7,
            'repository_packages_db_mask': 8,
            'repository_packages_db_keywords': 9,
            'user_license_mask': 10,
            'user_live_unmask': 11,
            'user_live_mask': 12,
        },

        'ugc_doctypes': {
            'comments': 1,
            'bbcode_doc': 2,
            'image': 3,
            'generic_file': 4,
            'youtube_video': 5,
        },
        'ugc_doctypes_description': {
            1: _('Comments'),
            2: _('BBcode Documents'),
            3: _('Images/Screenshots'),
            4: _('Generic Files'),
            5: _('YouTube(tm) Videos'),
        },
        'ugc_doctypes_description_singular': {
            1: _('Comment'),
            2: _('BBcode Document'),
            3: _('Image/Screenshot'),
            4: _('Generic File'),
            5: _('YouTube(tm) Video'),
        },
        'ugc_accessfile': default_etp_ugc_confdir+"/access.xml",
        'ugc_voterange': list(range(1, 6)),

    }

    # set current nice level
    try:
        my_const['current_nice'] = os.nice(0)
    except OSError:
        pass

    etpConst.update(my_const)

def const_set_nice_level(nice_level = 0):
    """
    Change current process scheduler "nice" level.

    @param nice_level: new valid nice level
    @type nice_level: int
    @rtype: int
    @return: current_nice new nice level
    """
    default_nice = etpConst['default_nice']
    current_nice = etpConst['current_nice']
    delta = current_nice - default_nice
    try:
        etpConst['current_nice'] = os.nice(delta*-1+nice_level)
    except OSError:
        pass
    return current_nice

def const_read_entropy_release():
    """
    Read Entropy release file content and fill etpConst['entropyversion']

    @rtype: None
    @return: None
    """
    # handle Entropy Version
    revision_file = "../libraries/revision"
    if not os.path.isfile(revision_file):
        revision_file = os.path.join(etpConst['installdir'],
            'libraries/revision')
    if os.path.isfile(revision_file) and \
        os.access(revision_file, os.R_OK):

        with open(revision_file, "r") as rev_f:
            myrev = rev_f.readline().strip()
            etpConst['entropyversion'] = myrev

def const_pid_exists(pid):
    """
    Determine whether given pid exists.

    @param pid: process id
    @type pid: int
    @return: pid exists? 1; pid does not exist? 0
    @rtype: int
    """
    try:
        os.kill(pid, signal.SIG_DFL)
        return 1
    except OSError as err:
        return err.errno == errno.EPERM

def const_setup_entropy_pid(just_read = False, force_handling = False):

    """
    Setup Entropy pid file, if possible and if UID = 0 (root).
    If the application is run with --no-pid-handling argument,
    this function will have no effect. If just_read is specified,
    this function will only try to read the current pid string in
    the Entropy pid file (etpConst['pidfile']). If any other entropy
    istance is currently owning the contained pid, etpConst['applicationlock']
    becomes True.

    @param just_read: only read the current pid file, if any and if possible
    @type just_read: bool
    @param force_handling: force pid handling even if "--no-pid-handling" is
        given
    @type force_handling: bool
    @rtype: bool
    @return: if pid lock file has been acquired
    """

    if (("--no-pid-handling" in sys.argv) and not force_handling) \
        and not just_read:
        return False

    setup_done = False

    # PID creation
    pid = os.getpid()
    pid_file = etpConst['pidfile']
    if os.path.isfile(pid_file) and os.access(pid_file, os.R_OK):

        try:
            with open(pid_file, "r") as pid_f:
                found_pid = str(pid_f.readline().strip())
        except (IOError, OSError, UnicodeEncodeError, UnicodeDecodeError,):
            found_pid = "0000" # which is always invalid

        try:
            found_pid = int(found_pid)
        except ValueError:
            found_pid = 0

        if found_pid != pid:
            # is found_pid still running ?
            if (found_pid != 0) and const_pid_exists(found_pid):
                etpConst['applicationlock'] = True
            elif (not just_read) and os.access(pid_file, os.W_OK):
                try:
                    with open(pid_file, "w") as pid_f:
                        pid_f.write(str(pid))
                        pid_f.flush()
                except IOError as err:
                    if err.errno != 30: # readonly filesystem
                        raise
                try:
                    const_chmod_entropy_pid()
                except OSError:
                    pass
                setup_done = True

    elif not just_read:

        #if etpConst['uid'] == 0:
        if os.access(os.path.dirname(pid_file), os.W_OK):

            if os.path.exists(pid_file):
                if os.path.islink(pid_file):
                    os.remove(pid_file)
                elif os.path.isdir(pid_file):
                    import shutil
                    shutil.rmtree(pid_file)

            with open(pid_file, "w") as pid_fw:

                try:
                    fcntl.flock(pid_fw.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    pid_fw.write(str(pid))
                    pid_fw.flush()
                except IOError as err:
                    # already locked?
                    if err.errno not in (errno.EACCES, errno.EAGAIN,):
                        raise
                    # lock is being acquired by somebody else
                    # cannot write
                    return False

            try:
                const_chmod_entropy_pid()
            except OSError:
                pass
            setup_done = True

    return setup_done

def const_remove_entropy_pid():
    """
    Remove Entropy pid if function calling pid matches the one stored.
    """
    pid = os.getpid()
    pid_file = etpConst['pidfile']
    if not os.path.lexists(pid_file):
        return True # not found, so removed

    # open file
    try:
        with open(pid_file, "r") as pid_f:
            found_pid = str(pid_f.readline().strip())
    except (IOError, OSError, UnicodeEncodeError, UnicodeDecodeError,):
        found_pid = "0000" # which is always invalid

    try:
        found_pid = int(found_pid)
    except ValueError:
        found_pid = 0

    if (pid != found_pid) and (found_pid != 0):
        # cannot remove, i'm not the owner
        return False

    removed = False
    try:
        # using os.remove for atomicity
        os.remove(pid_file)
        removed = True
    except OSError as err:
        if err.errno not in (errno.ENOENT, errno.EACCES,):
            raise

        if err.errno == errno.EACCES:
            removed = False
        else:
            removed = True

    return removed

def const_secure_config_file(config_file):
    """
    Setup entropy file needing strict permissions, no world readable.

    @param config_file: valid config file path
    @type config_file: string
    @rtype: None
    @return: None
    """
    try:
        mygid = const_get_entropy_gid()
    except KeyError:
        mygid = 0
    try:
        const_setup_file(config_file, mygid, 0o660)
    except (OSError, IOError,):
        pass

def const_chmod_entropy_pid():
    """
    Setup entropy pid file permissions, if possible.

    @return: None
    """
    try:
        mygid = const_get_entropy_gid()
    except KeyError:
        mygid = 0
    const_setup_file(etpConst['pidfile'], mygid, 0o664)

def const_create_working_dirs():

    """
    Setup Entropy directory structure, as much automagically as possible.

    @rtype: None
    @return: None
    """

    # handle pid file
    piddir = os.path.dirname(etpConst['pidfile'])
    if not os.path.exists(piddir) and (etpConst['uid'] == 0):
        os.makedirs(piddir)

    # create tmp dir
    #if not os.path.isdir(xpakpath_dir):
    #    os.makedirs(xpakpath_dir,0775)
    #    const_setup_file(xpakpath_dir, 

    # create user if it doesn't exist
    gid = None
    try:
        gid = const_get_entropy_gid()
    except KeyError:
        if etpConst['uid'] == 0:
            # create group
            # avoid checking cause it's not mandatory for entropy/equo itself
            const_add_entropy_group()
            try:
                gid = const_get_entropy_gid()
            except KeyError:
                pass

    # Create paths
    keys = [x for x in etpConst if const_isstring(etpConst[x])]
    for key in keys:

        if not etpConst[key] or \
        etpConst[key].endswith(".conf") or \
        not os.path.isabs(etpConst[key]) or \
        etpConst[key].endswith(".cfg") or \
        etpConst[key].endswith(".tmp") or \
        etpConst[key].find(".db") != -1 or \
        etpConst[key].find(".log") != -1 or \
        os.path.isdir(etpConst[key]) or \
        not key.endswith("dir"):
            continue

        # allow users to create dirs in custom paths,
        # so don't fail here even if we don't have permissions
        try:
            key_dir = etpConst[key]
            d_paths = []
            while not os.path.isdir(key_dir):
                d_paths.append(key_dir)
                key_dir = os.path.dirname(key_dir)
            d_paths = sorted(d_paths)
            for d_path in d_paths:
                os.mkdir(d_path)
                const_setup_file(d_path, gid, 0o775)
        except (OSError, IOError,):
            pass

    if gid:
        etpConst['entropygid'] = gid
        if not os.path.isdir(etpConst['entropyworkdir']):
            try:
                os.makedirs(etpConst['entropyworkdir'])
            except OSError:
                pass
        w_gid = os.stat(etpConst['entropyworkdir'])[stat.ST_GID]
        if w_gid != gid:
            const_setup_perms(etpConst['entropyworkdir'], gid)

        if not os.path.isdir(etpConst['entropyunpackdir']):
            try:
                os.makedirs(etpConst['entropyunpackdir'])
            except OSError:
                pass
        try:
            w_gid = os.stat(etpConst['entropyunpackdir'])[stat.ST_GID]
            if w_gid != gid:
                if os.path.isdir(etpConst['entropyunpackdir']):
                    const_setup_perms(etpConst['entropyunpackdir'], gid)
        except OSError:
            pass
        # always setup /var/lib/entropy/client permissions
        if not const_islive():
            # aufs/unionfs will start to leak otherwise
            const_setup_perms(etpConst['etpdatabaseclientdir'], gid)

def const_configure_lock_paths():
    """
    Setup Entropy lock file paths.

    @rtype: None
    @return: None
    """
    etpConst['locks'] = {
        'using_resources': os.path.join(etpConst['etpdatabaseclientdir'],
            '.using_resources'),
    }

def const_setup_perms(mydir, gid, f_perms = None, recursion = True):
    """
    Setup permissions and group id (GID) to a directory, recursively.

    @param mydir: valid file path
    @type mydir: string
    @param gid: valid group id (GID)
    @type gid: int
    @keyword f_perms: file permissions in octal type
    @type f_perms: octal
    @keyword recursion: set permissions recursively?
    @type recursion: bool
    @rtype: None
    @return: None
    """

    if gid == None:
        return
    if f_perms is None:
        f_perms = 0o664

    def do_setup_dir(currentdir):
        try:
            cur_gid = os.stat(currentdir)[stat.ST_GID]
            if cur_gid != gid:
                os.chown(currentdir, -1, gid)
            cur_mod = const_get_chmod(currentdir)
            if cur_mod != oct(0o775):
                os.chmod(currentdir, 0o775)
        except OSError:
            pass

    do_setup_dir(mydir)
    if recursion:
        for currentdir, subdirs, files in os.walk(mydir):
            do_setup_dir(currentdir)
            for item in files:
                item = os.path.join(currentdir, item)
                try:
                    const_setup_file(item, gid, f_perms)
                except OSError:
                    pass

def const_setup_file(myfile, gid, chmod):
    """
    Setup file permissions and group id (GID).

    @param myfile: valid file path
    @type myfile: string
    @param gid: valid group id (GID)
    @type gid: int
    @param chmod: permissions
    @type chmod: integer representing an octal
    @rtype: None
    @return: None
    """
    cur_gid = os.stat(myfile)[stat.ST_GID]
    if cur_gid != gid:
        os.chown(myfile, -1, gid)
    const_set_chmod(myfile, chmod)

# you need to convert to int
def const_get_chmod(myfile):
    """
    This function get the current permissions of the specified
    file. If you want to use the returning value with const_set_chmod
    you need to convert it back to int.

    @param myfile: valid file path
    @type myfile: string
    @rtype: integer(8) (octal)
    @return: octal representing permissions
    """
    myst = os.stat(myfile)[stat.ST_MODE]
    return oct(myst & 0o777)

def const_set_chmod(myfile, chmod):
    """
    This function sets specified permissions to a file.
    If they differ from the current ones.

    @param myfile: valid file path
    @type myfile: string
    @param chmod: permissions
    @type chmod: integer representing an octal
    @rtype: None
    @return: None
    """
    cur_mod = const_get_chmod(myfile)
    if cur_mod != oct(chmod):
        os.chmod(myfile, chmod)

def const_get_entropy_gid():
    """
    This function tries to retrieve the "entropy" user group
    GID.

    @rtype: None
    @return: None
    @raise KeyError: when "entropy" system GID is not available
    """
    group_file = etpConst['systemroot']+'/etc/group'
    if not os.path.isfile(group_file):
        raise KeyError

    with open(group_file, "r") as group_f:
        for line in group_f.readlines():
            if line.startswith('%s:' % (etpConst['sysgroup'],)):
                try:
                    gid = int(line.split(":")[2])
                except ValueError:
                    raise KeyError
                return gid
    raise KeyError

def const_add_entropy_group():
    """
    This function looks for an "entropy" user group.
    If not available, it tries to create one.

    @rtype: None
    @return: None
    @raise KeyError: if ${ROOT}/etc/group is not found
    """
    group_file = etpConst['systemroot']+'/etc/group'
    if not os.path.isfile(group_file):
        raise KeyError
    ids = set()

    with open(group_file, "r") as group_f:
        for line in group_f.readlines():
            if line and line.split(":"):
                try:
                    myid = int(line.split(":")[2])
                except ValueError:
                    pass
                ids.add(myid)
        if ids:
            # starting from 1000, get the first free
            new_id = 1000
            while True:
                new_id += 1
                if new_id not in ids:
                    break
        else:
            new_id = 10000

    with open(group_file, "a") as group_fw:
        group_fw.seek(0, 2)
        app_line = "entropy:x:%s:\n" % (new_id,)
        group_fw.write(app_line)
        group_fw.flush()

def const_get_stringtype():
    """
    Return generic string type for usage in isinstance().
    On Python 2.x, it returns basestring while on Python 3.x it returns
    (str, bytes,)
    """
    if sys.hexversion >= 0x3000000:
        return (str, bytes,)
    else:
        return (basestring,)

def const_isstring(obj):
    """
    Return whether obj is a string (unicode or raw).

    @param obj: Python object
    @type obj: Python object
    @return: True, if object is string
    @rtype: bool
    """
    if sys.hexversion >= 0x3000000:
        return isinstance(obj, (str, bytes))
    else:
        return isinstance(obj, basestring)

def const_isunicode(obj):
    """
    Return whether obj is a unicode.

    @param obj: Python object
    @type obj: Python object
    @return: True, if object is unicode
    @rtype: bool
    """
    if sys.hexversion >= 0x3000000:
        return isinstance(obj, str)
    else:
        return isinstance(obj, unicode)

def const_israwstring(obj):
    if sys.hexversion >= 0x3000000:
        return isinstance(obj, bytes)
    else:
        return isinstance(obj, str)

def const_convert_to_unicode(obj, enctype = 'raw_unicode_escape'):
    """
    Convert generic string to unicode format, this function supports both
    Python 2.x and Python 3.x unicode bullshit.

    @param obj: generic string object
    @type obj: string
    @return: unicode string object
    @rtype: unicode object
    """

    # None support
    if obj is None:
        return const_convert_to_unicode("None")

    # int support
    if isinstance(obj, int):
        if sys.hexversion >= 0x3000000:
            return str(obj)
        else:
            return unicode(obj)

    # buffer support
    if isinstance(obj, const_get_buffer()):
        if sys.hexversion >= 0x3000000:
            return str(obj.tobytes(), enctype)
        else:
            return unicode(obj, enctype)

    # string/unicode support
    if const_isunicode(obj):
        return obj
    if hasattr(obj, 'decode'):
        return obj.decode(enctype)
    else:
        if sys.hexversion >= 0x3000000:
            return str(obj, enctype)
        else:
            return unicode(obj, enctype)

def const_convert_to_rawstring(obj, from_enctype = 'raw_unicode_escape'):
    """
    Convert generic string to raw string (str for Python 2.x or bytes for
    Python 3.x).

    @param obj: input string
    @type obj: string object
    @keyword from_enctype: encoding which string is using
    @type from_enctype: string
    @return: raw string
    @rtype: bytes
    """
    if obj is None:
        return const_convert_to_rawstring("None")
    if const_isnumber(obj):
        if sys.hexversion >= 0x3000000:
            return bytes(str(obj), from_enctype)
        else:
            return str(obj)
    if isinstance(obj, const_get_buffer()):
        if sys.hexversion >= 0x3000000:
            return obj.tobytes()
        else:
            return str(obj)
    if not const_isunicode(obj):
        return obj
    return obj.encode(from_enctype)

def const_get_buffer():
    """
    Return generic buffer object (supporting both Python 2.x and Python 3.x)
    """
    if sys.hexversion >= 0x3000000:
        return memoryview
    else:
        return buffer

def const_isfileobj(obj):
    """
    Return whether obj is a file object
    """
    if sys.hexversion >= 0x3000000:
        import io
        return isinstance(obj, io.IOBase)
    else:
        return isinstance(obj, file)

def const_isnumber(obj):
    """
    Return whether obj is an int, long object.
    """
    if sys.hexversion >= 0x3000000:
        return isinstance(obj, int)
    else:
        return isinstance(obj, (int, long,))

def const_cmp(a, b):
    """
    cmp() is gone in Python 3.x provide our own implementation.
    """
    return (a > b) - (a < b)

def const_islive():
    """
    Live environments (Operating System running off a CD/DVD)
    must feature the "cdroot" parameter in kernel /proc/cmdline

    Sample code:
        >>> from entropy.const import const_islive
        >>> const_islive()
        False

    @rtype: bool
    @return: determine wether this is a Live system or not
    """
    if "cdroot" in etpConst['cmdline']:
        return True
    return False

def const_kill_threads():
    """
    Entropy threads killer. Even if Python threads cannot
    be stopped or killed, TimeScheduled ones can, exporting
    the kill() method.

    Sample code:
        >>> from entropy.const import const_kill_threads
        >>> const_kill_threads()

    @rtype: None
    @return: None
    """
    import threading
    threads = threading.enumerate()
    for running_t in threads:
        # do not join current thread
        if running_t.getName() == 'MainThread':
            continue
        if hasattr(running_t, 'kill'):
            running_t.kill()
        running_t.join(120.0) # wait 2 minutes?

def __const_handle_exception(etype, value, t_back):
    """
    Our default Python exception handler. It kills
    all the threads generated by Entropy before
    raising exceptions. Overloads sys.excepthook,
    internal function !!

    @param etype: exception type
    @type etype: exception type
    @param value: exception data
    @type value: string
    @param t_back: traceback object?
    @type t_back: Python traceback object
    @rtype: default Python exceptions hook
    @return: sys.__excepthook__
    """
    try:
        const_kill_threads()
    except (AttributeError, ImportError, TypeError,):
        pass
    return sys.__excepthook__(etype, value, t_back)

def const_debug_write(identifier, msg):
    """
    Entropy debugging output write functions.

    @param identifier: debug identifier
    @type identifier: string
    @param msg: debugging message
    @type msg: string
    @rtype: None
    @return: None
    """
    if etpUi['debug']:
        if sys.hexversion >= 0x3000000:
            sys.stdout.buffer.write(const_convert_to_rawstring(identifier) + \
                b" " + const_convert_to_rawstring(msg) + b"\n")
        else:
            sys.stdout.write("%s: %s" % (identifier, msg + "\n"))
        sys.stdout.flush()

# load config
initconfig_entropy_constants(etpSys['rootdir'])
