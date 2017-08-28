﻿import os
import subprocess
import threading
import time
import json
import sublime
import sublime_plugin
import time
import dxmate.lib.util as util
from .logger import log
from . import json_helpers
from . import global_vars

# queue module name changed from Python 2 to 3
if int(sublime.version()) < 3000:
    import Queue as queue
else:
    import queue


class CommClient(object):

    def started(self): pass

    def postCmd(self, cmd): pass

    def sendCmd(self, cmd, cb): pass

    def sendCmdSync(self, cmd): pass

    def sendCmdAsync(self, cmd, cb): pass


class NodeCommClient(CommClient):
    __CONTENT_LENGTH_HEADER = b"Content-Length: "

    def __init__(self):
        self.server_proc = None

        # create event handler maps
        self.event_handlers = dict()

        # create response and event queues
        self.msgq = queue.Queue()
        self.postq = queue.Queue()
        self.asyncReq = {}

        self.debug_proc = None
        self.breakpoints = []

        post_thread = threading.Thread(
            target=NodeCommClient.monitorPostQueue, args=(self,))
        post_thread.daemon = True
        post_thread.start()

    def makeTimeoutMsg(self, cmd, seq):
        jsonDict = json_helpers.decode(cmd)
        timeoutMsg = {
            "seq": 0,
            "type": "response",
            "success": False,
            "request_seq": seq,
            "command": jsonDict["command"],
            "message": "timeout"
        }
        return timeoutMsg

    def add_event_handler(self, event_name, cb):
        event_handlers = self.event_handlers
        if event_name not in event_handlers:
            event_handlers[event_name] = []
        if cb not in event_handlers[event_name]:
            event_handlers[event_name].append(cb)

    def started(self):
        return self.server_proc is not None

    # work in progress
    def addBreakpoint(self, file, line):
        self.breakpoints.append((file, line))

    # work in progress
    def debug(self, file):
        # TODO: msg if already debugging
        self.debug_proc = subprocess.Popen(["node", "--debug", file],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def sendCmd(self, cmd, cb, seq):
        """
        send single-line command string; no sequence number; wait for response
        this assumes stdin/stdout; for TCP, need to add correlation with sequence numbers
        """
        if self.postCmd(cmd):
            reqSeq = -1
            try:
                while reqSeq < seq:
                    data = self.msgq.get(True, 1)
                    dict = json_helpers.decode(data)
                    reqSeq = dict['request_seq']
                if cb:
                    cb(dict)
            except queue.Empty:
                print("queue timeout")
                if (cb):
                    cb(self.makeTimeoutMsg(cmd, seq))
        else:
            if (cb):
                cb(self.makeTimeoutMsg(cmd, seq))

    def sendCmdAsync(self, cmd, cb, seq):
        """
        Sends the command and registers a callback
        """
        print('tscmd==> ', cmd)
        if self.postCmd(cmd):
            self.asyncReq[seq] = cb

    def sendCmdSync(self, cmd, seq):
        """
        Sends the command and wait for the result and returns it
        """
        if self.postCmd(cmd):
            reqSeq = -1
            try:
                while reqSeq < seq:
                    data = self.msgq.get(True, 2)
                    dict = json_helpers.decode(data)
                    reqSeq = dict['request_seq']
                return dict
            except queue.Empty:
                print("queue timeout")
                return self.makeTimeoutMsg(cmd, seq)
        else:
            return self.makeTimeoutMsg(cmd, seq)

    def monitorPostQueue(self):
        """
        Monitor queue and post commands asynchronously
        """
        while True:
            cmd = self.postq.get(True) + "\n"
            if not self.server_proc:
                log.error("can not send request; node process not running")
            else:
                st = time.time()
                self.server_proc.stdin.write(cmd.encode())
                self.server_proc.stdin.flush()
                log.debug("command posted, elapsed %.3f sec" %
                          (time.time() - st))

    def postCmd(self, cmd):
        """
        Post command to server; no response needed
        """
        log.debug('Posting command: {0}'.format(cmd))
        if not self.server_proc:
            log.error("can not send request; node process not running")
            return False
        self.postq.put_nowait(cmd)
        return True

    @staticmethod
    def read_msg(stream, msgq, asyncReq, proc, asyncEventHandlers):
        """
        Reader thread helper.
        Return True to indicate the wish to stop reading the next message.
        """
        state = "init"
        body_length = 0
        while state != "body":
            header = stream.readline().strip()
            if len(header) == 0:
                if state == 'init':
                    # log.info('0 byte line in stream when expecting header')
                    return proc.poll() is not None
                else:
                    # Done reading header
                    state = "body"
            else:
                state = 'header'
                if header.startswith(NodeCommClient.__CONTENT_LENGTH_HEADER):
                    body_length = int(
                        header[len(NodeCommClient.__CONTENT_LENGTH_HEADER):])

        if body_length > 0:
            data = stream.read(body_length)
            log.debug('Read body of length: {0}'.format(body_length))
            data_json = data.decode("utf-8")
            data_dict = json_helpers.decode(data_json)
            if data_dict['type'] == "response":
                request_seq = data_dict['request_seq']
                log.debug('Body sequence#: {0}'.format(request_seq))
                if request_seq in asyncReq:
                    callback = asyncReq.pop(request_seq, None)
                    if callback:
                        callback(data_dict)
                else:
                    # Only put in the queue if wasn't an async request
                    msgq.put(data_json)
            elif data_dict["type"] == "event":
                event_name = data_dict["event"]
                if event_name in asyncEventHandlers:
                    for cb in asyncEventHandlers[event_name]:
                        # Run <cb> asynchronously to keep read_msg as small as
                        # possible
                        sublime.set_timeout(lambda: cb(data_dict), 0)
        else:
            log.info('Body length of 0 in server stream')

        return False

    @staticmethod
    def is_executable(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    @staticmethod
    def which(program):
        fpath, fname = os.path.split(program)
        if fpath:
            if NodeCommClient.is_executable(program):
                return program
        else:
            # /usr/local/bin is not on mac default path
            # but is where node is typically installed on mac
            path_list = os.path.expandvars(os.environ[
                                           "PATH"]) + os.pathsep + "/usr/local/bin" + os.pathsep + os.path.expandvars("$NVM_BIN")
            for path in path_list.split(os.pathsep):
                path = path.strip('"')
                programPath = os.path.join(path, program)
                if NodeCommClient.is_executable(programPath):
                    return programPath
        return None


class ServerClient(NodeCommClient):

    def __init__(self):
        """
        Starts a node client (if not already started) and communicate with it.
        The script file to run is passed to the constructor.
        """
        super(ServerClient, self).__init__()
        log.debug('starting java server')
        working_dir = os.path.join(
            util.get_plugin_folder(), 'apex-jorje-lsp.jar')
        args = ['java', '-cp', working_dir, '-Dtrace.protocol=false',
                'apex.jorje.lsp.ApexLanguageServerLauncher']
        if os.name == "nt":
            # linux subprocess module does not have STARTUPINFO
            # so only use it if on Windows
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
            self.server_proc = subprocess.Popen(args,
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, startupinfo=si, bufsize=-1, cwd=util.dxProjectFolder())
        else:
            self.server_proc = subprocess.Popen(args,
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=-1, cwd=util.dxProjectFolder())

        # start reader thread
        if self.server_proc and (not self.server_proc.poll()):
            log.debug("server proc " + str(self.server_proc))
            log.debug("starting reader thread")
            readerThread = threading.Thread(target=ServerClient.__reader, args=(
                self.server_proc.stdout, self.msgq, self.asyncReq, self.server_proc, self.event_handlers))
            readerThread.daemon = True
            readerThread.start()

    @staticmethod
    def __reader(stream, msgq, asyncReq, proc, eventHandlers):
        """ Main function for reader thread """
        while True:
            if NodeCommClient.read_msg(stream, msgq, asyncReq, proc, eventHandlers):
                log.debug("server exited")
                return


class WorkerClient(NodeCommClient):
    stop_worker = False

    def __init__(self):
        super(WorkerClient, self).__init__()

    def start(self):
        print('starting java server')
        WorkerClient.stop_worker = False

        working_dir = os.path.join(
            util.get_plugin_folder(), 'apex-jorje-lsp.jar')
        print(working_dir)
        args = ['java', '-cp', working_dir, '-Dtrace.protocol=false',
                'apex.jorje.lsp.ApexLanguageServerLauncher']
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
            self.server_proc = subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, startupinfo=si, bufsize=-1
            )
        else:
            self.server_proc = subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=-1)

        # start reader thread
        if self.server_proc and (not self.server_proc.poll()):
            log.debug("worker proc " + str(self.server_proc))
            log.debug("starting worker thread")
            workerThread = threading.Thread(target=WorkerClient.__reader, args=(
                self.server_proc.stdout, self.msgq, self.asyncReq, self.server_proc, self.event_handlers))
            workerThread.daemon = True
            workerThread.start()

    def stop(self):
        WorkerClient.stop_worker = True
        self.server_proc.kill()
        self.server_proc = None

    @staticmethod
    def __reader(stream, msgq, asyncReq, proc, eventHandlers):
        """ Main function for worker thread """
        while True:
            if NodeCommClient.read_msg(stream, msgq, asyncReq, proc, eventHandlers) or WorkerClient.stop_worker:
                log.debug("worker exited")
                return
