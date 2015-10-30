'''A module containing only the PerformedReaction class'''
from django.db import models
from Reaction import Reaction
from RecommendedReaction import RecommendedReaction
from django.contrib.auth.models import User
from StatsModel import StatsModel
from django.core.exceptions import ValidationError
from itertools import chain

class PerformedReaction(Reaction):
  '''A class representing concrete instances of reactions that have actually been performed'''
  
  class Meta:
    app_label="DRP"

  user=models.ForeignKey(User)
  performedBy=models.ForeignKey(User, related_name='performedReactions', null=True, default=None)
  reference=models.CharField(max_length=40) #uniqueness validated conditionally- see method below.
  performedDateTime=models.DateTimeField('Date Reaction Performed', null=True, default=None)
  insertedDateTime=models.DateTimeField('Date Reaction Saved', auto_now_add=True)
  recommendation=models.ForeignKey(RecommendedReaction, blank=True, unique=False, null=True, default=None, related_name='resultantExperiment')
  legacyRecommendedFlag=models.NullBooleanField(default=None)
  '''If this reaction was based from a recommendation, reference that recommendation'''
  valid=models.BooleanField(default=True)
  '''A flag to denote reactions which have been found to be invalid, for instance,
  if the wrong reactant was used or some bad lab record has been found'''
  public=models.BooleanField(default=False)
  duplicateOf=models.ForeignKey('self', related_name='duplicatedBy', blank=True, unique=False, null=True, default=None)
  inTrainingSetFor=models.ManyToManyField(StatsModel, related_name='trainingSet', through='DRP.TrainingSet')
  '''Describes the many to many mapping when a StatsModel uses a Performed Reaction as part of its
  test or training sets. Must be placed on this model as a workaround to circular dependency issues'''
  inTestSetFor=models.ManyToManyField(StatsModel, related_name='testSet', through='DRP.TestSet')

  def __unicode__(self):
    return self.reference

  def validate_unique(self, exclude=None):
    if self is valid and PerformedReaction.objects.exclude(pk=self.pk).filter(reference=self.reference, valid=True).exists():
      raise ValidationError('A valid reaction with that reference code already exists.', code='not_unique')
    super(PerformedReaction, self).validate_unique(exclude=exclude)

  def save(self, *args, **kwargs):
    if self.pk is not None:
      for model in chain(self.inTrainingSetFor.all(), self.inTestSetFor.all()):
        model.invalidate()
        model.save()
    super(PerformedReaction, self).save(*args, **kwargs)
