#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import time
import json
import shutil
import random
import socket
import tempfile
import subprocess
import selenium.common
import selenium.webdriver

POPULAR_GAME_PAGE_COUNT = 10

PROGRESS_STAGE_1 = 50
PROGRESS_STAGE_2 = 50


def main():
    sock = Util.connect()
    try:
        selfDir = os.path.dirname(os.path.realpath(__file__))
        classicGameListFile = os.path.join(selfDir, "games_classic.txt")
        badGameListFile = os.path.join(selfDir, "games_bad.txt")
        dataDir = sys.argv[1]
        logDir = sys.argv[2]
        isDebug = (sys.argv[3] == "1")
        mainUrl = "https://romhustler.org/roms"
        romUrlPrefix = "https://romhustler.org/rom"

        # download classic games
        gameIdList = _readGameListFile(classicGameListFile)
        i = 0
        for gameId in gameIdList:
            targetDir = os.path.join(dataDir, gameId)
            if not os.path.exists(targetDir):
                with _GameDownloader(isDebug) as obj:
                    try:
                        romName, romUrl, romFile = obj.download(gameId, os.path.join(romUrlPrefix, gameId))
                        Util.ensureDir(targetDir)
                        shutil.move(romFile, targetDir)
                        print("Classic game %s downloaded." % (gameId))
                    except _GameDownloader.BadUrlError:
                        print("Classic game %s does not exists." % (gameId))
                    except _GameDownloader.NotAvailableError:
                        print("Classic game %s is not available for download." % (gameId))
                    except _GameDownloader.DownloadFailedError:
                        print("Classic game %s is not successfully downloaded." % (gameId))
                    except Exception:
                        print("Unknown error occured when downloading classic game %s." % (gameId))
                        raise
            i += 1
            Util.progress_changed(sock, PROGRESS_STAGE_1 * i // len(gameIdList))

        # download popular games
        if Util.getInitOrUpdate():
            gameIdList = _readGameListFromWebSite(mainUrl, dataDir, POPULAR_GAME_PAGE_COUNT,
                                                  _readGameListFile(badGameListFile), isDebug)
            i = 0
            for gameId in gameIdList:
                targetDir = os.path.join(dataDir, gameId)
                if not os.path.exists(targetDir):
                    with _GameDownloader(isDebug) as obj:
                        try:
                            romName, romUrl, romFile = obj.download(gameId, os.path.join(romUrlPrefix, gameId))
                            Util.ensureDir(targetDir)
                            shutil.move(romFile, targetDir)
                            print("Popular game %s downloaded." % (gameId))
                        except _GameDownloader.BadUrlError:
                            print("Popular game %s does not exists." % (gameId))
                        except _GameDownloader.NotAvailableError:
                            print("Popular game %s is not available for download." % (gameId))
                        except _GameDownloader.DownloadFailedError:
                            print("Popular game %s is not successfully downloaded." % (gameId))
                        except Exception:
                            print("Unknown error occured when downloading popular game %s." % (gameId))
                            raise
                i += 1
                Util.progress_changed(sock, PROGRESS_STAGE_1 + PROGRESS_STAGE_2 * i // len(gameIdList))

        # report full progress
        Util.progress_changed(sock, 100)
    except Exception:
        Util.error_occured(sock, sys.exc_info())
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


def _readGameListFromWebSite(mainUrl, dataDir, pageCount, blackList, isDebug):
    gameIdList = []
    with SeleniumChrome(isDebug) as cobj:
        cobj.driver.get(mainUrl)                                                        # get first page
        for i in range(0, pageCount):
            for atag in cobj.driver.find_elements_by_xpath('//div[@class="title"]/a'):
                gameId = "/".join(atag.get_attribute("href").split("/")[-2:])           # "https://romhustler.org/rom/ps2/god-of-war-usa" -> "ps2/god-of-war-usa"
                gameIdList.append(gameId)
            time.sleep(1.0)
            for atag in cobj.driver.find_elements_by_xpath("//a"):
                if atag.text == "next>":                                                # find_element_by_xpath('//a[text()="next>"]') has no effect, don't know why
                    atag.click()
                    break
    return gameIdList


class _GameDownloader:

    class BadUrlError(Exception):
        pass

    class NotAvailableError(Exception):
        pass

    class DownloadFailedError(Exception):
        pass

    def __init__(self, isDebug):
        self.isDebug = isDebug
        self.downloadTmpDir = tempfile.mkdtemp()
        Util.ensureDir(self.downloadTmpDir)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        shutil.rmtree(self.downloadTmpDir)
        del self.downloadTmpDir
        del self.isDebug

    def download(self, gameId, gameUrl):
        with SeleniumChrome(self.isDebug, self.downloadTmpDir) as cobj:
            # load game page
            cobj.driver.get(gameUrl)
            if cobj.driver.current_url != gameUrl:
                raise self.BadUrlError()

            # check if we can download this rom
            try:
                atag = cobj.driver.find_element_by_xpath("//div[contains(text(), \"download is disabled\")]")
                raise self.NotAvailableError()
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

            # wait download complete
            cobj.gotoDownloadManagerAndWaitDownloadStart()
            for i in range(0, 60):
                time.sleep(1)
                print("1 %d" % (cobj.getDownloadProgress()))
                if cobj.getDownloadProgress() >= 100:
                    return (romName, cobj.getDownloadUrl(), cobj.getDownloadFilePath())
            if cobj.getDownloadProgress() >= 50:
                while cobj.getDownloadProgress() < 100:
                    print("2 %d" % (cobj.getDownloadProgress()))
                    time.sleep(1)
                return (romName, cobj.getDownloadUrl(), cobj.getDownloadFilePath())

            # use wget to download FIXME
            while cobj.getDownloadProgress() < 100:
                print("3 %d" % (cobj.getDownloadProgress()))
                time.sleep(1)
            return (romName, cobj.getDownloadUrl(), cobj.getDownloadFilePath())


class Util:

    @staticmethod
    def getInitOrUpdate():
        if len(sys.argv) == 6:
            return True
        elif len(sys.argv) == 7:
            return False
        else:
            print(len(sys.argv))
            assert False

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

    @staticmethod
    def error_occured(sock, exc_info):
        sock.send(json.dumps({
            "message": "error_occured",
            "data": {
                "exc_info": "abc",
            },
        }).encode("utf-8"))

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


class SeleniumChrome:

    def __init__(self, isDebug, downloadDir=None):
        self.downloadDir = os.getcwd() if downloadDir is None else downloadDir

        options = selenium.webdriver.chrome.options.Options()
        if not isDebug:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')                    # FIXME
        options.add_argument("--disable-gpu")
        options.add_experimental_option("prefs", {
            "download.default_directory": self.downloadDir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": False,
            "safebrowsing.disable_download_protection": True,
        })
        self.driver = selenium.webdriver.Chrome(options=options)

        self._enableDownloadInHeadlessChrome()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.driver.quit()
        self.driver = None

    def scrollToPageEnd(self):
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")

    def gotoDownloadManagerAndWaitDownloadStart(self):
        self.driver.get("chrome://downloads/")
        while self.driver.execute_script("return %s" % (self._downloadManagerSelector())) is None:
            time.sleep(1)
        while self.driver.execute_script("return %s" % (self._downloadFileSelector())) is None:
            print("None")
            time.sleep(1)
        self.downloadUrl = self.driver.execute_script("return %s.shadowRoot.querySelector('div#content  #file-link').href" % (self._downloadFileSelector()))
        self.downloadFilePath = os.path.join(self.downloadDir, self.driver.execute_script("return %s.shadowRoot.querySelector('div#content  #file-link').text" % (self._downloadFileSelector())))

    def isInDownloadManager(self):
        return self.driver.current_url == "chrome://downloads/"

    def getDownloadUrl(self):
        return self.downloadUrl

    def getDownloadFilePath(self):
        return self.downloadFilePath

    def getDownloadProgress(self):
        try:
            return self.driver.execute_script("return %s.shadowRoot.querySelector('#progress').value" % (self._downloadFileSelector()))
        except selenium.common.exceptions.WebDriverException:
            # it's weird that chrome auto close after download complete
            # so we get this exception "selenium.common.exceptions.WebDriverException: Message: chrome not reachable"
            return 100

    def cancelDownload(self):
        assert self.isInDownloadManager()
        self.driver.execute_script("%s.shadowRoot.querySelector('cr-button[focus-type=\"cancel\"]').click()" % (self._downloadFileSelector()))

    def removeDownload(self):
        self.driver.execute_script("%s.shadowRoot.querySelector('cr-icon-button').click()" % (self._downloadFileSelector()))

    def _enableDownloadInHeadlessChrome(self):
        """
        there is currently a "feature" in chrome where
        headless does not allow file download: https://bugs.chromium.org/p/chromium/issues/detail?id=696481
        This method is a hacky work-around until the official chromedriver support for this.
        Requires chrome version 62.0.3196.0 or above.
        """

        # add missing support for chrome "send_command"  to selenium webdriver
        self.driver.command_executor._commands["send_command"] = ("POST", '/session/$sessionId/chromium/send_command')

        params = {'cmd': 'Page.setDownloadBehavior', 'params': {'behavior': 'allow', 'downloadPath': self.downloadDir}}
        self.driver.execute("send_command", params)

    def _downloadManagerSelector(self):
        return "document.querySelector('downloads-manager')"

    def _downloadFileSelector(self):
        return "%s.shadowRoot.querySelector('#downloadsList downloads-item')" % (self._downloadManagerSelector())


###############################################################################

if __name__ == "__main__":
    main()
