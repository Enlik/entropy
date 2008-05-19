#!/usr/bin/python -tt
# -*- coding: iso-8859-1 -*-
#    Yum Exteder (yumex) - A GUI for yum
#    Copyright (C) 2006 Tim Lauridsen < tim<AT>yum-extender<DOT>org > 
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

from etpgui.packages import EntropyPackage, DummyEntropyPackage
import logging
from spritz_setup import SpritzConf

#import yum.misc as misc
#import yum.Errors as Errors
#from yum.packages import parsePackages

from i18n import _

class EntropyPackages:

    def __init__(self, EquoInstance):
        self.Entropy = EquoInstance
        self.logger = logging.getLogger('yumex.Packages')
        self.filterCallback = None
        self._packages = {}
        self.pkgCache = {}
        self.currentCategory = None
        self._categoryPackages = {}
        self.categories = set()
        self.selected_treeview_item = None
        self.selected_advisory_item = None

    def clearPackages(self):
        self._packages.clear()
        self.selected_treeview_item = None
        self.selected_advisory_item = None

    def clearCache(self):
        self.pkgCache.clear()
        self.selected_treeview_item = None
        self.selected_advisory_item = None

    def populatePackages(self,masks):
        for flt in masks:
            if self._packages.has_key(flt):
                continue
            self._packages[flt] = [p for p in self._getPackages(flt)]

    def setCategoryPackages(self,pkgdict = {}):
        self._categoryPackages = pkgdict

    def getPackagesByCategory(self,cat=None):
        if not cat:
           cat =  self.currentCategory
        else:
           self.currentCategory = cat
        if not self._categoryPackages.has_key(cat):
            self.populateCategory(cat)
        return self._categoryPackages[cat]

    def populateCategory(self, category):

        catsdata = self.Entropy.list_repo_packages_in_category(category)
        catsdata.update(set([(x,0) for x in self.Entropy.list_installed_packages_in_category(category)]))
        pkgsdata = []
        for pkgdata in catsdata:
            yp, new = self.getPackageItem(pkgdata,True)
            install_status = yp.install_status
            ok = False
            if install_status == 1:
                yp.action = 'i'
                ok = True
            elif install_status == 2:
                yp.action = 'u'
                yp.color = SpritzConf.color_update
                ok = True
            #elif install_status == 3:
            #    yp.action = 'r'
            #    yp.color = SpritzConf.color_install
            #    ok = True
            if ok: pkgsdata.append(yp)
        del catsdata
        self._categoryPackages[category] = pkgsdata

    def populateCategories(self):
        try:
            self.categories = self.Entropy.list_repo_categories()
        except self.Entropy.dbapi2.OperationalError:
            self.categories.clear()

    def getPackages(self,flt):
        if flt == 'all':
            return self.getAllPackages()
        else:
            return self.doFiltering(self.getRawPackages(flt))

    def getAllPackages(self):
        pkgs = []
        pkgs.extend(self.getPackages('installed'))
        pkgs.extend(self.getPackages('available'))
        pkgs.extend(self.getPackages('reinstallable'))
        pkgs.extend(self.getPackages('updates'))
        return pkgs

    def setFilter(self,fn = None):
        self.filterCallback = fn

    def doFiltering(self,pkgs):
        if self.filterCallback:
            return filter(self.filterCallback,pkgs)
        else:
            return pkgs

    def isInst(self,atom): # fast check for if package is installed
        m = self.Entropy.clientDbconn.atomMatch(atom)
        if m[0] != -1:
            return True
        return False

    def findPackagesByTuples(self,typ,tuplist):
        pkgs = self.getRawPackages(typ)
        foundlst = []
        for pkg in pkgs:
            tup = pkg.pkgtup
            if tup in tuplist:
                foundlst.append(pkg)
        return foundlst

    def getRawPackages(self,flt):
        self.populatePackages([flt])
        return self._packages[flt]

    def getPackageItem(self, pkgdata, avail):
        new = False
        if self.pkgCache.has_key((pkgdata,avail)):
            yp = self.pkgCache[(pkgdata,avail)]
        else:
            new = True
            yp = EntropyPackage(pkgdata, avail)
            self.pkgCache[(pkgdata,avail)] = yp
        return yp, new

    def _getPackages(self,mask):
        #print "mask:",mask
        if mask == 'installed':
            for idpackage in self.Entropy.clientDbconn.listAllIdpackages(order_by = 'atom'):
                yp, new = self.getPackageItem((idpackage,0),True)
                yp.action = 'r'
                yp.color = SpritzConf.color_install
                yield yp
        elif mask == 'available':
            # Get the rest of the available packages.
            available = self.Entropy.calculate_available_packages()
            for pkgdata in available:
                yp, new = self.getPackageItem(pkgdata,True)
                yp.action = 'i'
                yield yp
        elif mask == 'updates':
            updates, remove, fine = self.Entropy.calculate_world_updates()
            del remove, fine
            for pkgdata in updates:
                yp, new = self.getPackageItem(pkgdata,True)
                yp.action = 'u'
                yp.color = SpritzConf.color_update
                yield yp
        elif mask == "reinstallable":
            for idpackage in self.Entropy.clientDbconn.listAllIdpackages(order_by = 'atom'):
                matched = self.isReinstallable(idpackage)
                if not matched:
                    continue
                yp, new = self.getPackageItem(matched,True)
                yp.installed_match = (idpackage,0)
                yp.action = 'rr'
                yp.color = SpritzConf.color_install
                yield yp

        elif mask == "fake_updates":
            # load a pixmap inside the treeview
            msg2 = _("Try clicking the %s button in the %s page") % ( _("Update Repositories"),_("Repository Selection"),)

            msg = "<big><b><span foreground='#FF0000'>%s</span></b></big>\n<span foreground='darkblue'>%s.\n%s</span>" % (
                    _('No updates available'),
                    _("It seems that your system is already up-to-date. Good!"),
                    msg2,
                )
            myobj = DummyEntropyPackage(namedesc = msg, dummy_type = SpritzConf.dummy_empty)
            yield myobj

    def isReinstallable(self, client_idpackage):
        atom = self.Entropy.clientDbconn.retrieveAtom(client_idpackage)
        upd, matched = self.Entropy.check_package_update(atom)
        if (not upd) and matched:
            if matched[0] != -1:
                inst_rev = self.Entropy.clientDbconn.retrieveRevision(client_idpackage)
                dbconn = self.Entropy.openRepositoryDatabase(matched[1])
                avail_rev = dbconn.retrieveRevision(matched[0])
                if avail_rev == inst_rev:
                    return matched

    def getCategories(self):
        catlist = []
        for cat in self.categories:
            catlist.append(cat)
        catlist.sort()
        return catlist
