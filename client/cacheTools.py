#!/usr/bin/python
'''
    # DESCRIPTION:
    # Equo on-disk caching tools

    Copyright (C) 2007 Fabio Erculiani

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
'''

from entropyConstants import *
from clientConstants import *
from outputTools import *
import exceptionTools

def cache(options):
    rc = 0
    if len(options) < 1:
	return -10

    if options[0] == "clean":
	rc = cleanCache()
    elif options[0] == "generate":
	rc = generateCache()
    else:
        rc = -10

    return rc
    

'''
   @description: scan etpCache and remove all the on disk caching files
   @output: status code
'''
def cleanCache():
    cacheConn = cacheHelper()
    cacheConn.purge()
    del cacheConn
    return 0

'''
   @description: cache entropy data and scan packages to collect info and fill caches
   @output: status code
'''
def generateCache(depcache = True, configcache = True):
    cacheConn = cacheHelper()
    cacheConn.generate(depcache = depcache, configcache = configcache)
    del cacheConn
    return 0

'''
    Entropy cache interface:
            - handles on-disk cache status
            - handles dictionary cache status
'''
class cacheHelper(TextInterface):

    def __init__(self):
        import confTools
        self.confTools = confTools
        import equoTools
        self.equoTools = equoTools
        # instantiate Equo handling class
        self.Equo = self.equoTools.Equo()
        import entropyTools
        self.entropyTools = entropyTools
        from databaseTools import openRepositoryDatabase
        self.openRepositoryDatabase = openRepositoryDatabase

    def purge(self):
        dumpdir = etpConst['dumpstoragedir']
        if not dumpdir.endswith("/"): dumpdir = dumpdir+"/"
        for key in etpCache:
            cachefile = dumpdir+etpCache[key]+"*.dmp"
            self.updateProgress(darkred("Cleaning %s...") % (cachefile,), importance = 1, type = "warning", back = True)
            try:
                os.system("rm -f "+cachefile)
            except:
                pass
        # reset dict cache
        self.updateProgress(darkgreen("Cache is now empty."), importance = 2, type = "info")
        const_resetCache()

    def generate(self, depcache = True, configcache = True):
        # clean first of all
        self.purge()
        if depcache:
            self.do_depcache()
        if configcache:
            self.do_configcache()

    def do_configcache(self):
        self.updateProgress(darkred("Configuration files"), importance = 2, type = "warning")
        self.updateProgress(red("Scanning hard disk"), importance = 1, type = "warning")
        self.confTools.scanfs(dcache = False)
        self.updateProgress(darkred("Cache generation complete."), importance = 2, type = "info")

    def do_depcache(self):
        self.updateProgress(darkred("Dependencies"), importance = 2, type = "warning")
        self.updateProgress(darkred("Scanning repositories"), importance = 2, type = "warning")
        names = set()
        keys = set()
        depends = set()
        atoms = set()
        for reponame in etpRepositories:
            self.updateProgress(darkgreen("Scanning %s" % (etpRepositories[reponame]['description'],)) , importance = 1, type = "info", back = True)
            # get all packages keys
            try:
                dbconn = self.openRepositoryDatabase(reponame)
            except exceptionTools.RepositoryError:
                self.updateProgress(darkred("Cannot download/access: %s" % (etpRepositories[reponame]['description'],)) , importance = 2, type = "error")
                continue
            pkgdata = dbconn.listAllPackages()
            pkgdata = set(pkgdata)
            for info in pkgdata:
                key = self.entropyTools.dep_getkey(info[0])
                keys.add(key)
                names.add(key.split("/")[1])
                atoms.add(info[0])
            # dependencies
            pkgdata = dbconn.listAllDependencies()
            for info in pkgdata:
                depends.add(info[1])
            dbconn.closeDB()
            del dbconn

        self.updateProgress(darkgreen("Resolving metadata"), importance = 1, type = "warning")
        atomMatchCache.clear()
        maxlen = len(names)
        cnt = 0
        for name in names:
            cnt += 1
            self.updateProgress(darkgreen("Resolving name: %s") % (
                                                name
                                        ), importance = 0, type = "info", back = True, count = (cnt, maxlen) )
            self.equoTools.atomMatch(name)
        maxlen = len(keys)
        cnt = 0
        for key in keys:
            cnt += 1
            self.updateProgress(darkgreen("Resolving key: %s") % (
                                                key
                                        ), importance = 0, type = "info", back = True, count = (cnt, maxlen) )
            self.equoTools.atomMatch(key)
        maxlen = len(atoms)
        cnt = 0
        for atom in atoms:
            cnt += 1
            self.updateProgress(darkgreen("Resolving atom: %s") % (
                                                atom
                                        ), importance = 0, type = "info", back = True, count = (cnt, maxlen) )
            self.equoTools.atomMatch(atom)
        maxlen = len(depends)
        cnt = 0
        for depend in depends:
            cnt += 1
            self.updateProgress(darkgreen("Resolving dependency: %s") % (
                                                depend
                                        ), importance = 0, type = "info", back = True, count = (cnt, maxlen) )
            self.equoTools.atomMatch(depend)
        self.updateProgress(darkred("Dependencies filled. Flushing to disk."), importance = 2, type = "warning")
        self.Equo.save_cache()
