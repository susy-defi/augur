from ethereum.tools import tester
from ethereum.tools.tester import ABIContract, TransactionFailed
from pytest import fixture, raises
from utils import longTo32Bytes, PrintGasUsed, fix, nullAddress, bytesToHexString, stringToBytes, AssertLog
from constants import BID, ASK, YES, NO, SHORT, LONG
from datetime import timedelta
from ethereum.utils import ecsign, sha3, normalize_key, int_to_32bytearray, bytearray_to_bytestr, zpad

def test_deposit_and_withdraw(localFixture, gnosisSafe, sigDecoder, cash, market, augur):
    trade = localFixture.contracts["Trade"]

    assert cash.faucet(fix(100))
    assert cash.transfer(gnosisSafe.address, fix(100))

    # Make gnosis safe approve Augur to transfer Cash
    doTx(gnosisSafe, cash, "approve", [augur.address, 2**254])

    # Perform a trade
    tradeGroupID = longTo32Bytes(42)
    orderCreatedLog = {
        'creator': gnosisSafe.address,
        'marketId': market.address,
        'tradeGroupId': stringToBytes(tradeGroupID),
        'outcome': YES,
    }
    with AssertLog(localFixture, "OrderCreated", orderCreatedLog):
        doTx(gnosisSafe, trade, "publicTrade", [SHORT, market.address, YES, fix(2), 60, "0", "0", tradeGroupID, 6, False, nullAddress, nullAddress])

    # If we now fill the order we can see the gnosis safe contract get shares
    assert cash.faucet(fix(2, 60), sender=tester.k1)
    orderFilledLog = {
        "filler": bytesToHexString(tester.a1),
        "fees": 0,
        "tradeGroupId": stringToBytes(tradeGroupID),
        "orderIsCompletelyFilled": True
    }
    with AssertLog(localFixture, "OrderFilled", orderFilledLog):
        assert trade.publicTrade(LONG, market.address, YES, fix(2), 60, "0", "0", tradeGroupID, 6, False, nullAddress, nullAddress, sender=tester.k1)

    noShare = localFixture.applySignature('ShareToken', market.getShareToken(NO))

    assert noShare.balanceOf(gnosisSafe.address) == fix(2)

def doTx(gnosisSafe, contract, methodName, methodArgs):
    dataBytes = contract.translator.encode_function_call(methodName, methodArgs)

    transactionArgsBase = [
        contract.address,
        0,
        dataBytes,
        0,
        2 * 10**7, # 2 mil gas
        0,
        0,
        0,
        0
    ]

    # create signed transaction
    nonce = gnosisSafe.nonce()
    transactionArgsNonce = transactionArgsBase + [nonce]
    transactionData = gnosisSafe.encodeTransactionData(*transactionArgsNonce)
    transactionHash = gnosisSafe.getTransactionHash(*transactionArgsNonce)
    gnosisSafe.approveHash(transactionHash)
    signatures = "000000000000000000000000" + bytesToHexString(tester.a0).replace('0x', '') + "0000000000000000000000000000000000000000000000000000000000000000" + "01"
    encodedSignatures = ''.join(['{:c}'.format(*[int(signatures[pos:pos+2], 16)]) for pos in range(0, len(signatures), 2)])

    # execute transaction
    transactionArgsSigs = transactionArgsBase + [encodedSignatures]
    assert gnosisSafe.execTransaction(*transactionArgsSigs)

@fixture(scope="session")
def localSnapshot(fixture, kitchenSinkSnapshot):
    fixture.resetToSnapshot(kitchenSinkSnapshot)
    augur = fixture.contracts["Augur"]
    # Deploy master copy of GnosisSafe
    kitchenSinkSnapshot['GnosisSafeMaster'] = fixture.upload('solidity_test_helpers/GnosisSafe/GnosisSafe.sol', "GnosisSafeMaster")
    # Deploy a proxy pointing to GnosisSafe and ref that here
    gnosisSafeProxy = fixture.upload('solidity_test_helpers/GnosisSafe/proxies/Proxy.sol', "gnosisSafe", constructorArgs=[kitchenSinkSnapshot['GnosisSafeMaster'].address])
    gnosisSafe = kitchenSinkSnapshot['gnosisSafe'] = fixture.applySignature("GnosisSafeMaster", gnosisSafeProxy.address)
    kitchenSinkSnapshot['SignatureDecoder'] = fixture.upload('solidity_test_helpers/GnosisSafe/common/SignatureDecoder.sol', "SignatureDecoder")
    gnosisSafe.setup([tester.a0], 1, nullAddress, longTo32Bytes(0), nullAddress, 0, nullAddress)
    return fixture.createSnapshot()

@fixture
def localFixture(fixture, localSnapshot):
    fixture.resetToSnapshot(localSnapshot)
    return fixture

@fixture
def gnosisSafe(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['GnosisSafeMaster'].translator, kitchenSinkSnapshot['gnosisSafe'].address)

@fixture
def sigDecoder(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['SignatureDecoder'].translator, kitchenSinkSnapshot['SignatureDecoder'].address)

@fixture
def market(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['yesNoMarket'].translator, kitchenSinkSnapshot['yesNoMarket'].address)

@fixture
def cash(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['cash'].translator, kitchenSinkSnapshot['cash'].address)

@fixture
def augur(localFixture, kitchenSinkSnapshot):
    return localFixture.contracts['Augur']

def signTransaction(transactionHash, key=tester.k0):
    signatureBytes = "0x"
    v, r, s = ecsign(sha3(transactionHash), key)
    signatureBytes += hex(r)[2:].rstrip('L') + hex(s)[2:].rstrip('L') + hex(v)[2:].rstrip('L')
    return signatureBytes
