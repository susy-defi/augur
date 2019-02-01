from os import path, mkdir
from textwrap import dedent

from solc import compile_standard


# TODO resolve relative source paths from the sources directory, not this directory
# used to resolve relative paths
BASE_PATH = path.dirname(path.abspath(__file__))
def resolve_relative_path(relativeFilePath):
    return path.abspath(path.join(BASE_PATH, relativeFilePath))
COMPILATION_CACHE = resolve_relative_path('./compilation_cache')


def compile_solidity(solidity_version, source_filepath):
    source_filepath = resolve_relative_path(source_filepath)
    contracts_path = resolve_relative_path('../../source/contracts')
    real = compile_contract(
        source_filepath,
        ['abi'],
        contracts_path,
        None)

    # TODO it's still generating Universe.sol (now MockUniverse.sol) so something's funky
    # mock out this contract's dependencies but not this contract itself
    contracts = {
        filename: body
        for filename,body
        in real['contracts'].iteritems()
        # if filename != source_filepath  # TODO figure out if this should be kept
    }
    mock_sources = generate_mock_contracts(solidity_version, contracts)
    test_contracts_path = resolve_relative_path('./temp_mock_contracts')
    if not path.exists(test_contracts_path):
        mkdir(test_contracts_path)
    for source in mock_sources:
        write_contract(test_contracts_path, source)

    mock = compile_contract(
        source_filepath,
        ['metadata', 'evm.bytecode', 'evm.sourceMap', 'abi'],
        contracts_path,
        test_contracts_path)
    import json
    print json.dumps(mock, indent=2, separators=',:')
    return mock


def generate_mock_contracts(solidity_version, contracts):
    sources = []
    for filename, body in contracts.items():
        contract_name = body.keys()[0]
        contract = body[contract_name]

        # fix contract name
        if contract_name[0] == "I":
            contract_name = contract_name[1:]
        contract_name = 'Mock{}'.format(contract_name)

        abi = contract['abi']

        if len(abi) == 0:
            continue  # no events or public functions to mock

        sources.append(build_contract_description(solidity_version, contract_name, abi))

    return sources


def write_contract(test_dir, contract_description):
    with open('{}/{}.sol'.format(test_dir, contract_description['name']), 'w') as f:
        f.write(render_contract(contract_description))


def render_contract(description):
    source = '{}\n'.format(description['version'])
    source += '\n'
    source += "contract {name} {{\n".format(name=description['name'])
    source += '\n'
    source += '\n'.join(description['variables'])
    source += '\n\n'
    source += '\n'.join(description['functions'])
    source += '}'
    return source


def build_contract_description(solidity_version, contract_name, abi):
    code = {
        'name': contract_name,
        'version': make_version(solidity_version),
        'imports': [],
        'variables': [],
        'functions': [],
        'events': []
    }

    for thing in abi:
        # print json.dumps(thing, indent=2, separators=',:')
        type_ = thing['type']
        if type_ == 'constructor':
            inputs = thing['inputs']
            state_mutability = thing['stateMutability']
            payable = thing['payable']  # TODO is this useful when we know stateMutability?
            constructor = make_constructor(inputs)
            code['functions'].append(constructor)
        elif type_ == 'function':
            name = thing['name']
            inputs = thing['inputs']
            outputs = thing['outputs']
            state_mutability = thing['stateMutability']
            constant = thing['constant']
            payable = thing['payable']  # TODO is this useful when we know stateMutability?
            new_variables, new_functions = make_function(name, inputs, outputs, state_mutability)
            code['variables'].extend(new_variables)
            code['functions'].extend(new_functions)
        elif type_ == 'event':
            name = thing['name']
            inputs = thing['inputs']
            anonymous = thing['anonymous']  # TODO is this useful when we know 'name'?
            event = make_event(name, inputs)
            code['events'].append(event)

        else:
            raise ValueError('Unexpected abi type "{}" in: {}'.format(type_, abi))
    return code


def make_version(version):
    return 'pragma solidity {};'.format(version)


def make_event(name, inputs):
    params = ', '.join('{} {}'.format(i['type'], i['name']) for i in inputs)
    return "event {name}({params});".format(name=name, params=params)


def make_constructor(inputs):
    params = ', '.join('{} {}'.format(i['type'], i['name']) for i in inputs)
    return "constructor({params}) public {{ }}".format(
        params=params
    )


def make_function(function_name, inputs, outputs, state_mutability):
    var_descriptions = [
        {'name': 'mock_{}_{}'.format(
            function_name,
            o['name'] or i,
        ),
         'type': o['type']}
        for i, o in enumerate(outputs)
    ]

    functions = []

    params = ', '.join('{} {}'.format(i['type'], i['name']) for i in inputs)
    returns_header = ', '.join('{} {}'.format(o['type'], o['name']) for o in outputs)
    returns = ','.join(v['name'] for v in var_descriptions)
    mutability = "" if state_mutability == "nonpayable" else state_mutability
    functions.append(dedent("""\
        function {name}({params}) public {mutability} returns ({returns_header}) {{
            return ({returns});
        }}
    """.format(
        name=function_name,
        params=params,
        mutability=mutability,
        returns_header=returns_header,
        returns=returns
    )))

    variables = []
    for v in var_descriptions:
        functions.append(dedent("""\
            function set_{name}({vartype} thing) public {{
                {name} = thing;
            }}
        """.format(
            name=v['name'],
            vartype=v['type']
        )))
        variables.append('{vartype} private {name};'.format(name=v['name'], vartype=v['type']))

    return variables, functions



def compile_contract(source_filepath, outputs, contracts_path, test_contracts_path):
    compiler_parameter = {
        'language': 'Solidity',
        'sources': {
            source_filepath: {
                'urls': [source_filepath]
            }
        },
        'settings': {
            # TODO: Remove 'remappings' line below and update 'sources' line above
            'remappings': [
                '=%s/' % contracts_path,
            ],
            'optimizer': {
                'enabled': True,
                'runs': 200
            },
            'outputSelection': {
                "*": {
                    '*': outputs
                }
            }
        }
    }
    if test_contracts_path:
        # TODO: Remove 'remappings' line below and update 'sources' line above
        compiler_parameter['settings']['remappings'].append(
            'TEST=%s/' % test_contracts_path
        )

    # contract_name = path.splitext(path.basename(source_filepath))[0]
    return compile_standard(compiler_parameter, allow_paths=resolve_relative_path("../../"))
    # return compiled['contracts'][source_filepath][contract_name]
