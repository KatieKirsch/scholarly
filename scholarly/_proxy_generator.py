from typing import Callable
from fp.fp import FreeProxy
import random
import logging
import time
import requests
import httpx
import tempfile
import urllib3

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from selenium.webdriver.support.wait import WebDriverWait, TimeoutException
from urllib.parse import urlparse
from contextlib import contextmanager
from deprecated import deprecated
try:
    import stem.process
    from stem import Signal
    from stem.control import Controller
except ImportError:
    stem = None

try:
    from fake_useragent import UserAgent
    FAKE_USERAGENT = True
except Exception:
    FAKE_USERAGENT = False
    DEFAULT_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36'

from .data_types import ProxyMode


class DOSException(Exception):
    """DOS attack was detected."""


class MaxTriesExceededException(Exception):
    """Maximum number of tries by scholarly reached"""


class ProxyGenerator(object):
    def __init__(self):
        # setting up logger
        self.logger = logging.getLogger('scholarly')

        self._proxy_works = False
        self.proxy_mode = None
        self._proxies = {}
        self._session = None
        self._TIMEOUT = 30

    def get_session(self):
        session = requests.Session()

        # Define the retry strategy
        retry_strategy = urllib3.util.Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504]
        )

        # Create an HTTP adapter with the retry strategy and mount it to session
        session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

        return session
    
    def get_proxies(self):
        return self._proxies

    def ZenrowsAPI(self, API_KEY, premium=False):
        """
        Sets up a proxy using ZenRows API

        :Example::
            >>> pg = ProxyGenerator()
            >>> pg.ZenrowsAPI(API_KEY)

        :param API_KEY: API Key value.
        :type API_KEY: string
        :type premium: bool, optional by default False
        """

        self._API_KEY = API_KEY
        
        if premium:
            proxy = f'http://{API_KEY}:premium_proxy=true@proxy.zenrows.com:8001'
        else:
            proxy = f'http://{API_KEY}:@proxy.zenrows.com:8001'

        # Suppress the unavoidable insecure request warnings with ZenRowsAPI
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.proxy_mode = ProxyMode.ZENROWSAPI
        self.logger.info(f"Proxy setup successfully: http={proxy} https={proxy}")
        self._proxies = {'http': proxy, 'https': proxy}

    # A context manager to suppress the misleading traceback from UserAgent()
    # Based on https://thesmithfam.org/blog/2012/10/25/temporarily-suppress-console-output-in-python/
    @staticmethod
    @contextmanager
    def _suppress_logger(loggerName: str, level=logging.CRITICAL):
        """Temporarily suppress logging output from a specific logger.
        """
        logger = logging.getLogger(loggerName)
        original_level = logger.getEffectiveLevel()
        logger.setLevel(level)
        try:
            yield
        finally:
            logger.setLevel(original_level)
