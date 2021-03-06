"""Command for re-importing the DRP database from a csv."""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction
from django.conf import settings
from os import path
import csv
from django.contrib.auth.models import User
from DRP.models import LabGroup, Compound, PerformedReaction
from DRP.models import ChemicalClass, NumRxnDescriptor
from DRP.models import BoolRxnDescriptor, OrdRxnDescriptor
from DRP.models import NumRxnDescriptorValue, BoolRxnDescriptorValue
from DRP.models import OrdRxnDescriptorValue, NumMolDescriptorValue
from DRP.models import CompoundRole, CompoundQuantity
from chemspipy import ChemSpider
import re
import warnings

outcomeDescriptor = OrdRxnDescriptor.objects.get_or_create(
    heading='crystallisation_outcome',
    name='Four class crystallisation outcome',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0',
    maximum=4,
    minimum=1
)[0]

outcomeBooleanDescriptor = BoolRxnDescriptor.objects.get_or_create(
    heading='boolean_crystallisation_outcome',
    name='Two class crystallisation outcome',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

purityDescriptor = OrdRxnDescriptor.objects.get_or_create(
    heading='crystallisation_purity_outcome',
    name='Two class crystallisation purity',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0',
    maximum=2,
    minimum=1
)[0]

temperatureDescriptor = NumRxnDescriptor.objects.get_or_create(
    heading='reaction_temperature',
    name='Reaction temperature in degrees C',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

timeDescriptor = NumRxnDescriptor.objects.get_or_create(
    heading='reaction_time',
    name='Reaction time in minutes',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

pHDescriptor = NumRxnDescriptor.objects.get_or_create(
    heading='reaction_pH',
    name='Reaction pH',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

preHeatStandingDescriptor = NumRxnDescriptor.objects.get_or_create(
    heading='pre_heat_standing',
    name='Pre heat standing time',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

teflonDescriptor = BoolRxnDescriptor.objects.get_or_create(
    heading='teflon_pouch',
    name='Was this reaction performed in a teflon pouch?',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

leakDescriptor = BoolRxnDescriptor.objects.get_or_create(
    heading='leak',
    name='Did this reaction leak?',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

slowCoolDescriptor = BoolRxnDescriptor.objects.get_or_create(
    heading='slow_cool',
    name='Was a slow cool performed for this reaction?',
    calculatorSoftware='manual',
    calculatorSoftwareVersion='0'
)[0]

# about how many things django can bulk_create at once without getting upset
save_at_once = 5000

ref_match = re.compile('[A-Za-z0-9._]*[A-Za-z][A-Za-z0-9._]*')

reagent_dict = {}
density_dict = {}


def convert_legacy_reference(legacy_reference):
    """Convert the legacy reference codes to conformant codes."""
    ref = legacy_reference.lower().replace(' ', '').replace('-', '.')
    if ref_match.match(ref) is None:
        ref = 'xxx' + ref
        if ref_match.match(ref) is None:
            raise ValueError('Unhandled mismatch of regex')
    return ref


class Command(BaseCommand):

    """Convert data from a pre-0.02 csv dump to the post 0.02 database."""

    help = 'Ports database from pre-0.02 to 0.02'

    def add_arguments(self, parser):
        """Add arguments for the parser."""
        parser.add_argument(
            'directory', help='The directory where the tsv files are')
        parser.add_argument('start_number', type=int, nargs='?', default=0,
                            help='Number to start on. By default this specifies a reaction. If descriptors or quantities is specified it refers to those.')
        parser.add_argument('--reactions', action='store_true',
                            help='Start at importing the reactions')
        parser.add_argument('--descriptors', action='store_true',
                            help='Start at importing the descriptors')
        parser.add_argument('--quantities', action='store_true',
                            help='Start at importing the compound quantities')
        parser.add_argument('--delete-all', action='store_true',
                            help='Delete all performed reactions.')
        parser.add_argument('--no-compound-prompts', action='store_true',
                            help="Don't prompt user to identify compounds. Mark unknown.")

    def handle(self, *args, **kwargs):
        """Handle the command call."""
        folder = kwargs['directory']
        start_at_reactions = kwargs['reactions']
        start_at_descriptors = kwargs['descriptors']
        start_at_quantities = kwargs['quantities']
        start_number = kwargs['start_number']
        delete_all = kwargs['delete_all']
        no_compound_prompts = kwargs['no_compound_prompts']
        start_at_delete = not (
            start_at_reactions or start_at_descriptors or start_at_quantities)

        if start_at_delete:
            self.stdout.write('Deleting reactions')
            if delete_all:
                PerformedReaction.objects.all().delete()
            else:
                with transaction.atomic():
                    with open(path.join(folder, 'performedReactions.tsv')) as reactions:
                        reader = csv.DictReader(reactions, delimiter='\t')
                        for i, r in enumerate(reader):
                            if start_at_delete and i < start_number:
                                continue
                            ref = convert_legacy_reference(r['reference'])
                            legacyID = r['id']
                            ps = PerformedReaction.objects.filter(
                                reference=ref)
                            if ps:
                                self.stdout.write(
                                    '{}: Deleting reaction with reference {}'.format(i, ref))
                                ps.delete()
                            ps = PerformedReaction.objects.filter(
                                reference=ref.lower())
                            if ps:
                                self.stdout.write(
                                    '{}: Deleting reaction with converted legacy reference {}'.format(i, ref))
                                ps.delete()
                            ps = PerformedReaction.objects.filter(
                                convertedLegacyRef=ref)
                            if ps:
                                self.stdout.write(
                                    '{}: Deleting reaction with converted legacy reference {}'.format(i, ref))
                                ps.delete()
                            ps = PerformedReaction.objects.filter(
                                legacyID=legacyID)
                            if ps:
                                self.stdout.write(
                                    '{}: Deleting reaction with legacy id {}'.format(i, legacyID))
                                ps.delete()

        if start_at_reactions or start_at_delete:
            warnings.simplefilter('error')
            with open(path.join(folder, 'performedReactions.tsv')) as reactions:
                self.stdout.write('Creating reactions')
                reader = csv.DictReader(reactions, delimiter='\t')
                for i, r in enumerate(reader):
                    if start_at_reactions and i < start_number:
                        continue
                    ref = convert_legacy_reference(r['reference'])
                    convertedLegacyRef = ref
                    ps = PerformedReaction.objects.filter(
                        convertedLegacyRef=convertedLegacyRef)
                    if ps.exists():
                        ref = '{}_{}'.format(ref, r['id'])
                        valid = False
                        notes = r[
                            'notes'] + ' Duplicate reference disambiguated with legacy id.'
                        for p in ps:
                            if p.convertedLegacyRef == p.reference:
                                p.valid = False
                                p.notes += u' Duplicate reference disambiguated with legacy id.'
                                p.reference = '{}_{}'.format(
                                    p.convertedLegacyRef, p.legacyID)
                                p.save(calcDescriptors=False)
                    else:
                        valid = bool(int(r['valid']))
                        notes = r['notes']

                    p = PerformedReaction(
                        reference=ref,
                        legacyRef=r['reference'],
                        convertedLegacyRef=convertedLegacyRef,
                        labGroup=LabGroup.objects.get(
                            title=r['labGroup.title']),
                        legacyID=r['id'],
                        notes=notes,
                        user=User.objects.get(username=r['user.username']),
                        valid=valid,
                        legacyRecommendedFlag=(
                            r['legacyRecommendedFlag'] == 'Yes'),
                        insertedDateTime=r['insertedDateTime'],
                        public=int(r['public'])
                    )
                    self.stdout.write(
                        '{}: Creating reaction with reference {}'.format(i, ref))
                    p.full_clean()
                    p.save(calcDescriptors=False)
        if start_at_delete or start_at_reactions or start_at_descriptors:
            with open(path.join(folder, 'performedReactions.tsv')) as reactions:
                self.stdout.write('Creating manual descriptors')
                reader = csv.DictReader(reactions, delimiter='\t')
                outValues = []
                outBoolValues = []
                purityValues = []
                temperatureValues = []
                timeValues = []
                pHValues = []
                preHeatStandingValues = []
                teflonValues = []
                slowCoolValues = []
                leakValues = []

                for i, r in enumerate(reader):
                    if start_at_descriptors and i < start_number:
                        continue
                    ref = convert_legacy_reference(r['reference'])

                    id = r['id']
                    self.stdout.write(
                        '{}: Reiterating for reaction with reference {}, legacyID {}'.format(i, ref, id))
                    p = PerformedReaction.objects.get(legacyID=id)
                    if r['duplicateOf.reference']:
                        convertedDupRef = convert_legacy_reference(
                            r['duplicateOf.reference'])
                        try:
                            p.duplicateOf = PerformedReaction.objects.get(
                                convertedLegacyRef=convertedDupRef)
                            p.save(calcDescriptors=False)
                        except PerformedReaction.DoesNotExist:
                            self.stderr.write('Reaction {} marked as duplicate of reaction {}, but the latter does not exist'.format(
                                ref, r['duplicateOf.reference']))
                            p.notes += 'Marked as duplicate of reaction with legacy reference {}, but it does not exist'.format(r[
                                                                                                                                'duplicateOf.reference'])
                            p.valid = False
                            p.save(calcDescriptors=False)
                        except PerformedReaction.MultipleObjectsReturned:
                            self.stderr.write('Reaction {} marked as duplicate of reaction {}, but more than one of the latter exists'.format(
                                ref, r['duplicateOf.reference']))
                            p.notes += 'Marked as duplicate of reaction with legacy reference {}, but more than one reaction with that reference exists'.format(r[
                                                                                                                                                                'duplicateOf.reference'])
                            p.valid = False
                            p.save(calcDescriptors=False)

                    outcomeValue = int(r['outcome']) if (
                        r['outcome'] in (str(x) for x in range(1, 5))) else None
                    try:
                        v = OrdRxnDescriptorValue.objects.get(
                            descriptor=outcomeDescriptor, reaction=p)
                        if v.value != outcomeValue:
                            v.value = outcomeValue
                            v.save()
                    except OrdRxnDescriptorValue.DoesNotExist:
                        outValue = outcomeDescriptor.createValue(
                            p, outcomeValue)
                        outValues.append(outValue)

                    value = True if (outcomeValue > 2) else False
                    try:
                        v = BoolRxnDescriptorValue.objects.get(
                            descriptor=outcomeBooleanDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except BoolRxnDescriptorValue.DoesNotExist:
                        outBoolValue = outcomeBooleanDescriptor.createValue(
                            p, value)
                        outBoolValues.append(outBoolValue)

                    value = int(r['purity']) if (
                        r['purity'] in ('1', '2')) else None
                    try:
                        v = OrdRxnDescriptorValue.objects.get(
                            descriptor=purityDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except OrdRxnDescriptorValue.DoesNotExist:
                        purityValue = purityDescriptor.createValue(p, value)
                        purityValues.append(purityValue)

                    value = (float(r['temp']) + 273.15) if (r['temp']
                                                            not in ('', '?')) else None
                    try:
                        v = NumRxnDescriptorValue.objects.get(
                            descriptor=temperatureDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except NumRxnDescriptorValue.DoesNotExist:
                        temperatureDescriptorValue = temperatureDescriptor.createValue(
                            p, value)
                        temperatureValues.append(temperatureDescriptorValue)

                    value = float(r['time']) * 60 if (r['time']
                                                      not in ['', '?']) else None
                    try:
                        v = NumRxnDescriptorValue.objects.get(
                            descriptor=timeDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except NumRxnDescriptorValue.DoesNotExist:
                        timeDescriptorValue = timeDescriptor.createValue(
                            p, value)
                        timeValues.append(timeDescriptorValue)

                    value = float(r['pH']) if (
                        r['pH'] not in ('', '?')) else None
                    try:
                        v = NumRxnDescriptorValue.objects.get(
                            descriptor=pHDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except NumRxnDescriptorValue.DoesNotExist:
                        pHDescriptorValue = pHDescriptor.createValue(p, value)
                        pHValues.append(pHDescriptorValue)

                    value = bool(r['pre_heat standing']) if (
                        r.get('pre_heat standing') not in ('', None)) else None
                    try:
                        v = NumRxnDescriptorValue.objects.get(
                            descriptor=preHeatStandingDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except NumRxnDescriptorValue.DoesNotExist:
                        preHeatStandingDescriptorValue = preHeatStandingDescriptor.createValue(
                            p, value)
                        preHeatStandingValues.append(
                            preHeatStandingDescriptorValue)

                    value = bool(int(r['teflon_pouch'])) if (
                        r.get('teflon_pouch') not in(None, '')) else None
                    try:
                        v = BoolRxnDescriptorValue.objects.get(
                            descriptor=teflonDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except BoolRxnDescriptorValue.DoesNotExist:
                        teflonDescriptorValue = teflonDescriptor.createValue(
                            p, value)
                        teflonValues.append(teflonDescriptorValue)

                    leak_string = r['leak']
                    if leak_string in (None, '', '?'):
                        value = None
                    elif leak_string.lower() == 'yes':
                        value = True
                    elif leak_string.lower() == 'no':
                        value = False
                    else:
                        raise RuntimeError(
                            "Unrecognized string '{}' in leak column".format(leak_string))
                    try:
                        v = BoolRxnDescriptorValue.objects.get(
                            descriptor=leakDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except BoolRxnDescriptorValue.DoesNotExist:
                        leakDescriptorValue = leakDescriptor.createValue(
                            p, value)
                        leakValues.append(leakDescriptorValue)

                    slow_cool_string = r['slow_cool']
                    if slow_cool_string in (None, '', '?'):
                        value = None
                    elif slow_cool_string.lower() == 'yes':
                        value = True
                    elif slow_cool_string.lower() == 'no':
                        value = False
                    else:
                        raise RuntimeError(
                            "Unrecognized string '{}' in slow_cool column".format(slow_cool_string))
                    try:
                        v = BoolRxnDescriptorValue.objects.get(
                            descriptor=slowCoolDescriptor, reaction=p)
                        if v.value != value:
                            v.value = value
                            v.save()
                    except BoolRxnDescriptorValue.DoesNotExist:
                        slowCoolDescriptorValue = slowCoolDescriptor.createValue(
                            p, value)
                        slowCoolValues.append(slowCoolDescriptorValue)

                    if len(outValues) > save_at_once:
                        self.stdout.write("Saving outValues...")
                        OrdRxnDescriptorValue.objects.bulk_create(outValues)
                        outValues = []
                        self.stdout.write("...saved")
                    if len(outBoolValues) > save_at_once:
                        self.stdout.write("Saving outBoolValues...")
                        BoolRxnDescriptorValue.objects.bulk_create(
                            outBoolValues)
                        outBoolValues = []
                        self.stdout.write("...saved")
                    if len(purityValues) > save_at_once:
                        self.stdout.write("Saving purityValues...")
                        OrdRxnDescriptorValue.objects.bulk_create(purityValues)
                        purityValues = []
                        self.stdout.write("...saved")
                    if len(temperatureValues) > save_at_once:
                        self.stdout.write("Saving temperatureValues...")
                        NumRxnDescriptorValue.objects.bulk_create(
                            temperatureValues)
                        temperatureValues = []
                        self.stdout.write("...saved")
                    if len(timeValues) > save_at_once:
                        self.stdout.write("Saving timeValues...")
                        NumRxnDescriptorValue.objects.bulk_create(timeValues)
                        timeValues = []
                        self.stdout.write("...saved")
                    if len(pHValues) > save_at_once:
                        self.stdout.write("Saving pHValues...")
                        NumRxnDescriptorValue.objects.bulk_create(pHValues)
                        pHValues = []
                        self.stdout.write("...saved")
                    if len(preHeatStandingValues) > save_at_once:
                        self.stdout.write("Saving preHeatStandingValues...")
                        NumRxnDescriptorValue.objects.bulk_create(
                            preHeatStandingValues)
                        preHeatStandingValues = []
                        self.stdout.write("...saved")
                    if len(teflonValues) > save_at_once:
                        self.stdout.write("Saving teflonValues...")
                        BoolRxnDescriptorValue.objects.bulk_create(
                            teflonValues)
                        teflonValues = []
                        self.stdout.write("...saved")
                    if len(leakValues) > save_at_once:
                        self.stdout.write("Saving leakValues...")
                        BoolRxnDescriptorValue.objects.bulk_create(leakValues)
                        leakValues = []
                        self.stdout.write("...saved")
                    if len(slowCoolValues) > save_at_once:
                        self.stdout.write("Saving slowCoolValues...")
                        BoolRxnDescriptorValue.objects.bulk_create(
                            slowCoolValues)
                        slowCoolValues = []
                        self.stdout.write("...saved")

                self.stdout.write("Saving all remaining values...")
                OrdRxnDescriptorValue.objects.bulk_create(outValues)
                BoolRxnDescriptorValue.objects.bulk_create(outBoolValues)
                OrdRxnDescriptorValue.objects.bulk_create(purityValues)
                NumRxnDescriptorValue.objects.bulk_create(temperatureValues)
                NumRxnDescriptorValue.objects.bulk_create(timeValues)
                NumRxnDescriptorValue.objects.bulk_create(pHValues)
                NumRxnDescriptorValue.objects.bulk_create(
                    preHeatStandingValues)
                BoolRxnDescriptorValue.objects.bulk_create(teflonValues)
                BoolRxnDescriptorValue.objects.bulk_create(leakValues)
                BoolRxnDescriptorValue.objects.bulk_create(slowCoolValues)

                outValues = []
                outBoolValues = []
                purityValues = []
                temperatureValues = []
                timeValues = []
                pHValues = []
                preHeatStandingValues = []
                teflonValues = []
                leakValues = []
                slowCoolValues = []
                self.stdout.write("...saved")

        with open(path.join(folder, 'compoundquantities.tsv')) as cqs, open(path.join(folder, 'compoundquantities_fixed.tsv'), 'a') as fixed_cqs:
            self.stdout.write('Creating or updating compound quantities')
            reader = csv.DictReader(cqs, delimiter='\t')
            writer = csv.DictWriter(
                fixed_cqs, reader.fieldnames + ['compound.old_abbrev'], delimiter='\t')
            if not (start_at_quantities and start_number > 0):
                writer.writeheader()
            quantities = []
            cs = ChemSpider(settings.CHEMSPIDER_TOKEN)
            for i, r in enumerate(reader):
                if start_at_quantities and (i < start_number):
                    continue
                if not (r['compound.abbrev'] or r['compoundrole.name'] or r['amount']):
                    # this is just a blank entry
                    continue

                legacyID = r['reaction.id']
                reaction = PerformedReaction.objects.get(legacyID=legacyID)
                compound_abbrev = r['compound.abbrev']

                correct_abbrev = reagent_dict[
                    compound_abbrev] if compound_abbrev in reagent_dict else compound_abbrev

                compound_found = False
                while correct_abbrev and not compound_found:
                    try:
                        compound = Compound.objects.get(
                            abbrev=correct_abbrev, labGroup=reaction.labGroup)
                        compound_found = True
                        r['compound.old_abbrev'] = r['compound.abbrev']
                        r['compound.abbrev'] = correct_abbrev
                    except Compound.DoesNotExist:
                        if no_compound_prompts:
                            correct_abbrev = ''
                        else:
                            self.stderr.write(
                                'Could not find compound with abbreviation {}. Checking chemspider...'.format(correct_abbrev))
                            results = cs.simple_search(correct_abbrev)
                            if len(results) != 1:
                                CSID = raw_input(
                                    'Could not find unique compound with abbreviation {}. Do you know the CSID? '.format(correct_abbrev))
                                if CSID.isdigit():
                                    results = cs.simple_search(CSID)
                            if len(results) == 1:
                                compound = None
                                try:
                                    compound = Compound.objects.get(
                                        CSID=results[0].csid, labGroup=reaction.labGroup)
                                except Compound.DoesNotExist:
                                    pass
                                user_response = None
                                while user_response is None:
                                    if compound is None:
                                        user_verification = raw_input('Found unique compound with CSID {} and name {} for abbreviation {}. This is NOT IN THE COMPOUND GUIDE. Is this correct? (y/n): '.format(
                                            results[0].csid, results[0].common_name, correct_abbrev))
                                    else:
                                        user_verification = raw_input('Found unique compound with CSID {}, name {}, and abbreviation {} for abbreviation {} in the compound guide. Is this correct? (y/n): '.format(
                                            compound.CSID, compound.name, compound.abbrev, correct_abbrev))
                                    if user_verification and user_verification.lower()[0] == 'y':
                                        user_response = True
                                    elif user_verification and user_verification.lower()[0] == 'n':
                                        user_response = False
                                if user_response:
                                    if compound is not None:
                                        correct_abbrev = compound.abbrev
                                        reagent_dict[
                                            compound_abbrev] = correct_abbrev
                                        continue
                                    else:
                                        self.stderr.write('Creating compound with CSID {}, abbrevation {}, name {}'.format(
                                            results[0].csid, correct_abbrev, results[0].common_name))
                                        c = Compound(
                                            CSID=results[0].csid, labGroup=reaction.labGroup, abbrev=correct_abbrev)
                                        try:
                                            c.csConsistencyCheck()
                                            c.save(invalidateReactions=False)
                                            continue
                                        except ValidationError:
                                            c.delete()
                                            raise

                            self.stderr.write(
                                'Could not get unambiguous chemspider entry for abbreviation {}'.format(correct_abbrev))
                            self.stderr.write('Unknown Reactant {} with amount {} {} in reaction {}'.format(
                                r['compound.abbrev'], r['amount'], r['unit'], r['reaction.reference']))
                            correct_abbrev = raw_input(
                                'What is the correct abbreviation for this? ')
                            reagent_dict[compound_abbrev] = correct_abbrev

                if compound_found:
                    self.stdout.write('{}: Creating quantity for compound {} and reaction {}'.format(
                        i, compound.abbrev, reaction.reference))
                    if r['compound.abbrev'] in ('water', 'H2O'):
                        r['density'] = 1
                    try:
                        mw = NumMolDescriptorValue.objects.get(
                            compound=compound, descriptor__heading='mw').value
                    except NumMolDescriptorValue.DoesNotExist:
                        compound.save(invalidateReactions=False)
                        mw = NumMolDescriptorValue.objects.get(
                            compound=compound, descriptor__heading='mw').value

                    if r['compound.old_abbrev'] is not None and r['compound.old_abbrev'] != r['compound.abbrev']:
                        reaction.notes += ' Compound abbreviation {} changed to {}'.format(
                            r['compound.old_abbrev'], r['compound.abbrev'])
                        reaction.save(calcDescriptors=False)
                    if r['compoundrole.name'] == 'pH':
                        reaction.notes += ' pH adjusting reagent used: {}, {}{}'.format(
                            compound, r['amount'], r['unit'])
                        reaction.save(calcDescriptors=False)
                    else:
                        compoundrole = None
                        while compoundrole is None and r['compoundrole.name'] in (None, '', '?'):
                            if r['compoundrole.name'] in (None, '', '?'):
                                classes = compound.chemicalClasses.all()
                                if classes.count() > 1:
                                    self.stderr.write(
                                        '{} has more than one chemical class: {}'.format(compound, classes))
                                    role_label = raw_input('Which is the correct role for reagent {} in reaction {} with amount {} {}'.format(
                                        compound, reaction, r['amount'], r['unit']))
                                elif classes.count() == 0:
                                    self.stderr.write(
                                        '{} has no chemical classes'.format(compound))
                                    role_label = raw_input(
                                        'What chemical class does {} belong to? '.format(compound))
                                    cc = ChemicalClass.objects.get(
                                        label=role_label)
                                    compound.chemicalClasses.add(cc)
                                    # Sanity check
                                    assert(
                                        compound.chemicalClasses.all().count() == 1)
                                else:  # count == 1
                                    role_label = classes[0].label
                                self.stderr.write('No reaction role listed for reagent {} with amount {} {} in reaction {}. '
                                                  'Using chemical class {}'.format(compound, reaction, r['amount'], r['unit'], role_label))
                                r['compoundrole.name'] = role_label
                            else:
                                role_label = r['compoundrole.name']
                            if not role_label:
                                reaction.notes += ' No role for reactant {} with amount {} {}'.format(
                                    r['compound.abbrev'], r['amount'], r['unit'])
                                reaction.save(calcDescriptors=False)
                            else:
                                try:
                                    compoundrole = CompoundRole.objects.get(
                                        label=role_label)
                                except CompoundRole.DoesNotExist:
                                    user_response = None
                                    if role_label in role_dict:
                                        new_role_label = role_dict[role_label]
                                    else:
                                        while user_response is None:
                                            user_verification = raw_input(
                                                'Compound role {} does not exist. Would you like to add it? ')
                                            if user_verification and user_verification.lower()[0] == 'y':
                                                user_response = True
                                            elif user_verification and user_verification.lower()[0] == 'n':
                                                user_response = False
                                        if user_response:
                                            compoundrole = CompoundRole.objects.create(
                                                label=role_label)
                                        else:
                                            new_role_label = raw_input(
                                                'What should this label be? ')
                                            role_dict[
                                                role_label] = new_role_label
                                            r['compoundrole.name'] = new_role_label

                                self.stdout.write('\tadding {} with role {} to {}'.format(
                                    compound.abbrev, role_label, reaction.reference))
                                if r['amount'] in ('', '?'):
                                    amount = None
                                    reaction.notes += ' No amount for reactant {} with role {}'.format(
                                        r['compound.abbrev'], r['compoundrole.name'])
                                    reaction.save(calcDescriptors=False)
                                elif r['unit'] == 'g':
                                    amount = float(r['amount']) / mw
                                elif r['unit'] == 'd' or r['unit'] == 'mL':
                                    valid_density = False
                                    while not valid_density:
                                        if compound.abbrev in density_dict:
                                            r['density'] = density_dict[
                                                compound.abbrev]
                                        try:
                                            density = float(r['density'])
                                            valid_density = True
                                        except (TypeError, ValueError):
                                            self.stderr.write("Density '{}' cannot be converted to float. (Compound {} with amount {} {} in reaction {})".format(
                                                r['density'], compound, r['amount'], r['unit'], reaction))
                                            r['density'] = raw_input(
                                                'What is the density? ')
                                    density_dict[compound.abbrev] = r[
                                        'density']
                                    if r['unit'] == 'd':
                                        amount = float(
                                            r['amount']) * 0.0375 * density / mw
                                    elif r['unit'] == 'mL':
                                        amount = float(
                                            r['amount']) * density / mw
                                else:
                                    raise RuntimeError('invalid unit entered')
                                # convert to millimoles
                                if amount is not None:
                                    amount = (amount * 1000)
                                cqq = CompoundQuantity.objects.filter(
                                    compound=compound, reaction=reaction)
                                if cqq.exists():
                                    cqq.delete()

                                quantity = CompoundQuantity(
                                    compound=compound, reaction=reaction, role=compoundrole, amount=amount)
                                quantities.append(quantity)

                            if len(quantities) > save_at_once:
                                self.stdout.write('Saving...')
                                CompoundQuantity.objects.bulk_create(
                                    quantities)
                                quantities = []

                else:
                    self.stderr.write('Unknown Reactant {} with amount {} {} in reaction {}'.format(
                        r['compound.abbrev'], r['amount'], r['unit'], r['reaction.reference']))
                    reaction.notes += ' Unknown Reactant {} with amount {} {}'.format(
                        r['compound.abbrev'], r['amount'], r['unit'])
                    reaction.valid = False
                    reaction.save(calcDescriptors=False)

                writer.writerow(r)

        self.stdout.write('Saving...')
        CompoundQuantity.objects.bulk_create(quantities)
        quantities = []
