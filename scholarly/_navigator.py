from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from ._proxy_generator import ProxyGenerator, MaxTriesExceededException, DOSException

from bs4 import BeautifulSoup

import codecs
import logging
import random
import time
import requests
from requests.exceptions import Timeout
from .publication_parser import _SearchScholarIterator
from .author_parser import AuthorParser
from .publication_parser import PublicationParser
from .data_types import Author, PublicationSource, ProxyMode

class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args,
                                                                 **kwargs)
        return cls._instances[cls]


class Navigator(object, metaclass=Singleton):
    """A class used to navigate pages on google scholar."""

    def __init__(self):
        super(Navigator, self).__init__()
        self.logger = logging.getLogger('scholarly')
        self._TIMEOUT = 5
        self.pm1 = ProxyGenerator()
        self._session1 = self.pm1.get_session()
        self._proxies1 = self.pm1.get_proxies()
        self.got_403 = False


    def set_logger(self, enable: bool):
        """Enable or disable the logger for google scholar."""

        self.logger.setLevel((logging.INFO if enable else logging.CRITICAL))

    def set_timeout(self, timeout: int):
        """Set timeout period in seconds for scholarly"""
        if timeout >= 0:
            self._TIMEOUT = timeout

    def use_proxy(self, pg1: ProxyGenerator):
        self.pm1 = pg1
        self._proxies1 = self.pm1.get_proxies()
        self._session1 = self.pm1.get_session()

    def _get_page(self, pagerequest: str) -> str:
        """Return the data from a webpage

        :param pagerequest: the page url
        :type pagerequest: str
        :returns: the text from a webpage
        :rtype: {str}
        """

        self.logger.info("Getting %s", pagerequest)
        resp = None
        proxies = self._proxies1
        session = self._session1

        try:
            resp = session.get(pagerequest, proxies=proxies, verify=False)

            if resp.status_code == 200:
                return resp.text
        
        except Exception as e:
                err = "Exception %s while fetching page: %s" % (type(e).__name__, e.args)
                self.logger.info(err)

    def _get_soup(self, url: str) -> BeautifulSoup:
        """Return the BeautifulSoup for a page on scholar.google.com"""
        html = self._get_page('https://scholar.google.com{0}'.format(url))
        html = html.replace(u'\xa0', u' ')
        res = BeautifulSoup(html, 'html.parser')

        if 'did not match any articles' in res.get_text():
            raise ValueError('Search did not match any articles')

        try:
            self.publib = res.find('div', id='gs_res_glb').get('data-sva')
        except Exception:
            pass
        return res

    def search_authors(self, url: str)->Author:
        """Generator that returns Author objects from the author search page"""
        soup = self._get_soup(url)

        author_parser = AuthorParser(self)
        while True:
            rows = soup.find_all('div', 'gsc_1usr')
            self.logger.info("Found %d authors", len(rows))
            for row in rows:
                yield author_parser.get_author(row)
            cls1 = 'gs_btnPR gs_in_ib gs_btn_half '
            cls2 = 'gs_btn_lsb gs_btn_srt gsc_pgn_pnx'
            next_button = soup.find(class_=cls1+cls2)  # Can be improved
            if next_button and 'disabled' not in next_button.attrs:
                self.logger.info("Loading next page of authors")
                url = next_button['onclick'][17:-1]
                url = codecs.getdecoder("unicode_escape")(url)[0]
                soup = self._get_soup(url)
            else:
                self.logger.info("No more author pages")
                break

    def search_publication(self, url: str,
                           filled: bool = False) -> PublicationParser:
        """Search by scholar query and return a single Publication object

        :param url: the url to be searched at
        :type url: str
        :param filled: Whether publication should be filled, defaults to False
        :type filled: bool, optional
        :returns: a publication object
        :rtype: {Publication}
        """
        soup = self._get_soup(url)
        publication_parser = PublicationParser(self)
        try:
            pub = publication_parser.get_publication(soup.find_all('div', 'gs_or')[0], PublicationSource.PUBLICATION_SEARCH_SNIPPET)
            if filled:
                pub = publication_parser.fill(pub)

        except Exception as e:
            raise RuntimeError(f"Error occurred in scholarly.publication_parser: {e}")

        return pub

    def search_publications(self, url: str) -> _SearchScholarIterator:
        """Returns a Publication Generator given a url

        :param url: the url where publications can be found.
        :type url: str
        :returns: An iterator of Publications
        :rtype: {_SearchScholarIterator}
        """
        return _SearchScholarIterator(self, url)

    def search_author_id(self, id: str, sections: list = [], sortby: str = "citedby", publication_limit: int = 0) -> Author:
        """Search by author ID and return a Author object
        :param id: the Google Scholar id of a particular author
        :type url: str
        :param sections: Select the sections that should be filled, defaults to ``[]``
        :type sections: list, optional
        :param sortby: if the object is an author, select the order of the citations in the author page. Either by 'citedby' or 'year'. Defaults to 'citedby'.
        :type sortby: string
        :param publication_limit: Select the max number of publications you want you want to fill for the author. Defaults to no limit.
        :type publication_limit: int
        :returns: an Author object
        :rtype: {Author}
        """
        author_parser = AuthorParser(self)
        res = author_parser.get_author(id)
        res = author_parser.fill(res, sections=sections, sortby=sortby, publication_limit=publication_limit)

        return res

    def search_organization(self, url: str, fromauthor: bool) -> list:
        """Generate instiution object from author search page.
           if no results are found and `fromuthor` is True, then use the first author from the search
           to get institution/organization name.
        """
        soup = self._get_soup(url)
        rows = soup.find_all('h3', 'gsc_inst_res')
        if rows:
            self.logger.info("Found institution")

        res = []
        for row in rows:
            res.append({'Organization': row.a.text, 'id': row.a['href'].split('org=', 1)[1]})

        if rows == [] and fromauthor is True:
            try:
                auth = next(self.search_authors(url))
                authorg = self.search_author_id(auth.id).organization
                authorg['fromauthor'] = True
                res.append(authorg)
            except Exception:
                res = []

        return res
