"""
This is pythonic implementation of webkit-server using PyQt4.
Based on https://github.com/niklasb/webkit-server
"""

from PySide.QtCore import QObject,QThread, QSize, QUrl, QDir, QFileInfo, Property, Signal, Slot, QRect, QPoint, QEvent, Qt, QByteArray
from PySide import QtNetwork
from PySide.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkCookieJar,QNetworkReply, QNetworkCookie
from PySide.QtGui import  QApplication, QImage, qRgba, QPainter, QMouseEvent
from PySide.QtWebKit import QWebSettings, QWebPage, QWebElement

from Queue import Queue, Empty


import subprocess
import re
import os
import socket
import atexit
import json
import logging
import base64
import time

from functools import partial
from threading import Thread, Condition, Event, currentThread

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class SelectionMixin(object):
  """ Implements a generic XPath selection for a class providing a
  ``_get_xpath_ids`` and a ``get_node_factory`` method. """

  def xpath(self, xpath):
    """ Finds another node by XPath originating at the current node. """
    nodes = self._get_xpath_ids(xpath)
    if isinstance(nodes, (str,unicode,)):
        nodes = nodes.split(',')
    elif not nodes:
        nodes = []
    return map(self.get_node_factory().create, filter(None, nodes))

class NodeFactory(object):
  """ Implements the default node factory.

  `client` is the associated client instance. """

  def __init__(self, client):
    self.client = client

  def create(self, node_id):
    return Node(self.client, node_id)

class NodeError(Exception):
  """ A problem occured within a ``Node`` instance method. """
  pass

class Node(SelectionMixin):
  """ Represents a DOM node in our Webkit session.

  `client` is the associated client instance.

  `node_id` is the internal ID that is used to identify the node when communicating
  with the server. """

  def __init__(self, client, node_id):
    super(Node, self).__init__()
    self.client = client
    self.node_id = node_id

  def text(self):
    """ Returns the inner text (*not* HTML). """
    return self._invoke("text")

  def get_bool_attr(self, name):
    """ Returns the value of a boolean HTML attribute like `checked` or `disabled`
    """
    val = self.get_attr(name)
    return val is not None and val.lower() in ("true", name)

  def get_attr(self, name):
    """ Returns the value of an attribute. """
    return self._invoke("attribute", name)

  def set_attr(self, name, value):
    """ Sets the value of an attribute. """
    self.exec_script("node.setAttribute(%s, %s)" % (repr(name), repr(value)))

  def value(self):
    """ Returns the node's value. """
    if self.is_multi_select():
      return [opt.value()
              for opt in self.xpath(".//option")
              if opt.get("selected")]
    else:
      return self._invoke("value")

  def set(self, value):
    """ Sets the node content to the given value (e.g. for input fields). """
    self._invoke("set", value)

  def path(self):
    """ Returns an XPath expression that uniquely identifies the current node. """
    return self._invoke("path")

  def submit(self, wait=True):
    """ Submits a form node. If `wait` is true, wait for the page to load after
    this operation. """
    logger.debug('submit')
    r = self._invoke("submit")

    if wait:
      self.client.wait()
    return r

  def eval_script(self, js):
    """ Evaluate arbitrary Javascript with the ``node`` variable bound to the
    current node. """
    return self.client.eval_script(self._build_script(js))

  def exec_script(self, js):
    """ Execute arbitrary Javascript with the ``node`` variable bound to
    the current node. """
    self.client.exec_script(self._build_script(js))

  def _build_script(self, js):
    return "var node = Capybara.nodes[%s]; %s;" % (self.node_id, js)

  def select_option(self):
    """ Selects an option node. """
    self._invoke("selectOption")

  def unselect_options(self):
    """ Unselects an option node (only possible within a multi-select). """
    if self.xpath("ancestor::select")[0].is_multi_select():
      self._invoke("unselectOption")
    else:
      raise NodeError, "Unselect not allowed."

  def _simple_mouse_event(self, event_name):
    """ Fires a simple mouse event such as ``mouseover``, ``mousedown`` or
    ``mouseup``. `event_name` specifies the event to trigger. """
    self.exec_script("""
      var ev = document.createEvent('MouseEvents');
      ev.initEvent(%s, true, false);
      node.dispatchEvent(ev);
      """ % repr(event_name))

  def click(self, wait=True):
    """ Clicks the current node. If `wait` is true, wait for the page to load after
    this operation. """
    #self._simple_mouse_event('mousedown')
    #self._simple_mouse_event('mouseup')
    self._invoke("click")
    if wait:
      self.client.wait()

  def drag_to(self, element):
    """ Drag the node to another one. """
    self._invoke("dragTo", element.id)

  def tag_name(self):
    """ Returns the tag name of the current node. """
    return self._invoke("tagName")

  def is_visible(self):
    """ Checks whether the current node is visible. """
    return self._invoke("visible") == "true"

  def is_attached(self):
    """ Checks whether the current node is actually existing on the currently
    active web page. """
    return self._invoke("isAttached") == "true"

  def is_selected(self):
    """ is the ``selected`` attribute set for this node? """
    return self.get_bool_attr("selected")

  def is_checked(self):
    """ is the ``checked`` attribute set for this node? """
    return self.get_bool_attr("checked")

  def is_disabled(self):
    """ is the ``disabled`` attribute set for this node? """
    return self.get_bool_attr("disabled")

  def is_multi_select(self):
    """ is this node a multi-select? """
    return self.tag_name() == "select" and self.get_bool_attr("multiple")

  def _get_xpath_ids(self, xpath):
    """ Implements a mechanism to get a list of node IDs for an relative XPath
    query. """
    return self._invoke("findWithin", xpath)

  def get_node_factory(self):
    """ Returns the associated node factory. """
    return self.client.get_node_factory()

  def __repr__(self):
    return "<Node #%s>" % self.path()

  def _invoke(self, cmd, *args):
    return self.client.issue_node_cmd(cmd, self.node_id, *args)

