"""Splitter visitor for the case when the data should not be separated."""
from AbstractSplitter import AbstractSplitter
import random


class Splitter(AbstractSplitter):

    """The splitter visitor."""

    def __init__(self, namingStub):
        """Standard splitter initialisation."""
        super(Splitter, self).__init__(namingStub)

    def split(self, reactions, verbose=False):
        """Perform the split."""
        super(Splitter, self).split(reactions, verbose=verbose)
        if verbose:
            print "Training set ({}) and no test set.".format(reactions.count())
        splits = [(self.package(reactions), self.package([]))]

        return splits
