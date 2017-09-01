#MIT License
#
#Copyright (c) 2017 Tom van Ommeren
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

import sublime
import sublime_plugin
import os
import subprocess
from .util import *
from .event_hub import EventHub
from .client import Client
import threading
import json
from collections import OrderedDict
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import pathname2url
from urllib.request import url2pathname
from .request import Request
from .notification import Notification

client = None


# TODO: this should be per-window ?
document_states = {}  # type: Dict[str, DocumentState]


class DocumentState:
    """Stores version count for documents open in a language service"""
    def __init__(self, path: str) -> 'None':
        self.path = path
        self.version = 0

    def inc_version(self):
        self.version += 1
        return self.version


def get_document_state(path: str) -> DocumentState:
    if path not in document_states:
        document_states[path] = DocumentState(path)
    return document_states[path]

def notify_did_open(view: sublime.View):
    if client and view and view.file_name():
        view.settings().set("show_definitions", False)
        if view.file_name() not in document_states:
            get_document_state(view.file_name())
            params = {
                "textDocument": {
                    "uri": filename_to_uri(view.file_name()),
                    "languageId": 'apex',
                    "text": view.substr(sublime.Region(0, view.size()))
                }
            }
            client.send_notification(Notification.didOpen(params))


def notify_did_close(view: sublime.View):
    if view.file_name() in document_states:
        del document_states[view.file_name()]
        if client:
            params = {"textDocument": {"uri": filename_to_uri(view.file_name())}}
            client.send_notification(Notification.didClose(params))


def notify_did_save(view: sublime.View):
    if view.file_name() in document_states:
        if client:
            params = {"textDocument": {"uri": filename_to_uri(view.file_name())}}
            client.send_notification(Notification.didSave(params))
    else:
        debug('document not tracked', view.file_name())

pending_buffer_changes = dict()  # type: Dict[int, Dict]


def purge_did_change(buffer_id: int, buffer_version=None):
    if buffer_id not in pending_buffer_changes:
        return

    pending_buffer = pending_buffer_changes.get(buffer_id)

    if pending_buffer:
        if buffer_version is None or buffer_version == pending_buffer["version"]:
            notify_did_change(pending_buffer["view"])

def queue_did_change(view: sublime.View):
    buffer_id = view.buffer_id()
    buffer_version = 1
    pending_buffer = None
    if buffer_id in pending_buffer_changes:
        pending_buffer = pending_buffer_changes[buffer_id]
        buffer_version = pending_buffer["version"] + 1
        pending_buffer["version"] = buffer_version
    else:
        pending_buffer_changes[buffer_id] = {
            "view": view,
            "version": buffer_version
        }
        
    sublime.set_timeout_async(
        lambda: purge_did_change(buffer_id, buffer_version), 500)


def notify_did_change(view: sublime.View):
    if view.buffer_id() in pending_buffer_changes:
        del pending_buffer_changes[view.buffer_id()]
    if client:
        document_state = get_document_state(view.file_name())
        uri = filename_to_uri(view.file_name())
        params = {
            "textDocument": {
                "uri": uri,
                # "languageId": config.languageId, clangd does not like this field, but no server uses it?
                "version": document_state.inc_version(),
            },
            "contentChanges": [{
                "text": view.substr(sublime.Region(0, view.size()))
            }]
        }
        client.send_notification(Notification.didChange(params))



document_sync_initialized = False
def initialize_document_sync(text_document_sync_kind):
    global document_sync_initialized
    if document_sync_initialized:
        return
    document_sync_initialized = True
    # TODO: hook up events per scope/client
    EventHub.subscribe('on_load_async', notify_did_open)
    EventHub.subscribe('on_activated_async', notify_did_open)
    EventHub.subscribe('on_modified_async', queue_did_change)
    EventHub.subscribe('on_post_save_async', notify_did_save)
    EventHub.subscribe('on_close', notify_did_close)


didopen_after_initialize = False

def handle_initialize_result(result, client, window, config):
    global didopen_after_initialize
    capabilities = result.get("capabilities")
    client.set_capabilities(capabilities)

    # TODO: These handlers is already filtered by syntax but does not need to
    # be enabled 2x per client
    # Move filtering?
    document_sync = capabilities.get("textDocumentSync")
    if document_sync:
        initialize_document_sync(document_sync)

    EventHub.subscribe('document.diagnostics', handle_diagnostics)
    EventHub.subscribe('on_close', remove_diagnostics)
    for view in didopen_after_initialize:
        notify_did_open(view)
    if show_status_messages:
        window.status_message("{} initialized".format(config.name))
    didopen_after_initialize = list()


def handle_initialize_result(result, client):
    global didopen_after_initialize
    capabilities = result.get("capabilities")
    client.set_capabilities(capabilities)
    document_sync = capabilities.get("textDocumentSync")
    initialize_document_sync(document_sync)

    for view in didopen_after_initialize:
        notify_did_open(view)
    debug('init complete')
    didopen_after_initialize = list()


def deleteDbIfExists():
    try:
        dx_folder = dxProjectFolder()
        if len(dx_folder) > 0:
            db_path = os.path.join(dx_folder, '.sfdx', 'tools', 'apex.db')
            if os.path.isfile(db_path):
                os.remove(db_path)
                debug('db deleted')
    except Exception as e:
        debug("db not deleted")


def start_server():
    deleteDbIfExists()
    working_dir = os.path.join(get_plugin_folder(), 'apex-jorje-lsp.jar')
    java_cmd = 'java'
    java_path = get_setting('java_path')
    debug(java_path)
    if java_path != '':
        java_cmd = os.path.join(java_path, java_cmd)
    args = [java_cmd, '-cp', working_dir, '-Ddebug.internal.errors=true','-Ddebug.semantic.errors=false',
            'apex.jorje.lsp.ApexLanguageServerLauncher']
    debug("starting " + str(args))
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()  # type: ignore
        si.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW  # type: ignore
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=dxProjectFolder(),
            startupinfo=si)
        return Client(process)

    except Exception as err:
        debug(err)


def start_client():
    global client
    client = start_server()
    if not client:
        debug("Could not start language server")
        return
    initializeParams = {
        "processId": client.process.pid,
        "rootPath": dxProjectFolder(),
        "capabilities": {
            "textDocument": {
                "completion": {
                    "completionItem": {
                        "snippetSupport": True
                    }
                }
            }
        }
    }
    client.send_request(
        Request.initialize(initializeParams),
        lambda result: handle_initialize_result(result, client))
    return client