# client commands
class Command(object):
    def __init__(self, callable, *args, **kwargs):
        self._callable = callable
        self._args = args
        self._kwargs = kwargs
        self.event = Event()
    def __call__(self, obj = None):
        if callable(self._callable):
            if obj:
                return self._invoke(self._callable, obj, *self._args, **self._kwargs)
            else:
                return self._invoke(self._callable, *self._args, **self._kwargs)
        elif obj:
            return self._invoke(getattr(obj, self._callable), obj, *self._args, **self._kwargs)
        raise Exception('You must provide calable or instance member.')
    def _invoke(self, cmd, *args, **kwargs):
        self.result = cmd(*args, **kwargs)
        self.event.set()
class Visit(Command):
    def __init__(self, url):
        super(Visit, self).__init__(WebPage.load, url)
class Body(Command):
    def __init__(self):
        super(Body, self).__init__(WebPage.html)
class Source(Command):
    def __init__(self):
        raise Exception('not implemented')
class Wait(Command):
    def __init__(self):
        super(Wait, self).__init__(WebPage.wait)
class Url(Command):
    def __init__(self):
        super(Url, self).__init__(WebPage.baseUrl)
class Reset(Command):
    def __init__(self):
        super(Reset, self).__init__(WebPage.reset)
class Status(Command):
    def __init__(self):
        super(Status, self).__init__(WebPage.getLastStatus)
class Header(Command):
    def __init__(self, key, value):
        super(Header, self).__init__(WebPage.setHeader, key, value)
class Headers(Command):
    def __init__(self):
        super(Headers, self).__init__(WebPage.pageHeaders)
class Evaluate(Command):
    def __init__(self, expr):
        super(Evaluate, self).__init__(WebPage.invokeJavascript, expr)
class Execute(Command):
    def __init__(self, script):
        super(Execute, self).__init__(WebPage.invokeJavascript, script+';true')
class Render(Command):
    def __init__(self, path, width, height):
        super(Render, self).__init__(WebPage.render, path, width, height)
class SetViewportSize(Command):
    def __init__(self, width, height):
        super(SetViewportSize, self).__init__(WebPage.setViewportSize, QSize(width, height))
