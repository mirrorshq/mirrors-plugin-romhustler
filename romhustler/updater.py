#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import time
import json
import random
import socket
import subprocess
import selenium.common
import selenium.webdriver


PROGRESS_STAGE_1 = 50
PROGRESS_STAGE_2 = 50


def main():
    sock = _Util.connect()
    try:
        selfDir = os.path.dirname(os.path.realpath(__file__))
        popularGameListFile = os.path.join(selfDir, "popular_games.txt")
        dataDir = sys.argv[1]
        downloadTmpDir = os.path.join(dataDir, "_tmp")
        logDir = sys.argv[3]
        isDebug = os.environ.get("MIRRORS_PLUGIN_DEBUG") is not None and os.environ.get("MIRRORS_PLUGIN_DEBUG") != "0"
        mainUrl = "https://romhustler.org/roms"

        # download popular games
        if True:
            gameIdList = _readGameListFile(popularGameListFile)
            for gameId in gameIdList:
                targetDir = os.path.join(dataDir, gameId)
                if os.path.exists(targetDir) and False:
                    # FIXME: only re-download randomly
                    continue

                with _SeleniumWebDriver(isDebug, downloadTmpDir) as driver:
                    # load game page
                    driver.get(os.path.join(mainUrl, gameId))

                    # check if we can download this rom
                    try:
                        atag = driver.find_element_by_xpath("//div[contains(text(), \"download is disabled\")]")
                        print("Games %s is not downloadable." % (gameId))
                        continue
                    except selenium.common.exceptions.NoSuchElementException:
                        pass

                    # get game name
                    romName = driver.find_element_by_xpath("//h1[@itemprop=\"name\"]").text

                    # load download page, click to download
                    driver.find_element_by_link_text("Click here to download this rom").click()
                    while True:
                        time.sleep(1)
                        try:
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                            atag = driver.find_element_by_link_text("here")
                            atag.click()
                            break
                        except selenium.common.exceptions.NoSuchElementException:
                            pass

                    # wait download complete
                    while not (len(os.listdir(downloadTmpDir)) > 0 and len(glob.glob(os.path.join(downloadTmpDir, "*.crdownload"))) == 0):
                        time.sleep(1)

                # update target directory
                if os.path.exists(targetDir):
                    pass
                else:
                    pass

            print("All popular games downloaded, total %d files." % (len(gameIdList)))
            _Util.progress_changed(sock, PROGRESS_STAGE_1)




        # get main page
        driver.get(mainUrl)

        # random select





        # stage1: create directories, get file list, ignore symlinks (file donwloaders can not cope with symlinks)
        print("Start fetching file list.")
        fileList = _makeDirAndGetFileList(rsyncSource, dataDir)
        print("File list fetched, total %d files." % (len(fileList)))
        _Util.progress_changed(sock, PROGRESS_STAGE_1)

        # stage2: download file list
        logFile = os.path.join(logDir, "wget.log")
        i = 1
        total = len(fileList)
        for fn in _Util.randomSorted(fileList):
            fullfn = os.path.join(dataDir, fn)
            if not os.path.exists(fullfn):
                print("Download file \"%s\"." % (fn))
                tmpfn = fullfn + ".tmp"
                url = os.path.join(fileSource, fn)
                rc, out = _Util.shellCallWithRetCode("/usr/bin/wget -O \"%s\" %s >%s 2>&1" % (tmpfn, url, logFile))
                if rc != 0 and rc != 8:
                    # ignore "file not found" error (8) since rsyncSource/fileSource may be different servers
                    raise Exception("download %s failed" % (url))
                os.rename(tmpfn, fullfn)
            else:
                print("File \"%s\" exists." % (fn))
            _Util.progress_changed(sock, PROGRESS_STAGE_1 + PROGRESS_STAGE_2 * i // total)
        _Util.progress_changed(sock, PROGRESS_STAGE_1 + PROGRESS_STAGE_2)

        # stage3: rsync
        print("Start rsync.")
        logFile = os.path.join(logDir, "rsync.log")
        _Util.shellCall("/usr/bin/rsync -a -z --no-motd --delete %s %s >%s 2>&1" % (rsyncSource, dataDir, logFile))
        print("Rsync over.")

        # report full progress
        _Util.progress_changed(sock, 100)
    except:
        _Util.error_occured(sock, sys.exc_info())
        raise
    finally:
        sock.close()


def _readGameListFile(filename):
    gameIdList = []
    with open(filename) as f:
        for line in f.read().split("\n"):
            line = line.strip()
            if line != "" and not line.startswith("#"):
                gameIdList.append(line)
    return gameIdList

def _downloadGame(url, tmpDir):
    out = _Util.shellCall("/usr/bin/rsync -a --no-motd --list-only %s 2>&1" % (rsyncSource))

    ret = []
    for line in out.split("\n"):
        m = re.match("(\\S{10}) +([0-9,]+) +(\\S+ \\S+) (.+)", line)
        if m is None:
            continue
        modstr = m.group(1)
        filename = m.group(4)
        if filename.startswith("."):
            continue
        if " -> " in filename:
            continue

        if modstr.startswith("d"):
            _Util.ensureDir(os.path.join(dataDir, filename))
        else:
            ret.append(filename)

    return ret


class _Util:

    @staticmethod
    def connect():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect("/run/mirrors/api.socket")
        return sock

    @staticmethod
    def progress_changed(sock, progress):
        sock.send(json.dumps({
            "message": "progress",
            "data": {
                "progress": progress,
            },
        }).encoding("utf-8"))

    @staticmethod
    def error_occured(sock, exc_info):
        sock.send(json.dumps({
            "message": "error_occured",
            "data": {
                "exc_info": "abc",
            },
        }).encoding("utf-8"))

    @staticmethod
    def randomSorted(tlist):
        return sorted(tlist, key=lambda x: random.random())

    @staticmethod
    def ensureDir(dirname):
        if not os.path.exists(dirname):
            os.makedirs(dirname)

    @staticmethod
    def shellCall(cmd):
        # call command with shell to execute backstage job
        # scenarios are the same as FmUtil.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def shellCallWithRetCode(cmd):
        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        return (ret.returncode, ret.stdout.rstrip())


class _SeleniumWebDriver:

    def __init__(self, isDebug, downloadDir):
        options = selenium.webdriver.chrome.options.Options()
        if not isDebug:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_experimental_option("prefs", {
            "download.default_directory": downloadDir,
            "download.prompt_for_download": False,
        })
        self.driver = selenium.webdriver.Chrome(options=options)

    def __enter__(self):
        return self.driver

    def __exit__(self, type, value, traceback):
        pass


###############################################################################

if __name__ == "__main__":
    main()
