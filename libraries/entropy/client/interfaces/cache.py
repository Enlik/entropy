# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Package Manager Client Cache Interface}.

"""
import os
import shutil
import hashlib

from entropy.i18n import _
from entropy.output import purple
from entropy.const import etpConst, const_setup_perms, \
    const_convert_to_unicode, const_convert_to_rawstring
from entropy.exceptions import RepositoryError
from entropy.cache import EntropyCacher
from entropy.db.exceptions import OperationalError, DatabaseError

REPO_LIST_CACHE_ID = 'repos/repolist'

class CacheMixin:

    def _validate_repositories_cache(self):
        # is the list of repos changed?
        cached = self._cacher.pop(REPO_LIST_CACHE_ID)
        if cached != self._settings['repositories']['order']:
            # invalidate matching cache
            try:
                self._settings._clear_repository_cache(repoid = None)
            except IOError:
                pass
            self._store_repository_list_cache()

    def _store_repository_list_cache(self):
        self._cacher.push(REPO_LIST_CACHE_ID,
            self._settings['repositories']['order'],
            async = False)

    def clear_cache(self):
        """
        Clear all the Entropy default cache directory. This function is
        fault tolerant and will never return any exception.
        """
        with self._cacher:
            # no data is written while holding self._cacher by the balls
            # drop all the buffers then remove on-disk data
            self._cacher.discard()
            # clear repositories live cache
            if self._installed_repository is not None:
                self._installed_repository.clearCache()
            for repo in self._repodb_cache.values():
                repo.clearCache()
            cache_dir = self._cacher.current_directory()
            try:
                shutil.rmtree(cache_dir, True)
            except (shutil.Error, IOError, OSError):
                return
            try:
                os.makedirs(cache_dir, 0o775)
            except (IOError, OSError):
                return
            try:
                const_setup_perms(cache_dir, etpConst['entropygid'])
            except (IOError, OSError):
                return

    def update_ugc_cache(self, repository_id):
        """
        Update User Generated Content local cache if given repository_id
        supports UGC.

        @param repository_id: repository identifier
        @type repository_id: string
        @return: True, if cache update went ok, False if not, None if
            repository doesn't support UGC
        @rtype: bool or None
        """
        if not self.UGC.is_repository_eapi3_aware(repository_id):
            return None
        status = True

        votes_dict, err_msg = self.UGC.get_all_votes(repository_id)
        if isinstance(votes_dict, dict):
            self.UGC.UGCCache.save_vote_cache(repository_id, votes_dict)
        else:
            status = False

        downloads_dict, err_msg = self.UGC.get_all_downloads(repository_id)
        if isinstance(downloads_dict, dict):
            self.UGC.UGCCache.save_downloads_cache(repository_id,
                downloads_dict)
        else:
            status = False
        return status

    def is_ugc_cached(self, repository):
        """
        Determine whether User Generated Content cache is available for
        given repository.

        @param repository: Entropy repository identifier
        @type repository: string
        @return: True if available
        @rtype: bool
        """
        down_cache = self.UGC.UGCCache.get_downloads_cache(repository)
        if down_cache is None:
            return False

        vote_cache = self.UGC.UGCCache.get_vote_cache(repository)
        if vote_cache is None:
            return False

        return True

    def _get_available_packages_hash(self):
        """
        Get available packages cache hash.
        """
        # client digest not needed, cache is kept updated
        c_hash = "%s|%s|%s" % (
            self._repositories_hash(),
            self._filter_available_repositories(),
            # needed when users do bogus things like editing config files
            # manually (branch setting)
            self._settings['repositories']['branch'])
        sha = hashlib.sha1()
        sha.update(const_convert_to_rawstring(repr(c_hash)))
        return sha.hexdigest()

    def _repositories_hash(self):
        """
        Return the checksum of available repositories, excluding package ones.
        """
        enabled_repos = self._filter_available_repositories()
        return self.__repositories_hash(enabled_repos)

    def __repositories_hash(self, repositories):
        sha = hashlib.sha1()
        sha.update(const_convert_to_rawstring("0"))
        for repo in repositories:
            try:
                dbconn = self.open_repository(repo)
            except (RepositoryError):
                continue # repo not available
            try:
                sha.update(const_convert_to_rawstring(repr(dbconn.mtime())))
            except (OperationalError, DatabaseError, OSError, IOError):
                txt = _("Repository") + " " + const_convert_to_unicode(repo) \
                    + " " + _("is corrupted") + ". " + \
                    _("Cannot calculate the checksum")
                self.output(
                    purple(txt),
                    importance = 1,
                    level = "warning"
                )
        return sha.hexdigest()

    def _all_repositories_hash(self):
        """
        Return the checksum of all the available repositories, including
        package repos.
        """
        return self.__repositories_hash(self._enabled_repos)

    def _get_masked_packages_cache(self, chash):
        """
        Return the on-disk cached object for all the masked packages.

        @param chash: cache hash
        @type chash: string
        @return: list of masked packages (if cache hit) otherwise None
        @rtype: list or None
        """
        return self._cacher.pop("%s%s" % (
            EntropyCacher.CACHE_IDS['world_masked'], chash))

    def _get_available_packages_cache(self, chash):
        """
        Return the on-disk cached object for all the available packages.

        @param chash: cache hash
        @type chash: string
        @return: list of available packages (if cache hit) otherwise None
        @rtype: list or None
        """
        return self._cacher.pop("%s%s" % (
            EntropyCacher.CACHE_IDS['world_available'], chash))

    def _get_updates_cache(self, empty_deps, repo_hash = None):
        """
        Get available updates on-disk cache, if available, otherwise return None
        """
        cl_id = self.sys_settings_client_plugin_id
        misc_settings = self._settings[cl_id]['misc']
        ignore_spm_downgrades = misc_settings['ignore_spm_downgrades']

        if self.xcache:

            if repo_hash is None:
                repo_hash = self._repositories_hash()

            c_hash = self._get_updates_cache_hash(repo_hash, empty_deps,
                ignore_spm_downgrades)

            disk_cache = self._cacher.pop(c_hash)
            if isinstance(disk_cache, tuple):
                return disk_cache

    def _filter_available_repositories(self):
        """
        Filter out package repositories from the list of available,
        enabled ones
        """
        enabled_repos = [x for x in self._enabled_repos if not \
            x.endswith(etpConst['packagesext_webinstall'])]
        enabled_repos = [x for x in enabled_repos if not \
            x.endswith(etpConst['packagesext'])]
        return enabled_repos

    def _get_updates_cache_hash(self, repo_hash, empty_deps,
        ignore_spm_downgrades):
        """
        Get package updates cache hash that can be used to retrieve the on-disk
        cached object.
        """
        enabled_repos = self._filter_available_repositories()
        repo_order = [x for x in self._settings['repositories']['order'] if
            x in enabled_repos]

        c_hash = "%s|%s|%s|%s|%s|%s" % (
            repo_hash, empty_deps, enabled_repos,
            repo_order,
            ignore_spm_downgrades,
            # needed when users do bogus things like editing config files
            # manually (branch setting)
            self._settings['repositories']['branch'],
        )
        sha = hashlib.sha1()
        sha.update(const_convert_to_rawstring(repr(c_hash)))
        return "%s_%s" % (EntropyCacher.CACHE_IDS['world_update'],
            sha.hexdigest(),)

    def _get_critical_updates_cache(self, repo_hash = None):
        """
        Get critical package updates cache object, if available, otherwise
        return None.
        """
        if self.xcache:
            if repo_hash is None:
                repo_hash = self._repositories_hash()
            c_hash = "%s%s" % (EntropyCacher.CACHE_IDS['critical_update'],
                self._get_critical_update_cache_hash(repo_hash),)

            return self._cacher.pop(c_hash)

    def _get_critical_update_cache_hash(self, repo_hash):
        """
        Get critical package updates cache hash that can be used to retrieve
        the on-disk cached object.
        """
        enabled_repos = self._filter_available_repositories()
        repo_order = [x for x in self._settings['repositories']['order'] if
            x in enabled_repos]
        c_hash = "%s|%s|%s|%s" % (
            repo_hash, enabled_repos,
            repo_order,
            # needed when users do bogus things like editing config files
            # manually (branch setting)
            self._settings['repositories']['branch'],
        )
        sha = hashlib.sha1()
        sha.update(const_convert_to_rawstring(repr(c_hash)))
        return sha.hexdigest()
