#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import time
import json
import manpa
import shutil
import random
import socket
import fnmatch
import traceback
import subprocess
import selenium.common
import selenium.webdriver


HOME_URL = "https://romhustler.org"
MAIN_URL = "https://romhustler.org/roms"
ROM_URL_PREFIX = "https://romhustler.org/rom"

PROGRESS_STAGE_CLASSIC = 20
PROGRESS_STAGE_POPULAR = 30
PROGRESS_STAGE_OTHER = 50


class Main:

    def __init__(self, sock):
        selfDir = os.path.dirname(os.path.realpath(__file__))
        args = json.loads(sys.argv[1])

        self.classicGameListFile = os.path.join(selfDir, "games_classic.txt")
        self.badGameListFile = os.path.join(selfDir, "games_bad.txt")

        self.popularGameFile = "POPULAR_GAMES"
        self.badGameFile = "UNAVAILABLE_GAMES"

        self.sock = sock
        self.dataDir = args["data-directory"]
        self.logDir = args["log-directory"]
        self.isDebug = (args["debug-flag"] != "")
        self.blackList = Util.readGameListFile(self.badGameListFile)
        self.mp = manpa.Manpa(isDebug=self.isDebug)
        self.p = InfoPrinter()

    def run(self):
        # download classic games
        self.p.print("Processing classic games.")
        self.p.incIndent()
        try:
            gameIdList = Util.randomSorted(Util.readGameListFile(self.classicGameListFile))
            downloadedList = []
            failList = []
            for i in range(0, len(gameIdList)):
                try:
                    self.downloadGame("Classic game", gameIdList[i])
                    downloadedList.append(gameIdList[i])
                except Exception:
                    failList.append(gameIdList[i])
            Util.writeGameListFile(os.path.join(self.dataDir, self.popularGameFile), downloadedList)
            Util.writeGameListFile(os.path.join(self.dataDir, self.badGameFile), failList)
            MUtil.progress_changed(self.sock, PROGRESS_STAGE_CLASSIC)
        finally:
            self.p.decIndent()

        # download popular games
        self.p.print("Processing popular games.")
        self.p.incIndent()
        try:
            gameIdList = self.readPopularGameList()
            downloadedList = []
            failList = []
            for i in range(0, len(gameIdList)):
                try:
                    self.downloadGame("Popular game", gameIdList[i])
                    downloadedList.append(gameIdList[i])
                except Exception:
                    failList.append(gameIdList[i])
            Util.writeGameListFile(os.path.join(self.dataDir, self.popularGameFile), downloadedList)
            Util.writeGameListFile(os.path.join(self.dataDir, self.badGameFile), failList)
            MUtil.progress_changed(self.sock, PROGRESS_STAGE_CLASSIC + PROGRESS_STAGE_POPULAR)
        finally:
            self.p.decIndent()

        # download all games
        self.p.print("Processing all games.")
        self.p.incIndent()
        try:
            gameIdList = self.readGameListFromWebSite()
            failList = []
            for i in range(0, len(gameIdList)):
                try:
                    self.downloadGame("Game", gameIdList[i])
                except Exception:
                    failList.append(gameIdList[i])
            Util.writeGameListFile(os.path.join(self.dataDir, self.badGameFile), failList)
            MUtil.progress_changed(self.sock, PROGRESS_STAGE_CLASSIC + PROGRESS_STAGE_POPULAR + PROGRESS_STAGE_OTHER)
        finally:
            self.p.decIndent()

    def readPopularGameList(self):
        gameIdList = []
        with self.mp.open_selenium_client() as driver:
            driver.get_and_wait(HOME_URL)
            elem = driver.find_element_by_xpath("/html/body/div[1]/div[2]/div[3]/div[1]/div[2]/div[2]/div/div")
            for atag in elem.find_elements_by_xpath(".//a"):
                gameId = "/".join(atag.get_attribute("href").split("/")[-2:])           # "https://romsmania.cc/roms/gameboy-color/pokemon-diamond-226691" -> "gameboy-color/pokemon-diamond-226691"
                gameIdList.append(gameId)
        return gameIdList

    def readGameListFromWebSite(self, pageCount=9999):
        gameIdList = []
        with self.mp.open_selenium_client() as driver:
            driver.get_and_wait(MAIN_URL)
            for i in range(0, pageCount):
                for atag in driver.find_elements_by_xpath('//div[@class="title"]/a'):
                    gameId = "/".join(atag.get_attribute("href").split("/")[-2:])
                    gameIdList.append(gameId)
                if i < pageCount - 1:
                    time.sleep(1.0)
                    for atag in driver.find_elements_by_xpath("//a"):
                        if atag.text == "next>":                                        # get next page, find_element_by_xpath('//a[text()="next>"]') has no effect, don't know why
                            atag.click_and_wait()
                            break
        return gameIdList

    def downloadGame(self, gameTypename, gameId):
        gameUrl = os.path.join(ROM_URL_PREFIX, gameId)

        # prepare temporary directory
        downloadTmpDir = self._getDownloadTmpDir(gameId)
        Util.ensureDir(downloadTmpDir)

        # do work
        targetDir = os.path.join(self.dataDir, gameId)
        if os.path.exists(targetDir):
            self._checkGame(gameTypename, gameId, gameUrl, targetDir, downloadTmpDir)
        else:
            self._downloadGame(gameTypename, gameId, gameUrl, targetDir, downloadTmpDir)

        # remove download temp files only if everything is OK
        Util.forceDelete(downloadTmpDir)

    def removeDownloadTmpDir(self, gameId):
        downloadTmpDir = self._getDownloadTmpDir(gameId)
        assert os.path.realpath(downloadTmpDir).startswith(self.dataDir)
        Util.shellCall("/bin/rm -rf %s" % (downloadTmpDir))

    def _downloadGame(self, gameTypename, gameId, gameUrl, targetDir, downloadTmpDir):
        try:
            # find game url
            romName = None
            url = None
            filename = None
            with self.mp.open_selenium_client() as driver:
                # load game page
                driver.get_and_wait(gameUrl)
                if driver.current_url != gameUrl:
                    print("%s %s does not exists." % (gameTypename, gameId))
                    return

                # check if we can download this rom
                try:
                    atag = driver.find_element_by_xpath("//div[contains(text(), \"download is disabled\")]")
                    print("%s %s is not available for download." % (gameTypename, gameId))
                    return
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
                        url, filename = driver.retrieve_download_information()
                        break
                    except selenium.common.exceptions.NoSuchElementException:
                        pass

            # download game
            if self._freshDownloadNeeded(url, romName, filename, downloadTmpDir):
                Util.shellCall("/bin/rm -rf %s/*" % (downloadTmpDir))
                with open(os.path.join(downloadTmpDir, "ROM_NAME"), "w") as f:
                    f.write(romName)
                Util.wgetDownload(url, os.path.join(downloadTmpDir, filename))
            else:
                Util.wgetContinueDownload(url, os.path.join(downloadTmpDir, filename))
        except Exception:
            traceback.print_exc()
            return

        # save to target directory
        Util.forceDelete(targetDir)
        Util.ensureDir(os.path.dirname(targetDir))
        Util.shellCall("/bin/mv %s %s" % (downloadTmpDir, targetDir))
        self.p.print("%s %s downloaded." % (gameTypename, gameId))

    def _checkGame(self, gameTypename, gameId, gameUrl, targetDir, downloadTmpDir):
        self.p.print("%s %s checked." % (gameTypename, gameId))

    def _freshDownloadNeeded(self, romUrl, romName, filename, downloadTmpDir):
        fn = os.path.join(downloadTmpDir, "ROM_NAME")
        if not os.path.exists(fn):
            return True
        if Util.readFile(fn) != romName:
            return True
        if not os.path.exists(os.path.join(downloadTmpDir, filename)):
            return True
        return False

    def _getDownloadTmpDir(self, gameId):
        return os.path.join(self.dataDir, "_tmp_" + gameId.replace("/", "_"))


class MUtil:

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
    def isInBlackList(gameId, blackList):
        for bgId in blackList:
            if fnmatch.fnmatch(gameId, bgId):
                return True
        return False

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
    sock = MUtil.connect()
    try:
        Main().run(sock)
        MUtil.progress_changed(sock, 100)
    except Exception:
        MUtil.error_occured(sock, sys.exc_info())
        raise
    finally:
        sock.close()
