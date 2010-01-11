# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Package Manager Client Packages retrieval Interface}.

"""
import os
from entropy.i18n import _
from entropy.const import etpConst, etpUi
from entropy.output import purple, bold, red, blue, darkgreen, darkred, brown, \
    darkblue

class FetchersMixin:

    def check_needed_package_download(self, filepath, checksum = None):
        # is the file available
        pkg_path = os.path.join(etpConst['entropyworkdir'],
            filepath)
        if os.path.isfile(pkg_path):

            if checksum is None:
                return 0
            # check digest
            md5res = self.entropyTools.compare_md5(pkg_path, checksum)
            if md5res:
                return 0
            return -2

        return -1

    def fetch_files(self, url_data_list, checksum = True, resume = True,
        fetch_file_abort_function = None):
        pkgs_bindir = etpConst['packagesbindir']
        url_path_list = []
        checksum_map = {}
        count = 0
        for url, dest_path, cksum, branch in url_data_list:
            count += 1
            filename = os.path.basename(url)
            if dest_path == None:
                dest_path = os.path.join(pkgs_bindir, branch, filename,)

            dest_dir = os.path.dirname(dest_path)
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir, 0o755)

            url_path_list.append((url, dest_path,))
            if cksum != None: checksum_map[count] = cksum

        # load class
        fetch_intf = self.MultipleUrlFetcher(url_path_list, resume = resume,
            abort_check_func = fetch_file_abort_function,
            OutputInterface = self, UrlFetcherClass = self.urlFetcher,
            checksum = checksum)
        try:
            data = fetch_intf.download()
        except KeyboardInterrupt:
            return -100, {}, 0

        diff_map = {}
        if checksum_map and checksum: # verify checksums
            diff_map = dict((url_path_list[x-1][0], checksum_map.get(x)) \
                for x in checksum_map if checksum_map.get(x) != data.get(x))

        data_transfer = fetch_intf.get_data_transfer()
        if diff_map:
            defval = -1
            for key, val in list(diff_map.items()):
                if val == "-1": # general error
                    diff_map[key] = -1
                elif val == "-2":
                    diff_map[key] = -2
                elif val == "-4": # timeout
                    diff_map[key] = -4
                elif val == "-3": # not found
                    diff_map[key] = -3
                elif val == -100:
                    defval = -100
            return defval, diff_map, data_transfer

        return 0, diff_map, data_transfer

    def fetch_files_on_mirrors(self, download_list, checksum = False,
        fetch_abort_function = None):

        avail_data = self.SystemSettings['repositories']['available']
        repo_uris = dict(((x[0], avail_data[x[0]]['packages'][::-1],) for x \
            in download_list))
        remaining = repo_uris.copy()
        my_download_list = download_list[:]

        def get_best_mirror(repository):
            try:
                return remaining[repository][0]
            except IndexError:
                return None

        def update_download_list(down_list, failed_down):
            newlist = []
            for repo, branch, fname, cksum, signatures in down_list:
                myuri = get_best_mirror(repo)
                myuri = os.path.join(myuri, fname)
                if myuri not in failed_down:
                    continue
                newlist.append((repo, branch, fname, cksum, signatures,))
            return newlist

        # return True: for failing, return False: for fine
        def mirror_fail_check(repository, best_mirror):
            # check if uri is sane
            if not self.MirrorStatus.get_failing_mirror_status(best_mirror) >= 30:
                return False
            # set to 30 for convenience
            self.MirrorStatus.set_failing_mirror_status(best_mirror, 30)
            mirrorcount = repo_uris[repo].index(best_mirror)+1
            mytxt = "( mirror #%s ) " % (mirrorcount,)
            mytxt += blue(" %s: ") % (_("Mirror"),)
            mytxt += red(self.entropyTools.spliturl(best_mirror)[1])
            mytxt += " - %s." % (_("maximum failure threshold reached"),)
            self.output(
                mytxt,
                importance = 1,
                type = "warning",
                header = red("   ## ")
            )

            if self.MirrorStatus.get_failing_mirror_status(best_mirror) == 30:
                self.MirrorStatus.add_failing_mirror(best_mirror, 45)
            elif self.MirrorStatus.get_failing_mirror_status(best_mirror) > 31:
                self.MirrorStatus.add_failing_mirror(best_mirror, -4)
            else:
                self.MirrorStatus.set_failing_mirror_status(best_mirror, 0)

            remaining[repository].discard(best_mirror)
            return True

        def show_download_summary(down_list):
            # fetch_files_list.append((myuri,None,cksum,branch,))
            for repo, branch, fname, cksum, signatures in down_list:
                best_mirror = get_best_mirror(repo)
                mirrorcount = repo_uris[repo].index(best_mirror)+1
                mytxt = "( mirror #%s ) " % (mirrorcount,)
                basef = os.path.basename(fname)
                mytxt += "[%s] %s " % (brown(basef), blue("@"),)
                mytxt += red(self.entropyTools.spliturl(best_mirror)[1])
                # now fetch the new one
                self.output(
                    mytxt,
                    importance = 1,
                    type = "info",
                    header = red("   ## ")
                )

        def show_successful_download(down_list, data_transfer):
            for repo, branch, fname, cksum, signatures in down_list:
                best_mirror = get_best_mirror(repo)
                mirrorcount = repo_uris[repo].index(best_mirror)+1
                mytxt = "( mirror #%s ) " % (mirrorcount,)
                basef = os.path.basename(fname)
                mytxt += "[%s] %s %s " % (brown(basef), darkred(_("success")), blue("@"),)
                mytxt += red(self.entropyTools.spliturl(best_mirror)[1])
                self.output(
                    mytxt,
                    importance = 1,
                    type = "info",
                    header = red("   ## ")
                )
            mytxt = " %s: %s%s%s" % (
                blue(_("Aggregated transfer rate")),
                bold(self.entropyTools.bytes_into_human(data_transfer)),
                darkred("/"),
                darkblue(_("second")),
            )
            self.output(
                mytxt,
                importance = 1,
                type = "info",
                header = red("   ## ")
            )

        def show_download_error(down_list, rc):
            for repo, branch, fname, cksum, signatures in down_list:
                best_mirror = get_best_mirror(repo)
                mirrorcount = repo_uris[repo].index(best_mirror)+1
                mytxt = "( mirror #%s ) " % (mirrorcount,)
                mytxt += blue("%s: %s") % (
                    _("Error downloading from"),
                    red(self.entropyTools.spliturl(best_mirror)[1]),
                )
                if rc == -1:
                    mytxt += " - %s." % (_("data not available on this mirror"),)
                elif rc == -2:
                    self.MirrorStatus.add_failing_mirror(best_mirror, 1)
                    mytxt += " - %s." % (_("wrong checksum"),)
                elif rc == -3:
                    mytxt += " - %s." % (_("not found"),)
                elif rc == -4: # timeout!
                    mytxt += " - %s." % (_("timeout error"),)
                elif rc == -100:
                    mytxt += " - %s." % (_("discarded download"),)
                else:
                    self.MirrorStatus.add_failing_mirror(best_mirror, 5)
                    mytxt += " - %s." % (_("unknown reason"),)
                self.output(
                    mytxt,
                    importance = 1,
                    type = "warning",
                    header = red("   ## ")
                )

        def remove_failing_mirrors(repos):
            for repo in repos:
                best_mirror = get_best_mirror(repo)
                if remaining[repo]:
                    remaining[repo].pop(0)

        def check_remaining_mirror_failure(repos):
            return [x for x in repos if not remaining.get(x)]

        while True:

            do_resume = True
            timeout_try_count = 50
            while True:

                fetch_files_list = []
                for repo, branch, fname, cksum, signatures in my_download_list:
                    best_mirror = get_best_mirror(repo)
                    # set working mirror, dont care if its None
                    self.MirrorStatus.set_working_mirror(best_mirror)
                    if best_mirror != None:
                        mirror_fail_check(repo, best_mirror)
                        best_mirror = get_best_mirror(repo)
                    if best_mirror == None:
                        # at least one package failed to download
                        # properly, give up with everything
                        return 3, my_download_list
                    myuri = os.path.join(best_mirror, fname)
                    fetch_files_list.append((myuri, None, cksum, branch,))

                try:

                    show_download_summary(my_download_list)
                    rc, failed_downloads, data_transfer = self.fetch_files(
                        fetch_files_list, checksum = checksum,
                        fetch_file_abort_function = fetch_abort_function,
                        resume = do_resume
                    )
                    if rc == 0:
                        show_successful_download(my_download_list, data_transfer)
                        return 0, []

                    # update my_download_list
                    my_download_list = update_download_list(my_download_list, failed_downloads)
                    if rc not in (-3, -4, -100,) and failed_downloads and do_resume:
                        # disable resume
                        do_resume = False
                        continue
                    else:
                        show_download_error(my_download_list, rc)
                        if rc == -4: # timeout
                            timeout_try_count -= 1
                            if timeout_try_count > 0:
                                continue
                        elif rc == -100: # user discarded fetch
                            return 1, []
                        myrepos = set([x[0] for x in my_download_list])
                        remove_failing_mirrors(myrepos)
                        # make sure we don't have nasty issues
                        remaining_failure = check_remaining_mirror_failure(myrepos)
                        if remaining_failure:
                            return 3, my_download_list
                        break
                except KeyboardInterrupt:
                    return 1, []
        return 0, []


    def fetch_file(self, url, branch, digest = None, resume = True,
        fetch_file_abort_function = None, filepath = None):

        def do_stfu_rm(xpath):
            try:
                os.remove(xpath)
            except OSError:
                pass

        filename = os.path.basename(url)
        if not filepath:
            filepath = os.path.join(etpConst['packagesbindir'], branch,
                filename)
        filepath_dir = os.path.dirname(filepath)
        # symlink support
        if not os.path.isdir(os.path.realpath(filepath_dir)):
            try:
                os.remove(filepath_dir)
            except OSError:
                pass
            os.makedirs(filepath_dir, 0o755)

        existed_before = False
        if os.path.isfile(filepath) and os.path.exists(filepath):
            existed_before = True

        # load class
        fetch_intf = self.urlFetcher(url, filepath, resume = resume,
            abort_check_func = fetch_file_abort_function,
            OutputInterface = self)
        fetch_intf.progress = self.progress

        # start to download
        data_transfer = 0
        resumed = False
        try:
            fetchChecksum = fetch_intf.download()
            data_transfer = fetch_intf.get_transfer_rate()
            resumed = fetch_intf.is_resumed()
        except KeyboardInterrupt:
            return -100, data_transfer, resumed
        except NameError:
            raise
        except:
            if etpUi['debug']:
                self.output(
                    "fetch_file:",
                    importance = 1,
                    type = "warning",
                    header = red("   ## ")
                )
                self.entropyTools.print_traceback()
            if (not existed_before) or (not resume):
                do_stfu_rm(filepath)
            return -1, data_transfer, resumed
        if fetchChecksum == "-3":
            # not found
            return -3, data_transfer, resumed
        elif fetchChecksum == "-4":
            # timeout
            return -4, data_transfer, resumed

        del fetch_intf

        if digest and (fetchChecksum != digest):
            # not properly downloaded
            if (not existed_before) or (not resume):
                do_stfu_rm(filepath)
            return -2, data_transfer, resumed

        return 0, data_transfer, resumed


    def fetch_file_on_mirrors(self, repository, branch, filename,
            digest = False, fetch_abort_function = None):

        avail_data = self.SystemSettings['repositories']['available']
        uris = avail_data[repository]['packages'][::-1]
        remaining = set(uris)

        mirrorcount = 0
        for uri in uris:

            if not remaining:
                # tried all the mirrors, quitting for error
                self.MirrorStatus.set_working_mirror(None)
                return 3

            self.MirrorStatus.set_working_mirror(uri)
            mirrorcount += 1
            mirror_count_txt = "( mirror #%s ) " % (mirrorcount,)
            url = uri + "/" + filename

            # check if uri is sane
            if self.MirrorStatus.get_failing_mirror_status(uri) >= 30:
                # ohohoh!
                # set to 30 for convenience
                self.MirrorStatus.set_failing_mirror_status(uri, 30)
                mytxt = mirror_count_txt
                mytxt += blue(" %s: ") % (_("Mirror"),)
                mytxt += red(self.entropyTools.spliturl(uri)[1])
                mytxt += " - %s." % (_("maximum failure threshold reached"),)
                self.output(
                    mytxt,
                    importance = 1,
                    type = "warning",
                    header = red("   ## ")
                )

                if self.MirrorStatus.get_failing_mirror_status(uri) == 30:
                    # put to 75 then decrement by 4 so we
                    # won't reach 30 anytime soon ahahaha
                    self.MirrorStatus.add_failing_mirror(uri, 45)
                elif self.MirrorStatus.get_failing_mirror_status(uri) > 31:
                    # now decrement each time this point is reached,
                    # if will be back < 30, then equo will try to use it again
                    self.MirrorStatus.add_failing_mirror(uri, -4)
                else:
                    # put to 0 - reenable mirror, welcome back uri!
                    self.MirrorStatus.set_failing_mirror_status(uri, 0)

                remaining.discard(uri)
                continue

            do_resume = True
            timeout_try_count = 50
            while True:
                try:
                    mytxt = mirror_count_txt
                    mytxt += blue("%s: ") % (_("Downloading from"),)
                    mytxt += red(self.entropyTools.spliturl(uri)[1])
                    # now fetch the new one
                    self.output(
                        mytxt,
                        importance = 1,
                        type = "warning",
                        header = red("   ## ")
                    )
                    rc, data_transfer, resumed = self.fetch_file(
                        url,
                        branch,
                        digest,
                        do_resume,
                        fetch_file_abort_function = fetch_abort_function
                    )
                    if rc == 0:
                        mytxt = mirror_count_txt
                        mytxt += blue("%s: ") % (_("Successfully downloaded from"),)
                        mytxt += red(self.entropyTools.spliturl(uri)[1])
                        human_bytes = self.entropyTools.bytes_into_human(data_transfer)
                        mytxt += " %s %s/%s" % (_("at"), human_bytes, _("second"),)
                        self.output(
                            mytxt,
                            importance = 1,
                            type = "info",
                            header = red("   ## ")
                        )

                        self.MirrorStatus.set_working_mirror(None)
                        return 0
                    elif resumed and (rc not in (-3, -4, -100,)):
                        do_resume = False
                        continue
                    else:
                        error_message = mirror_count_txt
                        error_message += blue("%s: %s") % (
                            _("Error downloading from"),
                            red(self.entropyTools.spliturl(uri)[1]),
                        )
                        # something bad happened
                        if rc == -1:
                            error_message += " - %s." % (_("file not available on this mirror"),)
                        elif rc == -2:
                            self.MirrorStatus.add_failing_mirror(uri, 1)
                            error_message += " - %s." % (_("wrong checksum"),)
                            # If file is fetched (with no resume) and its complete
                            # better to enforce resume to False.
                            if (data_transfer < 1) and do_resume:
                                error_message += " %s." % (_("Disabling resume"),)
                                do_resume = False
                                continue
                        elif rc == -3:
                            self.MirrorStatus.add_failing_mirror(uri, 3)
                            error_message += " - %s." % (_("not found"),)
                        elif rc == -4: # timeout!
                            timeout_try_count -= 1
                            if timeout_try_count > 0:
                                error_message += " - %s." % (_("timeout, retrying on this mirror"),)
                            else:
                                error_message += " - %s." % (_("timeout, giving up"),)
                        elif rc == -100:
                            error_message += " - %s." % (_("discarded download"),)
                        else:
                            self.MirrorStatus.add_failing_mirror(uri, 5)
                            error_message += " - %s." % (_("unknown reason"),)
                        self.output(
                            error_message,
                            importance = 1,
                            type = "warning",
                            header = red("   ## ")
                        )
                        if rc == -4: # timeout
                            if timeout_try_count > 0:
                                continue
                        elif rc == -100: # user discarded fetch
                            self.MirrorStatus.set_working_mirror(None)
                            return 1
                        remaining.discard(uri)
                        # make sure we don't have nasty issues
                        if not remaining:
                            self.MirrorStatus.set_working_mirror(None)
                            return 3
                        break
                except KeyboardInterrupt:
                    self.MirrorStatus.set_working_mirror(None)
                    return 1

        self.MirrorStatus.set_working_mirror(None)
        return 0
