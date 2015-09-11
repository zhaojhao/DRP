'''Module containing only the CompoundQuantities Class'''
from django.db import models
from django import forms
from django.core.exceptions import ValidationError
from Compound import Compound
from CompoundRole import CompoundRole
from Reaction import Reaction

class CompoundQuantity(models.Model):
  '''A class to contain the relationship between a reaction and a compound,
  and thus to contain the amount of a given compound used in a reaction
  with the applicable units. At present, no unit convention is enforced.
  '''

  class Meta:
    app_label='DRP'

  compound=models.ForeignKey(Compound, on_delete=models.PROTECT)
  reaction=models.ForeignKey(Reaction)
  role=models.ForeignKey(CompoundRole)
  amount=models.FloatField() 

class BaseReactantFormSet(forms.models.BaseModelFormSet):

  def clean(self):
    super(BaseReactantFormSet, self).clean()
    if len(self.forms) < 1:
      raise ValidationError('At least one reactant must be supplied', 'no_reactant') 
