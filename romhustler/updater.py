#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import time
import json
import shutil
import random
import socket
import traceback
import subprocess
import selenium.common
import selenium.webdriver

POPULAR_GAME_PAGE_COUNT = 10

HOME_URL = "https://romhustler.org"
MAIN_URL = "https://romhustler.org/roms"
ROM_URL_PREFIX = "https://romhustler.org/rom"

POPULAR_GAME_FILE = "POPULAR_GAMES"
BAD_GAME_FAILE = "UNAVAILABLE_GAMES"

PROGRESS_STAGE_1 = 50
PROGRESS_STAGE_2 = 50


def main():
    selfDir = os.path.dirname(os.path.realpath(__file__))
    classicGameListFile = os.path.join(selfDir, "games_classic.txt")
    badGameListFile = os.path.join(selfDir, "games_bad.txt")

    p = InfoPrinter()
    sock = MUtil.connect()
    try:
        args = json.loads(sys.argv[1])
        dataDir = args["data-directory"]
        bShowUi = ("show-ui" in re.compile(" *\\| *").split(args["debug-flag"]))
        bFakeDownload = ("fake-download" in re.compile(" *\\| *").split(args["debug-flag"]))
        isDebug = (args["debug-flag"] != "")                                                        # FIXME
        blackList = Util.readGameListFile(badGameListFile)

        # download classic games
        p.print("Processing classic games.")
        p.incIndent()
        try:
            gameIdList = Util.randomSorted(Util.readGameListFile(classicGameListFile))
            for i in range(0, len(gameIdList)):
                gameId = gameIdList[i]
                targetDir = os.path.join(dataDir, gameId)
                if not os.path.exists(targetDir):
                    with _GameDownloader(isDebug) as obj:
                        try:
                            obj.download(dataDir, targetDir, "Classic game", gameId, os.path.join(ROM_URL_PREFIX, gameId))
                        except Exception:
                            print(traceback.format_exc())
                MUtil.progress_changed(sock, PROGRESS_STAGE_1 * i // len(gameIdList))
        finally:
            p.decIndent()

        # download popular games
        p.print("Processing popular games.")
        p.incIndent()
        try:
            gameIdList = Util.randomSorted(_readPopularGameList())
            for i in range(0, len(gameIdList)):
                gameId = gameIdList[i]
                targetDir = os.path.join(dataDir, gameId)
                if not os.path.exists(targetDir):
                    with _GameDownloader(isDebug) as obj:
                        try:
                            obj.download(dataDir, targetDir, "Popular game", gameId, os.path.join(ROM_URL_PREFIX, gameId))
                        except Exception:
                            print(traceback.format_exc())
                MUtil.progress_changed(sock, PROGRESS_STAGE_1 + PROGRESS_STAGE_2 * i // len(gameIdList))
        finally:
            p.decIndent()

        # download all games
        p.print("Read random game list.")
        p.incIndent()
        try:
            pass
        finally:
            p.decIndent()

        # report full progress
        MUtil.progress_changed(sock, 100)
    except Exception:
        MUtil.error_occured(sock, sys.exc_info())
        raise
    finally:
        sock.close()


def _readPopularGameList(blackList, bShowUi):
    gameIdList = []
    with SeleniumChrome(bShowUi) as cobj:
        cobj.getAndWait(HOME_URL)
        elem = cobj.driver.find_element_by_xpath("/html/body/div[1]/div[2]/div[3]/div[1]/div[2]/div[2]/div/div")
        for atag in elem.find_elements_by_xpath(".//a"):
            gameId = "/".join(atag.get_attribute("href").split("/")[-2:])           # "https://romsmania.cc/roms/gameboy-color/pokemon-diamond-226691" -> "gameboy-color/pokemon-diamond-226691"
            if not _isInBlackList(gameId, blackList):
                gameIdList.append(gameId)
    return gameIdList


def _readGameListFromWebSite(MAIN_URL, dataDir, pageCount, blackList, isDebug):
    gameIdList = []
    with SeleniumChrome(isDebug) as cobj:
        cobj.driver.get(MAIN_URL)                                                        # get first page
        for i in range(0, pageCount):
            for atag in cobj.driver.find_elements_by_xpath('//div[@class="title"]/a'):
                gameId = "/".join(atag.get_attribute("href").split("/")[-2:])
                gameIdList.append(gameId)
            if i < pageCount - 1:
                time.sleep(1.0)
                for atag in cobj.driver.find_elements_by_xpath("//a"):
                    if atag.text == "next>":                                            # get next page, find_element_by_xpath('//a[text()="next>"]') has no effect, don't know why
                        atag.click()
                        break
    return gameIdList


def _isInBlackList(gameId, blackList):
    for bgId in blackList:
        if fnmatch.fnmatch(gameId, bgId):
            return True
    return False


class _GameDownloader:

    def __init__(self, isDebug):
        self.isDebug = isDebug

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass

    def download(self, dataDir, targetDir, gameTypename, gameId, gameUrl):
        self.downloadTmpDir = os.path.join(dataDir, "_tmp_" + gameId.replace("/", "_"))
        Util.ensureDir(self.downloadTmpDir)
        try:
            romName = None
            url = None
            filename = None
            with SeleniumChrome(self.isDebug, self.downloadTmpDir) as cobj:
                # load game page
                cobj.driver.get(gameUrl)
                if cobj.driver.current_url != gameUrl:
                    print("%s %s does not exists." % (gameTypename, gameId))
                    return

                # check if we can download this rom
                try:
                    atag = cobj.driver.find_element_by_xpath("//div[contains(text(), \"download is disabled\")]")
                    print("%s %s is not available for download." % (gameTypename, gameId))
                    return
                except selenium.common.exceptions.NoSuchElementException:
                    pass

                # get game name
                romName = cobj.driver.find_element_by_xpath("//h1[@itemprop=\"name\"]").text

                # load download page, click to download
                cobj.driver.find_element_by_link_text("Click here to download this rom").click()
                while True:
                    time.sleep(1)
                    try:
                        cobj.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                        atag = cobj.driver.find_element_by_link_text("here")
                        atag.click()
                        break
                    except selenium.common.exceptions.NoSuchElementException:
                        pass

                # get download information
                url, filename = cobj.gotoDownloadManagerAndGetDownloadInfo()

            # do download
            if self._freshDownloadNeeded(url, romName, filename):
                Util.shellCall("/bin/rm -rf %s/*" % (self.downloadTmpDir))
                with open(os.path.join(self.downloadTmpDir, "ROM_NAME"), "w") as f:
                    f.write(romName)
                Util.wgetDownload(url, os.path.join(self.downloadTmpDir, filename))
            else:
                Util.wgetContinueDownload(url, os.path.join(self.downloadTmpDir, filename))

            # save to target directory
            Util.ensureDir(targetDir)
            Util.shellCall("/bin/mv %s/* %s" % (self.downloadTmpDir, targetDir))
            print("%s %s downloaded." % (gameTypename, gameId))

            # remove download temp files only if everything is OK
            shutil.rmtree(self.downloadTmpDir)
        finally:
            del self.downloadTmpDir

    def _freshDownloadNeeded(self, romUrl, romName, filename):
        fn = os.path.join(self.downloadTmpDir, "ROM_NAME")
        if not os.path.exists(fn):
            return True
        if Util.readFile(fn) != romName:
            return True
        if not os.path.exists(os.path.join(self.downloadTmpDir, filename)):
            print("true 5")
            return True
        print("false")
        return False


class MUtil:

    @staticmethod
    def getInitOrUpdate():
        # must be called when plugin starts
        if len(sys.argv) == 6:
            return True
        elif len(sys.argv) == 7:
            return False
        else:
            raise Exception("is invalid number %d" % (len(sys.argv)))

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
        }).encode("utf-8"))
        sock.send(b'\n')

    @staticmethod
    def error_occured(sock, exc_info):
        sock.send(json.dumps({
            "message": "error_occured",
            "data": {
                "exc_info": "abc",
            },
        }).encode("utf-8"))
        sock.send(b'\n')


