'''A module containing base classes and decorators for HttpTests'''

import requests
from django.conf import settings
from django.core.urlresolvers import reverse
from abc import ABCMeta
from DRP.tests import DRPTestCase
from DRP.models import License, LicenseAgreement, LabGroup, ChemicalClass
import json
from datetime import date, timedelta
from django.contrib.auth.models import User

class GetHttpTest(DRPTestCase):

  baseUrl = 'http://' + settings.SERVER_NAME
  url = baseUrl
  testCodes = []
  _params = {}
  '''any GET params to be added to the reuqest.'''
  status = 200
  '''The expected status code for this test case'''
  _headers = {}

  def __init__(self, *args, **kwargs):
    super(GetHttpTest, self).__init__(*args, **kwargs)
    self.params = self._params.copy()
    self.headers = self._headers.copy()

  def setUp(self):
    '''Sets up the test by requesting the home page uri'''
    self.response = requests.get(self.url, params=self.params)

  @staticmethod
  def constructFailureMessage(message):
    '''Constructs failure messages by parsing the output from the w3c validator'''
    m = message['type'] + ':'
    if 'subtype' in message.keys():
      m += message['subtype'] + ':'
    if 'message' in message.keys():
      m += message['message']
    if 'line' in message.keys():
      m += 'on line {0}'.format(message['line'])
    if 'column' in message.keys():
      m += ', column {0}'.format(message['column'])
    return m +'\n'

  def validate(self):
    self.validationResponse = requests.post(settings.EXTERNAL_HTML_VALIDATOR, headers={'content-type':'text/html; charset=utf-8'}, data=self.response.text, params={'out':'json'})

  def test_Status(self):
    '''Checks that the http response code is the expected value'''
    self.assertEqual(self.response.status_code, self.status, 'Url {0} returns code {1}. Page content follows:\n\n{2}'.format(self.url, self.response.status_code, self.response.text))

  def test_CorrectTemplate(self):
    '''Checks that the expected template is loaded'''
    for testCode in self.testCodes:
      self.assertIn(testCode, self.response.text, 'There appears to be a problem with the rendering of the template, TestCode: {0}. Template returns the following:\n{1}'.format(testCode, self.response.text))

  def test_ValidHtml(self):
    '''Checks HTML validity'''
    self.validate()
    responseData = json.loads(self.validationResponse.content)
    testPassed = True
    failureMessages = ''
    for message in responseData['messages']:
      if message['type'] == 'info':
        if 'subtype' in message.keys():
           if message['subtype'] == 'warning':
              testPassed = False
              failureMessages += self.constructFailureMessage(message)
      if message['type'] in ('error', 'non-document-error'):
        failureMessages += self.constructFailureMessage(message)
        testPassed = False
    self.assertTrue(testPassed, failureMessages + '\n Response html: \n {0}'.format(self.response.text))

class PostHttpTest(GetHttpTest):
  '''A test for post requests that do not use sessions'''

  _payload = {}
  '''The data to be POSTed to the sever'''
  _files = {}
  '''File data to be POSTed'''

  def __init__(self, *args, **kwargs):
    super(PostHttpTest, self).__init__(*args, **kwargs)
    self.payload = self._payload.copy()
    self.files = self._files.copy()

  def setUp(self):
    self.response = requests.post(self.url, data=self.payload, files=self.files, params=self.params, headers=self.headers)

class GetHttpSessionTest(GetHttpTest):

  def __init__(self, *args, **kwargs):
    super(GetHttpSessionTest, self).__init__(*args, **kwargs)
    self.s = requests.Session()

  def setUp(self):
    self.response = self.s.get(self.url, params=self.params,headers=self.headers)

class PostHttpSessionTest(PostHttpTest):
  '''A test for post requests that use sessions (e.g. get decorated with logsInAs)'''

  def __init__(self, *args, **kwargs):
    super(PostHttpSessionTest, self).__init__(*args, **kwargs)
    self.s = requests.Session()

  def setUp(self):
    self.response = self.s.post(self.url, data=self.payload, files=self.files, params=self.params, headers=self.headers) 

class OneRedirectionMixin:
  '''A mixin for testing redirection pages.'''

  def test_redirect(self):
    '''Checks the response history for 302 redirects'''
    self.assertEqual(len(self.response.history), 1, 'Response history has length: {0}. Page Content is: \n{1}'.format(len(self.response.history), self.response.text))
    self.assertEqual(302, self.response.history[0].status_code)

def usesCsrf(c):
  '''A class decorator to indicate the test utilises csrf'''
  
  _oldSetup = c.setUp

  def setUp(self):
    getResponse = self.s.get(self.url, params=self.params)
    self.csrf = self.s.cookies.get_dict()['csrftoken'] #for some old-school tests TODO:Deprecate this.
    self.payload['csrfmiddlewaretoken'] = self.csrf #special case for post classes
    _oldSetup(self)

  c.setUp = setUp

  return c

def logsInAs(username, password, csrf=True):
  '''A class decorator that creates and logs in a user on setup, and deletes it on teardown. Should be applied BEFORE usesCsrf decorator'''

  def _logsInAs(c):
  
    c.loginUrl = c.baseUrl + reverse('login')
    _oldSetUp = c.setUp
    _oldTearDown = c.tearDown
  
    def setUp(self):
      user = User.objects.create_user(username=username, password=password)
      user.save()
      if self.s is None:
        self.s = requests.Session()
      getResponse = self.s.get(self.loginUrl)
      loginCsrf = self.s.cookies.get_dict()['csrftoken']
      loginResponse = self.s.post(self.loginUrl, data={'username':username, 'password':password, 'csrfmiddlewaretoken':loginCsrf})
      _oldSetUp(self)
  
    def tearDown(self):
      _oldTearDown(self)
      User.objects.filter(username=username).delete()

    c.setUp = setUp
    c.tearDown = tearDown
    return c
    
  return _logsInAs

def choosesLabGroup(username, labGroupTitle):
  '''A class decorator that sets up a user to be using a given labgroup for a session to view e.g. compound lists
  Necessarily assumes that the user has been logged in and adjoined to the lab group
  '''

  def _choosesLabGroup(c):

    _oldSetUp = c.setUp
    _oldTearDown = c.tearDown
    c.groupSelectUrl = c.baseUrl + reverse('selectGroup')

    def setUp(self):
      labGroup = LabGroup.objects.get(title=labGroupTitle)
      user = User.objects.get(username=username)
      getResponse = self.s.get(self.groupSelectUrl)
      selectCsrf = self.s.cookies.get_dict()['csrftoken']
      self.s.post(self.groupSelectUrl, data={'labGroup':labGroup.id, 'csrfmiddlewaretoken':selectCsrf})
      _oldSetUp(self)

    c.setUp = setUp
    return c
  return _choosesLabGroup
