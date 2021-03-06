from datetime import timedelta
from ethereum.tools import tester
from ethereum.tools.tester import Chain
from ethereum.abi import ContractTranslator
from ethereum.tools.tester import ABIContract
from ethereum.config import config_metropolis, Env
import ethereum
from io import open as io_open
from json import dump as json_dump, load as json_load, dumps as json_dumps
from os import path, walk, makedirs, remove as remove_file
import pytest
from re import findall
from solc import compile_standard
from reporting_utils import proceedToFork
from mock_templates import generate_mock_contracts
from utils import bytesToHexString, longToHexString, stringToBytes, BuyWithCash

# Make TXs free.
ethereum.opcodes.GCONTRACTBYTE = 0
ethereum.opcodes.GTXDATAZERO = 0
ethereum.opcodes.GTXDATANONZERO = 0

# Monkeypatch to bypass the contract size limit
def monkey_post_spurious_dragon_hardfork():
    return False

original_create_contract = ethereum.messages.create_contract

def new_create_contract(ext, msg):
    old_post_spurious_dragon_hardfork_check = ext.post_spurious_dragon_hardfork
    ext.post_spurious_dragon_hardfork = monkey_post_spurious_dragon_hardfork
    res, gas, dat = original_create_contract(ext, msg)
    ext.post_spurious_dragon_hardfork = old_post_spurious_dragon_hardfork_check
    return res, gas, dat

ethereum.messages.create_contract = new_create_contract

# used to resolve relative paths
BASE_PATH = path.dirname(path.abspath(__file__))
def resolveRelativePath(relativeFilePath):
    return path.abspath(path.join(BASE_PATH, relativeFilePath))
COMPILATION_CACHE = resolveRelativePath('./compilation_cache')

class bcolors:
    WARN = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

CONTRACT_SIZE_LIMIT = 24576.0
CONTRACT_SIZE_WARN_LEVEL = CONTRACT_SIZE_LIMIT * 0.75

def pytest_addoption(parser):
    parser.addoption("--cover", action="store_true", help="Use the coverage enabled contracts. Meant to be used with the tools/generateCoverageReport.js script")
    parser.addoption("--subFork", action="store_true", help="Use the coverage enabled contracts. Meant to be used with the tools/generateCoverageReport.js script")

def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers",
        "cover: use coverage contracts")

