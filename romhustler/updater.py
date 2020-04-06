#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import glob
import time
import json
import shutil
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
        popularGameListFile = os.path.join(selfDir, "games_popular.txt")
        badGameListFile = os.path.join(selfDir, "games_bad.txt")
        dataDir = sys.argv[1]
        downloadTmpDir = os.path.join(dataDir, "_tmp")
        logDir = sys.argv[3]
        isDebug = os.environ.get("MIRRORS_PLUGIN_DEBUG") is not None and os.environ.get("MIRRORS_PLUGIN_DEBUG") != "0"
        mainUrl = "https://romhustler.org/roms"

        # download popular games
        gameIdList = _readGameListFile(popularGameListFile)
        i = 0
        for gameId in gameIdList:
            targetDir = os.path.join(dataDir, gameId)
            if not os.path.exists(targetDir):
                _Util.ensureDir(downloadTmpDir)
                romName, romFile = _downloadOneGame(gameId, os.path.join(mainUrl, gameId), isDebug, downloadTmpDir)
                if romName is not None:
                    # update target directory
                    _Util.ensureDir(targetDir)
                    os.rename(romFile, targetDir)
                    print("Popular game %s downloaded." % (gameId))
                else:
                    # download is not available
                    print("Popular game %s is not available for download." % (gameId))
                    pass
                shutil.rmtree(downloadTmpDir)
            i += 1
            _Util.progress_changed(sock, PROGRESS_STAGE_1 * i // len(gameIdList))

        # download or update some games randomly
        gameNumber = random.randint(10, 100)
        i = 0

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


def _downloadOneGame(gameId, gameUrl, isDebug, downloadTmpDir):
    with _SeleniumWebDriver(isDebug, downloadTmpDir) as driver:
        # load game page
        driver.get(gameUrl)

        # check if we can download this rom
        try:
            atag = driver.find_element_by_xpath("//div[contains(text(), \"download is disabled\")]")
            return (None, None)
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
        romFile = os.path.join(downloadTmpDir, os.listdir(downloadTmpDir)[0])

        return (romName, romFile)


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
