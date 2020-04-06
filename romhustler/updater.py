#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import glob
import time
import json
import shutil
import random
import socket
import tempfile
import subprocess
import selenium.common
import selenium.webdriver


PROGRESS_STAGE_1 = 50
PROGRESS_STAGE_2 = 50


def main():
    sock = _Util.connect()
    try:
        selfDir = os.path.dirname(os.path.realpath(__file__))
        popularGameListFile = os.path.join(selfDir, "games_popular.txt")
        badGameListFile = os.path.join(selfDir, "games_bad.txt")
        dataDir = sys.argv[1]
        logDir = sys.argv[2]
        isDebug = (sys.argv[3] == "1")
        mainUrl = "https://romhustler.org/roms"
        romUrlPrefix = "https://romhustler.org/rom"

        # download popular games
        gameIdList = _readGameListFile(popularGameListFile)
        i = 0
        for gameId in gameIdList:
            targetDir = os.path.join(dataDir, gameId)
            if not os.path.exists(targetDir):
                with _GameDownloader(isDebug) as obj:
                    try:
                        romName, romFile = obj.download(gameId, os.path.join(romUrlPrefix, gameId))
                        _Util.ensureDir(targetDir)
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
                        pass
            i += 1
            _Util.progress_changed(sock, PROGRESS_STAGE_1 * i // len(gameIdList))

        # download some games randomly
        gameIdList = _readGameListFromWebSite(mainUrl, dataDir, random.randint(10, 100),
                                              _readGameListFile(badGameListFile), isDebug)
        print(gameIdList)   # FIXME
        i = 0
        for gameId in gameIdList:
            targetDir = os.path.join(dataDir, gameId)
            with _GameDownloader(isDebug) as obj:
                try:
                    romName, romFile = obj.download(gameId, os.path.join(romUrlPrefix, gameId))
                    _Util.ensureDir(targetDir)
                    shutil.move(romFile, targetDir)
                    print("Game %s downloaded." % (gameId))
                except _GameDownloader.BadUrlError:
                    print("Game %s does not exists." % (gameId))
                except _GameDownloader.NotAvailableError:
                    print("Game %s is not available for download." % (gameId))
                except _GameDownloader.DownloadFailedError:
                    print("Game %s is not successfully downloaded." % (gameId))
                except Exception:
                    print("Unknown error occured when downloading game %s." % (gameId))
                    pass
            i += 1
            _Util.progress_changed(sock, PROGRESS_STAGE_1 + PROGRESS_STAGE_2 * i // len(gameIdList))

        # report full progress
        _Util.progress_changed(sock, 100)
    except Exception:
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


def _readGameListFromWebSite(mainUrl, dataDir, gameCount, blackList, isDebug):
    gameIdList = []
    with _SeleniumWebDriver(isDebug) as driver:
        driver.get(mainUrl)                                                         # get first page
        while True:
            for atag in driver.find_elements_by_xpath('//div[@class="title"]/a'):
                gameId = "/".join(atag.get_attribute("href").split("/")[-2:])       # "https://romhustler.org/rom/ps2/god-of-war-usa" -> "ps2/god-of-war-usa"
                if not os.path.exists(os.path.join(dataDir, gameId)):
                    gameIdList.append(gameId)
                    if len(gameIdList) >= gameCount:
                        return gameIdList
            time.sleep(1.0)
            atag = driver.find_element_by_xpath('//a[text()="next>"]')              # get next page
            atag.click()


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
        _Util.ensureDir(self.downloadTmpDir)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        shutil.rmtree(self.downloadTmpDir)
        del self.downloadTmpDir
        del self.isDebug

    def download(self, gameId, gameUrl):
        with _SeleniumWebDriver(self.isDebug, self.downloadTmpDir) as driver:
            # load game page
            driver.get(gameUrl)
            if driver.current_url != gameUrl:
                raise self.BadUrlError()

            # check if we can download this rom
            try:
                atag = driver.find_element_by_xpath("//div[contains(text(), \"download is disabled\")]")
                raise self.NotAvailableError()
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
            romFile = self._waitDownloadComplete()

            return (romName, romFile)

    def _waitDownloadComplete(self):
        crDwnFileLastName = ""
        crDwnFileLastSize = -1
        crDwnFileSizeEqualCount = 0
        noFileCount = 0

        while True:
            flist = glob.glob(os.path.join(self.downloadTmpDir, "*.crdownload"))
            if len(flist) > 0:
                if crDwnFileLastName == flist[0]:
                    sz = os.path.getsize(flist[0])
                    if crDwnFileLastSize == sz:
                        if crDwnFileSizeEqualCount > 30:
                            raise self.DownloadFailedError()    # file size have not changed for 30s, download failed
                        crDwnFileSizeEqualCount += 1
                    else:
                        crDwnFileLastSize = sz
                        crDwnFileSizeEqualCount = 0
                else:
                    crDwnFileLastName = flist[0]
                    crDwnFileLastSize = os.path.getsize(crDwnFileLastName)
            else:
                flist = os.listdir(self.downloadTmpDir)
                if len(flist) > 0:
                    return os.path.join(self.downloadTmpDir, flist[0])
                else:
                    if noFileCount > 30:
                        raise self.DownloadFailedError()
                    noFileCount += 1
            time.sleep(1)


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


class _SeleniumWebDriver:

    def __init__(self, isDebug, downloadDir=None):
        options = selenium.webdriver.chrome.options.Options()
        if not isDebug:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_experimental_option("prefs", {
            "download.default_directory": os.getcwd() if downloadDir is None else downloadDir,
            "download.prompt_for_download": False,
        })
        self.driver = selenium.webdriver.Chrome(options=options)

    def __enter__(self):
        return self.driver

    def __exit__(self, type, value, traceback):
        self.driver.quit()
        self.driver = None


###############################################################################

if __name__ == "__main__":
    main()
