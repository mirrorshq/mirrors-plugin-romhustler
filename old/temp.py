
class SeleniumChrome:

    def __init__(self, showUi, downloadDir=None):
        self.downloadDir = os.getcwd() if downloadDir is None else downloadDir

        options = selenium.webdriver.chrome.options.Options()
        if not showUi:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')                    # FIXME
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

    def gotoDownloadManagerAndGetDownloadInfo(self):
        # return (url, filename)

        # goto download manager page
        self.driver.get("chrome://downloads/")
        while self.driver.execute_script("return %s" % (self._downloadManagerSelector())) is None:
            time.sleep(1)
        while self.driver.execute_script("return %s" % (self._downloadFileSelector())) is None:
            time.sleep(1)

        # get information
        url = self.driver.execute_script("return %s.shadowRoot.querySelector('div#content  #file-link').href" % (self._downloadFileSelector()))
        filename = self.driver.execute_script("return %s.shadowRoot.querySelector('div#content  #file-link').text" % (self._downloadFileSelector()))

        # cancel download
        self.driver.execute_script("%s.shadowRoot.querySelector('cr-button[focus-type=\"cancel\"]').click()" % (self._downloadFileSelector()))

        return (url, filename)

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




# def gotoDownloadManagerAndWaitDownloadStart(self):
#     self.driver.get("chrome://downloads/")
#     while self.driver.execute_script("return %s" % (self._downloadManagerSelector())) is None:
#         time.sleep(1)
#     while self.driver.execute_script("return %s" % (self._downloadFileSelector())) is None:
#         print("None")
#         time.sleep(1)
#     self.downloadUrl = self.driver.execute_script("return %s.shadowRoot.querySelector('div#content  #file-link').href" % (self._downloadFileSelector()))
#     self.downloadFilePath = os.path.join(self.downloadDir, self.driver.execute_script("return %s.shadowRoot.querySelector('div#content  #file-link').text" % (self._downloadFileSelector())))

# def isInDownloadManager(self):
#     return self.driver.current_url == "chrome://downloads/"

# def getDownloadUrl(self):
#     return self.downloadUrl

# def getDownloadFilePath(self):
#     return self.downloadFilePath

# def getDownloadProgress(self):
#     try:
#         return self.driver.execute_script("return %s.shadowRoot.querySelector('#progress').value" % (self._downloadFileSelector()))
#     except selenium.common.exceptions.WebDriverException:
#         # it's weird that chrome auto close after download complete
#         # so this exception "selenium.common.exceptions.WebDriverException: Message: chrome not reachable" means progress 100
#         return 100

# def cancelDownload(self):
#     assert self.isInDownloadManager()
#     self.driver.execute_script("%s.shadowRoot.querySelector('cr-button[focus-type=\"cancel\"]').click()" % (self._downloadFileSelector()))

# def removeDownload(self):
#     self.driver.execute_script("%s.shadowRoot.querySelector('cr-icon-button').click()" % (self._downloadFileSelector()))

