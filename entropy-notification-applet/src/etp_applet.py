# This file is a portion of the Red Hat Network Panel Applet
#
# Copyright (C) 1999-2002 Red Hat, Inc. All Rights Reserved.
# Distributed under GPL version 2.
#
# Author: Chip Turner
#
# def help added by Tammy Fox
#
# $Id: rhn_applet.py,v 1.114 2003/11/09 16:56:33 veillard Exp $

import gnome
import gnome.ui
# from msw to avoid odd bugs in some pygtk builds
import gtk
import gobject
import gtk.gdk
import egg.trayicon
import pynotify

import os, sys, math, time, threading, subprocess

import etp_applet_animation
from etp_applet_dialogs import \
     rhnAppletNoticeWindow, \
     rhnRegistrationPromptDialog, \
     rhnAppletAboutWindow, \
     rhnAppletFirstTimeDruid, \
     rhnAppletErrorDialog, \
     rhnAppletExceptionDialog
import etp_applet_config
from etpgui import busyCursor,normalCursor

# Entropy imports
from entropyConstants import *
import exceptionTools, entropyTools
from entropy import EquoInterface, RepoInterface, urlFetcher
from entropy_i18n import _

class Entropy(EquoInterface):

    def __init__(self):
        EquoInterface.__init__(self, noclientdb = True)
        self.nocolor()

    def connect_progress_objects(self, appletInterface):
        self.appletInterface = appletInterface
        self.appletX, self.appletY = self.appletInterface.appletX, self.appletInterface.appletY
        self.progress_tooltip = self.appletInterface.update_tooltip
        self.progress_widget = self.appletInterface.tooltip
        self.updateProgress = self.appletUpdateProgress
        self.progress_tooltip_message_title = _("Updates Notification")
        self.appletCreateNotification()
        self.urlFetcher = GuiUrlFetcher
        self.progress = self.appletPrintText # for the GuiUrlFetcher
        self.applet_last_message = ''


    def appletSetCoordinates(self):
        self.progress_tooltip_notification.set_hint("x", self.appletX)
        self.progress_tooltip_notification.set_hint("y", self.appletY)

    def appletCreateNotification(self):
        gtk.gdk.threads_enter()
        pynotify.init("XY")
        self.progress_tooltip_notification = pynotify.Notification(self.progress_tooltip_message_title,"Hello world")
        self.progress_tooltip_notification.set_timeout(3000)
        self.appletSetCoordinates()
        gtk.gdk.threads_leave()

    def appletUpdateProgress(self, text, header = "", footer = "", back = False, importance = 0, type = "info", count = [], percent = False):

        count_str = ""
        if count:
            if percent:
                count_str = str(int(round((float(count[0])/count[1])*100,1)))+"% "
            else:
                count_str = "(%s/%s) " % (str(count[0]),str(count[1]),)

        message = count_str+_(text)
        #if importance in (1,2):
        if importance == 2:
            self.progress_tooltip_message_title = message
            self.appletPrintText(self.applet_last_message)
        else:
            self.appletPrintText(message)

    def appletPrintText(self, message):
        gtk.gdk.threads_enter()
        self.progress_tooltip_notification.update(self.progress_tooltip_message_title,message)
        self.progress_tooltip_notification.show()
        self.applet_last_message = message
        gtk.gdk.threads_leave()

class GuiUrlFetcher(urlFetcher):

    def connect_to_gui(self, progress):
        self.progress = progress

    def updateProgress(self):
        self.gather = self.downloadedsize
        message = "Fetching data %s/%s kB @ %s" % (
                                        str(round(float(self.downloadedsize)/1024,1)),
                                        str(round(self.remotesize,1)),
                                        str(self.entropyTools.bytesIntoHuman(self.datatransfer))+"/sec",
                                    )
        gtk.gdk.threads_enter()
        self.progress(message)
        gtk.gdk.threads_leave()

