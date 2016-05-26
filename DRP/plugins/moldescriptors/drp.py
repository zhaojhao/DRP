from scipy.stats import gmean
from utils import setup
import DRP
from DRP import chemical_data
import warnings

calculatorSoftware = 'DRP'

elements = chemical_data.elements

#Inorganic descriptors
inorgAtomicProperties = (
    'ionization_energy',
    'electron_affinity',
    'pauling_electronegativity',
    'pearson_electronegativity',
    'hardness',
    'atomic_radius'
)

weightings= (
    ('unw', 'unweighted'),
    ('stoich', 'stoichiometry')
)

inorgElements = {}
for element, info in elements.items():
    if (element == 'Se') or (info['group'] in range(3, 13)) or ((info['group'] > 12) and ((not info['nonmetal']) or info['metalloid'])):
        inorgElements[element] = info 

_descriptorDict = {}

for prop in inorgAtomicProperties:
    stem = 'drpInorgAtom' + prop.title().replace('_', '') 
    for weighting in weightings:
        _descriptorDict['{}_geom_{}'.format(stem, weighting[0])] = {
            'type':'num',
            'name': 'Geometric mean of {} weighted by {}.'.format(prop.replace('_', ' '), weighting[1]),
            'calculatorSoftware': calculatorSoftware,
            'calculatorSoftwareVersion':'0.02',
            'maximum': None,
            'minimum': 0,
            }
    _descriptorDict['{}_max'.format(stem)] = {
        'type': 'num',
        'name': 'Maximal value of {}'.format(prop.replace('_', '')),
        'calculatorSoftware': calculatorSoftware,
        'calculatorSoftwareVersion':'0.02',
        'maximum':None,
        'minimum':None
        }
    _descriptorDict['{}_range'.format(stem)] = {
        'type': 'num',
        'name': 'Range of {}'.format(prop.replace('_', '')),
        'calculatorSoftware': calculatorSoftware,
        'calculatorSoftwareVersion':'0.02',
        'maximum': None,
        'minimum': None
        }

for group_num in range(1,18):
    _descriptorDict['boolean_group_{}'.format(group_num)] = {
        'type': 'bool',
        'name': 'Presence of elements in group {}'.format(group_num),
        'calculatorSoftware': calculatorSoftware,
        'calculatorSoftwareVersion':'1.5',
        }
        
for period_num in range(1,7):
    _descriptorDict['boolean_period_{}'.format(period_num)] = {
        'type': 'bool',
        'name': 'Presence of elements in period {}'.format(period_num),
        'calculatorSoftware': calculatorSoftware,
        'calculatorSoftwareVersion':'1.5',
        }
        
for valence_num in range(1,8):
    _descriptorDict['boolean_valence_{}'.format(valence_num)] = {
        'type': 'bool',
        'name': 'Presence of elements with valence {}'.format(valence_num),
        'calculatorSoftware': calculatorSoftware,
        'calculatorSoftwareVersion':'1.5',
        }

descriptorDict = setup(_descriptorDict)

def delete_descriptors(compound_set):
    DRP.models.NumMolDescriptorValue.objects.filter(descriptor__in=[desc for desc in descriptorDict.values() if isinstance(desc, DRP.models.NumMolDescriptor)], compound__in=compound_set).delete(recalculate_reactions=False)
    DRP.models.BoolMolDescriptorValue.objects.filter(descriptor__in=[desc for desc in descriptorDict.values() if isinstance(desc, DRP.models.BoolMolDescriptor)], compound__in=compound_set).delete(recalculate_reactions=False)

def calculate_many(compound_set, verbose=False):
    delete_descriptors(compound_set)
    for i, compound in enumerate(compound_set):
        _calculate(compound)
        if verbose:
            print "{}; Compound {} ({}/{})".format(compound, compound.pk, i+1, len(compound_set))

def calculate(compound):
    delete_descriptors([compound])
    _calculate(compound)
    
