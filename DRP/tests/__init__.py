from DRPTestCase import DRPTestCase, runTests
import fileTests
import unittest
import Email
import forms
import HttpTests
import decorators
import CompoundFromCsv
import CompoundDescriptor
import CompoundToCsv
import CompoundToArff
import modelBuildingTests

suite = unittest.TestSuite([
    #Email.suite,
    #forms.suite,
    HttpTests.suite,
    #modelBuildingTests.suite,
    #CompoundFromCsv.suite,
    #CompoundDescriptor.suite,
    #CompoundToCsv.suite,
    #CompoundToArff.suite,
    #fileTests.suite,
])