class SetAttribute(Command):
    def __init__(self, attr, value):
        super(SetAttribute, self).__init__(WebPage.setAttribute, attr, value)
class SetHtml(Command):
    def __init__(self, html, url):
        super(SetHtml, self).__init__(WebPage.setHtml, html, url)
class SetCookie(Command):
    def __init__(self, cookie):
        super(SetCookie, self).__init__(WebPage.setCookie, cookie)
class ClearCookies(Command):
    def __init__(self):
        super(ClearCookies, self).__init__(WebPage.clearCookies)
class GetCookies(Command):
    def __init__(self):
        super(GetCookies, self).__init__(WebPage.getCookies)
class SetErrorTolerance(Command):
    def __init__(self, tolerant):
        super(SetErrorTolerance, self).__init__(WebPage.setErrorTolerant, tolerant != 'false')
class SetProxy(Command):
    def __init__(self):
        raise Exception('not implemented')
class ClearProxy(Command):
    def __init__(self):
        raise Exception('not implemented')
class Node_(Command):
    def __init__(self, name, *args):
        super(Node_, self).__init__(WebPage.invokeCapybaraFunction, name, *args)
class Find(Command):
    def __init__(self, xpath):
        super(Find, self).__init__(WebPage.invokeCapybaraFunction, 'find', xpath)