class ContractsFixture:
    signatures = {}
    compiledCode = {}

    ####
    #### Static Methods
    ####

    @staticmethod
    def ensureCacheDirectoryExists():
        if not path.exists(COMPILATION_CACHE):
            makedirs(COMPILATION_CACHE)

    def generateSignature(self, relativeFilePath):
        ContractsFixture.ensureCacheDirectoryExists()
        filename = path.basename(relativeFilePath)
        name = path.splitext(filename)[0]
        outputPath = path.join(COMPILATION_CACHE,  name + 'Signature')
        lastCompilationTime = path.getmtime(outputPath) if path.isfile(outputPath) else 0
        if path.getmtime(relativeFilePath) > lastCompilationTime:
            print('generating signature for ' + name)
            extension = path.splitext(filename)[1]
            signature = None
            if extension == '.sol':
                signature = self.compileSolidity(relativeFilePath)['abi']
            else:
                raise
            with open(outputPath, mode='w') as file:
                json_dump(signature, file)
        else:
            pass#print('using cached signature for ' + name)
        with open(outputPath, 'r') as file:
            signature = json_load(file)
        return(signature)

    def getCompiledCode(self, relativeFilePath):
        filename = path.basename(relativeFilePath)
        name = path.splitext(filename)[0]
        if name in ContractsFixture.compiledCode:
            return ContractsFixture.compiledCode[name]
        dependencySet = set()
        self.getAllDependencies(relativeFilePath, dependencySet)
        ContractsFixture.ensureCacheDirectoryExists()
        compiledOutputPath = path.join(COMPILATION_CACHE, name)
        lastCompilationTime = path.getmtime(compiledOutputPath) if path.isfile(compiledOutputPath) else 0
        needsRecompile = False
        for dependencyPath in dependencySet:
            if (path.getmtime(dependencyPath) > lastCompilationTime):
                needsRecompile = True
                break
        if (needsRecompile):
            print('compiling ' + name + '...')
            extension = path.splitext(filename)[1]
            compiledCode = None
            if extension == '.sol':
                compiledCode = bytearray.fromhex(self.compileSolidity(relativeFilePath)['evm']['bytecode']['object'])
            else:
                raise
            with io_open(compiledOutputPath, mode='wb') as file:
                file.write(compiledCode)
        else:
            pass#print('using cached compilation for ' + name)
        with io_open(compiledOutputPath, mode='rb') as file:
            compiledCode = file.read()
            contractSize = len(compiledCode)
            if (contractSize >= CONTRACT_SIZE_LIMIT):
                print('%sContract %s is OVER the size limit by %d bytes%s' % (bcolors.FAIL, name, contractSize - CONTRACT_SIZE_LIMIT, bcolors.ENDC))
            elif (contractSize >= CONTRACT_SIZE_WARN_LEVEL):
                print('%sContract %s is under size limit by only %d bytes%s' % (bcolors.WARN, name, CONTRACT_SIZE_LIMIT - contractSize, bcolors.ENDC))
            elif (contractSize > 0):
                pass#print('Size: %i' % contractSize)
            ContractsFixture.compiledCode[name] = compiledCode
            return(compiledCode)

    def compileSolidity(self, relativeFilePath):
        absoluteFilePath = resolveRelativePath(relativeFilePath)
        filename = path.basename(relativeFilePath)
        contractName = path.splitext(filename)[0]
        compilerParameter = {
            'language': 'Solidity',
            'sources': {
                absoluteFilePath: {
                    'urls': [ absoluteFilePath ]
                }
            },
            'settings': {
                # TODO: Remove 'remappings' line below and update 'sources' line above
                'remappings': [ 'ROOT=%s/' % resolveRelativePath(self.relativeContractsPath), 'TEST=%s/' % resolveRelativePath(self.relativeTestContractsPath) ],
                'optimizer': {
                    'enabled': True,
                    'runs': 200
                },
                'outputSelection': {
                    "*": {
                        '*': [ 'metadata', 'evm.bytecode', 'evm.sourceMap', 'abi' ]
                    }
                }
            }
        }
        return compile_standard(compilerParameter, allow_paths=resolveRelativePath("../"))['contracts'][absoluteFilePath][contractName]

    def getAllDependencies(self, filePath, knownDependencies):
        knownDependencies.add(filePath)
        fileDirectory = path.dirname(filePath)
        with open(filePath, 'r') as file:
            fileContents = file.read()
        matches = findall("inset\('(.*?)'\)", fileContents)
        for match in matches:
            dependencyPath = path.abspath(path.join(fileDirectory, match))
            if not dependencyPath in knownDependencies:
                self.getAllDependencies(dependencyPath, knownDependencies)
        matches = findall("create\('(.*?)'\)", fileContents)
        for match in matches:
            dependencyPath = path.abspath(path.join(fileDirectory, match))
            if not dependencyPath in knownDependencies:
                self.getAllDependencies(dependencyPath, knownDependencies)
        matches = findall("import ['\"](.*?)['\"]", fileContents)
        for match in matches:
            dependencyPath = path.join(BASE_PATH, self.relativeContractsPath, match).replace("ROOT/", "")
            if "TEST" in dependencyPath:
                dependencyPath = path.join(BASE_PATH, self.relativeTestContractsPath, match).replace("TEST/", "")
            if not path.isfile(dependencyPath):
                raise Exception("Could not resolve dependency file path: %s" % dependencyPath)
            if not dependencyPath in knownDependencies:
                self.getAllDependencies(dependencyPath, knownDependencies)
        return(knownDependencies)

    ####
    #### Class Methods
    ####

    def __init__(self):
        tester.GASPRICE = 0
        tester.STARTGAS = long(6.7 * 10**7)
        config_metropolis['GASLIMIT_ADJMAX_FACTOR'] = .000000000001
        config_metropolis['GENESIS_GAS_LIMIT'] = 2**60
        config_metropolis['MIN_GAS_LIMIT'] = 2**60
        config_metropolis['BLOCK_GAS_LIMIT'] = 2**60

        for a in range(10):
            tester.base_alloc[getattr(tester, 'a%i' % a)] = {'balance': 10**24}

        self.chain = Chain(env=Env(config=config_metropolis))
        self.contracts = {}
        self.testerAddress = self.generateTesterMap('a')
        self.testerKey = self.generateTesterMap('k')
        self.testerAddressToKey = dict(zip(self.testerAddress.values(), self.testerKey.values()))
        if path.isfile('./allFiredEvents'):
            remove_file('./allFiredEvents')
        self.relativeContractsPath = '../source/contracts'
        self.relativeTestContractsPath = 'solidity_test_helpers'
        # self.relativeTestContractsPath = 'mock_templates/contracts'
        self.externalContractsPath = '../source/contracts/external'
        self.coverageMode = pytest.config.option.cover
        self.subFork = pytest.config.option.subFork
        if self.coverageMode:
            self.chain.head_state.log_listeners.append(self.writeLogToFile)
            self.relativeContractsPath = '../coverageEnv/contracts'
            self.relativeTestContractsPath = '../coverageEnv/solidity_test_helpers'
            self.externalContractsPath = '../coverageEnv/contracts/external'

    def writeLogToFile(self, message):
        with open('./allFiredEvents', 'a') as logsFile:
            logsFile.write(json_dumps(message.to_dict()) + '\n')

    def distributeRep(self, universe):
        # Get the reputation token for this universe and migrate legacy REP to it
        reputationToken = self.applySignature('ReputationToken', universe.getReputationToken())
        legacyRepToken = self.applySignature('LegacyReputationToken', reputationToken.getLegacyRepToken())
        totalSupply = legacyRepToken.balanceOf(tester.a0)
        legacyRepToken.approve(reputationToken.address, totalSupply)
        reputationToken.migrateFromLegacyReputationToken()

    def generateTesterMap(self, ch):
        testers = {}
        for i in range(0,9):
            testers[i] = getattr(tester, ch + "%d" % i)
        return testers

    def uploadAndAddToAugur(self, relativeFilePath, lookupKey = None, signatureKey = None, constructorArgs=[]):
        lookupKey = lookupKey if lookupKey else path.splitext(path.basename(relativeFilePath))[0]
        contract = self.upload(relativeFilePath, lookupKey, signatureKey, constructorArgs)
        if not contract: return None
        self.contracts['Augur'].registerContract(lookupKey.ljust(32, '\x00'), contract.address)
        return(contract)

    def generateAndStoreSignature(self, relativePath):
        key = path.splitext(path.basename(relativePath))[0]
        resolvedPath = resolveRelativePath(relativePath)
        if self.coverageMode:
            resolvedPath = resolvedPath.replace("tests", "coverageEnv").replace("source/", "coverageEnv/")
        if key not in ContractsFixture.signatures:
            ContractsFixture.signatures[key] = self.generateSignature(resolvedPath)

    def upload(self, relativeFilePath, lookupKey = None, signatureKey = None, constructorArgs=[]):
        resolvedPath = resolveRelativePath(relativeFilePath)
        if self.coverageMode:
            resolvedPath = resolvedPath.replace("tests", "coverageEnv").replace("source/", "coverageEnv/")
        lookupKey = lookupKey if lookupKey else path.splitext(path.basename(resolvedPath))[0]
        signatureKey = signatureKey if signatureKey else lookupKey
        if lookupKey in self.contracts:
            return(self.contracts[lookupKey])
        compiledCode = self.getCompiledCode(resolvedPath)
        # abstract contracts have a 0-length array for bytecode
        if len(compiledCode) == 0:
            if ("libraries" in relativeFilePath or lookupKey.startswith("I") or lookupKey.startswith("Base") or lookupKey.startswith("DS")):
                pass#print "Skipping upload of " + lookupKey + " because it had no bytecode (likely a abstract class/interface)."
            else:
                raise Exception("Contract: " + lookupKey + " has no bytecode, but this is not expected. It probably doesn't implement all its abstract methods")
            return None
        if signatureKey not in ContractsFixture.signatures:
            ContractsFixture.signatures[signatureKey] = self.generateSignature(resolvedPath)
        signature = ContractsFixture.signatures[signatureKey]
        contractTranslator = ContractTranslator(signature)
        if len(constructorArgs) > 0:
            compiledCode += contractTranslator.encode_constructor_arguments(constructorArgs)
        contractAddress = bytesToHexString(self.chain.contract(compiledCode, language='evm'))
        contract = ABIContract(self.chain, contractTranslator, contractAddress)
        self.contracts[lookupKey] = contract
        return(contract)

    def applySignature(self, signatureName, address):
        assert address
        if type(address) is long:
            address = longToHexString(address)
        translator = ContractTranslator(ContractsFixture.signatures[signatureName])
        contract = ABIContract(self.chain, translator, address)
        return contract

    def createSnapshot(self):
        self.chain.tx(sender=tester.k0, to=tester.a1, value=0)
        self.chain.mine(1)
        contractsCopy = {}
        for contractName in self.contracts:
            contractsCopy[contractName] = dict(translator = self.contracts[contractName].translator, address = self.contracts[contractName].address)
        return  { 'state': self.chain.head_state.to_snapshot(), 'contracts': contractsCopy }

    def resetToSnapshot(self, snapshot):
        if not 'state' in snapshot: raise "snapshot is missing 'state'"
        if not 'contracts' in snapshot: raise "snapshot is missing 'contracts'"
        self.chain = Chain(genesis=snapshot['state'], env=Env(config=config_metropolis))
        if self.coverageMode:
            self.chain.head_state.log_listeners.append(self.writeLogToFile)
        self.contracts = {}
        for contractName in snapshot['contracts']:
            contract = snapshot['contracts'][contractName]
            self.contracts[contractName] = ABIContract(self.chain, contract['translator'], contract['address'])

    ####
    #### Bulk Operations
    ####

    def uploadAllContracts(self):
        for directory, _, filenames in walk(resolveRelativePath(self.relativeContractsPath)):
            # skip the legacy reputation directory since it is unnecessary and we don't support uploads of contracts with constructors yet
            if 'legacy_reputation' in directory: continue
            if 'external' in directory: continue
            for filename in filenames:
                name = path.splitext(filename)[0]
                extension = path.splitext(filename)[1]
                if extension != '.sol': continue
                if name == 'augur': continue
                if name == 'Augur': continue
                if name == 'Orders': continue # In testing we use the TestOrders version which lets us call protected methods
                if name == 'Time': continue # In testing and development we swap the Time library for a ControlledTime version which lets us manage block timestamp
                if name == 'ReputationTokenFactory': continue # In testing and development we use the TestNetReputationTokenFactory which lets us faucet
                if name in ['IAugur', 'IAuction', 'IAuctionToken', 'IDisputeOverloadToken', 'IDisputeCrowdsourcer', 'IDisputeWindow', 'IUniverse', 'IMarket', 'IReportingParticipant', 'IReputationToken', 'IOrders', 'IShareToken', 'Order', 'IInitialReporter']: continue # Don't compile interfaces or libraries
                # TODO these four are necessary for test_universe but break everything else
                # if name == 'MarketFactory': continue # tests use mock
                # if name == 'ReputationTokenFactory': continue # tests use mock
                # if name == 'DisputeWindowFactory': continue # tests use mock
                # if name == 'UniverseFactory': continue # tests use mock
                onlySignatures = ["ReputationToken", "TestNetReputationToken", "Universe"]
                if name in onlySignatures:
                    self.generateAndStoreSignature(path.join(directory, filename))
                elif name == "TimeControlled":
                    self.uploadAndAddToAugur(path.join(directory, filename), lookupKey = "Time", signatureKey = "TimeControlled")
                # TODO this breaks test_universe tests but is necessary for other tests
                elif name == "TestNetReputationTokenFactory":
                    self.uploadAndAddToAugur(path.join(directory, filename), lookupKey = "ReputationTokenFactory", signatureKey = "TestNetReputationTokenFactory")
                elif name == "TestOrders":
                    self.uploadAndAddToAugur(path.join(directory, filename), lookupKey = "Orders", signatureKey = "TestOrders")
                else:
                    self.uploadAndAddToAugur(path.join(directory, filename))

    def buildMockContracts(self):
        testContractsPath = resolveRelativePath(self.relativeTestContractsPath)
        with open("./output/contracts/abi.json") as f:
            abi = json_load(f)
        if not path.exists(testContractsPath):
            makedirs(testContractsPath)
        mock_sources = generate_mock_contracts("0.5.4", abi)
        for source in mock_sources.values():
            source.write(testContractsPath)

    def uploadAllMockContracts(self):
        for directory, _, filenames in walk(resolveRelativePath(self.relativeTestContractsPath)):
            for filename in filenames:
                name, extension = path.splitext(filename)
                if extension != '.sol': continue
                if not name.startswith('Mock'): continue
                if 'Factory' in name:
                    self.upload(path.join(directory, filename))
                else:
                    self.uploadAndAddToAugur(path.join(directory, filename))

    def uploadExternalContracts(self):
        for directory, _, filenames in walk(resolveRelativePath(self.externalContractsPath)):
            for filename in filenames:
                name = path.splitext(filename)[0]
                extension = path.splitext(filename)[1]
                if extension != '.sol': continue
                constructorArgs = []
                self.upload(path.join(directory, filename), constructorArgs=constructorArgs)

    def initializeAllContracts(self):
        contractsToInitialize = ['CompleteSets','CreateOrder','FillOrder','CancelOrder','Trade','ClaimTradingProceeds','Orders','Time','Cash','LegacyReputationToken', 'ProfitLoss']
        for contractName in contractsToInitialize:
            if getattr(self.contracts[contractName], "initializeERC820", None):
                self.contracts[contractName].initializeERC820(self.contracts['Augur'].address)
            elif getattr(self.contracts[contractName], "initialize", None):
                self.contracts[contractName].initialize(self.contracts['Augur'].address)
            else:
                raise "contract has no 'initialize' method on it."

    ####
    #### Helpers
    ####

    def getSeededCash(self):
        cash = self.contracts['Cash']
        cash.faucet(1, sender = tester.k9)
        return cash

    def approveCentralAuthority(self):
        authority = self.contracts['Augur']
        contractsToApprove = ['Cash']
        testersGivingApproval = [getattr(tester, 'k%i' % x) for x in range(0,10)]
        for testerKey in testersGivingApproval:
            for contractName in contractsToApprove:
                self.contracts[contractName].approve(authority.address, 2**254, sender=testerKey)

    def uploadAugur(self):
        # We have to upload Augur first
        return self.upload("../source/contracts/Augur.sol")

    def uploadShareToken(self, augurAddress = None):
        augurAddress = augurAddress if augurAddress else self.contracts['Augur'].address
        self.ensureShareTokenDependencies()
        shareTokenFactory = self.contracts['ShareTokenFactory']
        shareToken = shareTokenFactory.createShareToken(augurAddress)
        return self.applySignature('shareToken', shareToken)

    def createUniverse(self):
        universeAddress = self.contracts['Augur'].createGenesisUniverse()
        universe = self.applySignature('Universe', universeAddress)
        assert universe.getTypeName() == stringToBytes('Universe')
        return universe

    def getShareToken(self, market, outcome):
        shareTokenAddress = market.getShareToken(outcome)
        assert shareTokenAddress
        shareToken = ABIContract(self.chain, ContractTranslator(ContractsFixture.signatures['ShareToken']), shareTokenAddress)
        return shareToken

    def getOrCreateChildUniverse(self, parentUniverse, market, payoutDistribution):
        assert payoutDistributionHash
        childUniverseAddress = parentUniverse.getOrCreateChildUniverse(payoutDistribution)
        assert childUniverseAddress
        childUniverse = ABIContract(self.chain, ContractTranslator(ContractsFixture.signatures['Universe']), childUniverseAddress)
        return childUniverse

    def createYesNoMarket(self, universe, endTime, feePerCashInAttoCash, affiliateFeeDivisor, designatedReporterAddress, sender=tester.k0, topic="", extraInfo="{description: '\"description\"}", validityBond=0):
        marketCreationFee = validityBond or universe.getOrCacheMarketCreationCost()
        with BuyWithCash(self.contracts['Cash'], marketCreationFee, sender, "validity bond"):
            marketAddress = universe.createYesNoMarket(endTime, feePerCashInAttoCash, affiliateFeeDivisor, designatedReporterAddress, topic, extraInfo, sender=sender)
        assert marketAddress
        market = ABIContract(self.chain, ContractTranslator(ContractsFixture.signatures['Market']), marketAddress)
        return market

    def createCategoricalMarket(self, universe, numOutcomes, endTime, feePerCashInAttoCash, affiliateFeeDivisor, designatedReporterAddress, sender=tester.k0, topic="", extraInfo="{description: '\"description\"}"):
        marketCreationFee = universe.getOrCacheMarketCreationCost()
        outcomes = [" "] * numOutcomes
        with BuyWithCash(self.contracts['Cash'], marketCreationFee, sender, "validity bond"):
            marketAddress = universe.createCategoricalMarket(endTime, feePerCashInAttoCash, affiliateFeeDivisor, designatedReporterAddress, outcomes, topic, extraInfo, sender=sender)
        assert marketAddress
        market = ABIContract(self.chain, ContractTranslator(ContractsFixture.signatures['Market']), marketAddress)
        return market

    def createScalarMarket(self, universe, endTime, feePerCashInAttoCash, affiliateFeeDivisor, maxPrice, minPrice, numTicks, designatedReporterAddress, sender=tester.k0, topic="", extraInfo="{description: '\"description\"}"):
        marketCreationFee = universe.getOrCacheMarketCreationCost()
        with BuyWithCash(self.contracts['Cash'], marketCreationFee, sender, "validity bond"):
            marketAddress = universe.createScalarMarket(endTime, feePerCashInAttoCash, affiliateFeeDivisor, designatedReporterAddress, [minPrice, maxPrice], numTicks, topic, extraInfo, sender=sender)
            # uint256 _endTime, uint256 _feePerCashInAttoCash, uint256 _affiliateFeeDivisor, address _designatedReporterAddress, int256[] memory _prices, uint256 _numTicks, bytes32 _topic, string memory _extraInfo
        assert marketAddress
        market = ABIContract(self.chain, ContractTranslator(ContractsFixture.signatures['Market']), marketAddress)
        return market

    def createReasonableYesNoMarket(self, universe, sender=tester.k0, topic="", extraInfo="{description: '\"description\"}", validityBond=0):
        return self.createYesNoMarket(
            universe = universe,
            endTime = long(self.contracts["Time"].getTimestamp() + timedelta(days=1).total_seconds()),
            feePerCashInAttoCash = 10**16,
            affiliateFeeDivisor = 4,
            designatedReporterAddress = tester.a0,
            sender = sender,
            topic= topic,
            extraInfo= extraInfo,
            validityBond= validityBond)

    def createReasonableCategoricalMarket(self, universe, numOutcomes, sender=tester.k0):
        return self.createCategoricalMarket(
            universe = universe,
            numOutcomes = numOutcomes,
            endTime = long(self.contracts["Time"].getTimestamp() + timedelta(days=1).total_seconds()),
            feePerCashInAttoCash = 10**16,
            affiliateFeeDivisor = 0,
            designatedReporterAddress = tester.a0,
            sender = sender)

    def createReasonableScalarMarket(self, universe, maxPrice, minPrice, numTicks, sender=tester.k0):
        return self.createScalarMarket(
            universe = universe,
            endTime = long(self.contracts["Time"].getTimestamp() + timedelta(days=1).total_seconds()),
            feePerCashInAttoCash = 10**16,
            affiliateFeeDivisor = 0,
            maxPrice= maxPrice,
            minPrice= minPrice,
            numTicks= numTicks,
            designatedReporterAddress = tester.a0,
            sender = sender)

