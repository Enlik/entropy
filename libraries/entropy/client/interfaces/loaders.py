# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Package Manager Client Instance Loaders Interface}.

"""
from entropy.spm.plugins.factory import get_default_instance as get_spm, \
    get_default_class as get_spm_default_class
from entropy.const import *
from entropy.exceptions import *

class LoadersMixin:

    __QA_cache = {}
    __security_cache = {}
    __spm_cache = {}
    def __init__(self):
        from entropy.client.interfaces.client import Client
        from entropy.client.interfaces.trigger import Trigger
        from entropy.client.interfaces.repository import Repository
        from entropy.client.interfaces.package import Package
        from entropy.security import Repository as RepositorySecurity
        self.__PackageLoader = Package
        self.__RepositoryLoader = Repository
        self.__TriggerLoader = Trigger
        self.__RepositorySecurityLoader = RepositorySecurity

    def closeAllQA(self):
        self.__QA_cache.clear()

    def closeAllSecurity(self):
        self.__security_cache.clear()

    def Security(self):
        chroot = etpConst['systemroot']
        cached = self.__security_cache.get(chroot)
        if cached != None:
            return cached
        from entropy.security import System as system_sec
        cached = system_sec(self)
        self.__security_cache[chroot] = cached
        return cached

    def RepositorySecurity(self):
        """
        @raise RepositorySecurity.GPGError: GPGError based instances in case
            of problems.
        """
        return self.__RepositorySecurityLoader(
            keystore_dir = etpConst['etpclientgpgdir'])

    def QA(self):
        chroot = etpConst['systemroot']
        cached = self.__QA_cache.get(chroot)
        if cached != None:
            return cached
        from entropy.qa import QAInterface
        cached = QAInterface(self)
        self.__QA_cache[chroot] = cached
        return cached

    def Triggers(self, *args, **kwargs):
        return self.__TriggerLoader(self, *args, **kwargs)

    def Repositories(self, *args, **kwargs):
        cl_id = self.sys_settings_client_plugin_id
        client_data = self.SystemSettings[cl_id]['misc']
        kwargs['gpg'] = client_data['gpg']
        return self.__RepositoryLoader(self, *args, **kwargs)

    def Spm(self):
        myroot = etpConst['systemroot']
        cached = self.__spm_cache.get(myroot)
        if cached is not None:
            return cached
        spm = get_spm(self)
        self.__spm_cache[myroot] = spm
        return spm

    def Spm_class(self):
        """
        Return Source Package Manager default plugin class.
        """
        return get_spm_default_class()

    def Package(self):
        return self.__PackageLoader(self)