class Client(SelectionMixin):
    """ Wrappers for the webkit_server commands.

    If `connection` is not specified, a new instance of ``ServerConnection`` is
    created.

    `node_factory_class` can be set to a value different from the default, in which
    case a new instance of the given class will be used to create nodes. The given
    class must accept a client instance through its constructor and support a
    ``create`` method that takes a node ID as an argument and returns a node object.
    """

    def __init__(self,
                 connection = None,
                 node_factory_class = NodeFactory):
        super(Client, self).__init__()
        self.conn = connection or WebkitConnection()
        self._node_factory = node_factory_class(self)

    def visit(self, url):
        """ Goes to a given URL. """
        return self.conn.issue_command(Visit, url)

    def body(self):
        """ Returns the current DOM as HTML. """
        return self.conn.issue_command(Body,)

    def source(self):
        """ Returns the source of the page as it was originally
        served by the web server. """
        return self.conn.issue_command(Source,)

    def wait(self):
        """ Waits for the current page to load. """
        return self.conn.issue_command(Wait,)

    def url(self):
        """ Returns the current location. """
        return self.conn.issue_command(Url,)

    def set_header(self, key, value):
        """ Sets a HTTP header for future requests. """
        return self.conn.issue_command(Header, key, value)

    def reset(self):
        """ Resets the current web session. """
        return self.conn.issue_command(Reset,)

    def status_code(self):
        """ Returns the numeric HTTP status of the last response. """
        return int(self.conn.issue_command(Status,))

    def headers(self):
        """ Returns a dict of the last HTTP response headers. """
        return self.conn.issue_command(Headers,)

    def eval_script(self, expr):
        """ Evaluates a piece of Javascript in the context of the current page and
        returns its value. """
        #TODO response parsing needed
        return self.conn.issue_command(Evaluate, expr)

    def exec_script(self, script):
        """ Executes a piece of Javascript in the context of the current page. """
        return self.conn.issue_command(Execute, script)

    def render(self, path, width = 1024, height = 1024):
        """ Renders the current page to a PNG file (viewport size in pixels). """
        return self.conn.issue_command(Render, path, width, height)

    def set_viewport_size(self, width, height):
        """ Sets the viewport size. """
        return self.conn.issue_command(SetViewportSize, width, height)

    def set_cookie(self, cookie):
        """ Sets a cookie for future requests (must be in correct cookie string  format). """
        return self.conn.issue_command(SetCookie, cookie)

    def clear_cookies(self):
        """ Deletes all cookies. """
        return self.conn.issue_command(ClearCookies,)

    def cookies(self):
        """ Returns a list of all cookies in cookie string format. """
        return filter(None, (line.strip() for line in self.conn.issue_command(GetCookies,)))

    def set_error_tolerant(self, tolerant=True):
        """ Sets or unsets the error tolerance flag in the server. If this flag
        is set, dropped requests or erroneous responses will not lead to an error! """
        value = "true" if tolerant else "false"
        return self.conn.issue_command(SetErrorTolerance, value)

    def set_attribute(self, attr, value = True):
        """ Sets a custom attribute for our Webkit instance. Possible attributes are:

          * ``auto_load_images``
          * ``dns_prefetch_enabled``
          * ``plugins_enabled``
          * ``private_browsing_enabled``
          * ``javascript_can_open_windows``
          * ``javascript_can_access_clipboard``
          * ``offline_storage_database_enabled``
          * ``offline_web_application_cache_enabled``
          * ``local_storage_enabled``
          * ``local_storage_database_enabled``
          * ``local_content_can_access_remote_urls``
          * ``local_content_can_access_file_urls``
          * ``accelerated_compositing_enabled``
          * ``site_specific_quirks_enabled``

        For all those options, ``value`` must be a boolean. You can find more
        information about these options `in the QT docs
        <http://developer.qt.nokia.com/doc/qt-4.8/qwebsettings.html#WebAttribute-enum>`_.
        """
        value = "true" if value else "false"
        return self.conn.issue_command(SetAttribute, self._normalize_attr(attr), value)

    def reset_attribute(self, attr):
        """ Resets a custom attribute. """
        return self.conn.issue_command(SetAttribute, self._normalize_attr(attr), "reset")

    def set_html(self, html, url = None):
        """ Sets custom HTML in our Webkit session and allows to specify a fake URL.
        Scripts and CSS is dynamically fetched as if the HTML had been loaded from
        the given URL. """
        if url:
            return self.conn.issue_command(SetHtml, html, url)
        else:
            return self.conn.issue_command(SetHtml, html)

    def set_proxy(self, host     = "localhost",
                  port     = 0,
                  user     = "",
                  password = ""):
        """ Sets a custom HTTP proxy to use for future requests. """
        return self.conn.issue_command(SetProxy, host, port, user, password)

    def clear_proxy(self):
        """ Resets custom HTTP proxy (use none in future requests). """
        return self.conn.issue_command(ClearProxy, )

    def issue_node_cmd(self, *args):
        """ Issues a node-specific command. """
        return self.conn.issue_command(Node_, *args)

    def get_node_factory(self):
        """ Returns the associated node factory. """
        return self._node_factory

    def _get_xpath_ids(self, xpath):
        """ Implements a mechanism to get a list of node IDs for an absolute XPath query. """
        return self.conn.issue_command(Find, xpath)

    def _normalize_attr(self, attr):
        """ Transforms a name like ``auto_load_images`` into ``AutoLoadImages``
        (allows Webkit option names to blend in with Python naming). """
        return ''.join(x.capitalize() for x in attr.split("_"))

class NoX11Error(Exception):
  """ Raised when the Webkit server cannot connect to X. """

class NoResponseError(Exception):
  """ Raised when the Webkit server does not respond. """

class InvalidResponseError(Exception):
  """ Raised when the Webkit server signaled an error. """

class EndOfStreamError(Exception):
  """ Raised when the Webkit server closed the connection unexpectedly. """

class NetworkAccessManager(QNetworkAccessManager):
    def __init__(self, *args, **kwargs):
        QNetworkAccessManager.__init__(self, *args, **kwargs)
        self.headers = {}
    def createRequest(self, operation, request, device=None):
        if self.headers:
            request = QNetworkRequest(request)
            if operation != QNetworkAccessManager.PostOperation and operation != QNetworkAccessManager.PutOperation :
                request.setHeader(QNetworkRequest.ContentTypeHeader, None)
            for item in self.headers.iteritems():
                request.setRawHeader(*item)
        return QNetworkAccessManager.createRequest(self,operation, request, device)
    def addHeader(self, key, value):
        self.headers[key] = value

class NetworkCookieJar(QNetworkCookieJar):
    def getAllCookies(self):
        return self.allCookies()
    def clearCookies(self):
        self.setAllCookies([])
    def overwriteCookies(self):
        pass
        #TODO: implement overwriting