class Util:

    @staticmethod
    def readGameListFile(filename):
        gameIdList = []
        with open(filename, "r") as f:
            for line in f.read().split("\n"):
                try:
                    line = line[0:line.index("#")]
                except ValueError:
                    pass
                line = line.strip()
                if line != "":
                    gameIdList.append(line)
        return gameIdList

    @staticmethod
    def writeGameListFile(filename, gameIdList):
        if len(gameIdList) == 0:
            return

        gameIdSet = set()
        if os.path.exists(filename):
            gameIdSet = set(Util.readGameListFile(filename))

        gameIdSet |= set(gameIdList)

        with open(filename, "w") as f:
            for gameId in sorted(list(gameIdSet)):
                f.write(gameId)
                f.write("\n")

    @staticmethod
    def touchFile(filename):
        assert not os.path.exists(filename)
        f = open(filename, 'w')
        f.close()

    @staticmethod
    def forceDelete(filename):
        if os.path.islink(filename):
            os.remove(filename)
        elif os.path.isfile(filename):
            os.remove(filename)
        elif os.path.isdir(filename):
            shutil.rmtree(filename)

    @staticmethod
    def randomSorted(tlist):
        return sorted(tlist, key=lambda x: random.random())

    @staticmethod
    def readFile(filename):
        with open(filename) as f:
            return f.read()

    @staticmethod
    def cmdExec(cmd, *kargs):
        # call command to execute frontend job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminate AFTER child-process, and do neccessary finalization
        #   * termination information should be printed by callee, not caller
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller should terminate callee, wait callee to stop, do neccessary finalization, print termination information, and be terminated by signal
        #   * callee does not need to treat this scenario specially
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment
        #   * callee should print termination information

        # FIXME, the above condition is not met, FmUtil.shellExec has the same problem

        ret = subprocess.run([cmd] + list(kargs), universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()

    @staticmethod
    def wgetDownload(url, localFile=None):
        param = Util.wgetCommonDownloadParam().split()
        if localFile is None:
            Util.cmdExec("/usr/bin/wget", *param, url)
        else:
            if os.path.exists(localFile):
                param.insert("-c")
                print("continue")
            Util.cmdExec("/usr/bin/wget", *param, "-O", localFile, url)

    @staticmethod
    def wgetContinueDownload(url, localFile):
        param = Util.wgetCommonDownloadParam().split()
        Util.cmdExec("/usr/bin/wget", "-c", *param, "-O", localFile, url)

    @staticmethod
    def wgetCommonDownloadParam():
        return "-t 0 -w 60 --random-wait -T 60 --passive-ftp"

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
        # scenarios are the same as Util.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            ret.check_returncode()
        return ret.stdout.rstrip()


class InfoPrinter:

    def __init__(self):
        self.indent = 0

    def incIndent(self):
        self.indent = self.indent + 1

    def decIndent(self):
        assert self.indent > 0
        self.indent = self.indent - 1

    def print(self, s):
        line = ""
        line += "\t" * self.indent
        line += s
        print(line)


###############################################################################

if __name__ == "__main__":
    main()
