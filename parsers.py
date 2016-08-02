#!/usr/bin/python2
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import abc
import subprocess
import urllib2
from collections import namedtuple
from HTMLParser import HTMLParser

__author__ = "Nakoryakov Aleksey, Sysoev Roman"
__maintainer__ = "Nakoryakov Aleksey"
__license__ = "GPL 3.0"


FileInfo = namedtuple('FileInfo', 'filename link')


class BaseParser(HTMLParser, object):
    """Base parser. Stores parsed result in data property as list of tuples (filename, link)"""
    __metaclass__ = abc.ABCMeta

    def __init__(self):
        super(BaseParser, self).__init__()
        self._data = []

    @property
    def data(self):
        """List of fileinfos. (filename, link)"""
        return self._data


class DropboxParser(BaseParser):
    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        is_found_link = False
        href = ''
        for name, value in attrs:
            if name == 'class' and 'filename-link' in value:
                is_found_link = True
            elif name == 'href':
                href = value
        if is_found_link and href:
            self._process_filelink(href)

    def _process_filelink(self, href):
        escaped_fname = href.split('/')[-1].rsplit('?', 1)[0]
        url = href.rstrip('0') + '1'
        file_info = FileInfo(urllib2.unquote(escaped_fname).decode('utf-8'), url)
        self._data.append(file_info)