class QObjectFactory(QObject):
    """ Factory for creation of QObject in own thread.
     """
    def __init__(self):
        QObject.__init__(self)
        self._list = []
    def __del__(self):
        for obj in self._list:
            if hasattr(obj,'stop'):
                obj.stop()
            else:
                del obj
    def new(self, cls, *args, **kwargs):
        obj = cls(*args, **kwargs)
        self._list.append(obj)
        return obj.result() if hasattr(obj, 'result') else obj

class QObjectRunner(QObject):
    """ QObjectRunner should be used for creation of QObject in own QThread. """
    def __init__(self, cls, *args, **kwargs):
        QObject.__init__(self)
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.run = self._run
        self._ev = Event()
        self._ev.clear()
        self._destroying = Event()
        self._destroying.clear()
        self._cls = cls
        self._args= args
        self._kwargs = kwargs
        self._start()
    def __del__(self):
        self.stop() # perform polite disposal of resources
        self._destroying.set() # terminate loop
        if self._thread.isRunning():
            self._thread.wait(1000) # wait 1 sec
            self._thread.terminate() # no-way
    def _run(self):
        self._result = self._cls(*self._args, **self._kwargs)
        self._ev.set()
        self.loop()
    def _start(self):
        self._thread.start()
    def loop(self):
        while not self._destroying.is_set():
            pass
    def stop(self):
        pass
    def result(self):
        self._ev.wait()
        return self._result if hasattr(self, '_result') else None

class QAppRunner(QObjectRunner):
    def __init__(self, *args, **kwargs):
        QObjectRunner.__init__(self, QApplication, *args, **kwargs)
    def loop(self):
        self._result.exec_()
    def stop(self):
        self._result.exit()

class QPageRunner(QObjectRunner):
    def __init__(self, app=None):
        self._commandQueue = Queue()
        self._app = app
        QObjectRunner.__init__(self, WebPage, app=app, commandQueue=self._commandQueue)
    def loop(self):
        while not self._destroying.is_set():
            self._app.processEvents()
            try:
                cmd = self._commandQueue.get(timeout=0.1)
                cmd(self._result)
            except Empty:
                pass