@pytest.fixture(scope="session")
def fixture():
    return ContractsFixture()

@pytest.fixture(scope="session")
def baseSnapshot(fixture):
    return fixture.createSnapshot()

@pytest.fixture(scope="session")
def augurInitializedSnapshot(fixture, baseSnapshot):
    fixture.resetToSnapshot(baseSnapshot)
    fixture.uploadAugur()
    fixture.uploadAllContracts()
    fixture.initializeAllContracts()
    fixture.approveCentralAuthority()
    fixture.uploadExternalContracts()
    return fixture.createSnapshot()

@pytest.fixture(scope="session")
def augurInitializedWithMocksSnapshot(fixture, augurInitializedSnapshot):
    fixture.buildMockContracts()
    fixture.uploadAllMockContracts()
    return fixture.createSnapshot()

@pytest.fixture(scope="session")
def kitchenSinkSnapshot(fixture, augurInitializedSnapshot):
    fixture.resetToSnapshot(augurInitializedSnapshot)
    # TODO: remove assignments to the fixture as they don't get rolled back, so can bleed across tests.  We should be accessing things via `fixture.contracts[...]`
    legacyReputationToken = fixture.contracts['LegacyReputationToken']
    legacyReputationToken.faucet(11 * 10**6 * 10**18)
    universe = fixture.createUniverse()
    cash = fixture.getSeededCash()
    augur = fixture.contracts['Augur']
    fixture.distributeRep(universe)

    if fixture.subFork:
        forkingMarket = fixture.createReasonableYesNoMarket(universe)
        proceedToFork(fixture, forkingMarket, universe)
        fixture.contracts["Time"].setTimestamp(universe.getForkEndTime() + 1)
        reputationToken = fixture.applySignature('ReputationToken', universe.getReputationToken())
        yesPayoutNumerators = [0, 0, forkingMarket.getNumTicks()]
        reputationToken.migrateOutByPayout(yesPayoutNumerators, reputationToken.balanceOf(tester.a0))
        universe = fixture.applySignature('Universe', universe.createChildUniverse(yesPayoutNumerators))

    yesNoMarket = fixture.createReasonableYesNoMarket(universe)
    startingGas = fixture.chain.head_state.gas_used
    categoricalMarket = fixture.createReasonableCategoricalMarket(universe, 3)
    print 'Gas Used: %s' % (fixture.chain.head_state.gas_used - startingGas)
    scalarMarket = fixture.createReasonableScalarMarket(universe, 30, -10, 400000)
    fixture.uploadAndAddToAugur("solidity_test_helpers/Constants.sol")
    snapshot = fixture.createSnapshot()
    snapshot['universe'] = universe
    snapshot['cash'] = cash
    snapshot['augur'] = augur
    snapshot['yesNoMarket'] = yesNoMarket
    snapshot['categoricalMarket'] = categoricalMarket
    snapshot['scalarMarket'] = scalarMarket
    snapshot['auction'] = fixture.applySignature('Auction', universe.getAuction())
    snapshot['reputationToken'] = fixture.applySignature('ReputationToken', universe.getReputationToken())
    return snapshot