def _calculate(compound):

    num = DRP.models.NumMolDescriptorValue
    boolVal = DRP.models.BoolMolDescriptorValue

    num_vals_to_create = []
    bool_vals_to_create = []

    if any(element in inorgElements for element in compound.elements):

        inorgElementNormalisationFactor = sum(info['stoichiometry'] for element, info in compound.elements.items() if element in inorgElements)
        for prop in inorgAtomicProperties:
            # zero is what scipy does natively. This is just to avoid warnings that are fine so they don't drown out the real ones
            if 0 in [inorgElements[element][prop] for element in compound.elements if element in inorgElements]:
                val = 0

            if any([(inorgElements[element][prop] == 0) for element, info in compound.elements.items() if element in inorgElements]):
                val = 0
            elif  any([(inorgElements[element][prop] < 0) for element, info in compound.elements.items() if element in inorgElements]):
                raise ValueError('Cannot take geometric mean of negative values. This descriptor ({}) should not use a geometric mean.'.format(descriptorDict['drpInorgAtom{}_geom_unw'.format(prop.title().replace('_', ''))]))
            else:
                val = gmean([inorgElements[element][prop] for element in compound.elements if element in inorgElements])
            n = num( 
                    compound=compound,
                    descriptor=descriptorDict['drpInorgAtom{}_geom_unw'.format(prop.title().replace('_', ''))],
                    value=val
                    )
            try:
                n.full_clean()
            except ValidationError as e:
                warnings.warn('Value {} for compound {} and descriptor {} failed validation. Value set to none. Validation error message: {}'.format(n.value, n.compound, n.descriptor, e.message))
                n.value = None
            num_vals_to_create.append(n)

            if any([(inorgElements[element][prop]*(info['stoichiometry']/inorgElementNormalisationFactor) == 0) for element, info in compound.elements.items() if element in inorgElements]):
                val = 0
            elif any([(inorgElements[element][prop]*(info['stoichiometry']/inorgElementNormalisationFactor) < 0) for element, info in compound.elements.items() if element in inorgElements]):
                raise ValueError('Cannot take geometric mean of negative values. This descriptor ({}) should not use a geometric mean.'.format(descriptorDict['drpInorgAtom{}_geom_stoich'.format(prop.title().replace('_', ''))]))
            else:
                val = gmean([inorgElements[element][prop]*(info['stoichiometry']/inorgElementNormalisationFactor) for element, info in compound.elements.items() if element in inorgElements])
            n = num( 
                    compound=compound,
                    descriptor=descriptorDict['drpInorgAtom{}_geom_stoich'.format(prop.title().replace('_', ''))],
                    value=val,
                    )
            try:
                n.full_clean()
            except ValidationError as e:
                warnings.warn('Value {} for compound {} and descriptor {} failed validation. Value set to none. Validation error message: {}'.format(n.value, n.compound, n.descriptor, e.message))
                n.value = None
            num_vals_to_create.append(n)

            val = max(inorgElements[element][prop] for element in compound.elements if element in inorgElements)
            n = num(
                    compound=compound,
                    descriptor=descriptorDict['drpInorgAtom{}_max'.format(prop.title().replace('_', ''))],
                    value=val
                    )
            try:
                n.full_clean()
            except ValidationError as e:
                warnings.warn('Value {} for compound {} and descriptor {} failed validation. Value set to none. Validation error message: {}'.format(n.value, n.compound, n.descriptor, e.message))
                n.value = None
            num_vals_to_create.append(n)

            val = max(inorgElements[element][prop] for element in compound.elements if element in inorgElements) - min(inorgElements[element][prop] for element in compound.elements if element in inorgElements)
            n = num(
                compound=compound,
                descriptor=descriptorDict['drpInorgAtom{}_range'.format(prop.title().replace('_', ''))],
                value=val,
                )
            try:
                n.full_clean()
            except ValidationError as e:
                warnings.warn('Value {} for compound {} and descriptor {} failed validation. Value set to none. Validation error message: {}'.format(n.value, n.compound, n.descriptor, e.message))
                n.value = None
            num_vals_to_create.append(n)
        num.objects.bulk_create(num_vals_to_create)

    for group_num in range(1,18):
        bool_vals_to_create.append(boolVal(
                                        compound=compound,
                                        descriptor=descriptorDict['boolean_group_{}'.format(group_num)],
                                        value=(any(elements[element]['group']==group_num for element in compound.elements.keys()))
                                    ))
    for period_num in range(1,7):
        bool_vals_to_create.append(boolVal(
                                        compound=compound,
                                        descriptor=descriptorDict['boolean_period_{}'.format(period_num)],
                                        value=(any(elements[element]['period']==period_num for element in compound.elements.keys()))
                                    ))
    for valence_num in range(1,8):
        bool_vals_to_create.append(boolVal(
                                compound=compound,
                                descriptor=descriptorDict['boolean_valence_{}'.format(valence_num)],
                                value=(any(elements[element]['valence']==valence_num for element in compound.elements.keys()))
                            ))
    boolVal.objects.bulk_create(bool_vals_to_create)
