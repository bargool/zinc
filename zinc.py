#!/usr/bin/python2
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import os
import shutil
import subprocess
import tempfile
from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError

from dialog import Dialog

from parsers import DropboxParser

__author__ = "Nakoryakov Aleksey, Sysoev Roman"
__version__ = "0.3.5"
__maintainer__ = "Nakoryakov Aleksey"
__license__ = "GPL 3.0"


class Singleton(type):
    """Metaclass for singleton pattern"""
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__()
        return cls._instances[cls]


class Settings(object):
    """Class to handle settings. We don't need more than one instance"""
    __metaclass__ = Singleton

    class DEFAULTS:
        DOWNLOAD_FOLDER = os.path.expanduser('~/Download/')
        DOWNLOAD_URL = 'https://www.dropbox.com/sh/3aycxk7war34ijo/AADeK2sC0IwbNEUtPnXXaOura?dl=0'

    def __init__(self):
        self._app_home_directory = os.path.expanduser('~/.zinc/')
        self._settings_filename = 'settings.cfg'
        self._read_config()

    def _read_config(self):
        self._config = SafeConfigParser()
        settings_filepath = os.path.join(self.app_home_directory, self._settings_filename)
        if not os.path.exists(settings_filepath):
            self._write_settings()
        self._config.read(settings_filepath)

    def _write_settings(self):
        if not os.path.exists(self.app_home_directory):
            os.makedirs(self.app_home_directory)
        self._config.add_section('General')
        self._config.set('General', 'logging_debug', 'no')
        self._config.add_section('Dropbox')
        self._config.set('Dropbox', 'default', self.DEFAULTS.DOWNLOAD_URL)
        self._config.add_section('Folders')
        self._config.set('Folders', 'download_folder', self.DEFAULTS.DOWNLOAD_FOLDER)
        settings_filepath = os.path.join(self.app_home_directory, self._settings_filename)
        with open(settings_filepath, 'wb') as configfile:
            self._config.write(configfile)

    @property
    def app_home_directory(self):
        return self._app_home_directory

    @property
    def download_path(self):
        path = self._config.get('Folders', 'download_folder')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def repos(self):
        return self._config.items('Dropbox')

    @property
    def do_logging(self):
        try:
            return self._config.getboolean('General', 'logging_debug')
        except (NoSectionError, NoOptionError):
            return False


def chunk_read_write(process, total_size, f_obj, dialog, chunk_size=8192):
    """Read process stdout by chunks and write that chunks to file-like object
    :param process: process which stdout to read
    :param total_size: expected total size just for progress reporting
    :param f_obj: file-like object to write
    :param dialog: dialog to report about progress
    :param chunk_size: size of chunks to read-write
    """
    bytes_so_far = 0
    while True:
        chunk = process.stdout.read(chunk_size)
        if not chunk:
            break
        bytes_so_far += len(chunk)
        f_obj.write(chunk)
        percent = int(bytes_so_far * 100.0 / total_size)
        dialog.gauge_update(percent)
    process.wait()


def download_file(url, directory_to, filename, dialog):
    """Download single file from url"""
    path = os.path.join(directory_to, filename)
    filesize = get_filesize(url)
    process = subprocess.Popen('wget --no-check-certificate -qO- ' + url,
                               stdout=subprocess.PIPE,
                               bufsize=0,
                               shell=True)
    dialog.gauge_start("Downloading {} of {}".format(sizeof_fmt(filesize), filename))
    with tempfile.NamedTemporaryFile() as f:
        chunk_read_write(process, filesize, f, dialog=dialog)
        f.seek(0)
        shutil.copy(f.name, path)
    dialog.gauge_stop()


def is_file_exists(filename):
    """Check if file exists in download directory"""
    download_directory = Settings().download_path
    local_filename = os.path.join(download_directory, filename)
    return os.path.exists(local_filename) and os.path.getsize(local_filename)


def choose_files(file_urls, dialog):
    """Choose files to download via dialog"""
    items = [(url, filename, False) for filename, url in file_urls]
    result = dialog.buildlist("Choose files to download",
                              items=items,
                              visit_items=True, help_status=False)
    return result[1] if result[0] == dialog.DIALOG_OK else []


def get_filesize(url):
    """Get size of file at url by simple HEAD request"""
    process = subprocess.Popen('wget --no-check-certificate --spider -q -S -O - ' + url,
                               stderr=subprocess.PIPE,
                               bufsize=0,
                               shell=True)
    content_length_line = next((line for line in process.stderr.readlines()
                                if 'Content-Length:' in line))
    res = int(content_length_line.replace('Content-Length:', '').strip())
    process.wait()
    return res


def sizeof_fmt(num, suffix='B'):
    for unit in ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi'):
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def process_filelist(dialog, url_list):
    """Recursively process list of urls. The recursion is just for convenience of user dialogs
    :param dialog: dialog object
    :param url_list: list of urls to process
    """
    file_urls = [(filename, url) for filename, url in url_list if not is_file_exists(filename)]
    if file_urls:
        download_urls = choose_files(file_urls, dialog)
        if download_urls:
            for url in download_urls:
                directory = settings.download_path
                fname = next(f for f, u in file_urls if u == url)
                download_file(url, directory, fname, dialog)
            # This recursion is just for convenience of user dialogs
            if dialog.yesno("All files downloaded. Want to choose more?") == dialog.DIALOG_OK:
                process_filelist(dialog, url_list)
    else:
        dialog.msgbox("Nothing to download")


def choose_repo(repos, dialog):
    """Choose repo from repos list via dialog"""
    dialog_result = dialog.menu("Choose repo", choices=repos, cancel_label="Exit")
    if dialog_result[0] == dialog.DIALOG_OK:
        return next((uri for name, uri in repos if name == dialog_result[1]))
    else:
        return None


def process_repos(dialog, repos):
    """
    Recursively choose repo and start processing.
    The recursion is just for convenience of user dialogs
    """
    if len(repos) == 1:
        filelist_url = repos[0][1]
    else:
        filelist_url = choose_repo(repos, dialog)
    if not filelist_url:
        dialog.msgbox("OK! Bye!")
        return
    dialog.infobox("Requesting filelist...")
    logging.debug("Downloading filelist from %s", filelist_url)
    process = subprocess.Popen('wget --no-check-certificate -qO- ' + filelist_url,
                               stdout=subprocess.PIPE,
                               shell=True)
    content = process.stdout.read()
    if not content:
        dialog.msgbox("No filelist! Check internet connection!")
        return
    with DropboxParser() as parser:
        parser.feed(content)
        logging.debug("Found %d file links", len(parser.data))
        process_filelist(dialog, parser.data)
    if len(repos) != 1 and dialog.yesno("Choose another repo?", no_label="Exit") == dialog.DIALOG_OK:
        process_repos(dialog, repos)


def main():
    dialog = Dialog()
    dialog.add_persistent_args(["--backtitle", "ZiNC is Not a Cloud. v%s" % __version__])
    repos = settings.repos
    process_repos(dialog, repos)


if __name__ == '__main__':
    settings = Settings()
    log_level = logging.DEBUG if settings.do_logging else logging.CRITICAL
    log_filepath = os.path.join(settings.app_home_directory, 'zinc.log')
    logging.basicConfig(filename=os.path.expanduser(log_filepath),
                        filemode='w+',
                        level=log_level,
                        format='%(asctime)s : %(levelname)-8s : %(message)s')
    main()
