"""A module containing only the PerformedReaction class."""
from django.db import models
from Reaction import Reaction, ReactionManager, ReactionQuerySet
from RecommendedReaction import RecommendedReaction
from django.contrib.auth.models import User
from itertools import chain
import DRP
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.forms.forms import NON_FIELD_ERRORS
from validators import notInTheFuture


class PerformedReactionQuerySet(ReactionQuerySet):

    """A custom queryset for performed reactions."""

    def __init__(self, model=None, **kwargs):
        """Initialise the queryset."""
        model = PerformedReaction if model is None else model
        super(PerformedReactionQuerySet, self).__init__(model=model, **kwargs)


class PerformedReactionManager(ReactionManager):

    """A custom manager for performed reactions."""

    def get_queryset(self):
        """Return the correct custom queryset."""
        return PerformedReactionQuerySet(model=PerformedReaction)


class PerformedReaction(Reaction):

    """A class representing concrete instances of reactions that have actually been performed."""

    class Meta:
        app_label = "DRP"

    objects = PerformedReactionManager()
    user = models.ForeignKey(User)
    performedBy = models.ForeignKey(
        User, related_name='performedReactions', null=True, blank=True, default=None)
    performedDateTime = models.DateTimeField('Date Reaction Performed', null=True, blank=True, default=None,
                                             help_text='Timezone assumed EST, Date in format YYYY-MM-DD', validators=[notInTheFuture])
    insertedDateTime = models.DateTimeField(
        'Date Reaction Saved', auto_now_add=True)
    recommendation = models.ForeignKey(
        RecommendedReaction, blank=True, unique=False, null=True, default=None, related_name='resultantExperiment')
    legacyRecommendedFlag = models.NullBooleanField(default=None)
    """If this reaction was based from a recommendation, reference that recommendation."""
    valid = models.BooleanField(default=True)
    """A flag to denote reactions which have been found to be invalid, for instance,
    if the wrong reactant was used or some bad lab record has been found."""
    public = models.BooleanField(default=False)
    duplicateOf = models.ForeignKey(
        'self', related_name='duplicatedBy', blank=True, unique=False, null=True, default=None)
    legacyID = models.IntegerField(null=True, blank=True, unique=True)
    """ID in legacy database."""
    legacyRef = models.CharField(max_length=40, null=True, blank=True)
    """Reaction reference in legacy database."""
    convertedLegacyRef = models.CharField(max_length=40, null=True, blank=True,
                                          validators=[
                                              RegexValidator(
                                                  '^[a-z0-9._]*[a-z][a-z0-9._]*$',
                                                            ('Please include only values which are limited to '
                                                             'alphanumeric characters, underscores, periods, '
                                                             'and must include at least one '
                                                             'alphabetic character.')
                                              )
                                          ]
                                          )
    """Reaction reference in legacy database converted to canonical form by removing spaces and converting to lowercase.
    This could differ from the reference because it is not disambiguated or validated as unique."""
    reference = models.CharField(
        max_length=40,
        validators=[
            RegexValidator(
                '^[a-z0-9\._]*[a-z][a-z0-9\._]*$',
                ('Please include only values which are limited to '
                 'alphanumeric characters, underscores, periods, '
                 'and must include at least one '
                 'alphabetic character.')
            )
        ]
    )

    def clean(self):
        """Custom clean method to make sure that the reaction does not already exist within this lab group."""
        super(PerformedReaction, self).clean()
        if PerformedReaction.objects.exclude(id=self.id).filter(labGroup=self.labGroup, reference=self.reference).exists():
            raise ValidationError(
                {'reference': 'This reference has already been used for this lab group.'}, code="duplicate_reference")

    def __unicode__(self):
        """Return the reference as the unicode representation."""
        return self.reference

    def save(self, invalidate_models=True, *args, **kwargs):
        """Custom save method makes ure that models based on an updated reaction are invalidated, because the data changed."""
        self.reference = self.reference.lower()
        if self.pk is not None and invalidate_models:
            test = DRP.models.StatsModel.objects.filter(
                testSets__reactions__in=[self])
            train = DRP.models.StatsModel.objects.filter(
                trainingSet__reactions=self)
            for model in chain(test, train):
                model.invalidate()
        super(PerformedReaction, self).save(*args, **kwargs)