@pytest.fixture
def kitchenSinkFixture(fixture, kitchenSinkSnapshot):
    fixture.resetToSnapshot(kitchenSinkSnapshot)
    return fixture

@pytest.fixture
def universe(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['universe'].translator, kitchenSinkSnapshot['universe'].address)

@pytest.fixture
def cash(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['cash'].translator, kitchenSinkSnapshot['cash'].address)

@pytest.fixture
def augur(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['augur'].translator, kitchenSinkSnapshot['augur'].address)

@pytest.fixture
def market(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['yesNoMarket'].translator, kitchenSinkSnapshot['yesNoMarket'].address)

@pytest.fixture
def yesNoMarket(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['yesNoMarket'].translator, kitchenSinkSnapshot['yesNoMarket'].address)

@pytest.fixture
def categoricalMarket(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['categoricalMarket'].translator, kitchenSinkSnapshot['categoricalMarket'].address)

@pytest.fixture
def scalarMarket(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['scalarMarket'].translator, kitchenSinkSnapshot['scalarMarket'].address)

@pytest.fixture
def auction(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['auction'].translator, kitchenSinkSnapshot['auction'].address)

@pytest.fixture
def reputationToken(kitchenSinkFixture, kitchenSinkSnapshot):
    return ABIContract(kitchenSinkFixture.chain, kitchenSinkSnapshot['reputationToken'].translator, kitchenSinkSnapshot['reputationToken'].address)

# TODO: globally replace this with `fixture` and `kitchenSinkSnapshot` as appropriate then delete this
@pytest.fixture(scope="session")
def sessionFixture(fixture, kitchenSinkSnapshot):
    fixture.resetToSnapshot(kitchenSinkSnapshot)
    return fixture

@pytest.fixture
def contractsFixture(fixture, kitchenSinkSnapshot):
    fixture.resetToSnapshot(kitchenSinkSnapshot)
    return fixture

@pytest.fixture
def augurInitializedFixture(fixture, augurInitializedSnapshot):
    fixture.resetToSnapshot(augurInitializedSnapshot)
    return fixture