class rhnApplet:

    def set_state(self, new_state, use_busy_icon = 0):

        if not new_state in etp_applet_config.APPLET_STATES:
            raise exceptionTools.IncorrectParameter("Error: invalid state %s" % new_state)

        #if self.refresh_timeout_tag and new_state not in [ "OKAY", "CRITICAL" ]:
        #    raise exceptionTools.IncorrectParameter("Error: can't switch to state %s while refresh timer is on" % new_state)

        if new_state == "OKAY":
            self.animate_to("okay")
        elif new_state == "BUSY":
            if use_busy_icon:
                self.set_displayed_image("busy")
        elif new_state == "CRITICAL":
            if self.never_viewed_notices:
                self.animate_to("critical", "critical-blank")
            else:
                self.set_displayed_image("critical")
        elif new_state == "NOCONSENT":
            if self.never_viewed_consent:
                self.animate_to("noconsent", "noconsent-blank")
            else:
                self.set_displayed_image("noconsent")
        elif new_state == "DISCONNECTED":
            self.animate_to("disconnect")
        elif new_state == "ERROR":
            self.animate_to("error")

        self.current_state = new_state


    def __init__(self):

        self.debug = False
        if "--debug" in sys.argv:
            self.debug = True

        self.appletX, self.appletY = 0,0
        self.animator = None
        self.client = None
        self.notice_window = None
        self.rhnreg_dialog = None
        self.error_dialog = None
        self.error_threshold = 0
        self.about_window = None
        self.last_error = None
        self.last_error_is_exception = 0
        self.last_error_is_network_error = 0
        self.change_number = 0
        self.available_packages = []
        self.last_alert = None
        self.Entropy = None
        self.destroyed = 0
        self.isWorking = False
        self.refresh_lock = threading.Lock()
        self.tooltip_text = ""
        gnome.program_init("spritz-updater", etpConst['entropyversion'])
        self.tooltip = gtk.Tooltips()
        self.applet_window = egg.trayicon.TrayIcon("spritz-updater")
        self.applet_window.connect("destroy", self.exit_applet)

        self.session = gnome.ui.master_client()
        if self.session:
            gtk.Object.connect(self.session, "save-yourself", self.save_yourself)
            gtk.Object.connect(self.session, "die", self.exit_applet)

        self.consent = {}
        self.never_viewed_consent = 1
        self.never_viewed_notices = 1

        self.skip_check_locked = False
        self.current_image = None
        self.refresh_timeout_tag = None
        self.animate_timeout_tag = None
        self.current_state = None
        self.old_critical_text = None
        self.network_timeout_tag = None

        self.icons = etp_applet_animation.rhnAppletIconPixbuf()

        self.icons.add_file("okay", "applet-okay.png")
        self.icons.add_file("error", "applet-error.png")
        self.icons.add_file("busy", "applet-busy.png")
        self.icons.add_file("critical", "applet-critical.png")
        self.icons.add_file("critical-blank", "applet-critical-blank.png")
        self.icons.add_file("noconsent", "applet-critical.png")
        self.icons.add_file("noconsent-blank", "applet-critical-blank.png")
        self.icons.add_file("disconnect", "applet-disconnect.png")
        self.icons.add_file("spritz","spritz.png")
        self.icons.add_file("about","applet-about.png")
        self.icons.add_file("web","applet-web.png")
        self.icons.add_file("configuration","applet-configuration.png")
        self.applet_size = 22

        menu_items = (
            ("disable_applet", _("_Disable Notification Applet"), _("Disable Notification Applet"), self.disable_applet),
            ("enable_applet", _("_Enable Notification Applet"), _("Enable Notification Applet"), self.enable_applet),
            ("check_now", _("_Check for updates"), _("Check for updates"), self.update_from_server),
            ("update_now", _("_Launch Package Manager"), _("Launch Package Manager"), self.launch_package_manager),
            ("web_panel", _("_Packages Website"), _("Use Packages web interface"), self.load_packages_url),
            ("web_site", _("_Sabayon Linux Website"), _("Launch Sabayon Linux Website"), self.load_website),
            None,
            ("about", _("_About"), _("About..."), self.about),
            ("exit", _("_Exit"), _("Exit"), self.exit_applet),
            )

        self.menu = gtk.Menu()
        self.menu_items = {}
        for i in menu_items:
            if i is None:
                self.menu.add(gtk.SeparatorMenuItem())
            else:
                sid = None
                myid = i[0]
                if myid == "exit":
                    sid = "gtk-quit"
                if sid:
                    w = gtk.ImageMenuItem(stock_id = sid)
                else:
                    w = gtk.ImageMenuItem(i[1])
                    self.set_menu_image(w, myid)
                self.menu_items[myid] = w
                w.connect('activate', i[3])
                w.show()
                self.menu.add(w)

        self.menu.show_all()

        self.event_box = gtk.EventBox()
        self.image_widget = gtk.Image()
        self.event_box.add(self.image_widget)

        self.event_box.connect("button_press_event", self.applet_face_click)
        self.image_widget.connect('destroy', self.on_destroy)

        self.applet_window.add(self.event_box)
        self.applet_window.realize()
        self.applet_window.show_all()

        hide_menu = False
        message = ''
        workdir_perms_issue = False
        if os.path.isdir(etpConst['entropyworkdir']):
            gid = os.stat(etpConst['entropyworkdir'])[5]
            if gid != etpConst['entropygid']:
                workdir_perms_issue = True

        permitted = entropyTools.is_user_in_entropy_group()
        load_intf = False
        if not permitted:
            hide_menu = True
            message = "%s: %s" % (_("You must add yourself to this group"),etpConst['sysgroup'],)
        elif workdir_perms_issue:
            hide_menu = True
            message = _("Please run Equo/Spritz as root to update Entropy permissions")
        else:
            load_intf = True

        if etp_applet_config.settings['APPLET_ENABLED']:
            self.enable_applet(init = True)
        else:
            self.disable_applet()

        if hide_menu:
            self.disable_refresh_timer()
            self.set_state("ERROR")
            self.update_tooltip(message)
            for key in self.menu_items:
                if key in ['exit','web_site','about','web_panel','update_now']:
                    continue
                w = self.menu_items[key]
                w.set_sensitive(False)
                w.hide()

        self.appletX, self.appletY = self.get_tray_coordinates()
        self.appletX += 10
        self.appletY += 10
        if load_intf:
            # Entropy initialization
            self.Entropy = Entropy()
            self.Entropy.connect_progress_objects(self)
            self.enable_refresh_timer()


    def get_tray_coordinates(self):
        """
        get the trayicon coordinates to send to
        notification-daemon
        trayicon=egg.trayicon.TrayIcon
        return : [x,y]
        """
        trayicon = self.applet_window
        coordinates = trayicon.window.get_origin()
        size = trayicon.window.get_size()
        screen = trayicon.window.get_screen()
        screen_height = screen.get_height()
        if coordinates[1] <= screen_height/2:
            y=coordinates[1]+size[1]/2
        else:
            y=coordinates[1]-size[1]/2
        msg_xy = (coordinates[0],y)
        return tuple(msg_xy)

    def set_menu_image(self, widget, name):
        img = gtk.Image()
        if name == "update_now":
            pix = self.icons.best_match("spritz",22)
        elif name == "about":
            pix = self.icons.best_match("about",22)
        elif name in ["web_panel","web_site"]:
            pix = self.icons.best_match("web",22)
        elif name == "configure_applet":
            pix = self.icons.best_match("configuration",22)
        elif name == "disable_applet":
            pix = self.icons.best_match("disconnect",22)
        elif name == "enable_applet":
            pix = self.icons.best_match("okay",22)
        else:
            pix = self.icons.best_match("busy",22)

        img.set_from_pixbuf(pix)
        widget.set_image(img)

    def enable_refresh_timer(self, when = etp_applet_config.settings['REFRESH_INTERVAL'] * 1000):
        if self.current_state in [ "CRITICAL" ]: return
        if not self.refresh_timeout_tag:
            self.refresh_timeout_tag = entropyTools.TimeScheduled(self.refresh_handler, when/1000)
            self.refresh_timeout_tag.delay_before = True
            self.refresh_timeout_tag.start()

    def disable_refresh_timer(self):
        if self.refresh_timeout_tag:
            self.refresh_timeout_tag.kill()
            self.refresh_timeout_tag = None

    def start_working(self):
        self.isWorking = True
        busyCursor(self.applet_window)

    def end_working(self):
        self.isWorking = False
        normalCursor(self.applet_window)

    def animate_stop(self):
        self.disable_animation_timer()

        # not animating?  then our current image is correct
        if self.animator:
            self.set_displayed_image(self.animator.final_frame)
            self.animator = None

        self.redraw()

    def disable_animation_timer(self):
        if self.animate_timeout_tag:
            self.animate_timeout_tag.kill()
            self.animate_timeout_tag = None

    def animate_handler(self, *data):

        next_frame = self.animator.next_frame()
        if not next_frame:
            self.disable_animation_timer()
            return False

        self.current_image = next_frame
        self.redraw()

        return True

    def animate_to(self, image, cycle_image = None):

        if self.current_image == image:
            return

        if self.current_image:
            from_image = self.current_image.copy()
        else:
            from_image = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, 1, 8, self.applet_size, self.applet_size)
            from_image.fill(0)

        to_image = self.icons.best_match(image, self.applet_size)

        frames = etp_applet_animation.alpha_tween(from_image, to_image, 16)

        self.animator = etp_applet_animation.rhnAppletAnimation()

        # if we're already in the to_image state, let's just start cycling
        if self.current_image != to_image or cycle_image:
            self.animator.append_frames(frames)

        if cycle_image:
            cycle_frames = []

            to_image = self.icons.best_match(image, self.applet_size)
            from_image = self.icons.best_match(cycle_image, self.applet_size)
            cycle_frames = etp_applet_animation.alpha_tween(to_image, from_image, 16)

            self.animator.append_cycle(cycle_frames)

        if not self.animate_timeout_tag:
            mytiming = float(math.floor(1000 * etp_applet_config.settings['ANIMATION_TOTAL_TIME']/len(frames)))
            self.animate_timeout_tag = entropyTools.TimeScheduled(self.animate_handler, mytiming/1000)
            self.animate_timeout_tag.start()

    def set_displayed_image(self, image):
        if isinstance(image,basestring): new_image = self.icons.best_match(image, self.applet_size)
        else: new_image = image
        self.disable_animation_timer()
        self.current_image = new_image
        self.redraw()

    def redraw(self):
        if not self.current_image: return
        self.image_widget.set_from_pixbuf(self.current_image)

    def on_destroy(self, *data):
        self.destroyed = 1
        self.disable_refresh_timer()
        self.disable_animation_timer()

    def load_packages_url(self, *data):
        try:
            gnome.url_show("http://packages.sabayonlinux.org/")
        except gobject.GError:
            self.load_browser("http://packages.sabayonlinux.org/")

    def load_website(self, *data):
        try:
            gnome.url_show("http://www.sabayonlinux.org/")
        except gobject.GError:
            self.load_browser("http://www.sabayonlinux.org/")

    def load_browser(self, url):
        browser = None
        konq_ret = subprocess.call("which konqueror &> /dev/null", shell = True)
        if os.access("/usr/bin/firefox",os.X_OK):
            browser = "/usr/bin/firefox"
        elif konq_ret:
            browser = "konqueror"
        elif os.access("/usr/bin/opera",os.X_OK):
            browser = "/usr/bin/opera"
        if browser:
            subprocess.call([browser,url])

    def disable_applet(self):
        self.update_tooltip(_("Updates Notification Applet Disabled"))
        self.disable_refresh_timer()
        self.set_state("DISCONNECTED")
        etp_applet_config.settings['APPLET_ENABLED'] = 0
        etp_applet_config.save_settings(etp_applet_config.settings)
        self.menu_items['disable_applet'].hide()
        self.menu_items['enable_applet'].show()

    def enable_applet(self, init = False):
        self.update_tooltip(_("Updates Notification Applet Enabled"))
        if not init:
            self.enable_refresh_timer()
        self.set_state("OKAY")
        etp_applet_config.settings['APPLET_ENABLED'] = 1
        etp_applet_config.save_settings(etp_applet_config.settings)
        self.menu_items['disable_applet'].show()
        self.menu_items['enable_applet'].hide()

    def launch_package_manager(self, *data):

        def spawn_spritz():
            os.execv('/usr/bin/spritz', ['spritz'])

        t = entropyTools.parallelTask(spawn_spritz)
        t.start()

    def show_alert(self, title, text, urgency = None):

        if (title,text) == self.last_alert:
            return

        pynotify.init("XY")
        n = pynotify.Notification(title, text)
        if urgency == 'critical':
            n.set_urgency(pynotify.URGENCY_CRITICAL)
        elif urgency == 'low':
            n.set_urgency(pynotify.URGENCY_LOW)

        n.set_hint("x", self.Entropy.appletX)
        n.set_hint("y", self.Entropy.appletY)
        self.last_alert = (title,text)
        n.show()

    def compare_repositories_status(self):
        repos = {}

        try:
            repoConn = self.Entropy.Repositories(noEquoCheck = True, fetchSecurity = False)
        except exceptionTools.MissingParameter:
            return repos,1 # no repositories specified
        except exceptionTools.OnlineMirrorError:
            return repos,2 # not connected ??
        except Exception, e:
            return repos,str(e) # unknown error

        # now get remote
        for repoid in etpRepositories:
            if repoConn.is_repository_updatable(repoid):
                self.Entropy.repository_move_clear_cache(repoid)
                repos[repoid] = {}
                repos[repoid]['local_revision'] = self.Entropy.get_repository_revision(repoid)
                repos[repoid]['remote_revision'] = repoConn.get_online_repository_revision(repoid)

        del repoConn

        return repos, 0

    def refresh_handler(self, force = 0, after = 0):
        gtk.gdk.threads_enter()
        if after: time.sleep(after)
        self.refresh(force)
        gtk.gdk.threads_leave()

    def refresh(self, force = 0):

        if not self.Entropy:
            if self.debug: print "refresh: Entropy interface not loaded"
            return
        if not etp_applet_config.settings['APPLET_ENABLED']:
            if self.debug: print "refresh: applet not enabled"
            return
        if self.debug: print "refresh: all fine, getting lock and running run_refresh"

        self.refresh_lock.acquire()
        try:
            return self.run_refresh(force)
        finally:
            self.refresh_lock.release()


    def run_refresh(self, force):

        locked = self.Entropy.application_lock_check(silent = True)

        self.start_working()
        old_tip = self.tooltip_text
        old_state = self.current_state

        self.disable_network_timer()

        self.set_state("BUSY", use_busy_icon = force)
        self.update_tooltip(_("Checking for updates..."))

        self.last_error = None
        self.last_error_is_network_error = 0
        self.error_threshold = 0
        self.available_packages = []

        rc = 0
        if not locked:

            # compare repos
            if self.debug: print "run_refresh: launching compare_repositories_status"
            repositories_to_update, rc = self.compare_repositories_status()
            if self.debug: print "run_refresh: completed compare_repositories_status: %s" % ((repositories_to_update, rc),)

            if repositories_to_update and rc == 0:
                repos = repositories_to_update.keys()

                if self.debug: print "run_refresh: loading repository interface"
                try:
                    repoConn = self.Entropy.Repositories(repos, fetchSecurity = False, noEquoCheck = True)
                    if self.debug: print "run_refresh: repository interface loaded"
                except exceptionTools.MissingParameter, e:
                    self.last_error = "%s: %s" % (_("No repositories specified in"),etpConst['repositoriesconf'],)
                    self.error_threshold += 1
                    if self.debug: print "run_refresh: MissingParameter exception, error: %s" % (e,)
                except exceptionTools.OnlineMirrorError, e:
                    self.last_error = _("Repository Network Error")
                    self.last_error_is_network_error = 1
                    if self.debug: print "run_refresh: OnlineMirrorError exception, error: %s" % (e,)
                except Exception, e:
                    self.error_threshold += 1
                    self.last_error_is_exception = 1
                    self.last_error = "%s: %s" % (_('Unhandled exception'),e,)
                    if self.debug: print "run_refresh: Unhandled exception, error: %s" % (e,)
                else:
                    # -128: sync error, something bad happened
                    # -2: repositories not available (all)
                    # -1: not able to update all the repositories
                    if self.debug: print "run_refresh: preparing to run sync"
                    rc = repoConn.sync()
                    rc = rc*-1
                    del repoConn
                    if self.debug: print "run_refresh: sync done"
                if self.debug: print "run_refresh: sync closed, rc: %s" % (rc,)

            if rc == 1:
                err = _("No repositories specified. Cannot check for package updates.")
                self.show_alert( _("Updates: attention"), err )
                self.error_threshold += 1
                self.last_error = err
            elif rc == 2:
                err = _("Cannot connect to the Updates Service, you're probably not connected to the world.")
                self.show_alert( _("Updates: connection issues"), err )
                self.last_error_is_network_error = 1
                self.last_error = err
            elif rc == -1:
                err = _("Not all the repositories have been fetched for checking")
                self.show_alert( _("Updates: repository issues"), err )
                self.last_error_is_network_error = 1
                self.last_error = err
            elif rc == -2:
                err = _("No repositories found online")
                self.show_alert( _("Updates: repository issues"), err )
                self.last_error_is_network_error = 1
                self.last_error = err
            elif rc == -128:
                err = _("Synchronization errors. Cannot update repositories. Check logs.")
                self.show_alert( _("Updates: sync issues"), err )
                self.error_threshold += 1
                self.last_error = err
            elif isinstance(rc,basestring):
                self.show_alert( _("Updates: unhandled error"), rc )
                self.error_threshold += 1
                self.last_error_is_exception = 1
                self.last_error = rc

            if self.last_error_is_network_error:
                self.update_tooltip(_("Updates: connection issues"))
                self.set_state("DISCONNECTED")
                self.end_working()
                return False

        try:
            update, remove, fine = self.Entropy.calculate_world_updates()
            del fine, remove
        except Exception, e:
            msg = "%s: %s" % (_("Updates: error"),e,)
            self.show_alert(_("Updates: error"), msg)
            self.error_threshold += 1
            self.last_error_is_exception = 1
            self.last_error = str(e)

        if self.last_error:
            self.disable_refresh_timer()
            msg = "%s: %s" % (_("Updates issue:"),self.last_error,)
            self.update_tooltip(msg)
            self.set_state("ERROR")
            self.end_working()
            return False

        if rc == 0:
            self.update_tooltip(old_tip)

        # it is possible that the applet was destroyed during the time it
        # took to update the model.  If the applet is gone, bail now.
        if self.destroyed:
            self.end_working()
            return False

        if update:
            self.available_packages = update[:]
            self.set_state("CRITICAL")
            msg = "%s %d %s" % (_("There are"),len(update),_("updates available."),)
            self.update_tooltip(msg)
            self.show_alert(    _("Updates available"),
                                msg,
                                urgency = 'critical'
                        )
            if self.notice_window:
                self.refresh_notice_window()

        else:
            self.set_state(old_state)
            self.update_tooltip(_("So far, so good. w00t!"))
            self.show_alert(    _("Everything up-to-date"),
                                _("So far, so good. w00t!"),
                                urgency = 'low'
                        )

        self.end_working()
        return True

    def is_network_error(self, msg):
        if msg.find("SysCallError") >= 0 and msg.find("104") >= 0:
            return 1
        if msg.find("onnection") >= 0:
            return 1
        if msg.find("etwork") >= 0:
            return 1
        if msg.find("certificate verify failed") >= 0:
            return 0
        if msg.find("SSL") >= 0:
            return 1
        return 0

    def network_retry_handler(self, force):
        self.refresh(force)

    def enable_network_timer(self, when = etp_applet_config.settings['NETWORK_RETRY_INTERVAL'] * 1000, force = 0):
        if self.current_state != "DISCONNECTED": return
        if not self.network_timeout_tag:
            self.network_timeout_tag = entropyTools.TimeScheduled(self.network_retry_handler, when/1000, dictData = {'force': force})
            self.network_timeout_tag.delay_before = True
            self.network_timeout_tag.start()

    def disable_network_timer(self):
        if self.network_timeout_tag:
            self.network_timeout_tag.kill()
            self.network_timeout_tag = None

    def update_tooltip(self, tip):
        self.tooltip_text = tip
        self.tooltip.set_tip(self.applet_window, tip)

    def update_from_server(self, widget=None):
        self.enable_applet()
        self.refresh(force = 1)

    def user_consented(self):
        self.consent = 1

    def notice_window_closed(self):
        self.notice_window = None

    def exit_applet(self, *args):

        for my in entropyTools.threading.enumerate():
            if hasattr(my,'kill'):
                my.kill()

        gtk.main_quit()
        raise SystemExit

    def save_yourself(self, *args):
        if self.session:
            self.session.set_clone_command(1, ["/usr/bin/entropy-update-applet"])
            self.session.set_restart_command(1, ["/usr/bin/entropy-update-applet"])

        return True

    def about(self, *data):
        if self.about_window:
            return
        self.about_window = rhnAppletAboutWindow(self)

    def about_dialog_closed(self):
        self.about_window = None

    def rhnreg_dialog_closed(self):
        self.rhnreg_dialog = None

    def error_dialog_closed(self):
        self.error_dialog = None
        self.last_error = None
        self.last_error_is_exception = 0
        self.last_error_is_network_error = 0
        self.set_state("OKAY")
        self.update_tooltip(_("Waiting before checkin..."))
        self.enable_refresh_timer()

    def applet_face_click(self, window, event, *data):
        if event.button == 3:
            self.menu.popup(None, None, None, 0, event.time)
            return

        if self.current_state in [ "CRITICAL", "NOCONSENT" ]:
            self.animate_stop()

        if not self.current_state in [ "OKAY", "ERROR", "DISCONNECTED", "CRITICAL" ]:
            return

        if self.last_error:
            if self.error_dialog:
                return
            if self.last_error_is_exception:
                self.error_dialog = rhnAppletExceptionDialog(self, self.last_error)
            else:
                self.error_dialog = rhnAppletErrorDialog(self, self.last_error)
            return

        self.never_viewed_notices = 0
        if self.notice_window and not self.rhnreg_dialog:
            self.notice_window.close_window()
            return

        if not self.notice_window:
            self.notice_window = rhnAppletNoticeWindow(self)

        self.refresh_notice_window()

        if self.rhnreg_dialog:
            self.rhnreg_dialog.set_transient(self.notice_window)
            self.rhnreg_dialog.raise_()

    def refresh_notice_window(self):
        self.notice_window.clear_window()

        if not self.available_packages:
            return

        names = {}
        entropy_data = {}
        for pkg in self.available_packages:
            dbconn = self.Entropy.openRepositoryDatabase(pkg[1])
            atom = dbconn.retrieveAtom(pkg[0])
            avail = dbconn.retrieveVersion(pkg[0])
            avail_rev = dbconn.retrieveRevision(pkg[0])
            key, slot = dbconn.retrieveKeySlot(pkg[0])
            installed_match = self.Entropy.clientDbconn.atomMatch(key, matchSlot = slot)

            if installed_match[0] != -1:
                installed = self.Entropy.clientDbconn.retrieveVersion(installed_match[0])
                installed_rev = self.Entropy.clientDbconn.retrieveRevision(installed_match[0])
            else:
                installed = _("Not installed")
            if key == "sys-apps/entropy":
                entropy_data['avail'] = avail+"~"+str(avail_rev)[:]
                entropy_data['installed'] = installed+"~"+str(installed_rev)

            names[atom] = {}
            names[atom]['installed'] = installed+"~"+str(installed_rev)
            names[atom]['avail'] = avail+"~"+str(avail_rev)


        ordered_names = names.keys()
        ordered_names.sort()
        for name in ordered_names:
            self.notice_window.add_package( name,
                                            names[name]['installed'],
                                            names[name]['avail']
                                          )

        critical_text = []
        if entropy_data.has_key("avail"):
            msg = "%s sys-apps/entropy <b>%s</b> %s, %s <b>%s</b>. %s." % (
                    _("Your system currently has"),
                    entropy_data['installed'],
                    _("installed"),
                    _("but the latest available version is"),
                    entropy_data['avail'],
                    _("It is recommended that you upgrade to the latest before updating any other packages")
            )
            critical_text.append(msg)

        if critical_text:
            if self.old_critical_text != critical_text:
                self.notice_window.set_critical('<br><br>'.join(critical_text), critical_active = 1)
            else:
                self.notice_window.set_critical('<br><br>'.join(critical_text), critical_active = 0)
            self.old_critical_text = critical_text
        else:
            self.notice_window.remove_critical()


    def set_ignored(self, name, new_value):
        self.never_viewed_notices = 0