class WebPage(QWebPage):
    def __init__(self, app, commandQueue):
        self.app = app
        QWebPage.__init__(self)

        self.setForwardUnsupportedContent(True)
        self._setUserStylesheet()

        self._loading = False
        self._navigationRequest = False
        self._loading_ev = Event()
        self._userAgent = None
        self._consoleMessages = []
        self._capybaraJavascript = self._loadCapybaraJavascript()
        self._error = None
        self._lastStatus = None
        self._pageHeaders = {}
        self._errorTolerant = False
        self._ignoreSslErrors = False

        self._setCustomNetworkAccessManager()

        self.frameCreated.connect(self._frameCreatedCallback)
        self.unsupportedContent.connect(self._unsupportedContentCallback)

        self.setLinkDelegationPolicy(WebPage.DelegateAllLinks)
        self.linkClicked.connect(self._linkClickedCallback)

        self.loadProgress.connect(self._loadProgressCallback)

        self.setViewportSize(QSize(1680, 1050))
        self._commandQueue = commandQueue

    def _setCustomNetworkAccessManager(self):
        manager = NetworkAccessManager()
        jar = NetworkCookieJar()
        manager.setCookieJar(jar)
        self.setNetworkAccessManager(manager)

        manager.finished.connect(self._replyFinishedCallbak)
        #manager.requestCreated.connect(manager.requestCreated)
        manager.sslErrors.connect(self._ignoreSslErrorsCallback)

    def invokeCommand(self, cmd, *args, **kwargs):
        if not isinstance(cmd,Command):
            cmd = Command(cmd, *args, **kwargs)
        cmd.event.clear()
        self._commandQueue.put(cmd)
        while not cmd.event.is_set():
            self.app.processEvents()
            cmd.event.wait(0.1)
        return cmd.result

    def load(self, url):
        self.mainFrame().load(QUrl(url))
    def html(self):
        return unicode(self.currentFrame().toHtml())
    def wait(self):
        iter = 10
        if self._loading:
            while not self._loading_ev.is_set() and iter:
                self.app.processEvents()
                self._loading_ev.wait(0.1)
                iter = iter - 1 if not self._navigationRequest else 100
        return self.failureString()
    def baseUrl(self):
        return self.mainFrame().baseUrl()
    def setHeader(self, key, value):
        if re.match(r'^user[-_]agent$',key.lower()):
            self.setUserAgent(value)
        else:
            self.networkAccessManager().addHeader(key, value)
    def setAttribute(self, attr, value):
        if not getattr(QWebSettings,attr):
            raise AttributeError('No such attribute: %s' % attr)
        if value != 'reset':
            self.settings().setAttribute(attr, value != 'false')
        else:
            self.settings().resetAttribute(attr)
    def setHtml(self, html, url=None):
        if url:
            self.currentFrame().setHtml(html, url)
        else:
            self.currentFrame().setHtml(html)
    def getCookies(self):
        jar = self.networkAccessManager().cookieJar()
        return map(QNetworkCookie.toRawForm, jar.getAllCookies())
    def clearCookies(self):
        self.networkAccessManager().cookieJar().clearCookies()
    def setCookie(self, cookie):
        self.networkAccessManager().cookieJar()
        pass
    def reset(self):
        self.triggerAction(WebPage.Stop)
        self.currentFrame().setHtml("<html><body></body></html>")
        self._setCustomNetworkAccessManager()
        self.setUserAgent(None)
        self.resetResponseHeaders()
        self.resetConsoleMessages()
        self.resetSettings()
    def render(self, fileName, width, height):
        self.setViewportSize(QSize(width, height))

        fileInfo = QFileInfo(fileName)
        dir = QDir()
        dir.mkpath(fileInfo.absolutePath())
        viewportSize = self.viewportSize()
        pageSize = self.mainFrame().contentsSize()
        if pageSize.isEmpty():
            return False

        buffer = QImage(pageSize, QImage.Format_ARGB32)
        buffer.fill(qRgba(255, 255, 255, 0))
        p =  QPainter(buffer)

        p.setRenderHint( QPainter.Antialiasing,          True)
        p.setRenderHint( QPainter.TextAntialiasing,      True)
        p.setRenderHint( QPainter.SmoothPixmapTransform, True)

        self.setViewportSize(pageSize)
        self.mainFrame().render(p)
        p.end()

        self.setViewportSize(viewportSize)

        return buffer.save(fileName)
    def acceptNavigationRequest(self, frame, request, type):
        self._navigationRequest = True
        logger.debug('navigate ' + request.url().toString())
        return QWebPage.acceptNavigationRequest(self, frame, request, type)
    def userAgentForUrl(self, url):
        if self._userAgent:
            agent = self._userAgent
        else:
            agent = QWebPage.userAgentForUrl(self,url)
        return agent
    def shouldInterruptJavaScript(self):
        return False
    def javaScriptConsoleMessage(self, message, lineNumber, sourceID):
        if not sourceID:
            fullMessage = '%s|%d|%s' % (sourceID,lineNumber, message)
        else:
            fullMessage = '%d|%s' % (lineNumber, message)
        self._consoleMessages.append(fullMessage)
        logger.debug(fullMessage)
    def javaScriptAlert(self, frame, message):
        logger.debug('ALERT: %s'%message)
    def javaScriptConfirm(self, frame, message):
        logger.debug('CONFIRMATION: %s'%message)
        return True
    def javaScriptPrompt(self, frame, message, defaultValue, result):
        logger.debug('PROMPT: %s'%message)
        return False

    def  __del__(self):
        try:
            self.app.quit()
        except Exception as e:
            logger.error('Exception during disposal of WebPage instance:',e)
    def isLoading(self):
        return self._loading
    def failureString(self):
        return self._error
    def consoleMessages(self):
        return '\n'.join(self._consoleMessages)
    def setUserAgent(self, userAgent):
        self._userAgent = userAgent
    def handleEvents(self):
        self.app.exec_()
    def _loadCapybaraJavascript(self):
        fn = os.path.join(os.path.dirname(__file__), 'capybara.js')
        f = open(fn,'r')
        try:
            return '\n'.join((f.readlines()))
        finally:
            f.close()
    def _setUserStylesheet(self):
        data = base64.b64encode("* { font-family: 'Arial' ! important; }")
        url = QUrl("data:text/css;charset=utf-8;base64," + data)
        self.settings().setUserStyleSheetUrl(url)
    def _linkClickedCallback(self, url):
        logger.debug('clicked '+ url)
        self._loading = True
        self._error = None
        self._loading_ev.clear()
    def _loadStartedCallback(self):
        logger.debug('started loading')
        self._loading = True
        self._error = None
        self._loading_ev.clear()
        #self.app.exec_()
    def _loadProgressCallback(self, progress):
        logger.debug('progress: %d' % progress)
    def _loadFinishedCallback(self, result):
        logger.debug('finished loading')
        self._loading = False
        self._navigationRequest = False
        if not result and not self._error:
            self._error = 'Unable to NetworkAccessManagerload URL: %s' % self.currentFrame().requestedUrl()
        result = result and ( not self._error or self._errorTolerant )
        self._loading_ev.set()
        #self.app.quit()
        return result
    def _frameCreatedCallback(self, frame):
        logger.debug('new frame' )
        frame.loadStarted.connect(self._loadStartedCallback)
        frame.loadFinished.connect(self._loadFinishedCallback)
        frame.javaScriptWindowObjectCleared.connect(partial(self._injectJavascriptHelpersCallback, frame))
    def _injectJavascriptHelpersCallback(self, frame):
        frame.evaluateJavaScript(self._capybaraJavascript)
    def _replyFinishedCallbak(self, reply):
        if reply.error() != QNetworkReply.NoError:
            self._error = 'Error while loading URL %s: %s (error code %s)' % (
                reply.url(),
                reply.errorString(),
                reply.error(),
                )
            self.triggerAction(WebPage.Stop)
            return
        if reply.url() == self.currentFrame().url():
            self._lastStatus = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            self._pageHeaders = dict( (key, reply.rawHeader(key)) for key in reply.rawHeaderList() )

    def _ignoreSslErrorsCallback(self, reply, errors):
        if self._ignoreSslErrors:
            reply.ignoreSslErrors(errors)
    def _unsupportedContentCallback(self, reply):
        reply.finished.connect(partial(self._handleUnsupportedContentCallback, reply))
        self.loadFinished.disconnect(self._loadFinishedCallback)
    def _handleUnsupportedContentCallback(self, reply):
        contentMimeType = reply.header(QNetworkRequest.ContentTypeHeader)
        if contentMimeType is None:
            self._finish(reply, False)
        else:
            text = reply.readAll()
            self.mainFrame().setContent(text, 'text/plain', reply.url())
            self._finish(reply, True)
        self.deleteLater()
    def _finish(self, reply, success):
        self.loadFinished.connect(self._loadFinishedCallback)
        self._replyFinishedCallbak(reply)
        self._loadFinishedCallback(success)
    def setIgnoreSslErrors(self, value):
        self._ignoreSslErrors = value
    def ignoreSslErrors(self):
        return self._ignoreSslErrors
    def setErrorTolerant(self,value):
        self._errorTolerant = value
    def getLastStatus(self):
        return self._lastStatus
    def resetResponseHeaders(self):
        self._lastStatus = 0
        self._pageHeaders = {}
    def resetConsoleMessages(self):
        self._consoleMessages = []
    def pageHeaders(self):
        return self._pageHeaders

    class CapybaraInvocation(QObject):
        def __init__(self, view, name,  *args):
            QObject.__init__(self)
            self._functionName = name
            self._arguments = list(args)
            self._view = view
        @Property(str)
        def functionName(self):
            return self._functionName
        @Property('QStringList')
        def arguments(self):
            return self._arguments
        @Slot(QWebElement, int , int , int , int )
        def click(self, element, left, top, width, height):
            elementBox = QRect(left, top, width, height)
            parent = element.webFrame()
            while parent:
                elementBox = elementBox.translated(parent.geometry().topLeft())
                parent = parent.parentFrame()
            viewport = QRect(QPoint(0, 0),self._view.viewportSize())
            mousePos = elementBox.intersected(viewport).center()
            event = QMouseEvent(QEvent.MouseMove,mousePos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            self._view.app.sendEvent(self._view, event)
            event = QMouseEvent(QEvent.MouseButtonPress,mousePos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            self._view.app.sendEvent(self._view, event)
            event = QMouseEvent(QEvent.MouseButtonRelease,mousePos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            self._view.app.sendEvent(self._view, event)
            href = element.attribute('href') if element.hasAttribute('href') else ''
            self._view._linkClickedCallback(href)

    def invokeCapybaraFunction(self, name, *args):
        obj = WebPage.CapybaraInvocation(self, name, *args)
        self.mainFrame().addToJavaScriptWindowObject('CapybaraInvocation', obj)
        return self.invokeJavascript('Capybara.invoke()')
    def invokeJavascript(self, expr):
        return self.mainFrame().evaluateJavaScript(expr)

class PageFactory:
    objFactory = QObjectFactory()
    app = objFactory.new(QAppRunner, [])
    @classmethod
    def page(cls):
        return cls.objFactory.new(QPageRunner, cls.app)
    @classmethod
    def stop(cls):
        del cls.objFactory


class WebkitConnection(object):

    def __init__(self, page = None):

        self.page = page or PageFactory.page()

    def issue_command(self, cmd, *args):
        """ Sends and receives a message to/from the server """
        Cls = cmd # if isinstance(cmd, Command) else getattr(commands, cmd)
        return self._to_py_object(self.page.invokeCommand(Cls(*args)))

    def _to_py_object(self, qObj):
        if qObj is None:
            return None

        #if isinstance(QObj,(QVariant, )):    # not needed for pyside
        #    return self._to_py_object(QObj.toPyObject())
        #    #return QObj.toPyObject()

        if isinstance(qObj, (QUrl,)):
            return self._to_py_object(qObj.toString())

        if isinstance(qObj, (QByteArray, QUrl)):
            return unicode(qObj)

        if isinstance(qObj, (dict, )):
            return dict((self._to_py_object(k),self._to_py_object(v)) for k,v in qObj.iteritems())

        if isinstance(qObj, (list, tuple, )):
            return map(self._to_py_object, qObj)

        if isinstance(qObj, (int, float, bool, unicode, str)):
            return  qObj

        raise TypeError('Unexpected type "%s".'%type(qObj))



if __name__ == '__main__':
    USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.71 Safari/537.36'
    ACCEPT_LANG = 'en-US,en;q=0.8'
    ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    c = Client()

    c.set_header('user-agent',USER_AGENT)
    c.set_header('accept-language', ACCEPT_LANG)
    c.set_header('accept', ACCEPT)
    c.set_error_tolerant(True)
    c.clear_cookies()

    c.visit('https://www.google.fr/?q=')
    print c.wait()
    print c.url()
    n, = c.xpath('//input[@name="q"]')
    n.set('"4-FA"')
    print n.value()
    f, = n.xpath("ancestor::form")
    print c.url()
    f.submit()
    print c.url()
    #b, = f.xpath('//*[@name="btnG"]')
    #b.click()
    res = c.xpath('//li[@class="g"]//h3[@class="r"]/a')
    print '\n'.join( '%s <%s>'%(r.text(),r.get_attr('href')) for r in res )
    next, = c.xpath('//a[@id="pnnext"]')
    next.click()
    #time.sleep(1)
    print c.url()
    res = c.xpath('//li[@class="g"]//h3[@class="r"]/a')
    print '\n'.join( '%s <%s>'%(r.text(),r.get_attr('href')) for r in res )
    #c.render('fok.png')
    #print c.body()
    #AppRunner.exit()
    time.sleep(10)

